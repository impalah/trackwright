"""TW-1620: the licensed audio library: sidecars, sounds left out, search, the tool and the CLI."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from trackwright.cli import main
from trackwright.core.policy import WritePolicy
from trackwright.core.service import CubaseService
from trackwright.errors import PreconditionFailedError
from trackwright.fake import FakeCubase
from trackwright.library import scan, search, sidecar_path, template

RATE = 48000


def sound(path: Path, seconds: float, sidecar: str | None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, np.zeros((round(seconds * RATE), 2)), RATE)
    if sidecar is not None:
        sidecar_path(path).write_text(sidecar, encoding="utf-8")
    return path


MARCH = 'title = "Together we march"\nkind = "music"\nlicense = "Shop licence"\nsource = "a shop"\n' \
        'allowed_uses = ["podcast", "youtube"]\ntags = ["march", "upbeat", "intro"]\n'  # fmt: skip
WHOOSH = 'title = "Whoosh"\nkind = "effect"\nlicense = "CC0"\nattribution = ""\nallowed_uses = ["podcast"]\n'


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "library"
    sound(root / "music" / "march.wav", 36.0, MARCH)
    sound(root / "fx" / "whoosh.wav", 1.5, WHOOSH)
    sound(root / "fx" / "boom.wav", 2.0, None)  # no sidecar
    sound(root / "fx" / "pop.wav", 0.5, 'title = "Pop"\nkind = "effect"\nlicense = "unknown"\n')  # no licence
    sound(root / "fx" / "bad.wav", 0.5, "title = ")  # broken TOML
    (root / "fx" / "gone.wav.toml").write_text(WHOOSH, encoding="utf-8")  # its sound was deleted
    return root


def test_only_licensed_sounds_are_offered(library: Path, tmp_path: Path) -> None:
    items, problems = scan([library, tmp_path / "nowhere"])
    assert sorted(i.sidecar.title for i in items) == ["Together we march", "Whoosh"]
    assert [p.name for p in problems.no_sidecar] == ["boom.wav"]
    assert sorted(p.name for p in problems.invalid) == ["bad.wav.toml", "pop.wav.toml"]
    assert "not known" in problems.invalid[library / "fx" / "pop.wav.toml"]
    assert [p.name for p in problems.orphan_sidecars] == ["gone.wav.toml"]
    assert problems.missing_folders == [tmp_path / "nowhere"]
    march = next(i for i in items if i.sidecar.kind == "music")
    assert march.seconds == pytest.approx(36.0)


def test_search(library: Path) -> None:
    items, _ = scan([library])
    assert [i.sidecar.title for i in search(items, "march intro")] == ["Together we march"]
    assert search(items, "march whoosh") == []  # every word must match
    assert [i.sidecar.title for i in search(items, kind="effect")] == ["Whoosh"]
    assert [i.sidecar.title for i in search(items, use="YouTube")] == ["Together we march"]
    assert [i.sidecar.title for i in search(items, max_seconds=10)] == ["Whoosh"]
    assert [i.sidecar.title for i in search(items, min_seconds=10)] == ["Together we march"]


def test_the_tool(fake: FakeCubase, library: Path) -> None:
    svc = CubaseService(fake, WritePolicy(), library_folders=[library])
    out = svc.library(query="march")
    assert (out.total, out.items[0].license, out.items[0].allowed_uses) == (1, "Shop licence", ["podcast", "youtube"])
    check = svc.library("check")
    assert [Path(p).name for p in check.no_sidecar] == ["boom.wav"]
    assert len(check.invalid) == 2
    assert any("not offered" in n for n in check.notes)
    with pytest.raises(PreconditionFailedError) as none:
        CubaseService(fake, WritePolicy()).library()
    assert none.value.code == "NO_LIBRARY"
    with pytest.raises(PreconditionFailedError):
        svc.library("delete")  # type: ignore[arg-type]
    empty = CubaseService(fake, WritePolicy(), library_folders=[library / "fx" / "nothing"]).library()
    assert any("no licensed sounds" in n for n in empty.notes)


def test_the_cli(library: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = tmp_path / "config.toml"
    config.write_text(f'[library]\nfolders = ["{library}"]\n', encoding="utf-8")
    assert main(["--config", str(config), "library", "search", "whoosh"]) == 0
    found = json.loads(capsys.readouterr().out)
    assert [i["title"] for i in found["items"]] == ["Whoosh"]
    assert main(["--config", str(config), "library", "check"]) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["licensed"] == 2
    assert main(["--config", str(config), "library", "template", str(library / "fx" / "boom.wav")]) == 0
    printed = capsys.readouterr().out
    assert 'title = "boom"' in printed
    assert not (library / "fx" / "boom.wav.toml").exists()  # printed, not written
    empty = tmp_path / "empty.toml"
    empty.write_text("", encoding="utf-8")
    assert main(["--config", str(empty), "library", "check"]) == 1


def test_template_parses_once_filled() -> None:
    import tomllib

    data = tomllib.loads(template(Path("x.wav")).replace('license = ""', 'license = "CC0"'))
    assert (data["title"], data["license"], data["kind"]) == ("x", "CC0", "music")
