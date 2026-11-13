"""Configuration: TOML file + environment, validated with pydantic.

Lookup order for the file:
1. the path in ``TRACKWRIGHT_CONFIG`` (must exist);
2. ``~/.config/trackwright/config.toml`` (optional).

Defaults are safe: **writes are disabled** until ``[writes] enabled = true``.
"""

from __future__ import annotations

import os
import tempfile
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from trackwright.errors import ConfigError

CONFIG_ENV = "TRACKWRIGHT_CONFIG"
DEFAULT_CONFIG_PATH = Path("~/.config/trackwright/config.toml")
DEFAULT_SCRIPT_DIR = Path("~/Documents/Steinberg/Cubase/MIDI Remote/Driver Scripts/Local/trackwright/bridge")


def default_socket_dir() -> Path:
    """Private per-user directory under ``$TMPDIR`` (never inside the project: the data volume may be ``noowners``)."""
    base = Path(os.environ.get("TMPDIR") or tempfile.gettempdir())
    return base / f"trackwright-{os.getuid()}"


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BridgeConfig(_Section):
    to_cubase_port: str = Field(default="Trackwright To Cubase", min_length=1)
    """Virtual port Python writes to; Cubase sees it as the script's MIDI input."""
    from_cubase_port: str = Field(default="Trackwright From Cubase", min_length=1)
    """Virtual port Python reads from; Cubase sees it as the script's MIDI output."""
    socket_dir: Path = Field(default_factory=default_socket_dir, validate_default=True)
    """Directory of the IPC Unix socket (created with mode 0700)."""
    request_timeout: float = Field(default=3.0, ge=0.05, le=30.0)
    """Default timeout in seconds for one request to Cubase."""
    write_timeout: float = Field(default=5.0, ge=0.05, le=30.0)
    """Timeout for write operations (they run in an idle tick and read back)."""
    backend: Literal["auto", "coremidi", "rtmidi"] = "auto"
    """MIDI transport: ``coremidi`` (ctypes, nothing to compile; macOS), ``rtmidi`` (mido + python-rtmidi,
    which must be installed: see pyproject.toml) or ``auto`` (coremidi on macOS, rtmidi elsewhere)."""
    autostart: bool = True
    """``trackwright serve`` starts the bridge when it is not running (TW-1201)."""
    autostart_timeout: float = Field(default=10.0, ge=0.5, le=60.0)
    """Seconds to wait for an auto-started bridge to accept connections."""

    @field_validator("socket_dir", mode="after")
    @classmethod
    def _expand(cls, value: Path) -> Path:
        return value.expanduser()

    @property
    def socket_path(self) -> Path:
        return self.socket_dir / "bridge.sock"


class WritesConfig(_Section):
    enabled: bool = False
    """Master switch. While false every write tool fails with ``WRITES_DISABLED`` (dry runs still work)."""
    allowed_tracks: tuple[str, ...] = ()
    """Track names that may be modified. Empty means every track (when ``enabled``)."""
    save: bool = False
    """Allow cubase_save_project to save the project file on disk (TW-1202). Separate from ``enabled``."""


class LoggingConfig(_Section):
    level: Literal["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    file: Path | None = None
    """Optional log file (rotated at 10 MB, 5 files kept)."""

    @field_validator("level", mode="before")
    @classmethod
    def _upper(cls, value: Any) -> Any:
        return value.upper() if isinstance(value, str) else value

    @field_validator("file", mode="after")
    @classmethod
    def _expand(cls, value: Path | None) -> Path | None:
        return value.expanduser() if value is not None else None


class ScriptConfig(_Section):
    # validate_default: pydantic does not run validators on defaults otherwise, and "~" would stay literal.
    install_dir: Path = Field(default=DEFAULT_SCRIPT_DIR, validate_default=True)
    """Where ``trackwright script install`` copies the MIDI Remote script."""

    @field_validator("install_dir", mode="after")
    @classmethod
    def _expand(cls, value: Path) -> Path:
        return value.expanduser()


class CubaseConfig(_Section):
    app: str = Field(default="Cubase 15", min_length=1)
    """Application name for ``open -a`` and process name for ``pgrep -x``."""
    launch_timeout: float = Field(default=120.0, ge=5.0, le=600.0)
    """Seconds cubase_launch waits for the script to answer after opening Cubase."""


class Settings(_Section):
    bridge: BridgeConfig = Field(default_factory=BridgeConfig)
    writes: WritesConfig = Field(default_factory=WritesConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    script: ScriptConfig = Field(default_factory=ScriptConfig)
    cubase: CubaseConfig = Field(default_factory=CubaseConfig)
    source: Path | None = None
    """File the settings were loaded from (``None`` = built-in defaults)."""


def config_path(path: Path | None = None, *, environ: dict[str, str] | None = None) -> tuple[Path, bool]:
    """The configuration file to use and whether it was given explicitly (argument or ``$TRACKWRIGHT_CONFIG``)."""
    env = os.environ if environ is None else environ
    explicit = path or (Path(env[CONFIG_ENV]) if env.get(CONFIG_ENV) else None)
    return (explicit or DEFAULT_CONFIG_PATH).expanduser(), explicit is not None


def load_settings(
    path: Path | None = None, *, environ: dict[str, str] | None = None, missing_ok: bool = False
) -> Settings:
    """Load settings from ``path``, ``$TRACKWRIGHT_CONFIG`` or the default location.

    A missing default file means built-in defaults; a missing explicit file is an error unless ``missing_ok``
    (``trackwright setup`` is about to create it).
    """
    candidate, explicit = config_path(path, environ=environ)
    if not candidate.exists():
        if explicit and not missing_ok:
            raise ConfigError(f"configuration file not found: {candidate}", details={"path": str(candidate)})
        return Settings()
    try:
        raw = tomllib.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read {candidate}: {exc}", details={"path": str(candidate)}) from exc
    if "source" in raw:
        raise ConfigError("'source' is not a configurable key", details={"path": str(candidate)})
    try:
        return Settings(**raw, source=candidate)
    except ValidationError as exc:
        errors = [{"loc": ".".join(str(p) for p in e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        raise ConfigError(f"invalid configuration in {candidate}", details={"errors": errors}) from exc
