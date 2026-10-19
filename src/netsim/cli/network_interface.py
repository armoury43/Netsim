"""Structural protocol boundary between CLI handlers and the network engine.

The protocol describes only the operations required by network commands, such
as simulated ping, ARP-table output, route-table output, and clearing dynamic
RIP routes on reload. The CLI does not construct topologies or implement packet
forwarding itself.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PingResultContext(Protocol):
    """What the CLI needs from a ping outcome."""

    @property
    def success(self) -> bool:
        ...

    @property
    def destination(self) -> str:
        ...

    @property
    def detail(self) -> str:
        """Human-readable elaboration (used directly in CLI output)."""
        ...


@runtime_checkable
class NetworkContext(Protocol):
    """What the CLI needs from the network engine.

    Satisfied structurally by :class:`netsim.network.engine.NetworkEngine`.
    """

    def ping(self, source_device_id: str, destination_ip: str) -> PingResultContext:
        """Simulate a ping. Never raises for an ordinary failed ping -
        see :class:`PingResultContext`; only raises for genuine
        programming errors (e.g. an unknown device ID)."""
        ...

    def format_arp_table(self, device_id: str) -> list[str]:
        """Pre-rendered ``show arp`` output lines for one device."""
        ...

    def format_routing_table(self, device_id: str) -> list[str]:
        """Pre-rendered ``show ip route`` output lines for one device."""
        ...

    def forget_rip_routes(self, device_id: str) -> None:
        """Discard a device's dynamic RIP-learned routes (used by the
        ``reload`` command - see
        :meth:`netsim.network.engine.NetworkEngine.forget_rip_routes`
        for why this is a separate, explicit call rather than
        something ``Device.reload()`` itself could ever trigger)."""
        ...
