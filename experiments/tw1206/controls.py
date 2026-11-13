"""TW-1207 experiment (variant B3): which parameters can Trackwright record automation for?

For each automation control (surface fader bound to a parameter of the selected track):
  1. record: write on, cursor to bar 1, Transport Start, touch, ramp, release, Transport Stop;
  2. readback: write off, read on, value back to the initial one, Start, sample the control, Stop;
  3. restore: read off, initial value.
A control "records" when, during readback, its value follows the ramp without being touched.

Usage (experiment build installed, POC-TEST in a disposable project, monitor turned down):
    uv run python experiments/tw1206/controls.py list
    uv run python experiments/tw1206/controls.py run [keys...]     # default: a representative set
Results are appended to results-b3.json next to this file.
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
TAG_WRITE, TAG_READ = 4013, 4014
RESULTS = Path(__file__).with_name("results-b3.json")
DEFAULT_KEYS = ["volume", "pan", "send1.level", "eq1.gain", "prefilter.gain", "qc1", "insert1.p1", "insert1.p2"]
RAMP_STEPS, RAMP_SECONDS, READ_SECONDS = 10, 2.5, 3.5


def service() -> CubaseService:
    base: CubaseService = make_service(load_settings(), simulate=False)
    return CubaseService(base.host, WritePolicy(enabled=True))


def controls(s: CubaseService) -> dict[str, dict[str, Any]]:
    return {c["key"]: c for c in s.call("auto.list")["controls"]}


def set_flag(s: CubaseService, track: str, tag: int, on: bool) -> bool:
    return bool(s.set_parameter(track, "channel", tag, 1.0 if on else 0.0, dry_run=False).verified)


def play_from_start(s: CubaseService) -> float:
    s.set_position("cursor", "1.1.1.0")
    time.sleep(0.5)
    start = s.get_transport().cursor.time
    s.run_command("transport.start", dry_run=False)
    deadline = time.monotonic() + 5
    while s.get_transport().cursor.time == start:
        if time.monotonic() > deadline:
            raise SystemExit("playback did not start")
        time.sleep(0.05)
    return time.monotonic()


def stop(s: CubaseService) -> None:
    s.run_command("transport.stop", dry_run=False)
    time.sleep(0.4)


def test_key(s: CubaseService, track: str, key: str) -> dict[str, Any]:
    before = controls(s).get(key)
    if before is None:
        return {"key": key, "error": "unknown control"}
    initial = before["value"] if isinstance(before["value"], int | float) else 0.5
    target = max(0.0, min(1.0, initial - 0.3 if initial >= 0.4 else initial + 0.3))
    result: dict[str, Any] = {"key": key, "title": before["title"], "initial": initial,
                              "initial_display": before["display"], "target": round(target, 4)}  # fmt: skip
    # 1. record
    set_flag(s, track, TAG_READ, False)
    set_flag(s, track, TAG_WRITE, True)
    started = play_from_start(s)
    written = [s.call("auto.control", {"key": key, "touch": True, "value": initial})]
    for i in range(1, RAMP_STEPS + 1):
        value = initial + (target - initial) * i / RAMP_STEPS
        written.append(s.call("auto.control", {"key": key, "value": value}))
        time.sleep(max(0.0, started + i * RAMP_SECONDS / RAMP_STEPS - time.monotonic()))
    s.call("auto.control", {"key": key, "touch": False})
    time.sleep(0.5)
    stop(s)
    result["recorded"] = [{"value": w.get("value"), "display": w.get("display")} for w in written]
    # 2. readback
    set_flag(s, track, TAG_WRITE, False)
    s.call("auto.control", {"key": key, "value": initial})
    set_flag(s, track, TAG_READ, True)
    started = play_from_start(s)
    samples = []
    while time.monotonic() - started < READ_SECONDS:
        c = controls(s)[key]
        samples.append({"t": round(time.monotonic() - started, 2), "value": c["value"], "display": c["display"]})
        time.sleep(0.25)
    stop(s)
    result["readback"] = samples
    # 3. restore
    set_flag(s, track, TAG_READ, False)
    s.call("auto.control", {"key": key, "value": initial})
    values = [x["value"] for x in samples if isinstance(x["value"], int | float)]
    moved = bool(values) and max(abs(v - initial) for v in values) > 0.5 * abs(target - initial)
    result["records_automation"] = moved
    return result


def main() -> None:
    s = service()
    if sys.argv[1] == "list":
        for _c in s.call("auto.list")["controls"]:
            pass
        return
    track = next(t.track for t in s.list_tracks().tracks if t.name == TRACK_NAME)
    s.select_track(track)
    keys = sys.argv[2:] or DEFAULT_KEYS
    results = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
    for key in keys:
        try:
            outcome = test_key(s, track, key)
        except Exception as exc:
            outcome = {"key": key, "error": str(exc)}
            stop(s)
        results[key] = {"at": time.strftime("%H:%M:%S"), **outcome}
        RESULTS.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    set_flag(s, track, TAG_WRITE, False)
    set_flag(s, track, TAG_READ, False)


if __name__ == "__main__":
    main()
