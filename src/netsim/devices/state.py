"""Device power/lifecycle state.

Four deterministic states, no simulated delays: a device is
``CREATED`` (just constructed, never powered), ``POWERED_OFF``,
``BOOTING`` (an explicit, observable intermediate step - see
:meth:`netsim.devices.base.Device.power_on`), or ``READY``. Real time
never elapses; tests drive each transition explicitly.
"""

from __future__ import annotations

from enum import Enum, auto
from types import MappingProxyType
from typing import Mapping

from netsim.devices.errors import InvalidLifecycleTransitionError


class DeviceState(Enum):
    """Lifecycle states a device can be in."""

    CREATED = auto()
    POWERED_OFF = auto()
    BOOTING = auto()
    READY = auto()

_ALLOWED_TRANSITIONS: Mapping[DeviceState, frozenset[DeviceState]] = MappingProxyType(
    {
        DeviceState.CREATED: frozenset({DeviceState.BOOTING}),
        DeviceState.POWERED_OFF: frozenset({DeviceState.BOOTING}),
        DeviceState.BOOTING: frozenset({DeviceState.READY}),
        DeviceState.READY: frozenset({DeviceState.POWERED_OFF}),
    }
)


def validate_transition(current: DeviceState, target: DeviceState) -> None:
    """Raise if moving from ``current`` to ``target`` is not a legal transition.

    Args:
        current: The device's current state.
        target: The state being requested.

    Raises:
        InvalidLifecycleTransitionError: If the transition is not allowed.
    """
    if target not in _ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise InvalidLifecycleTransitionError(
            f"Cannot transition from {current.name} to {target.name}"
        )
