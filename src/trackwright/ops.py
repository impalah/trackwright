"""Operations understood by the Trackwright MIDI Remote script.

Kept in one place so that the bridge allowlist, the host client and the tests agree.
"""

from __future__ import annotations

DIRECT_READ_OPS = frozenset({"hello", "ping", "status", "capabilities", "events", "transport.get", "cmd.list"})
"""Answered inside ``mOnSysex`` (milliseconds)."""

IDLE_READ_OPS = frozenset(
    {
        "da.base",
        "da.object",
        "da.children",
        "da.params",
        "da.param.get",
        "da.convert",
        "da.channels",
        "pm.collections",
        "pm.entries",
        "cmd.canPerform",
    }
)
"""Queued and run in ``page.mOnIdle`` (one idle tick, ~112 ms)."""

WRITE_OPS = frozenset(
    {
        "da.param.set",
        "da.param.setDisplay",
        "pm.set",
        "sel.step",
        "transport.setTime",
        "transport.setTempo",
        "cmd.run",
    }
)
"""Change Cubase state. Never retried after a timeout: the outcome is unknown."""

READ_OPS = DIRECT_READ_OPS | IDLE_READ_OPS
ALL_OPS = READ_OPS | WRITE_OPS
SESSIONLESS_OPS = frozenset({"hello", "ping"})
"""The script answers these whatever session id the request carries."""
