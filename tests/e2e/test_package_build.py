"""TW-0906: the built distribution ships the Cubase script and the ``trackwright`` executable."""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not on PATH")
def test_wheel_contains_script_and_entry_point(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    assert uv is not None
    subprocess.run([uv, "build", "--wheel", "-q", "-o", str(tmp_path)], cwd=ROOT, check=True)
    wheel = next(tmp_path.glob("trackwright_mcp-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        entry_points = next(n for n in names if n.endswith("entry_points.txt"))
        assert "trackwright = trackwright.cli:main" in archive.read(entry_points).decode()
    assert "trackwright/cubase/Trackwright_Bridge.js" in names
    assert "trackwright/py.typed" in names
