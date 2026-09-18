"""plan-B TCP bridge client for the live CLANNAD engine.

The engine (siglus_engine.exe) runs in a normal window and, when launched with
CLANNAD_BRIDGE=1, listens on an ephemeral 127.0.0.1 port.  It reads one command
line per connection, queues it, and replies with a single JSON status line.

Wire protocol (one line in -> one JSON line out):
    ADVANCE | CLICK            forward / confirm (Enter)
    CHOOSE:<n>                 pick choice index n (0-based)
    SAVE:<n>                   save to slot n
    LOAD:<n>                   load slot n
    JUMP:<scene>               restart scene by name
    SKIP                       start fast-forward to next choice
    STOPSKIP                   stop an in-flight fast-forward (reply keeps skip_lines)
    STATE                      just return the latest snapshot

Status JSON:
    {"scene": "...", "scene_no": ..., "line": ..., "blocked": true/false,
     "name": "...", "text": "...", "choices": [...], "save_slots": ...}

The port is written to CLANNAD_BRIDGE_PORT_FILE if the engine was launched with
that env var; otherwise it is printed to stderr ("[BRIDGE] listening on ..."),
which you can capture by starting the engine yourself and waiting for the line.
"""
from __future__ import annotations

import json
import os
import socket

# File the engine writes the ephemeral port into.  Start the engine with
# CLANNAD_BRIDGE=1 and CLANNAD_BRIDGE_PORT_FILE=<this path>.
_DEFAULT_PORT_FILE = r"E:\7_projects\clannad_mcp\clannad_bridge.port"
PORT_FILE = os.environ.get("CLANNAD_BRIDGE_PORT_FILE", _DEFAULT_PORT_FILE)


def _candidate_port_files() -> list[str]:
    """All the places the engine may have written its port file.

    The engine default is a *relative* `clannad_bridge.port` in its own current
    working directory, while this client default is the absolute
    `_DEFAULT_PORT_FILE`.  They only coincide when the engine is launched from
    `E:\\7_projects\\clannad_mcp`.  To be robust, probe the explicitly configured
    path first, then the absolute default, then `clannad_bridge.port` in the
    client's current working directory (and its parent), so a separate-terminal
    launch in any directory is still found.
    """
    candidates: list[str] = []
    if PORT_FILE:
        candidates.append(PORT_FILE)
    if _DEFAULT_PORT_FILE not in candidates:
        candidates.append(_DEFAULT_PORT_FILE)
    cwd = os.path.abspath(os.getcwd())
    for d in (cwd, os.path.dirname(cwd)):
        candidates.append(os.path.join(d, "clannad_bridge.port"))
    return candidates


def _read_port_now() -> int | None:
    """Read the port file once, without waiting: the current port, or None."""
    for path in _candidate_port_files():
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    raw = f.read().strip()
                if raw:
                    return int(raw)
            except (OSError, ValueError):
                pass
    return None


def _read_port(timeout: float = 30.0) -> int:
    """Wait for the engine to write a port file, then return the port."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        port = _read_port_now()
        if port is not None:
            return port
        time.sleep(0.2)
    raise RuntimeError(
        "engine didn't write a port file within {}s; "
        "start siglus_engine.exe with CLANNAD_BRIDGE=1 and "
        f"CLANNAD_BRIDGE_PORT_FILE={PORT_FILE}".format(timeout)
    )


class ClannadBridge:
    """A tiny blocking client for one logical request/reply at a time."""

    #: Fallback budget: how long the client waits for the ENGINE's own fast-forward
    #: budget to end before it gives up, asks the engine to stop (`STOPSKIP`) and
    #: returns whatever it has.
    #:
    #: The engine enforces its own budget (`CLANNAD_SKIP_BUDGET_MS`, default 40s) and
    #: stops exactly when it elapses — that is what makes the game stop AT the budget
    #: instead of one round trip later (AGENT.md 19.32). The whole call must finish
    #: inside the MCP client's timeout (60s in practice): 45s here + 0.5s of polling
    #: after `STOPSKIP` + at most one 10s socket timeout (only if the engine is wedged)
    #: stays under 60s, while still leaving the engine's 40s budget room to land first.
    SKIP_TIMEOUT = float(os.environ.get("CLANNAD_SKIP_TIMEOUT", "45"))

    def __init__(self, host: str = "127.0.0.1", port: int | None = None) -> None:
        self.host = host
        self.port = port
        self._sock: socket.socket | None = None

    def _connect(self) -> tuple[socket.socket, int]:
        """Open one connection, resolving the port from the port file if needed."""
        port = self.port if self.port is not None else _read_port()
        return socket.create_connection((self.host, port), timeout=10.0), port

    def send(self, cmd: str) -> dict:
        """Send one command line, read one JSON status line, return parsed dict.

        The engine handles each connection as one request: it reads a single
        command, replies, then closes the connection.  So we open a fresh
        connection per command.

        The engine picks a NEW ephemeral port on every start and rewrites the
        port file, so a cached port goes stale the moment the engine restarts
        (the MCP server itself keeps running across that).  A failed connect
        therefore drops the cached port, re-reads the port file, and retries
        exactly once before giving up.
        """
        # Close any stale socket from a previous request; the engine closes the
        # connection after replying, so reusing it would block/fail.
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        try:
            sock, port = self._connect()
        except OSError as first:
            stale = self.port
            self.port = None
            try:
                sock, port = self._connect()
            except OSError as second:
                self.port = None
                raise RuntimeError(
                    "cannot reach the CLANNAD engine bridge on 127.0.0.1 "
                    f"(cached port {stale}, port file now {_read_port_now()!r}): {second}. "
                    "Start siglus_engine.exe with --bridge / CLANNAD_BRIDGE=1 "
                    "and CLANNAD_BRIDGE_PORT_FILE pointing at the same file."
                ) from second
        self.port = port
        self._sock = sock
        try:
            with sock.makefile("rwb", buffering=0) as f:
                f.write((cmd.strip() + "\n").encode("utf-8"))
                line = f.readline()
        except OSError:
            self._sock = None
            return {}
        if not line:
            self._sock = None  # server closed; reconnect next call
            return {}
        try:
            return json.loads(line.decode("utf-8", errors="replace").strip())
        except json.JSONDecodeError:
            return {"_raw": line.decode("utf-8", errors="replace").strip()}
        finally:
            self._sock = None  # one response per connection; close for next call

    def state(self) -> dict:
        """Read the latest status snapshot (no action).

        `date` (in-game month/day/weekday) is present only when it just changed.
        """
        return self.send("STATE")

    def _poll_state(self, cond, timeout: float = 8.0, interval: float = 0.08, seen: dict | None = None) -> dict:
        """Repeatedly read STATE until `cond(state)` is true or `timeout` elapses.

        The engine executes queued bridge commands on its render loop and refreshes
        the shared status every frame, so polling STATE returns the *post-action*
        state once the action has taken effect. This fixes the "reply is sent before
        the command executes" problem.

        `seen` (optional) collects values that appeared in ANY intermediate state —
        the in-game `date` — because the engine publishes that field only on the
        frame where it changed, so the final state may no longer carry it.
        """
        import time

        deadline = time.monotonic() + timeout
        last = {}
        while time.monotonic() < deadline:
            last = self.state()
            if seen is not None and last.get("date") is not None:
                seen["date"] = last["date"]
            # Text-matched ending (AGENT.md 19.34): the engine publishes it for ~1s
            # around the match, which an `advance` poll can still step over, so keep
            # the last one seen anywhere in the poll.
            if seen is not None and last.get("ending") is not None:
                seen["ending"] = last["ending"]
            if cond(last):
                return last
            time.sleep(interval)
        return last

    @staticmethod
    def _with_seen(state: dict, seen: dict) -> dict:
        """Merge change-only fields observed mid-poll into the returned state."""
        out = dict(state)
        for key, value in seen.items():
            out.setdefault(key, value)
        return out

    @staticmethod
    def _attach_skip_signals(out: dict) -> dict:
        """Derive positioned `skip_dates` / `skip_endings` from `skip_lines`.

        The engine stamps `date` on the first collected line and on every line where
        the in-game date changed, so `skip_dates` is the segment's day timeline
        (index into `skip_lines` + the date at that point). It stamps `ending` on the
        exact line whose text matched a configured TRUE END judgment phrase
        (AGENT.md 17 / 19.34), so `skip_endings` says which line ended the route
        instead of leaving a caller to re-match text itself.
        """
        lines = out.get("skip_lines") or []
        dates = []
        endings = []
        for i, line in enumerate(lines):
            if not isinstance(line, dict):
                continue
            if isinstance(line.get("date"), dict):
                dates.append({"index": i, **line["date"]})
            end = line.get("ending")
            if isinstance(end, dict):
                endings.append({"index": i, "text": line.get("text", ""), **end})
        if dates:
            out["skip_dates"] = dates
        if endings:
            out["skip_endings"] = endings
            # The last one is the route's end state; also surface it at the top level
            # so a caller that only reads the summary still sees the ending.
            out.setdefault("ending", {"name": endings[-1]["name"], "phrase": endings[-1]["phrase"]})
        return out

    def advance(self) -> dict:
        """Advance one dialogue step; return the state AFTER it advanced.

        `date` is present only when the in-game date changed during this step, and
        `ending` (text-matched TRUE END, AGENT.md 17/19.34) only when this step
        displayed a configured judgment phrase — the engine keeps it in the status
        for ~1s around the match so the poll cannot step over it.
        """
        before = self.state()
        self.send("ADVANCE")
        bscene, bline, btext = before.get("scene"), before.get("line"), before.get("text")
        seen: dict = {}

        def changed(s):
            if s.get("choices"):
                return True  # reached a choice; stop
            return (s.get("line") != bline) or (s.get("text") != btext) or (s.get("scene") != bscene)

        return self._with_seen(self._poll_state(changed, seen=seen), seen)

    def choose(self, idx: int) -> dict:
        """Choose choice index `idx`; return the state AFTER the choice is applied."""
        self.send(f"CHOOSE:{int(idx)}")

        def resolved(s):
            return not (s.get("choices") or [])

        return self._poll_state(resolved)

    def skip(self) -> dict:
        """Fast-forward to the next choice; return the whole fast-forwarded segment.

        `skip_lines` holds every dialogue line collected during the fast-forward
        (from the moment skip started until the choice), plus the final state.
        Stops at a real choice, at a text-matched **ending**, a genuine VM halt, or
        when the budget elapses.

        Ending signal (AGENT.md 17 / 19.34): `skip_lines[i].ending` is stamped on the
        exact line whose text matched a configured TRUE END judgment phrase
        (`endings_map.toml`), and `skip_endings` lists them as
        `[{"index", "text", "name", "phrase"}]`; the top-level `ending`
        (`{"name", "phrase"}`) carries the last one. A skip that reaches an ending
        stops there with `skip_stop_reason="ending"` (a normal arrival, not a
        timeout).

        The budget exists because the caller (an MCP client) has its own timeout: a
        skip that outlives it leaves the game fast-forwarding with nobody listening.
        When the budget elapses we ask the engine to STOP the fast-forward
        (`STOPSKIP`) and return a normal snapshot with `"skip_timeout": true` and the
        partial `skip_lines`, so the state stays consistent and a later skip works.

        The ENGINE enforces the real budget and stops the fast-forward itself
        (`CLANNAD_SKIP_BUDGET_MS`, default 40s), so the reply lands within one poll of
        that budget. This client-side budget (default 45s) is only a fallback for an
        engine that stopped responding; both must stay below the MCP client's own
        timeout (60s in practice). Override with the `CLANNAD_SKIP_TIMEOUT` env var
        (seconds).
        """
        import time

        budget = self.SKIP_TIMEOUT
        # Baseline BEFORE asking for the skip: `skip_seq` identifies the fast-forward
        # that `skip_active`/`skip_stop_reason` describe. Without it, a skip that both
        # starts and finishes between two polls is indistinguishable from "not
        # processed yet" and the call would sit until the fallback budget.
        before = self.state()
        seq0 = before.get("skip_seq")
        ready_deadline = time.monotonic() + 5.0
        while seq0 is None and time.monotonic() < ready_deadline:
            time.sleep(0.2)
            before = self.state()
            seq0 = before.get("skip_seq")
        self.send("SKIP")
        started = time.monotonic()
        saw_active = False
        seen: dict = {}

        def arrived(s: dict) -> bool:
            """True when the fast-forward is over.

            Authoritative signals, in order:
            1. we watched `skip_active` become true and then false;
            2. `skip_seq` moved past our baseline, so OUR skip ran -- and since
               `skip_active` is false, it has already finished (a short skip can start
               and stop entirely between two polls);
            3. the VM halted;
            4. an older engine without `skip_seq`: fall back to `choices` after a short
               grace period (it may not start a skip at all if the game already sits
               on a choice).
            """
            nonlocal saw_active
            if s.get("skip_active"):
                saw_active = True
                return False
            if saw_active:
                return True
            if s.get("halted"):
                return True
            seq = s.get("skip_seq")
            if seq is not None and seq0 is not None:
                return seq != seq0
            # Engine without the field, or a skip that could not start because the
            # game already sits on a choice: fall back to the old signal after a
            # short grace period instead of stalling until the budget.
            return bool(s.get("choices")) and (time.monotonic() - started) > 1.5

        state = self._poll_state(arrived, timeout=budget, interval=0.15, seen=seen)
        if arrived(state):
            out = self._with_seen(state, seen)
            reason = out.get("skip_stop_reason")
            # The ENGINE ended the skip: "choice"/"halted" is a real arrival, while
            # "time_budget"/"step_budget" means its own budget ran out (the caller
            # asked for fast-forward, not for an arrival).
            out["skip_timeout"] = reason in ("time_budget", "step_budget")
            if out["skip_timeout"]:
                out["skip_stopped"] = True
            return self._attach_skip_signals(out)

        # Budget elapsed with the fast-forward still running: stop the engine and
        # return a normal snapshot. The engine keeps the partial segment, so
        # `skip_lines` survives, and the game is no longer running away.
        self.send("STOPSKIP")

        def stopped(s: dict) -> bool:
            # A missing key means an older engine that has no fast-forward state to
            # report; treat it as stopped so we still return promptly.
            return not s.get("skip_active", False)

        final = self._poll_state(stopped, timeout=0.5, interval=0.1, seen=seen)
        out = self._with_seen(final or state, seen)
        out["skip_timeout"] = True
        out["skip_stopped"] = True
        out["skip_stop_reason"] = out.get("skip_stop_reason") or "client_timeout"
        return self._attach_skip_signals(out)

    def save(self, slot: int) -> dict:
        return self.send(f"SAVE:{int(slot)}")

    def load(self, slot: int) -> dict:
        """Load slot; return the state AFTER load takes effect.

        Polls until the scene/line changes (load applied) or a timeout. The
        dialog text can lag the scene switch by a frame or two; we return the
        freshest snapshot either way so the caller never hangs.
        """
        before = self.state()
        self.send(f"LOAD:{int(slot)}")
        bscene, bline = before.get("scene"), before.get("line")

        def changed(s):
            return (s.get("scene") != bscene) or (s.get("line") != bline)

        return self._poll_state(changed, timeout=15.0)

    def jump(self, scene: str) -> dict:
        """Jump to a scene; return the state AFTER the jump."""
        before = self.state()
        self.send(f"JUMP:{scene}")
        bscene = before.get("scene")

        def changed(s):
            return s.get("scene") != bscene

        return self._poll_state(changed)

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None


# Module-level singleton so all tools share one live engine session.
_bridge: ClannadBridge | None = None


def get_bridge() -> ClannadBridge:
    global _bridge
    if _bridge is None:
        _bridge = ClannadBridge()
    return _bridge
