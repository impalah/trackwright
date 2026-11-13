"""Build the TW-1101 experiment script: the packaged script with the status panel switched on.

Usage (from the repository root):
    uv run python experiments/tw1101/build.py
    uv run trackwright script install --file experiments/tw1101/Trackwright_Bridge.js            # dry run
    uv run trackwright script install --file experiments/tw1101/Trackwright_Bridge.js --apply    # install
Back to the released script:
    uv run trackwright script install --apply
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1] / "src" / "trackwright" / "cubase" / "Trackwright_Bridge.js"
TARGET = HERE / "Trackwright_Bridge.js"
SUFFIX = "+tw1101"


def build(source: Path = SOURCE, target: Path = TARGET) -> Path:
    text = source.read_text(encoding="utf-8")
    text, flags = re.subn(r"^var PANEL_ENABLED = false$", "var PANEL_ENABLED = true", text, flags=re.MULTILINE)
    text, versions = re.subn(r"^var SCRIPT_VERSION = '([^']+)'$", rf"var SCRIPT_VERSION = '\1{SUFFIX}'", text,
                             flags=re.MULTILINE)  # fmt: skip
    if flags != 1 or versions != 1:
        raise SystemExit(f"unexpected script layout (PANEL_ENABLED x{flags}, SCRIPT_VERSION x{versions})")
    target.write_text(text, encoding="utf-8")
    return target


if __name__ == "__main__":
    sys.stdout.write(f"{build()}\n")
