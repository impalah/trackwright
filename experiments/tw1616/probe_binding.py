"""TW-1616: which track's PreGain does the automation control move once a track is selected?

Reads every audio track's PreGain (DirectAccess), selects the target the way the tools do (waiting until the
volume control carries its name), moves the PreGain automation control to -5 dB WITHOUT playing (nothing is
recorded), reads every PreGain again, and puts back what changed. Test project only.

    uv run python experiments/tw1616/probe_binding.py "TW1616 signal"
"""

from __future__ import annotations

import sys

from trackwright.cli import make_service
from trackwright.config import load_settings
from trackwright.core.refs import TrackSelector


def main() -> None:
    target = sys.argv[1]
    svc = make_service(load_settings(), simulate=False)
    with svc.pinned_session():
        tracks = [t for t in svc.list_tracks(limit=128).tracks if t.type == "AudioChannel"]

        def pregains() -> dict[str, tuple[int, int, float]]:
            out = {}
            for t in tracks:
                item = svc.resolve_track(TrackSelector.parse(t.track))
                flt = svc._child_of_type(item, "InputFilter")
                tag = svc._tag_by_title(flt, "PreGain")
                raw = svc.read_parameter(int(flt["id"]), tag)
                out[t.name] = (int(flt["id"]), tag, float(raw.get("process") or 0))
            return out

        before = pregains()
        item = svc.resolve_track(TrackSelector.parse(target))
        controls = svc._controls_of(item)
        control = controls["prefilter.gain"]
        print(
            f"selected {target!r}: volume control {controls['volume'].get('title')!r}, "
            f"PreGain control {control.get('title')!r} value {control.get('value')}"
        )
        svc.call("auto.control", {"key": "prefilter.gain", "value": 0.4479})  # about -5 dB, no touch, no play
        svc._sleep(0.5)
        after = pregains()
        moved = [name for name in before if abs(after[name][2] - before[name][2]) > 1e-4]
        print("PreGain before:", {k: round(v[2], 4) for k, v in before.items()})
        print("PreGain after: ", {k: round(v[2], 4) for k, v in after.items()})
        print("moved by the control:", moved or "none")
        for name in moved:  # put back
            obj, tag, value = before[name]
            svc.call("da.param.set", {"id": obj, "tag": tag, "value": value, "scope": "mixer"})
        if moved:
            print("restored:", {k: round(v[2], 4) for k, v in pregains().items() if k in moved})


if __name__ == "__main__":
    main()
