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


def _read_port(timeout: float = 30.0) -> int:
    """Wait for the engine to write a port file, then return the port."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for path in _candidate_port_files():
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        raw = f.read().strip()
                    if raw:
                        return int(raw)
                except (OSError, ValueError):
                    pass
        time.sleep(0.2)
    raise RuntimeError(
        "engine didn't write a port file within {}s; "
        "start siglus_engine.exe with CLANNAD_BRIDGE=1 and "
        f"CLANNAD_BRIDGE_PORT_FILE={PORT_FILE}".format(timeout)
    )


class ClannadBridge:
    """A tiny blocking client for one logical request/reply at a time."""

    #: Fallback budget: how long the client waits for the ENGINE's own fast-forward
    #: budget to end before it gives up and asks the engine to stop (`STOPSKIP`).
    #:
    #: The engine enforces its own budget (`CLANNAD_SKIP_BUDGET_MS`, default 60s) and
    #: stops exactly when it elapses — that is what makes the game stop AT the budget
    #: instead of one round trip later (AGENT.md 19.32). Keep this above the engine
    #: budget, and keep the engine budget comfortably below the MCP client's timeout.
    SKIP_TIMEOUT = float(os.environ.get("CLANNAD_SKIP_TIMEOUT", "70"))

    def __init__(self, host: str = "127.0.0.1", port: int | None = None) -> None:
        self.host = host
        self.port = port
        self._sock: socket.socket | None = None

    def send(self, cmd: str) -> dict:
        """Send one command line, read one JSON status line, return parsed dict.

        The engine handles each connection as one request: it reads a single
        command, replies, then closes the connection.  So we open a fresh
        connection per command.
        """
        # Close any stale socket from a previous request; the engine closes the
        # connection after replying, so reusing it would block/fail.
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if self.port is None:
            self.port = _read_port()
        sock = socket.create_connection((self.host, self.port), timeout=10.0)
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
    def _attach_skip_dates(out: dict) -> dict:
        """Derive `skip_dates` from the positioned dates inside `skip_lines`.

        The engine stamps `date` on the first collected line and on every line where
        the in-game date changed, so this compact list is the segment's day timeline
        (index into `skip_lines` + the date at that point). Forward-fill from it to
        label every line, which is what makes multi-day fast-forwards readable.
        """
        lines = out.get("skip_lines") or []
        dates = []
        for i, line in enumerate(lines):
            if isinstance(line, dict) and isinstance(line.get("date"), dict):
                dates.append({"index": i, **line["date"]})
        if dates:
            out["skip_dates"] = dates
        return out

    def advance(self) -> dict:
        """Advance one dialogue step; return the state AFTER it advanced.

        `date` is present only when the in-game date changed during this step.
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
        Stops at a real choice, a genuine VM halt, or when the budget elapses.

        The budget exists because the caller (an MCP client) has its own timeout: a
        skip that outlives it leaves the game fast-forwarding with nobody listening.
        When the budget elapses we ask the engine to STOP the fast-forward
        (`STOPSKIP`) and return a normal snapshot with `"skip_timeout": true` and the
        partial `skip_lines`, so the state stays consistent and a later skip works.

        The budget defaults to 60s; override it with the `CLANNAD_SKIP_TIMEOUT` env
        var (seconds).
        """
        import time

        budget = self.SKIP_TIMEOUT
        self.send("SKIP")
        started = time.monotonic()
        saw_active = False
        seen: dict = {}

        def arrived(s: dict) -> bool:
            """True when the fast-forward is over.

            Authoritative signal is the engine's own `skip_active` going back to
            false (it clears it at a choice, on a halt, and when the step budget runs
            out). `choices` alone is NOT enough: the title/menu scenes report menu
            items as choices while the fast-forward is still running, which is how a
            reply used to come back while the game kept skipping.
            """
            nonlocal saw_active
            if s.get("halted"):
                return True
            if s.get("skip_active"):
                saw_active = True
                return False
            if saw_active:
                return True
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
            return self._attach_skip_dates(out)

        # Budget elapsed with the fast-forward still running: stop the engine and
        # return a normal snapshot. The engine keeps the partial segment, so
        # `skip_lines` survives, and the game is no longer running away.
        self.send("STOPSKIP")

        def stopped(s: dict) -> bool:
            # A missing key means an older engine that has no fast-forward state to
            # report; treat it as stopped so we still return promptly.
            return not s.get("skip_active", False)

        final = self._poll_state(stopped, timeout=3.0, interval=0.1, seen=seen)
        out = self._with_seen(final or state, seen)
        out["skip_timeout"] = True
        out["skip_stopped"] = True
        out["skip_stop_reason"] = out.get("skip_stop_reason") or "client_timeout"
        return self._attach_skip_dates(out)

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
