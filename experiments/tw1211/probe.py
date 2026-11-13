"""TW-1211 experiment: positions in seconds, event probing and range editing. One step per run.

    uv run python experiments/tw1211/probe.py <step> [args]

Steps (all print JSON; destructive ones only act with --apply):
  state                       cursor (bars and seconds via Transport time2), locators, selected track
  seconds <which> <h:mm:ss.mmm>   set cursor|cycle_left|cycle_right in seconds and read back
  events [max]                walk Locate Next Event from the project start; list cursor stops (seconds)
  select <track>              select a track
  run <command-key> [--apply] run one Trackwright command key (canPerform shown first)
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

from trackwright.cli import make_service
from trackwright.config import load_settings

MIXER = {"scope": "mixer"}
service = make_service(load_settings(), simulate=False)


def transport_object() -> int:
    root = next(o for o in range(64) if _type(o) == "Device Root")
    children = service.call("da.children", {"id": root, "limit": 50, **MIXER})["items"]
    return int(next(c["id"] for c in children if c["type"] == "Transport"))


def _type(oid: int) -> str | None:
    try:
        return str(service.call("da.object", {"id": oid, **MIXER}).get("type"))
    except Exception:  # probing ids
        return None


TRANSPORT = transport_object()


def tparam(tag: int) -> str:
    return str(service.call("da.param.get", {"id": TRANSPORT, "tag": tag, **MIXER}).get("display"))


def state() -> dict[str, Any]:
    base = service.call("da.base", {"scope": "selected"})
    return {
        "cursor_bars": tparam(4023),
        "cursor_seconds": tparam(4101),
        "cycle": [tparam(4030), tparam(4031)],
        "cycle_active": tparam(4022),
        "selected": (base.get("object") or {}).get("title"),
    }


def settle(previous: str, seconds: float = 2.0) -> str:
    deadline = time.monotonic() + seconds
    value = tparam(4101)
    while value == previous and time.monotonic() < deadline:
        time.sleep(0.1)
        value = tparam(4101)
    return value


def main(argv: list[str]) -> Any:
    step = argv[0] if argv else "state"
    if step == "state":
        return state()
    if step == "seconds":
        out = service.set_position(argv[1], argv[2], unit="seconds")
        time.sleep(0.3)
        return {"set": out.model_dump(), "state": state()}
    if step == "events":
        limit = int(argv[1]) if len(argv) > 1 else 12
        service.run_command("transport.return_to_zero", dry_run=False, force=True)
        stops = [settle("x", 0.5)]
        for _ in range(limit):
            service.run_command("transport.locate_next_event", dry_run=False, force=True)
            value = settle(stops[-1])
            if value == stops[-1]:
                break
            stops.append(value)
        return {"stops_seconds": stops, "bars_now": tparam(4023)}
    if step == "select":
        return service.select_track(argv[1]).model_dump()
    if step == "run":
        key, apply = argv[1], "--apply" in argv
        plan = service.run_command(key, dry_run=True)
        if not apply:
            return {"plan": plan.model_dump()}
        before = state()
        done = service.run_command(key, dry_run=False, force=True)
        time.sleep(0.5)
        return {"before": before, "result": done.model_dump(), "after": state()}
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.stdout.write(json.dumps(main(sys.argv[1:]), ensure_ascii=False, indent=1, default=str) + "\n")
