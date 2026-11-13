"""The Cubase service: every tool's logic, independent of MCP so it can be tested directly."""

from __future__ import annotations

from trackwright.core.automation import AutomationMixin
from trackwright.core.commanding import CommandingMixin
from trackwright.core.lifecycle import LifecycleMixin
from trackwright.core.reading import ReadingMixin
from trackwright.core.writing import WritingMixin


class CubaseService(LifecycleMixin, AutomationMixin, CommandingMixin, WritingMixin, ReadingMixin):
    """Read (E05), write and navigation (E06), commands (E07), automation (TW-1207) and launch (TW-1201)."""
