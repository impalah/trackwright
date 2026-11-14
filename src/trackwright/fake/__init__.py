"""FakeCubase: an in-memory simulator of the Trackwright script and of Cubase.

It answers the same operations with the same result shapes as ``Trackwright_Bridge.js`` and
reproduces the behaviours verified against Cubase Elements 15.0.30 in the POC:

- the mixer's last child duplicates the last channel (same id);
- removed objects return sentinels and ``INVALID_OBJECT``;
- process writes outside [0, 1] are refused; routing values (e.g. 22) cannot be written back;
- selection is single; ``da.base`` follows it and is ``-1`` on tracks without a mixer channel;
- after a script reload the session changes and old ids point at *different* objects;
- commands: ``dialog`` ones leave a pending dialog, ``confirm`` ones may wait for confirmation;
- "Locate Next Marker" without a next marker moves to the end of the last event (``last_event_end``).

It is used by the unit and contract tests and by ``trackwright serve --simulate``. Everything it
reports is flagged ``simulated``: it is never evidence about real Cubase behaviour.
"""

from __future__ import annotations

from trackwright.fake.doubles import FakeExports, FakeLauncher
from trackwright.fake.model import Obj, Param
from trackwright.fake.reads import FakeCubase

__all__ = ["FakeCubase", "FakeExports", "FakeLauncher", "Obj", "Param"]
