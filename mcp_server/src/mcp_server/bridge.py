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
        """Read the latest status snapshot (no action)."""
        return self.send("STATE")

    def _poll_state(self, cond, timeout: float = 8.0, interval: float = 0.08) -> dict:
        """Repeatedly read STATE until `cond(state)` is true or `timeout` elapses.

        The engine executes queued bridge commands on its render loop and refreshes
        the shared status every frame, so polling STATE returns the *post-action*
        state once the action has taken effect. This fixes the "reply is sent before
        the command executes" problem.
        """
        import time

        deadline = time.monotonic() + timeout
        last = {}
        while time.monotonic() < deadline:
            last = self.state()
            if cond(last):
                return last
            time.sleep(interval)
        return last

    def advance(self) -> dict:
        """Advance one dialogue step; return the state AFTER it advanced."""
        before = self.state()
        self.send("ADVANCE")
        bscene, bline, btext = before.get("scene"), before.get("line"), before.get("text")

        def changed(s):
            if s.get("choices"):
                return True  # reached a choice; stop
            return (s.get("line") != bline) or (s.get("text") != btext) or (s.get("scene") != bscene)

        return self._poll_state(changed)

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
        Stops only at a real choice or a genuine VM halt.
        """
        self.send("SKIP")

        def reached(s):
            ch = s.get("choices") or []
            if ch:
                return True
            # genuine halt only (NOT line<0: non-story scenes like _system_language
            # report line=-1 but are not end-of-content)
            return bool(s.get("halted"))

        return self._poll_state(reached, timeout=180.0, interval=0.15)

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
