"""Route models, route selection, and device-configuration projection.

The routing table supports connected, static, default, RIP, and reserved OSPF
route sources. Connected and static routes are derived from device
configuration; RIP-learned routes are supplied by the network engine as
explicit runtime state. Route selection uses longest-prefix matching followed
by administrative distance and stable tie-breaking.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from enum import Enum, auto
from types import MappingProxyType
from typing import Mapping

from netsim.devices.base import Device
from netsim.devices.host import Host
from netsim.devices.router import Router


class RouteSource(Enum):
    """Where a route came from."""

    CONNECTED = auto()
    STATIC = auto()
    DEFAULT = auto()
    RIP = auto()
    OSPF = auto()

ADMINISTRATIVE_DISTANCE: Mapping[RouteSource, int] = MappingProxyType(
    {
        RouteSource.CONNECTED: 0,
        RouteSource.STATIC: 1,
        RouteSource.OSPF: 110,
        RouteSource.RIP: 120,
        RouteSource.DEFAULT: 1,
    }
)


@dataclass(frozen=True)
class Route:
    """A single routing table entry.

    Attributes:
        network: The destination network this route covers.
        interface_name: Which of the owning device's interfaces to
            forward out of.
        next_hop: IPv4 address of the next router to forward toward,
            or ``None`` if the destination is directly connected (in
            which case the destination IP itself is what gets ARP-resolved).
        source: Where this route came from.
        metric: Route-source-specific cost (e.g. RIP hop count).
            Unused for tie-breaking - :data:`ADMINISTRATIVE_DISTANCE`
            handles that - present for display (``show ip route``)
            and for a later stage that might compare metrics *within*
            a single source (e.g. two RIP routes for the same network
            from different neighbors).
    """

    network: ipaddress.IPv4Network
    interface_name: str | None
    next_hop: str | None
    source: RouteSource
    metric: int = 0


class RoutingTable:
    """A device's set of routes, queryable by destination address."""

    def __init__(self) -> None:
        self._routes: list[Route] = []

    def add_route(self, route: Route) -> None:
        """Add a route to the table."""
        self._routes.append(route)

    def routes(self) -> list[Route]:
        """Every route currently in the table."""
        return list(self._routes)

    def lookup(self, destination_ip: str) -> Route | None:
        """Find the best-matching route for a destination address.

        Two-stage tie-break, exactly like real IP forwarding:
        1. Longest-prefix-match: among every route whose network
           contains ``destination_ip``, only the most specific
           (longest prefix) ones are considered.
        2. Administrative distance: among those, the one with the
           lowest :data:`ADMINISTRATIVE_DISTANCE` for its source wins
           (e.g. a connected route always beats a RIP route for the
           identical prefix).

        Args:
            destination_ip: The address being routed toward.

        Returns:
            The best-matching route, or ``None`` if no route covers it.
        """
        address = ipaddress.ip_address(destination_ip)
        candidates = [route for route in self._routes if address in route.network]
        if not candidates:
            return None
        max_prefix = max(route.network.prefixlen for route in candidates)
        most_specific = [route for route in candidates if route.network.prefixlen == max_prefix]
        return min(most_specific, key=lambda route: ADMINISTRATIVE_DISTANCE.get(route.source, 255))


def build_connected_routes(router: Router) -> list[Route]:
    """Connected routes for a router, derived from its own interface state.

    Args:
        router: The router to build connected routes for.

    Returns:
        One :class:`Route` per up, IP-configured interface.
    """
    return [
        Route(network=network, interface_name=name, next_hop=None, source=RouteSource.CONNECTED)
        for name, network in router.connected_interfaces()
    ]


def build_static_routes(router: Router) -> list[Route]:
    """Static routes configured on a router.

    Args:
        router: The router whose configured static routes to read.

    Returns:
        One :class:`Route` per configured static route. ``interface_name``
        is left unset (``None``) here - resolving *which* interface
        reaches a static route's next hop is a recursive lookup the
        network engine performs at forwarding time, not something
        stored on the route itself.
    """
    return [
        Route(
            network=static_route.network,
            interface_name=None,
            next_hop=str(static_route.next_hop),
            source=RouteSource.STATIC,
        )
        for static_route in router.static_routes.values()
    ]


def build_routing_table(device: Device, rip_routes: list[Route] | None = None) -> RoutingTable:
    """Build a :class:`RoutingTable` reflecting a device's current configuration.

    Args:
        device: A :class:`~netsim.devices.router.Router` (connected +
            static + RIP-learned routes) or
            :class:`~netsim.devices.host.Host` (its own subnet +
            default gateway). Any other device type yields an empty
            table.
        rip_routes: RIP-learned routes to include, if any - dynamic
            protocol state owned by the caller (the network engine's
            RIP implementation), never read from here directly. Safe
            to omit entirely (or pass an empty list) for a router with
            no RIP configured, or when RIP convergence hasn't been run.

    Returns:
        A freshly built table. Not cached: call this again after any
        configuration change (or RIP convergence round) to get an
        up-to-date view.
    """
    table = RoutingTable()

    if isinstance(device, Router):
        for route in build_connected_routes(device):
            table.add_route(route)
        for route in build_static_routes(device):
            table.add_route(route)
        for route in rip_routes or []:
            table.add_route(route)

    elif isinstance(device, Host):
        interface_name, interface = next(iter(device.interfaces.items()))
        if interface.admin_up and interface.network is not None:
            table.add_route(
                Route(
                    network=interface.network,
                    interface_name=interface_name,
                    next_hop=None,
                    source=RouteSource.CONNECTED,
                )
            )
        if device.default_gateway is not None and interface.admin_up:
            table.add_route(
                Route(
                    network=ipaddress.ip_network("0.0.0.0/0"),
                    interface_name=interface_name,
                    next_hop=device.default_gateway,
                    source=RouteSource.DEFAULT,
                )
            )

    return table
