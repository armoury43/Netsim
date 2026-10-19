"""Device-layer exceptions.

All derive from :class:`netsim.core.exceptions.DeviceError`, so
:class:`netsim.cli.session.CliSession` - which already catches any
:class:`~netsim.core.exceptions.NetsimError` raised from a command
handler and turns it into user-facing text - handles these with zero
CLI-side changes. Device validation logic lives here, not in the CLI
parser, per the project's architecture rule.
"""

from __future__ import annotations

from netsim.core.exceptions import DeviceError


class InterfaceNotFoundError(DeviceError):
    """Raised when an interface name does not exist on a device."""

    def __init__(self, name: str) -> None:
        super().__init__(f"% Invalid interface: {name!r} does not exist on this device")
        self.name = name


class DuplicateInterfaceError(DeviceError):
    """Raised when constructing a device with a repeated interface name."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Duplicate interface name: {name!r}")
        self.name = name


class InvalidLifecycleTransitionError(DeviceError):
    """Raised when a device power/lifecycle transition is not legal
    from the current state."""


class DuplicateIPAddressError(DeviceError):
    """Raised when an IPv4 address is already assigned to another
    interface on the same device."""

    def __init__(self, address: str, existing_interface: str) -> None:
        super().__init__(
            f"% {address} is already assigned to interface {existing_interface}"
        )
        self.address = address
        self.existing_interface = existing_interface


class UnsupportedCapabilityError(DeviceError):
    """Raised when a command requires a capability (e.g. a VLAN
    database) that this device type does not have."""
