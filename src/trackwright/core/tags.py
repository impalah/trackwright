"""Cubase DirectAccess parameter tags, by the object they belong to (C-23).

The same number means different things on different objects (4101 is a channel's input routing, the
Transport's seconds display and an insert slot's "Edit" switch), so tags are only used through these
namespaces. Every value was read from Cubase Elements 15.0.30; see the verification log.
"""

from __future__ import annotations


class Channel:
    """A mixer channel (audio, instrument, group, output...)."""

    NAME = 1024
    SELECTED = 4000
    VOLUME = 1025
    MUTE = 1027
    SOLO = 1028
    RECORD_ARM = 4002
    INPUT = 4101
    OUTPUT = 4102
    WRITE_AUTOMATION = 4013
    READ_AUTOMATION = 4014


class Panner:
    PAN = 4201


class Send:
    LEVEL = 4097


class Transport:
    """The Transport object under Cubase's Device Root (TW-1209, TW-1211)."""

    START = 4015
    RECORD = 4019
    TIME_BARS = 4023
    TIME_SECONDS = 4101
    SIGNATURE = 4027


class Slot:
    """An insert slot."""

    EDIT = 4101  # opens or closes the plugin editor ("Edición" in a Spanish Cubase, TW-1205)


CHANNEL_TAGS = (
    Channel.NAME,
    Channel.SELECTED,
    Channel.VOLUME,
    Channel.MUTE,
    Channel.SOLO,
    Channel.INPUT,
    Channel.OUTPUT,
)
"""The channel parameters read with every track listing (``da.channels``)."""
