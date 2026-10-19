"""RIP (Routing Information Protocol) - distance-vector routing.

:class:`RipEngine` owns each RIP-participating router's *learned*
route table - dynamic protocol state, not configuration, so it lives
here (network engine layer) rather than on
:class:`~netsim.devices.router.Router`, exactly like this project's
ARP cache lives on :class:`~netsim.network.engine.NetworkEngine`
rather than on any device. What Router *does* own is which networks
RIP should run on (:attr:`Router.rip_networks
<netsim.devices.router.Router.rip_networks>`) - real configuration,
persisted through save/reload - which this module only ever reads.

No wall-clock timers, no background threads: real RIP broadcasts
every 30 seconds and converges over however many exchanges that takes.
This project has never modeled simulated time anywhere (device boot,
ping, and ARP are all synchronous), so :meth:`RipEngine.converge` is
instead an explicit, deterministic, bounded-round distance-vector
algorithm - callable once and inspectable immediately, substituting
"run enough exchange rounds to reach a fixed point" for "wait long
enough in real time". Router adjacency reuses
:meth:`Topology.l2_reachable_peers
<netsim.network.topology.Topology.l2_reachable_peers>` (the same
mechanism ARP resolution uses) rather than re-deriving which routers
sit on the same segment.

Only the minimum viable RIP is implemented: hop-count metric (max 15,
16 = unreachable) and split horizon. No route poisoning, no triggered
updates, no holddown timers - real RIP's classic count-to-infinity
weakness in complex (non-simple-chain) topologies is a known,
understood limitation shared with real basic RIP, naturally bounded by
``max_rounds`` rather than causing this simulator to hang.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from netsim.devices.router import Router
from netsim.network.routing import Route, RouteSource
from netsim.network.topology import Topology

MAX_METRIC = 15

INFINITY_METRIC = 16

DEFAULT_MAX_ROUNDS = 16


@dataclass(frozen=True)
class RipLearnedRoute:
    """One entry in a router's RIP-learned table.

    Attributes:
        network: Destination network.
        metric: Hop count, 1-:data:`MAX_METRIC`. A route that would
            reach :data:`INFINITY_METRIC` is never stored as one of
            these - it's simply absent.
        next_hop: IPv4 address of the neighbor this was learned from.
        learned_via_interface: Which of the *owning* router's own
            interfaces this was learned on - needed for split horizon.
    """

    network: ipaddress.IPv4Network
    metric: int
    next_hop: ipaddress.IPv4Address
    learned_via_interface: str


class RipEngine:
    """Runs RIP distance-vector convergence over a topology.

    Args:
        topology: The topology to run RIP over. Routers participate
            automatically based on their own configuration (see
            :meth:`Router.rip_enabled_interfaces
            <netsim.devices.router.Router.rip_enabled_interfaces>`) -
            nothing needs to be registered separately here.
    """

    def __init__(self, topology: Topology) -> None:
        self.topology = topology
        self._learned: dict[str, dict[str, RipLearnedRoute]] = {}

    def learned_table(self, device_id: str) -> Mapping[str, RipLearnedRoute]:
        """Read-only view of a router's current RIP-learned table, keyed by network."""
        return MappingProxyType(self._learned.get(device_id, {}))

    def forget(self, device_id: str) -> None:
        """Discard a router's learned RIP table (a no-op if it had none).

        This is dynamic protocol state, never part of device
        configuration (see the module docstring) - a device reload
        should call this explicitly (through
        :meth:`netsim.network.engine.NetworkEngine.forget_rip_routes`)
        rather than this happening automatically, since
        :class:`~netsim.devices.router.Router` has no visibility into
        this engine at all and never should.

        Args:
            device_id: Which router's learned table to clear.
        """
        self._learned.pop(device_id, None)

    def routes_for(self, device_id: str) -> list[Route]:
        """A router's RIP-learned routes as generic :class:`~netsim.network.routing.Route`
        objects, ready to pass to :func:`~netsim.network.routing.build_routing_table`.

        Args:
            device_id: Which router's learned table to convert.

        Returns:
            One :class:`~netsim.network.routing.Route` per learned
            entry (empty if this router isn't a RIP participant, or
            :meth:`converge` hasn't been run yet).
        """
        return [
            Route(
                network=learned.network,
                interface_name=None,
                next_hop=str(learned.next_hop),
                source=RouteSource.RIP,
                metric=learned.metric,
            )
            for learned in self._learned.get(device_id, {}).values()
        ]

    def converge(self, max_rounds: int = DEFAULT_MAX_ROUNDS) -> int:
        """Run synchronous distance-vector rounds until a fixed point.

        Each round, every RIP-participating router computes what it
        would learn based on the *current* (pre-round) state of every
        other router - then all routers' tables are updated together,
        so results never depend on dict/iteration ordering. Safe to
        call again later (e.g. after a config or topology change) to
        reconverge from scratch.

        Args:
            max_rounds: Safety cap - see the module docstring.

        Returns:
            The number of rounds actually run (0 if already stable).
        """
        for round_number in range(1, max_rounds + 1):
            next_learned = self._compute_next_round()
            if next_learned == self._learned:
                return round_number - 1
            self._learned = next_learned
        return max_rounds

    def _compute_next_round(self) -> dict[str, dict[str, RipLearnedRoute]]:
        """One synchronous round: every participating router recomputes
        its learned table from its neighbors' current advertisements."""
        next_learned: dict[str, dict[str, RipLearnedRoute]] = {}
        for router in self._rip_routers():
            incoming: dict[str, RipLearnedRoute] = {}
            for interface_name in sorted(router.rip_enabled_interfaces()):
                for neighbor, neighbor_out_interface in self._neighbors(router, interface_name):
                    advertisement = self._advertisement_from(neighbor, neighbor_out_interface)
                    neighbor_ip = neighbor.get_interface(neighbor_out_interface).ipv4_address
                    if neighbor_ip is None:
                        continue
                    for network_str, metric in advertisement.items():
                        if self._is_own_connected_network(router, network_str):
                            continue
                        candidate = RipLearnedRoute(
                            network=ipaddress.ip_network(network_str),
                            metric=metric,
                            next_hop=ipaddress.ip_address(neighbor_ip),
                            learned_via_interface=interface_name,
                        )
                        existing = incoming.get(network_str)
                        if existing is None or self._is_better(candidate, existing):
                            incoming[network_str] = candidate
            next_learned[router.device_id] = incoming
        return next_learned

    @staticmethod
    def _is_better(candidate: RipLearnedRoute, existing: RipLearnedRoute) -> bool:
        """Deterministic tie-break: lower metric wins; equal metrics
        break the tie by next-hop address, so results never depend on
        iteration order."""
        if candidate.metric != existing.metric:
            return candidate.metric < existing.metric
        return str(candidate.next_hop) < str(existing.next_hop)

    @staticmethod
    def _is_own_connected_network(router: Router, network_str: str) -> bool:
        """A router should never install a RIP route for a network it's
        already directly connected to - administrative distance would
        make Connected win anyway, but there's no reason to store it."""
        return any(network_str == str(network) for _, network in router.connected_interfaces())

    def _advertisement_from(self, router: Router, out_interface: str) -> dict[str, int]:
        """What ``router`` would advertise out ``out_interface`` right
        now: network -> metric, with split horizon applied.

        Args:
            router: The advertising router.
            out_interface: Which of its interfaces the advertisement
                would go out of.

        Returns:
            Mapping of network (as a string) to hop-count metric.
            Empty if ``out_interface`` isn't RIP-enabled at all.
        """
        rip_enabled = set(router.rip_enabled_interfaces())
        if out_interface not in rip_enabled:
            return {}

        advertisement: dict[str, int] = {}

        for name, network in router.connected_interfaces():
            if name in rip_enabled:
                key = str(network)
                advertisement[key] = min(advertisement.get(key, MAX_METRIC), 1)

        for learned in self._learned.get(router.device_id, {}).values():
            if learned.learned_via_interface == out_interface:
                continue
            metric = learned.metric + 1
            if metric >= INFINITY_METRIC:
                continue
            key = str(learned.network)
            advertisement[key] = min(advertisement.get(key, MAX_METRIC), metric)

        return advertisement

    def _neighbors(self, router: Router, interface_name: str) -> list[tuple[Router, str]]:
        """Other RIP-enabled routers directly reachable at Layer 2 from
        this interface - reuses the same adjacency mechanism ARP does."""
        neighbors: list[tuple[Router, str]] = []
        for peer_device_id, peer_interface_name in self.topology.l2_reachable_peers(
            router.device_id, interface_name
        ):
            peer = self.topology.get_device(peer_device_id)
            if isinstance(peer, Router) and peer_interface_name in peer.rip_enabled_interfaces():
                neighbors.append((peer, peer_interface_name))
        return neighbors

    def _rip_routers(self) -> list[Router]:
        """Every Router in the topology with at least one RIP-enabled
        interface, in a stable (device ID) order for determinism."""
        routers = [
            device
            for device in self.topology.devices().values()
            if isinstance(device, Router) and device.rip_enabled_interfaces()
        ]
        return sorted(routers, key=lambda r: r.device_id)
