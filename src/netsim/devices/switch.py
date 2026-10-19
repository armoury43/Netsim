"""Virtual switch model with VLAN configuration and MAC learning state.

VLAN settings are persistent configuration. The learned MAC table is runtime
state and is cleared when the device reloads or the network runtime is reset.
Access/trunk port settings are stored on each interface and participate in the
normal device configuration lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, cast

from netsim.core.exceptions import ValidationError
from netsim.devices.base import Device
from netsim.devices.interface import SwitchportConfig
from netsim.devices.types import DeviceType

_DEFAULT_INTERFACES = ["FastEthernet0/1", "FastEthernet0/2", "FastEthernet0/3", "FastEthernet0/4"]
_DEFAULT_VLAN_ID = 1


@dataclass(frozen=True)
class Vlan:
    """A single entry in a switch's VLAN database.

    Attributes:
        vlan_id: 802.1Q VLAN ID (1-4094).
        name: Human-readable name. Defaults to the IOS-style
            ``VLANxxxx`` placeholder if none is given.
    """

    vlan_id: int
    name: str


class Switch(Device):
    """A virtual switch.

    Args:
        hostname: Initial hostname. Defaults to ``"Switch"``.
        interface_names: Interface names to build. Defaults to four
            FastEthernet ports if not given. Every interface is built
            with :class:`~netsim.devices.interface.SwitchportConfig`
            already attached (access mode, VLAN 1) - unlike a router's
            interfaces, which never carry one.
    """

    def __init__(
        self,
        hostname: str = "Switch",
        interface_names: list[str] | None = None,
    ) -> None:
        super().__init__(
            hostname=hostname,
            device_type=DeviceType.SWITCH,
            interface_names=list(interface_names) if interface_names is not None else list(_DEFAULT_INTERFACES),
        )
        for iface in self.interfaces.values():
            iface.switchport = SwitchportConfig()

        self._vlans: dict[int, Vlan] = {}
        self.get_or_create_vlan(_DEFAULT_VLAN_ID, name="default")
        self._mac_table: dict[str, str] = {}

    @property
    def vlans(self) -> Mapping[int, Vlan]:
        """Read-only view of the VLAN database, keyed by VLAN ID."""
        return MappingProxyType(self._vlans)

    def get_or_create_vlan(self, vlan_id: int, name: str | None = None) -> Vlan:
        """Return the VLAN with this ID, creating it if it doesn't exist yet.

        Args:
            vlan_id: 802.1Q VLAN ID. Must be in the legal 1-4094 range.
            name: Name to use if this VLAN doesn't exist yet. Defaults
                to an IOS-style ``VLANxxxx`` placeholder. Ignored if
                the VLAN already exists (creating doesn't rename).

        Returns:
            The (possibly newly created) :class:`Vlan`.

        Raises:
            ValidationError: If ``vlan_id`` is out of range.
        """
        if not (1 <= vlan_id <= 4094):
            raise ValidationError(
                "VLAN ID must be between 1 and 4094", field="vlan_id", value=vlan_id
            )
        if vlan_id not in self._vlans:
            self._vlans[vlan_id] = Vlan(vlan_id=vlan_id, name=name or f"VLAN{vlan_id:04d}")
        return self._vlans[vlan_id]

    def replace_vlan_database(self, vlans: list[Vlan]) -> None:
        """Atomically replace the VLAN database from validated records.

        This is primarily for lab import/export. The default VLAN is restored
        automatically if the supplied database omits it; duplicate IDs,
        invalid IDs, and blank names are rejected before the live database is
        changed.
        """
        replacement: dict[int, Vlan] = {}
        for vlan in vlans:
            if not isinstance(vlan.vlan_id, int) or isinstance(vlan.vlan_id, bool):
                raise ValidationError("VLAN ID must be an integer", field="vlan_id", value=vlan.vlan_id)
            if not (1 <= vlan.vlan_id <= 4094):
                raise ValidationError("VLAN ID must be between 1 and 4094", field="vlan_id", value=vlan.vlan_id)
            if not isinstance(vlan.name, str) or not vlan.name.strip():
                raise ValidationError("VLAN name cannot be empty", field="name", value=vlan.name)
            if vlan.vlan_id in replacement:
                raise ValidationError("VLAN IDs must be unique", field="vlan_id", value=vlan.vlan_id)
            replacement[vlan.vlan_id] = Vlan(vlan_id=vlan.vlan_id, name=vlan.name)
        if _DEFAULT_VLAN_ID not in replacement:
            replacement[_DEFAULT_VLAN_ID] = Vlan(vlan_id=_DEFAULT_VLAN_ID, name="default")
        self._vlans = replacement

    @property
    def mac_table(self) -> Mapping[str, str]:
        """Read-only view of the MAC address table (MAC -> interface name)."""
        return MappingProxyType(self._mac_table)

    def learn_mac(self, mac_address: str, interface_name: str) -> None:
        """Record (or update) which interface a MAC address was seen on.

        Foundation only - there is no actual frame flow yet to trigger
        this automatically; it exists so a future switching engine has
        somewhere to record what it learns, and so this data is already
        representable in ``show mac address-table`` once that command
        exists.

        Args:
            mac_address: The MAC address, as a string (format is not
                yet validated - deferred to whichever stage actually
                parses frames).
            interface_name: Which interface it was learned on.

        Raises:
            InterfaceNotFoundError: If ``interface_name`` doesn't exist
                on this switch.
        """
        self.get_interface(interface_name)
        self._mac_table[mac_address] = interface_name

    def forget_mac(self, mac_address: str) -> None:
        """Remove a single learned MAC address entry, if present.

        Foundation for MAC aging: this simulator has no simulated
        clock, so nothing calls this automatically on a timer - a
        future stage that adds one (or a CLI ``clear mac
        address-table``-style command) has a clean, already-tested
        primitive to call rather than reaching into
        :attr:`mac_table` directly.

        Args:
            mac_address: The MAC address to forget. A no-op if it
                isn't currently learned.
        """
        self._mac_table.pop(mac_address, None)

    def clear_mac_table(self) -> None:
        """Forget every learned MAC address entry."""
        self._mac_table.clear()

    def reload(self) -> None:
        """Reload, restoring saved configuration (see
        :class:`~netsim.devices.base.Device`) and additionally
        clearing the MAC table - dynamic learned state is never
        preserved across a reload, matching real switch hardware."""
        super().reload()
        self.clear_mac_table()

    def _capture_extra_config(self) -> dict[str, object]:

        return {"vlans": dict(self._vlans)}

    def _restore_extra_config(self, extra: dict[str, object]) -> None:
        vlans: dict[int, Vlan] = dict(cast(dict[int, Vlan], extra.get("vlans", {})))
        if _DEFAULT_VLAN_ID not in vlans:
            vlans[_DEFAULT_VLAN_ID] = Vlan(vlan_id=_DEFAULT_VLAN_ID, name="default")
        self._vlans = vlans
