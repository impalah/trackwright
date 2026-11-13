"""TW-1206 experiment: can volume automation be recorded through the API?

Steps (see docs/issues/E12-funcionalidades-ampliadas.md, TW-1206):
    uv run python experiments/tw1206/automation.py prepare    # A0 + A1: record state, enable write, cursor to bar 1
    uv run python experiments/tw1206/automation.py record     # A2: waits for Play, writes a volume ramp
    uv run python experiments/tw1206/automation.py record-b2  # A2, variant B2: ramp through the touched surface fader
    uv run python experiments/tw1206/automation.py readback   # A3 + A4: read mode, waits for Play, samples volume
    uv run python experiments/tw1206/automation.py cleanup    # A6: restore read/write flags and volume

Every step appends its measurements to results.json next to this file.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from trackwright.cli import make_service
from trackwright.config import load_settings
from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService

TRACK_NAME = "POC-TEST"
TAG_VOLUME, TAG_WRITE, TAG_READ = 1025, 4013, 4014
RESULTS = Path(__file__).with_name("results.json")
RAMP_FROM, RAMP_TO, RAMP_SECONDS, STEP_SECONDS = 0.79, 0.40, 4.0, 0.2
WAIT_FOR_PLAY_SECONDS = 180
READBACK_SECONDS = 8.0


def service() -> CubaseService:
    base: CubaseService = make_service(load_settings(), simulate=False)
    return CubaseService(base.host, WritePolicy(enabled=True))


def track(s: CubaseService) -> str:
    return next(t.track for t in s.list_tracks().tracks if t.name == TRACK_NAME)


def param(s: CubaseService, t: str, tag: int) -> dict[str, Any]:
    p = s.get_parameter(t, "channel", tag).parameter
    return {"tag": tag, "title": p.title, "process": p.process, "display": p.display}


def save(step: str, data: dict[str, Any]) -> None:
    results = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
    results[step] = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), **data}
    RESULTS.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def wait_for_play(s: CubaseService) -> tuple[str, float]:
    """Playback is detected when the cursor advances.

    The baseline is taken after a short settle so that the callbacks caused by our own cursor move
    (set_position) are not mistaken for playback (that happened in the first B2 readback).
    """
    time.sleep(0.6)
    start = s.get_transport().cursor.time
    deadline = time.monotonic() + WAIT_FOR_PLAY_SECONDS
    while time.monotonic() < deadline:
        now = s.get_transport().cursor.time
        if now != start:
            return now, time.monotonic()
        time.sleep(0.05)
    raise SystemExit(f"no playback detected in {WAIT_FOR_PLAY_SECONDS} s")


def prepare() -> None:
    s = service()
    t = track(s)
    a0 = {"volume": param(s, t, TAG_VOLUME), "write": param(s, t, TAG_WRITE), "read": param(s, t, TAG_READ),
          "cursor": s.get_transport().cursor.time}  # fmt: skip
    write = s.set_parameter(t, "channel", TAG_WRITE, 1, dry_run=False)
    cursor = s.set_position("cursor", "1.1.1.0")
    save("A0_A1", {"initial": a0, "write_enabled": write.verified, "write_after": param(s, t, TAG_WRITE),
                   "cursor_set": cursor.verified})  # fmt: skip


def record() -> None:
    s = service()
    t = track(s)
    first, started = wait_for_play(s)
    steps = int(RAMP_SECONDS / STEP_SECONDS)
    written = []
    for i in range(steps + 1):
        value = RAMP_FROM + (RAMP_TO - RAMP_FROM) * i / steps
        result = s.set_parameter(t, "channel", TAG_VOLUME, value, dry_run=False)
        change = result.changes[0]
        written.append({"t": round(time.monotonic() - started, 2), "requested": round(value, 4),
                        "after": change.after.process if change.after else None,
                        "display": change.after.display if change.after else None,
                        "cursor": s.get_transport().cursor.time})  # fmt: skip
        time.sleep(max(0.0, started + (i + 1) * STEP_SECONDS - time.monotonic()))
    save("A2_record", {"playback_detected_at_cursor": first, "steps": written})


def record_b2() -> None:
    """Variant B2: drive the experiment build's surface fader (bound to the selected track's volume) with touch."""
    s = service()
    t = track(s)
    selected = s.select_track(t)
    first, started = wait_for_play(s)
    steps = int(RAMP_SECONDS / STEP_SECONDS)
    written = []
    touched = s.call("auto.fader", {"touch": True, "value": RAMP_FROM})
    for i in range(steps + 1):
        value = RAMP_FROM + (RAMP_TO - RAMP_FROM) * i / steps
        out = s.call("auto.fader", {"value": value})
        written.append({"t": round(time.monotonic() - started, 2), "requested": round(value, 4),
                        "fader": out.get("value"), "volume": param(s, t, TAG_VOLUME)["display"],
                        "cursor": s.get_transport().cursor.time})  # fmt: skip
        time.sleep(max(0.0, started + (i + 1) * STEP_SECONDS - time.monotonic()))
    released = s.call("auto.fader", {"touch": False})
    save("A2_record_b2", {"selected": selected.selected_after, "playback_detected_at_cursor": first,
                          "touch": touched, "release": released, "steps": written})  # fmt: skip


def readback() -> None:
    s = service()
    t = track(s)
    off = s.set_parameter(t, "channel", TAG_WRITE, 0, dry_run=False).verified
    on = s.set_parameter(t, "channel", TAG_READ, 1, dry_run=False).verified
    reset = s.set_parameter(t, "channel", TAG_VOLUME, RAMP_FROM, dry_run=False).verified
    s.set_position("cursor", "1.1.1.0")
    first, started = wait_for_play(s)
    samples = []
    while time.monotonic() - started < READBACK_SECONDS:
        v = param(s, t, TAG_VOLUME)
        samples.append({"t": round(time.monotonic() - started, 2), "process": v["process"], "display": v["display"],
                        "cursor": s.get_transport().cursor.time})  # fmt: skip
        time.sleep(STEP_SECONDS)
    step_name = (
        "A3_A4_readback"
        if not (RESULTS.exists() and "A3_A4_readback" in RESULTS.read_text(encoding="utf-8"))
        else "A3_A4_readback_retry"
    )
    save(step_name, {"write_off": off, "read_on": on, "volume_reset": reset,
                            "playback_detected_at_cursor": first, "samples": samples})  # fmt: skip


def cleanup() -> None:
    s = service()
    t = track(s)
    results = json.loads(RESULTS.read_text(encoding="utf-8"))
    initial = results["A0_A1"]["initial"]
    for tag, key in ((TAG_WRITE, "write"), (TAG_READ, "read")):
        s.set_parameter(t, "channel", tag, float(initial[key]["process"]), dry_run=False)
    s.set_parameter(t, "channel", TAG_VOLUME, float(initial["volume"]["process"]), dry_run=False)
    s.set_position("cursor", initial["cursor"])
    save("A6_cleanup", {"volume": param(s, t, TAG_VOLUME), "write": param(s, t, TAG_WRITE),
                        "read": param(s, t, TAG_READ), "cursor": s.get_transport().cursor.time})  # fmt: skip


if __name__ == "__main__":
    {"prepare": prepare, "record": record, "record-b2": record_b2, "readback": readback, "cleanup": cleanup}[
        sys.argv[1]
    ]()
