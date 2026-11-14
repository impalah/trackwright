"""TW-1501: measure an exported file against the known test signal.

Prints the format, where the alignment click is, the levels and the spans below a threshold, as JSON.
Usage: uv run --with numpy --with soundfile python experiments/tw1501/measure.py FILE [--locator SECONDS]
       [--placed SECONDS] [--threshold DBFS] [--min SECONDS]
--placed is where the fixture starts in the project, --locator where the export starts: the click is
expected at placed + 1.000 - locator seconds into the file.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf

WINDOW = 0.020


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("--locator", type=float, default=None)
    parser.add_argument("--placed", type=float, default=None)
    parser.add_argument("--threshold", type=float, default=-40.0)
    parser.add_argument("--min", type=float, default=0.5)
    args = parser.parse_args()
    info = sf.info(str(args.file))
    data, rate = sf.read(str(args.file), dtype="float64", always_2d=True)
    mono = data.mean(axis=1)
    hop = int(rate * WINDOW)
    frames = mono[: len(mono) // hop * hop].reshape(-1, hop)
    rms_db = 20 * np.log10(np.sqrt((frames**2).mean(axis=1)) + 1e-12)
    peak_index = int(np.argmax(np.abs(mono) > 0.5)) if np.any(np.abs(mono) > 0.5) else None
    quiet = rms_db < args.threshold
    spans, start = [], None
    for i, q in enumerate([*quiet, False]):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if (i - start) * WINDOW >= args.min:
                spans.append([round(start * WINDOW, 3), round(i * WINDOW, 3)])
            start = None
    out = {
        "file": args.file.name,
        "format": info.format,
        "subtype": info.subtype,
        "rate": rate,
        "channels": info.channels,
        "seconds": round(len(mono) / rate, 4),
        "click_seconds": None if peak_index is None else round(peak_index / rate, 5),
        "peak_dbfs": round(float(20 * np.log10(np.abs(mono).max() + 1e-12)), 2),
        "channel_peaks_dbfs": [
            round(float(20 * np.log10(np.abs(data[:, c]).max() + 1e-12)), 2) for c in range(data.shape[1])
        ],
        "noise_floor_dbfs_p10": round(float(np.percentile(rms_db, 10)), 2),
        "tone_rms_dbfs_p90": round(float(np.percentile(rms_db, 90)), 2),
        "quiet_spans": spans,
    }
    if args.placed is not None and args.locator is not None and peak_index is not None:
        expected = args.placed + 1.0 - args.locator
        out["click_expected_seconds"] = round(expected, 5)
        out["click_error_samples"] = peak_index - round(expected * rate)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
