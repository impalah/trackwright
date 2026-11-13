"""``trackwright doctor``: check every link of the chain and say what to do next.

Used by the ``doctor`` command and as the last step of ``trackwright setup``. Read-only: it never starts
the bridge nor writes anything.
"""

from __future__ import annotations

from typing import Any

from trackwright.bridge import BridgeClient
from trackwright.config import Settings
from trackwright.cubase import script_status
from trackwright.errors import TrackwrightError

JsonObject = dict[str, Any]


def run_doctor(settings: Settings) -> JsonObject:
    """Return ``{"ok": bool, "checks": [{"check", "ok", "detail", "fix"?}, ...]}``."""
    checks: list[JsonObject] = []

    def check(name: str, ok: bool, detail: Any, fix: str | None = None) -> bool:
        checks.append({"check": name, "ok": ok, "detail": detail, **({"fix": fix} if fix and not ok else {})})
        return ok

    check("configuration", True, str(settings.source or "built-in defaults"))
    status = script_status(settings.script.install_dir)
    check(
        "script installed",
        status.state == "up_to_date",
        status.to_dict(),
        "run 'trackwright setup' (or 'trackwright script install --apply') and restart Cubase",
    )
    client = BridgeClient(settings.bridge.socket_path)
    bridge_fix = (
        "it starts by itself with the MCP server ([bridge] autostart); to start it by hand: 'trackwright bridge'"
        if settings.bridge.autostart
        else "start it in a terminal: 'trackwright bridge'"
    )
    try:
        bridge = client.call("bridge.status", timeout=settings.bridge.request_timeout)
        bridge_ok = check(
            "bridge running", True, {"socket": str(settings.bridge.socket_path), "pid": bridge.get("pid")}
        )
    except TrackwrightError as exc:
        bridge_ok = check("bridge running", False, exc.to_dict(), bridge_fix)
    if bridge_ok:
        try:
            hello = client.call("hello", timeout=settings.bridge.request_timeout)
            check("Cubase answers", True, {"script": hello.get("scriptVersion"), "host": hello.get("host")})
        except TrackwrightError as exc:
            check(
                "Cubase answers",
                False,
                exc.to_dict(),
                "open Cubase; in the MIDI Remote tab of the lower zone the 'Trackwright - Bridge' surface "
                "must be active (see docs/manual/01-instalacion.md, step 6)",
            )
    check(
        "writes",
        True,
        {
            "enabled": settings.writes.enabled,
            "save": settings.writes.save,
            "allowed_tracks": list(settings.writes.allowed_tracks),
        },
    )
    return {"ok": all(c["ok"] for c in checks), "checks": checks}
