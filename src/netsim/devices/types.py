"""Device type identity.

A tiny, standalone enum so :mod:`netsim.devices.base` and every
concrete device subclass can share one vocabulary without any of them
importing each other.
"""

from __future__ import annotations

from enum import Enum, auto


class DeviceType(Enum):
    """What kind of device this is."""

    ROUTER = auto()
    SWITCH = auto()
    HOST = auto()
