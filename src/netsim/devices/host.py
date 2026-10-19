"""The Host device model.

A host is deliberately the simplest device: one interface, an
optional default gateway, and a derived "is this endpoint reachable at
all" indicator. There is no ping, no ARP, no actual reachability
check yet - :meth:`Host.is_online` only reflects locally-known state
(power state + interface state + IP configuration), not real
connectivity to anything else. Real connectivity checking is Network
Engine work for a later stage.
"""

from __future__ import annotations

from netsim.devices.addressing import parse_ipv4_address
from netsim.devices.base import Device
from netsim.devices.state import DeviceState
from netsim.devices.types import DeviceType

_DEFAULT_INTERFACE = ["Ethernet0"]


class Host(Device):
    """A virtual end-host (PC/server/workstation).

    Args:
        hostname: Initial hostname. Defaults to ``"PC"``.
        interface_name: Name of the host's single network interface.
            Defaults to ``"Ethernet0"``.
    """

    def __init__(self, hostname: str = "PC", interface_name: str = "Ethernet0") -> None:
        super().__init__(
            hostname=hostname,
            device_type=DeviceType.HOST,
            interface_names=[interface_name],
        )
        self._default_gateway: str | None = None

    @property
    def default_gateway(self) -> str | None:
        """The configured default gateway address, or None."""
        return self._default_gateway

    def set_default_gateway(self, address: str) -> None:
        """Set the default gateway.

        Args:
            address: Dotted-decimal IPv4 address of the gateway.

        Raises:
            ValidationError: If ``address`` is not a valid IPv4 address.
        """
        self._default_gateway = str(parse_ipv4_address(address))

    def clear_default_gateway(self) -> None:
        """Remove the configured default gateway."""
        self._default_gateway = None

    def is_online(self) -> bool:
        """Whether this host is, as far as it can tell locally, reachable.

        True only when the device is powered on and READY, its
        interface is administratively up, and it has an IPv4 address
        configured. This says nothing about whether anything else on
        the network can actually reach it - there is no link/topology
        model yet.

        Returns:
            Whether local conditions for connectivity are satisfied.
        """
        if self.state is not DeviceState.READY:
            return False
        iface = next(iter(self.interfaces.values()))
        return iface.admin_up and iface.ipv4_address is not None

    def _capture_extra_config(self) -> dict[str, object]:
        """Persist the default gateway with the host's other configuration."""
        return {"default_gateway": self._default_gateway} if self._default_gateway is not None else {}

    def _restore_extra_config(self, extra: dict[str, object]) -> None:
        """Restore the saved default gateway, or clear it on factory reset."""
        gateway = extra.get("default_gateway")
        self._default_gateway = str(gateway) if gateway is not None else None
