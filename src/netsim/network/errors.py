"""Exceptions for topology and network-engine operations.

These errors describe failures involving the simulated topology, such as
unknown devices, missing interfaces, duplicate connections, or invalid links.
Device-configuration errors are defined separately in ``netsim.devices``.
"""

from __future__ import annotations

from netsim.core.exceptions import NetworkSimulationError


class DeviceAlreadyInTopologyError(NetworkSimulationError):
    """Raised when the same device instance/ID is registered more than once."""

    def __init__(self, device_id: str) -> None:
        super().__init__(f"Device ID {device_id!r} is already registered")
        self.device_id = device_id


class DeviceNotInTopologyError(NetworkSimulationError):
    """Raised when referencing a device ID the topology doesn't know about."""

    def __init__(self, device_id: str) -> None:
        super().__init__(f"Device {device_id!r} is not part of this topology")
        self.device_id = device_id


class InterfaceNotInTopologyError(NetworkSimulationError):
    """Raised when referencing an interface that doesn't exist on a
    device that IS in the topology (distinct from
    :class:`netsim.devices.errors.InterfaceNotFoundError`, which is
    the device's own, lower-level version of this check)."""

    def __init__(self, device_id: str, interface_name: str) -> None:
        super().__init__(
            f"Interface {interface_name!r} does not exist on device {device_id!r}"
        )
        self.device_id = device_id
        self.interface_name = interface_name


class SelfConnectionError(NetworkSimulationError):
    """Raised when trying to link an interface to itself."""

    def __init__(self, device_id: str, interface_name: str) -> None:
        super().__init__(
            f"Cannot connect interface {interface_name!r} on device {device_id!r} to itself"
        )
        self.device_id = device_id
        self.interface_name = interface_name


class InterfaceAlreadyConnectedError(NetworkSimulationError):
    """Raised when an interface already has a link and a second one is attempted."""

    def __init__(self, device_id: str, interface_name: str) -> None:
        super().__init__(
            f"Interface {interface_name!r} on device {device_id!r} is already connected"
        )
        self.device_id = device_id
        self.interface_name = interface_name


class LinkNotFoundError(NetworkSimulationError):
    """Raised when an operation expects a link that doesn't exist."""

    def __init__(self, device_id: str, interface_name: str) -> None:
        super().__init__(
            f"No link found for interface {interface_name!r} on device {device_id!r}"
        )
        self.device_id = device_id
        self.interface_name = interface_name
