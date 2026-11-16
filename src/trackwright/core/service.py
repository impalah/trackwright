"""The Cubase service: every tool's logic, independent of MCP so it can be tested directly."""

from __future__ import annotations

from trackwright.core.analyzing import AnalyzingMixin
from trackwright.core.automation import AutomationMixin
from trackwright.core.commanding import CommandingMixin
from trackwright.core.importing import ImportMixin
from trackwright.core.lifecycle import LifecycleMixin
from trackwright.core.presets import PresetMixin
from trackwright.core.profiling import ProfilesMixin
from trackwright.core.qc import QualityMixin
from trackwright.core.reading import ReadingMixin
from trackwright.core.rendering import RenderingMixin
from trackwright.core.saving import SavingMixin
from trackwright.core.settings import SettingsMixin
from trackwright.core.workspacing import WorkspaceMixin
from trackwright.core.writing import WritingMixin


class CubaseService(
    QualityMixin,
    RenderingMixin,
    ProfilesMixin,
    WorkspaceMixin,
    AnalyzingMixin,
    PresetMixin,
    SettingsMixin,
    SavingMixin,
    ImportMixin,
    LifecycleMixin,
    AutomationMixin,
    CommandingMixin,
    WritingMixin,
    ReadingMixin,
):
    """Every tool: read, write, commands, automation, launch, project, ranges, export, import, save,
    audio analysis, workspace, renders and profiles (E05-E12, E15, E16)."""
