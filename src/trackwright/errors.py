"""Error hierarchy shared by every layer.

Every error carries a stable machine-readable ``code`` (also used as the MCP tool error prefix),
a human message and optional ``details``. Codes reported by the Cubase script (``HostError``) are
passed through unchanged so that the evidence in the POC documentation maps directly to them.
"""

from __future__ import annotations

from typing import Any, ClassVar


class TrackwrightError(Exception):
    """Base class. ``code`` is stable and documented in the tools reference."""

    default_code: ClassVar[str] = "TRACKWRIGHT_ERROR"

    def __init__(self, message: str, *, code: str | None = None, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code or self.default_code
        self.message = message
        self.details: dict[str, Any] = dict(details or {})

    def to_dict(self) -> dict[str, Any]:
        """Serializable form used by the bridge IPC and in logs."""
        out: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            out["details"] = self.details
        return out

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class ConfigError(TrackwrightError):
    """The configuration file or environment is invalid."""

    default_code = "CONFIG_ERROR"


class TransportError(TrackwrightError):
    """The MIDI transport could not be opened or used."""

    default_code = "TRANSPORT_ERROR"


class ProtocolError(TrackwrightError):
    """A frame or envelope does not follow the protocol."""

    default_code = "PROTOCOL_ERROR"


class RequestTimeoutError(TrackwrightError):
    """No response in time. For writes the outcome is unknown: never retry, read back instead."""

    default_code = "TIMEOUT"

    def __init__(self, message: str, *, outcome_unknown: bool, details: dict[str, Any] | None = None) -> None:
        merged = {"outcome": "unknown" if outcome_unknown else "not_executed_or_lost", **(details or {})}
        super().__init__(message, details=merged)
        self.outcome_unknown = outcome_unknown


class StaleSessionError(TrackwrightError):
    """The script was reloaded: its session id changed and runtime ids are no longer valid."""

    default_code = "STALE_SESSION"


class HostError(TrackwrightError):
    """An error reported by the Cubase script; ``code`` is the script's code (for example ``INVALID_OBJECT``)."""

    default_code = "HOST_ERROR"


class BridgeUnavailableError(TrackwrightError):
    """The bridge daemon is not running or its socket is not usable."""

    default_code = "BRIDGE_UNAVAILABLE"


class PolicyError(TrackwrightError):
    """The configured write policy forbids the operation (``WRITES_DISABLED`` or ``NOT_ALLOWED``)."""

    default_code = "NOT_ALLOWED"


class NotFoundError(TrackwrightError):
    """A track, slot, parameter or command does not exist."""

    default_code = "NOT_FOUND"


class StaleReferenceError(TrackwrightError):
    """An opaque object reference belongs to another session or now points at a different object."""

    default_code = "STALE_REF"


class PreconditionFailedError(TrackwrightError):
    """The current state does not allow the operation (slot occupied, selection mismatch...)."""

    default_code = "PRECONDITION_FAILED"


class VerificationFailedError(TrackwrightError):
    """The operation ran but reading the state back does not show the requested result."""

    default_code = "VERIFY_FAILED"


_HOST_CODE_CLASSES: dict[str, type[TrackwrightError]] = {
    "STALE_SESSION": StaleSessionError,
}


def host_error(code: str, message: str, details: dict[str, Any] | None = None) -> TrackwrightError:
    """Build the error for a code returned by the Cubase script."""
    cls = _HOST_CODE_CLASSES.get(code, HostError)
    return cls(message, code=code, details=details)
