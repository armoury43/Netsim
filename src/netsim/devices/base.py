"""The Device base class.

Everything shared by Router, Switch, and Host lives here: identity,
hostname, the interface table, IPv4 duplicate-address detection
(a single interface can't see its siblings, so this is the device's
job), lifecycle, and running/startup configuration. Subclasses add
their own defaults (how many interfaces, of what type) and their own
capabilities (VLAN database, default gateway, ...) - nothing about
*this* class needs to change when a new device type is added.

This module has zero knowledge of :mod:`netsim.cli` - it is exactly
what satisfies :class:`netsim.cli.device_interface.FullDeviceContext`
structurally, and nothing here imports that module.
"""

from __future__ import annotations

import uuid
from types import MappingProxyType
from typing import Mapping

from netsim.core.exceptions import ValidationError
from netsim.devices.addressing import parse_ipv4_address
from netsim.devices.configuration import ConfigSnapshot, render_config_text
from netsim.devices.errors import DuplicateInterfaceError, DuplicateIPAddressError, InterfaceNotFoundError
from netsim.devices.interface import Interface
from netsim.devices.state import DeviceState, validate_transition
from netsim.devices.types import DeviceType


class Device:
    """Base class for all virtual network devices.

    Args:
        hostname: Initial hostname.
        device_type: Which kind of device this is (set by the subclass).
        interface_names: Names of the interfaces this device is built
            with. Real hardware doesn't grow new physical interfaces at
            runtime, so the interface set is fixed at construction time -
            there is deliberately no ``add_interface`` later.

    Raises:
        ValidationError: If any interface name is invalid.
        DuplicateInterfaceError: If ``interface_names`` contains repeats.
    """

    def __init__(self, hostname: str, device_type: DeviceType, interface_names: list[str]) -> None:
        self._device_id = str(uuid.uuid4())
        self._device_type = device_type
        self._hostname = hostname
        self._state = DeviceState.CREATED

        seen: set[str] = set()
        interfaces: dict[str, Interface] = {}
        for name in interface_names:
            if name in seen:
                raise DuplicateInterfaceError(name)
            seen.add(name)
            interfaces[name] = Interface(name=name)
        self._interfaces = interfaces

        self._factory_defaults = ConfigSnapshot.capture(self._hostname, self._interfaces)
        self._startup_config: ConfigSnapshot | None = None

        self._startup_extra_config: dict[str, object] | None = None

    @property
    def device_id(self) -> str:
        """Unique identifier for this device instance."""
        return self._device_id

    @property
    def device_type(self) -> DeviceType:
        """Which kind of device this is."""
        return self._device_type

    @property
    def hostname(self) -> str:
        return self._hostname

    def set_hostname(self, hostname: str) -> None:
        """Change the hostname.

        Args:
            hostname: The new hostname.

        Raises:
            ValidationError: If ``hostname`` is empty or whitespace-only.
        """
        if not hostname.strip():
            raise ValidationError("Hostname cannot be empty", field="hostname", value=hostname)
        self._hostname = hostname

    @property
    def interfaces(self) -> Mapping[str, Interface]:
        """Read-only view of this device's interfaces, keyed by name."""
        return MappingProxyType(self._interfaces)

    def get_interface(self, name: str) -> Interface:
        """Look up an interface by exact name.

        Args:
            name: Interface name, e.g. ``"GigabitEthernet0/0"``.

        Returns:
            The interface.

        Raises:
            InterfaceNotFoundError: If no interface with that name exists.
        """
        try:
            return self._interfaces[name]
        except KeyError:
            raise InterfaceNotFoundError(name) from None

    def configure_ipv4(self, interface_name: str, address: str, mask: str) -> None:
        """Assign an IPv4 address to one of this device's interfaces.

        This is the device-level entry point for IP configuration
        (rather than calling ``interface.set_ipv4_address`` directly)
        because duplicate-address detection requires seeing every
        interface on the device, which a single :class:`Interface`
        cannot do on its own.

        Args:
            interface_name: Which interface to configure.
            address: Dotted-decimal IPv4 address.
            mask: Dotted-decimal subnet mask (or bare prefix length).

        Raises:
            InterfaceNotFoundError: If ``interface_name`` doesn't exist.
            ValidationError: If ``address`` or ``mask`` is malformed.
            DuplicateIPAddressError: If ``address`` is already assigned
                to a *different* interface on this device.
        """
        target = self.get_interface(interface_name)

        normalized = str(parse_ipv4_address(address))
        for name, iface in self._interfaces.items():
            if name != interface_name and iface.ipv4_address == normalized:
                raise DuplicateIPAddressError(normalized, name)

        target.set_ipv4_address(address, mask)

    @property
    def state(self) -> DeviceState:
        return self._state

    def power_on(self) -> None:
        """Begin booting. Legal from CREATED or POWERED_OFF."""
        validate_transition(self._state, DeviceState.BOOTING)
        self._state = DeviceState.BOOTING

    def complete_boot(self) -> None:
        """Finish booting. Legal only from BOOTING."""
        validate_transition(self._state, DeviceState.READY)
        self._state = DeviceState.READY

    def power_off(self) -> None:
        """Power off. Legal only from READY."""
        validate_transition(self._state, DeviceState.POWERED_OFF)
        self._state = DeviceState.POWERED_OFF

    def boot(self) -> None:
        """Convenience: power on and complete boot in one call.

        No simulated delay - this is exactly ``power_on()`` followed
        immediately by ``complete_boot()``, for callers that don't need
        to observe the BOOTING state separately.
        """
        self.power_on()
        self.complete_boot()

    def render_running_config(self) -> str:
        """Render the live device state as IOS-style configuration text."""
        return render_config_text(hostname=self._hostname, interfaces=self._interfaces)

    def render_startup_config(self) -> str:
        """Render the saved (or factory-default) configuration as text."""
        snapshot = self._startup_config or self._factory_defaults
        return render_config_text(hostname=snapshot.hostname, interfaces=snapshot.interfaces)

    def save_config(self) -> None:
        """Copy the current running configuration into startup-config."""
        self._startup_config = ConfigSnapshot.capture(self._hostname, self._interfaces)
        self._startup_extra_config = self._capture_extra_config()

    def reload(self) -> None:
        """Discard running configuration, restoring the last saved
        startup-config (or factory defaults, if nothing was ever saved)."""
        snapshot = self._startup_config or self._factory_defaults
        restored = ConfigSnapshot.capture(snapshot.hostname, snapshot.interfaces)
        self._hostname = restored.hostname
        self._interfaces = restored.interfaces
        self._restore_extra_config(self._startup_extra_config or {})

    def _capture_extra_config(self) -> dict[str, object]:
        """Hook for subclasses with configuration beyond hostname and
        interfaces (e.g. a Router's static routes, a Switch's VLAN
        database) to fold it into the same save/reload cycle.

        Called by :meth:`save_config`. The base implementation
        captures nothing extra - :class:`~netsim.devices.host.Host`
        never needs to override this.

        Returns:
            A plain dict of whatever should be captured; interpreted
            only by this same class's :meth:`_restore_extra_config`.
        """
        return {}

    def _restore_extra_config(self, extra: dict[str, object]) -> None:
        """Restore whatever :meth:`_capture_extra_config` produced.

        Called by :meth:`reload` with an empty dict when nothing was
        ever saved (subclasses should treat that as "reset to empty/
        factory defaults" for their extra state). The base
        implementation does nothing.

        Args:
            extra: The dict a prior :meth:`_capture_extra_config` call
                returned (or ``{}`` if nothing was ever saved).
        """
        pass

    def __repr__(self) -> str:
        return f"{type(self).__name__}(hostname={self._hostname!r}, state={self._state.name})"
