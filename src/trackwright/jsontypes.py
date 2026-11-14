"""The JSON object type shared by every module (I-16: one definition instead of a dozen)."""

from __future__ import annotations

from typing import Any

JsonObject = dict[str, Any]
"""A decoded JSON object: requests, responses, script results."""
