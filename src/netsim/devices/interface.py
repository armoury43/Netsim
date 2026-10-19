"""The Interface model.

One class covers both routed (Layer 3) and switched (Layer 2)
interfaces rather than splitting into parallel class hierarchies per
device type - a real network OS lets almost any interface carry an IP
address (including switch SVIs and routed switchports), so the
capability difference is data (:class:`SwitchportConfig` present or
not), not a type difference. :class:`~netsim.devices.router.Router`
never populates ``switchport``; :class:`~netsim.devices.switch.Switch`
always does.

This class is also exactly what satisfies
:class:`netsim.cli.device_interface.InterfaceContext` structurally -
nothing here imports from :mod:`netsim.cli`, and nothing in
:mod:`netsim.cli` imports this class.
"""

from __future__ import annotations

import copy
import ipaddress
import re
from dataclasses import dataclass, field
from typing import Literal

from netsim.core.exceptions import ValidationError
from netsim.devices.addressing import parse_ipv4_address, parse_ipv4_mask
from netsim.devices.mac import generate_mac_address, is_valid_mac

_NAME_PATTERN = re.compile(r"^[A-Za-z]+[0-9]+(/[0-9]+)*$")


@dataclass
class SwitchportConfig:
    """Layer-2 switchport configuration foundation.

    Only the data needed for later stages to build real VLAN/trunking
    behavior on top of - no forwarding or trunk negotiation logic
    lives here yet.

    Attributes:
        mode: ``"access"`` or ``"trunk"``.
        access_vlan: VLAN this port is a member of in access mode.
        trunk_allowed_vlans: VLANs permitted across this port in trunk mode.
    """

    mode: Literal["access", "trunk"] = "access"
    access_vlan: int = 1
    trunk_allowed_vlans: set[int] = field(default_factory=set)


class Interface:
    """A single network interface on a device.

    Args:
        name: Interface name, e.g. ``"GigabitEthernet0/0"``. Must match
            an interface-type-plus-numbering pattern.
        description: Optional initial description.
        switchport: Present (non-``None``) for Layer-2 switchports;
            absent for routed interfaces.

    Raises:
        ValidationError: If ``name`` doesn't look like a real interface name.
    """

    def __init__(
        self,
        name: str,
        description: str = "",
        switchport: SwitchportConfig | None = None,
    ) -> None:
        if not _NAME_PATTERN.match(name):
            raise ValidationError(
                f"{name!r} is not a valid interface name", field="name", value=name
            )
        self._name = name
        self._description = description
        self._admin_up = False
        self._ipv4_address: ipaddress.IPv4Address | None = None
        self._ipv4_prefix_length: int | None = None
        self._mac_address = generate_mac_address()
        self.switchport = switchport

    @property
    def name(self) -> str:
        """Interface name (immutable after creation, like real hardware)."""
        return self._name

    @property
    def mac_address(self) -> str:
        """This interface's simulated MAC address, generated once at
        construction and stable thereafter."""
        return self._mac_address

    def set_mac_address(self, mac_address: str) -> None:
        """Explicitly override the MAC address (rare - real hardware
        does this too, "MAC spoofing").

        Args:
            mac_address: The new MAC address, e.g. ``"02:AA:BB:CC:DD:EE"``.

        Raises:
            ValidationError: If ``mac_address`` is not a validly
                formatted MAC address.
        """
        if not is_valid_mac(mac_address):
            raise ValidationError(
                f"{mac_address!r} is not a valid MAC address",
                field="mac_address",
                value=mac_address,
            )
        self._mac_address = mac_address

    def set_switchport_access_vlan(self, vlan_id: int) -> None:
        """Assign this port to an access VLAN, switching it to access
        mode if it wasn't already (backs the ``switchport access vlan``
        CLI command).

        Args:
            vlan_id: 802.1Q VLAN ID (1-4094).

        Raises:
            ValidationError: If this interface has no switchport
                configuration at all (e.g. a routed Router interface -
                this is what makes the CLI command naturally fail with
                a clear message on a non-switch device, with no
                separate device-type check needed), or if ``vlan_id``
                is out of range.
        """
        if self.switchport is None:
            raise ValidationError(
                f"{self._name!r} is not a switchport", field="switchport", value=self._name
            )
        if not (1 <= vlan_id <= 4094):
            raise ValidationError("VLAN ID must be between 1 and 4094", field="vlan_id", value=vlan_id)
        self.switchport.mode = "access"
        self.switchport.access_vlan = vlan_id

    def set_switchport_trunk(self, allowed_vlans: set[int] | None = None) -> None:
        """Switch this port to trunk mode (backs ``switchport mode
        trunk`` / ``switchport trunk allowed vlan``).

        Args:
            allowed_vlans: If given, replaces the trunk's allowed VLAN
                list. If omitted, only the mode changes - any
                previously configured allowed-VLAN list is left as-is
                (matching real IOS: ``switchport mode trunk`` and
                ``switchport trunk allowed vlan`` are separate commands).

        Raises:
            ValidationError: If this interface has no switchport
                configuration at all, or any VLAN in ``allowed_vlans``
                is out of range.
        """
        if self.switchport is None:
            raise ValidationError(
                f"{self._name!r} is not a switchport", field="switchport", value=self._name
            )
        if allowed_vlans is not None:
            for vlan_id in allowed_vlans:
                if not (1 <= vlan_id <= 4094):
                    raise ValidationError(
                        "VLAN ID must be between 1 and 4094", field="vlan_id", value=vlan_id
                    )
        self.switchport.mode = "trunk"
        if allowed_vlans is not None:
            self.switchport.trunk_allowed_vlans = set(allowed_vlans)

    @property
    def description(self) -> str:
        return self._description

    def set_description(self, description: str) -> None:
        """Set the interface description. Any string is accepted, including empty."""
        self._description = description

    @property
    def admin_up(self) -> bool:
        """Administrative state: True if enabled (``no shutdown``)."""
        return self._admin_up

    def set_admin_up(self, admin_up: bool) -> None:
        """Set administrative state (``shutdown`` / ``no shutdown``)."""
        self._admin_up = admin_up

    def status_summary(self) -> str:
        """One-word-ish status string for `show` commands."""
        return "up" if self._admin_up else "administratively down"

    @property
    def ipv4_address(self) -> str | None:
        """The configured IPv4 address as a dotted-decimal string, or None."""
        return str(self._ipv4_address) if self._ipv4_address is not None else None

    @property
    def ipv4_prefix_length(self) -> int | None:
        """The configured IPv4 prefix length (0-32), or None."""
        return self._ipv4_prefix_length

    @property
    def network(self) -> ipaddress.IPv4Network | None:
        """The IPv4 network this interface is directly connected to, or None."""
        if self._ipv4_address is None or self._ipv4_prefix_length is None:
            return None
        return ipaddress.ip_network(
            f"{self._ipv4_address}/{self._ipv4_prefix_length}", strict=False
        )

    def set_ipv4_address(self, address: str, mask: str) -> None:
        """Configure an IPv4 address and mask on this interface.

        Args:
            address: Dotted-decimal IPv4 address.
            mask: Dotted-decimal subnet mask (or a bare prefix length).

        Raises:
            ValidationError: If ``address`` or ``mask`` is malformed.
                Duplicate-IP-on-device checking is the owning
                :class:`~netsim.devices.base.Device`'s responsibility,
                since a single interface has no visibility into its
                siblings.
        """
        parsed_address = parse_ipv4_address(address)
        prefix_length = parse_ipv4_mask(mask)
        self._ipv4_address = parsed_address
        self._ipv4_prefix_length = prefix_length

    def clear_ipv4_address(self) -> None:
        """Remove any configured IPv4 address from this interface."""
        self._ipv4_address = None
        self._ipv4_prefix_length = None

    def __deepcopy__(self, memo: dict[int, object]) -> "Interface":
        clone = Interface.__new__(Interface)
        clone._name = self._name
        clone._description = self._description
        clone._admin_up = self._admin_up
        clone._ipv4_address = self._ipv4_address
        clone._ipv4_prefix_length = self._ipv4_prefix_length
        clone._mac_address = self._mac_address
        clone.switchport = copy.deepcopy(self.switchport, memo)
        return clone

    def __repr__(self) -> str:
        return f"Interface(name={self._name!r}, admin_up={self._admin_up}, ipv4_address={self.ipv4_address!r})"
