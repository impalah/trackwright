"""The Cubase service: every tool's logic, independent of MCP so it can be tested directly."""

from __future__ import annotations

from trackwright.core.commanding import CommandingMixin
from trackwright.core.reading import ReadingMixin
from trackwright.core.writing import WritingMixin


class CubaseService(CommandingMixin, WritingMixin, ReadingMixin):
    """Read tools (E05), write and navigation tools (E06) and command tools (E07)."""
