"""mcp-server package for CLANNAD real-time control."""

from __future__ import annotations

from .clannad_mcp import mcp


def main() -> None:
    """Console-script entry point (mcp-server)."""
    mcp.run()


__all__ = ["mcp", "main"]
