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
PORT_FILE = os.environ.get(
    "CLANNAD_BRIDGE_PORT_FILE",
    r"E:\7_projects\clannad_mcp\clannad_bridge.port",
)


def _read_port(timeout: float = 30.0) -> int:
    """Wait for the engine to write its port file, then return the port."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if os.path.exists(PORT_FILE):
            try:
                with open(PORT_FILE, "r", encoding="utf-8", errors="replace") as f:
                    raw = f.read().strip()
                if raw:
                    return int(raw)
            except (OSError, ValueError):
                pass
        time.sleep(0.2)
    raise RuntimeError(
        f"engine didn't write {PORT_FILE} within {timeout}s; "
        "start siglus_engine.exe with CLANNAD_BRIDGE=1 and CLANNAD_BRIDGE_PORT_FILE set"
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

    # -- convenience wrappers for the MCP tools --------------------------------
    def advance(self) -> dict:
        return self.send("ADVANCE")

    def choose(self, idx: int) -> dict:
        return self.send(f"CHOOSE:{int(idx)}")

    def save(self, slot: int) -> dict:
        return self.send(f"SAVE:{int(slot)}")

    def load(self, slot: int) -> dict:
        return self.send(f"LOAD:{int(slot)}")

    def jump(self, scene: str) -> dict:
        return self.send(f"JUMP:{scene}")

    def skip(self) -> dict:
        return self.send("SKIP")

    def state(self) -> dict:
        return self.send("STATE")

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
