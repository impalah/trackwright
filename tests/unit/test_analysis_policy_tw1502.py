"""TW-1502: reading audio is a capability of its own, off by default and limited in duration."""

from __future__ import annotations

from pathlib import Path

import pytest

from trackwright.config import AnalysisConfig, Settings, WritesConfig, load_settings
from trackwright.core.policy import WritePolicy
from trackwright.errors import ConfigError, PolicyError, PreconditionFailedError


def test_off_by_default() -> None:
    assert Settings().analysis.enabled is False
    with pytest.raises(PolicyError) as exc:
        WritePolicy().check_analysis()
    assert exc.value.code == "ANALYSIS_DISABLED"


def test_independent_of_writes() -> None:
    policy = WritePolicy.from_config(WritesConfig(), AnalysisConfig(enabled=True))
    assert policy.enabled is False
    policy.check_analysis(60.0)  # no write needed to read a file
    with pytest.raises(PolicyError) as exc:
        WritePolicy.from_config(WritesConfig(enabled=True, save=True)).check_analysis()
    assert exc.value.code == "ANALYSIS_DISABLED"  # writes do not imply reading audio


def test_duration_limit() -> None:
    policy = WritePolicy.from_config(WritesConfig(), AnalysisConfig(enabled=True, max_seconds=600))
    policy.check_analysis(600.0)
    with pytest.raises(PreconditionFailedError) as exc:
        policy.check_analysis(600.5)
    assert exc.value.code == "TOO_LONG"
    assert exc.value.details == {"seconds": 600.5, "max_seconds": 600.0}


def test_disabled_wins_over_the_limit() -> None:
    with pytest.raises(PolicyError) as exc:
        WritePolicy(analysis=False, analysis_max_seconds=1.0).check_analysis(10.0)
    assert exc.value.code == "ANALYSIS_DISABLED"


def test_loaded_from_toml(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("[analysis]\nenabled = true\nmax_seconds = 7200\n", encoding="utf-8")
    settings = load_settings(config)
    assert (settings.analysis.enabled, settings.analysis.max_seconds) == (True, 7200.0)
    config.write_text("[analysis]\nmax_seconds = 0\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_settings(config)
    config.write_text("[analysis]\nenable = true\n", encoding="utf-8")  # a typo is not ignored
    with pytest.raises(ConfigError):
        load_settings(config)


def test_status_reports_it(fake: object) -> None:
    from trackwright.core.service import CubaseService

    service = CubaseService(fake, WritePolicy(analysis=True))  # type: ignore[arg-type]
    assert service.status().analysis_enabled is True
    assert WritePolicy().describe()["analysis_enabled"] is False
