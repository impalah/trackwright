"""The Cubase service: every tool's logic, independent of MCP so it can be tested directly."""

from __future__ import annotations

from trackwright.core.automation import AutomationMixin
from trackwright.core.commanding import CommandingMixin
from trackwright.core.importing import ImportMixin
from trackwright.core.lifecycle import LifecycleMixin
from trackwright.core.reading import ReadingMixin
from trackwright.core.saving import SavingMixin
from trackwright.core.writing import WritingMixin


class CubaseService(
    SavingMixin, ImportMixin, LifecycleMixin, AutomationMixin, CommandingMixin, WritingMixin, ReadingMixin
):
    """Every tool: read, write, commands, automation, launch, project, ranges, export, import and save (E05-E12)."""
