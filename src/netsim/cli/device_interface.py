"""Structural protocol boundary between CLI handlers and device models.

The minimal device protocol is extended by capability-specific protocols for
interfaces, VLANs, MAC tables, routing, and access control. Concrete device
classes need not import or inherit from the CLI package, keeping the front end
replaceable by the GUI, scripts, and test harnesses.
"""

from __future__ import annotations

from typing import Mapping, Protocol, runtime_checkable


@runtime_checkable
class DeviceContext(Protocol):
    """The minimal shape the CLI requires of *any* device.

    Deliberately minimal: it exposes a human-readable name for the
    prompt and a method to change that name. Concrete devices satisfy
    this protocol structurally through their public attributes and
    methods; no inheritance from this protocol is required.
    """

    @property
    def hostname(self) -> str:
        """The device's current hostname, shown in the CLI prompt."""
        ...

    def set_hostname(self, hostname: str) -> None:
        """Change the device's hostname.

        Args:
            hostname: The new hostname. Validation of what counts as a
                legal hostname is the device's responsibility, not the
                CLI's - the CLI only validates argument *syntax*
                generically (see :mod:`netsim.cli.command`).
        """
        ...


@runtime_checkable
class InterfaceContext(Protocol):
    """What the CLI needs from a single interface.

    Satisfied structurally by :class:`netsim.devices.interface.Interface`
    without either module importing the other.
    """

    @property
    def name(self) -> str:
        """Interface name, e.g. ``"GigabitEthernet0/0"``."""
        ...

    @property
    def description(self) -> str:
        ...

    def set_description(self, description: str) -> None:
        ...

    @property
    def admin_up(self) -> bool:
        ...

    def set_admin_up(self, admin_up: bool) -> None:
        ...

    @property
    def ipv4_address(self) -> str | None:
        """Configured IPv4 address as a dotted-decimal string, or None."""
        ...

    @property
    def ipv4_prefix_length(self) -> int | None:
        ...

    def set_ipv4_address(self, address: str, mask: str) -> None:
        """Raises whatever NetsimError subclass the device layer deems
        appropriate (malformed input, duplicate address, ...) - the CLI
        session already catches any NetsimError from a handler and
        surfaces it as user-facing text, so no CLI-side change is
        needed to support this."""
        ...

    def status_summary(self) -> str:
        """Short status string for `show` commands, e.g. ``"up"``."""
        ...

    def set_switchport_access_vlan(self, vlan_id: int) -> None:
        """Raises a NetsimError (handled generically by CliSession) if
        this interface has no switchport at all (e.g. a routed Router
        interface) - this is what makes ``switchport access vlan``
        naturally fail with a clear message on a non-switch device."""
        ...

    def set_switchport_trunk(self, allowed_vlans: "set[int] | None" = None) -> None:
        """Same failure mode as :meth:`set_switchport_access_vlan` on
        a non-switchport interface."""
        ...


@runtime_checkable
class FullDeviceContext(DeviceContext, Protocol):
    """Extends :class:`DeviceContext` with interface and configuration
    management - satisfied by the real Router, Switch, and Host models.

    It remains separate from ``DeviceContext`` so lightweight test doubles
    and alternate device implementations need only implement the minimal
    contract when they do not support interface configuration.
    """

    @property
    def interfaces(self) -> "Mapping[str, InterfaceContext]":
        """Read-only view of this device's interfaces, keyed by name."""
        ...

    @property
    def device_id(self) -> str:
        """Stable identifier used by topology, ARP, and routing state."""
        ...

    def get_interface(self, name: str) -> InterfaceContext:
        """Raises an InterfaceNotFoundError-shaped NetsimError if
        ``name`` doesn't exist - handled generically by CliSession."""
        ...

    def configure_ipv4(self, interface_name: str, address: str, mask: str) -> None:
        """Assign an IPv4 address to one of this device's interfaces,
        with device-wide duplicate-address checking. This is why IP
        configuration goes through the device rather than calling
        ``get_interface(...).set_ipv4_address(...)`` directly - a
        single interface can't see its siblings to detect a conflict."""
        ...

    def render_running_config(self) -> str:
        ...

    def render_startup_config(self) -> str:
        ...

    def save_config(self) -> None:
        ...

    def reload(self) -> None:
        ...


@runtime_checkable
class VlanCapableDeviceContext(Protocol):
    """Capability protocol for devices with a VLAN database (switches).

    Used with an ``isinstance`` check by VLAN-related command handlers
    so they degrade gracefully (a clear error, not a crash) on device
    types - like Router or Host - that were never meant to have VLANs,
    without ``DeviceContext``/``FullDeviceContext`` needing to know
    VLANs exist at all.
    """

    def get_or_create_vlan(self, vlan_id: int, name: str | None = None) -> object:
        ...


@runtime_checkable
class MacTableCapableDeviceContext(Protocol):
    """Capability protocol for devices with a MAC address table (switches).

    Same pattern as :class:`VlanCapableDeviceContext`: a command like
    ``show mac address-table`` checks this via ``isinstance`` rather
    than requiring every device type to have a (meaningless, for a
    Router or Host) MAC table.
    """

    @property
    def mac_table(self) -> "Mapping[str, str]":
        """Learned MAC-address-to-port-name mappings."""
        ...


@runtime_checkable
class StaticRoutingCapableDeviceContext(Protocol):
    """Capability protocol for devices that support static routes (routers).

    Same pattern as :class:`VlanCapableDeviceContext`: the ``ip
    route`` command checks this via ``isinstance`` rather than
    requiring every device type to support routing configuration -
    a Host or Switch simply doesn't.
    """

    def add_static_route(self, network: str, mask: str, next_hop: str) -> None:
        ...


@runtime_checkable
class RipCapableDeviceContext(Protocol):
    """Capability protocol for devices that support RIP configuration
    (routers). Same pattern as :class:`StaticRoutingCapableDeviceContext`:
    the ``network`` command (under ``router rip``) checks this via
    ``isinstance`` rather than requiring every device type to support
    dynamic routing configuration.
    """

    def enable_rip(self, network: str, mask: str) -> None:
        ...


@runtime_checkable
class AclCapableDeviceContext(Protocol):
    """Capability protocol for devices that support access control
    lists (routers). Same pattern as
    :class:`StaticRoutingCapableDeviceContext`: the ``access-list``,
    ``ip access-group``, and ``no ip access-group`` commands use ``isinstance``
    rather than requiring every device type to support ACL configuration.
    """

    def add_access_list_rule(self, number: int, action: str, network: str, mask: "str | None" = None) -> None:
        ...

    def set_interface_acl(self, interface_name: str, direction: str, number: int) -> None:
        """Apply an ACL to an interface; the device layer validates inputs."""
        ...

    def remove_interface_acl(
        self, interface_name: str, direction: str, number: int | None = None
    ) -> None:
        """Remove an ACL binding, optionally only when its number matches."""
        ...
