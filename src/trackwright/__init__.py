"""Trackwright: an MCP server that inspects and controls Cubase through a MIDI Remote script."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("trackwright-mcp")
except PackageNotFoundError:  # pragma: no cover - only when running from a raw source tree
    __version__ = "0.0.0"

SERVER_NAME = "trackwright"
"""Identifier of the MCP server."""

__all__ = ["SERVER_NAME", "__version__"]
