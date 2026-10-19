"""The network engine facade.

:class:`NetworkEngine` is where everything else in :mod:`netsim.network`
comes together: it owns per-device ARP caches (devices themselves
don't store one - ARP state is protocol/simulation state, not device
configuration, so it lives at the engine layer alongside the topology
it depends on), and implements :meth:`ping`, which is the one method
that actually walks routing -> interface/link state -> ARP -> the next
hop, exactly reflecting current simulated state. Nothing here ever
returns success without having genuinely checked every one of those
steps against live topology and device state - there is no shortcut
path that fabricates connectivity.

This is also what satisfies the CLI-facing
:class:`netsim.cli.network_interface.NetworkContext` protocol
structurally (see that module) - :mod:`netsim.network` still never
imports :mod:`netsim.cli`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

from netsim.devices.addressing import parse_ipv4_address
from netsim.devices.base import Device
from netsim.devices.router import Router
from netsim.devices.state import DeviceState
from netsim.network.arp import ArpCache
from netsim.network.icmp import PingFailureReason, PingResult
from netsim.network.rip import RipEngine
from netsim.network.routing import ADMINISTRATIVE_DISTANCE, Route, RoutingTable, build_routing_table
from netsim.network.topology import Topology

_MAX_HOPS = 16


@dataclass(frozen=True)
class ArpResolution:
    """The outcome of successfully resolving an IP address to a MAC address.

    Attributes:
        mac_address: The resolved MAC address.
        peer_device_id: Device ID of whoever answered.
        peer_interface_name: Which of that device's interfaces answered.
    """

    mac_address: str
    peer_device_id: str
    peer_interface_name: str


def _is_ready(device: Device) -> bool:
    """Whether a device is powered on and able to participate in the network."""
    return device.state is DeviceState.READY


class NetworkEngine:
    """Ties topology, routing, and ARP together into a working ping.

    Args:
        topology: The topology this engine simulates traffic across.
    """

    def __init__(self, topology: Topology) -> None:
        self.topology = topology
        self._arp_caches: dict[str, ArpCache] = {}
        self._rip_engine = RipEngine(topology)

    def arp_cache_for(self, device_id: str) -> ArpCache:
        """Get (creating if needed) the ARP cache belonging to a device."""
        if device_id not in self._arp_caches:
            self._arp_caches[device_id] = ArpCache()
        return self._arp_caches[device_id]

    def arp_table(self, device_id: str) -> Mapping[str, str]:
        """Read-only view of a device's current ARP cache entries."""
        return self.arp_cache_for(device_id).entries()

    def resolve_arp(self, device_id: str, interface_name: str, target_ip: str) -> ArpResolution | None:
        """Resolve an IP address to a MAC address, simulating an ARP exchange.

        Always re-derives the answer from *current* topology and
        device state (never trusts a stale cache entry to decide
        success or failure - a link going down since the last
        resolution must correctly cause this to fail now). The cache
        is updated as a side effect either way: learned on success,
        or dropped if a previously-learned mapping is no longer valid.

        This simulates broadcasting an ARP request across every
        interface reachable at Layer 2 from ``(device_id,
        interface_name)`` (via :meth:`Topology.l2_broadcast
        <netsim.network.topology.Topology.l2_broadcast>` - an ARP
        request genuinely is a broadcast frame, so every switch it
        crosses really does learn the requester's MAC address, exactly
        as it would learn from any other broadcast) and checking which
        reached interface, if any, actually holds ``target_ip`` - real
        ARP learning is bidirectional, so the replier also learns the
        requester's address in the same exchange.

        Args:
            device_id: The device performing the resolution.
            interface_name: Which of its interfaces to resolve from.
            target_ip: The IP address being resolved.

        Returns:
            An :class:`ArpResolution` on success, or ``None`` if
            nothing on the reachable segment holds ``target_ip``.
        """
        cache = self.arp_cache_for(device_id)
        found = self._find_l2_owner(device_id, interface_name, target_ip)

        if found is None:
            cache.remove(target_ip)
            return None

        peer_device_id, peer_interface_name = found
        peer_device = self.topology.get_device(peer_device_id)
        peer_iface = peer_device.get_interface(peer_interface_name)

        cache.learn(target_ip, peer_iface.mac_address)

        requester_device = self.topology.get_device(device_id)
        requester_iface = requester_device.get_interface(interface_name)
        if requester_iface.ipv4_address is not None:
            self.arp_cache_for(peer_device_id).learn(
                requester_iface.ipv4_address, requester_iface.mac_address
            )

        return ArpResolution(
            mac_address=peer_iface.mac_address,
            peer_device_id=peer_device_id,
            peer_interface_name=peer_interface_name,
        )

    def _find_l2_owner(
        self, device_id: str, interface_name: str, target_ip: str
    ) -> tuple[str, str] | None:
        """Find the (device_id, interface_name) of whichever L2-reachable
        interface currently holds ``target_ip`` and is administratively up.

        Uses :meth:`~netsim.network.topology.Topology.l2_broadcast`
        rather than the plain reachability query - this models an
        actual ARP request being sent, not just a hypothetical "who
        could answer" check, so every switch along the way genuinely
        learns the requester's MAC address as a real side effect.

        Deliberately does not check the owning device's power state
        here - an offline destination is reported as a distinct,
        more specific failure (`DESTINATION_UNREACHABLE`) by
        :meth:`ping` rather than folded into ARP failure.
        """
        requester_device = self.topology.get_device(device_id)
        requester_mac = requester_device.get_interface(interface_name).mac_address

        for peer_device_id, peer_interface_name in self.topology.l2_broadcast(
            device_id, interface_name, requester_mac
        ):
            peer_device = self.topology.get_device(peer_device_id)
            peer_iface = peer_device.get_interface(peer_interface_name)
            if peer_iface.admin_up and peer_iface.ipv4_address == target_ip:
                return (peer_device_id, peer_interface_name)
        return None

    def forget_rip_routes(self, device_id: str) -> None:
        """Discard a router's RIP-learned routes (e.g. on device reload).

        Dynamic protocol state, not configuration - real hardware
        loses this on reboot, exactly like its ARP cache. Nothing
        calls this automatically: :class:`~netsim.devices.base.Device`
        has no visibility into this engine and never should (see the
        project's layering - Device must stay completely independent
        of NetworkEngine). Whatever orchestrates "reload a device that
        happens to have a network engine attached" (the CLI's
        ``reload`` command) calls this explicitly, alongside
        :meth:`~netsim.devices.base.Device.reload`, exactly the same
        way ``ping``/``show ip route`` already reach both a device and
        this engine together at the CLI integration layer.

        Args:
            device_id: Which router's learned table to clear.
        """
        self._rip_engine.forget(device_id)

    def converge_rip(self, max_rounds: int = 16) -> int:
        """Explicitly run RIP distance-vector convergence.

        No wall-clock timers anywhere in this simulator - see
        :mod:`netsim.network.rip` for why this is a deterministic,
        bounded-round algorithm you call once rather than a background
        process. Routes learned become visible to :meth:`routing_table`
        and :meth:`ping` immediately; nothing here is cached beyond
        that point, so call this again after any RIP configuration or
        topology change to reconverge.

        Args:
            max_rounds: Safety cap on convergence rounds.

        Returns:
            The number of rounds actually run.
        """
        return self._rip_engine.converge(max_rounds=max_rounds)

    def routing_table(self, device_id: str) -> RoutingTable:
        """Build a fresh routing table reflecting a device's current
        configuration, including any RIP-learned routes from the last
        :meth:`converge_rip` call."""
        device = self.topology.get_device(device_id)
        return build_routing_table(device, rip_routes=self._rip_engine.routes_for(device_id))

    def ping(self, source_device_id: str, destination_ip: str) -> PingResult:
        """Simulate an ICMP echo request and its return echo reply.

        Both directions traverse the same live routing, link, ARP and ACL
        checks. This matters for asymmetric routes and standard source-based
        ACLs: a request can reach the destination while its reply is blocked
        or has no route back to the originating source address.

        Raises:
            ValidationError: If ``destination_ip`` is not a valid IPv4 address.

        Returns:
            A :class:`PingResult` indicating whether the echo reply reached
            the original source device, or the specific failure encountered.
        """
        destination = str(parse_ipv4_address(destination_ip))
        request, destination_device_id, packet_source_ip = self._forward_packet(
            source_device_id,
            destination,
        )
        if not request.success:
            return request

        if destination_device_id is None or packet_source_ip is None:
            return PingResult(
                success=False,
                destination=destination,
                reason=PingFailureReason.DESTINATION_UNREACHABLE,
                detail="% Unable to determine the source IPv4 address for the echo reply",
            )

        reply, _reply_device_id, _reply_source_ip = self._forward_packet(
            destination_device_id,
            packet_source_ip,
            source_ip_override=destination,
            expected_destination_device_id=source_device_id,
        )
        if not reply.success:
            return PingResult(
                success=False,
                destination=destination,
                reason=reply.reason,
                detail=reply.detail,
            )

        return PingResult(
            success=True,
            destination=destination,
            detail=f"Reply from {destination}: bytes=32 time<1ms",
        )

    def _forward_packet(
        self,
        source_device_id: str,
        destination_ip: str,
        *,
        source_ip_override: str | None = None,
        expected_destination_device_id: str | None = None,
    ) -> tuple[PingResult, str | None, str | None]:
        """Forward one IPv4 packet through the simulated network.

        ``source_ip_override`` is used for the echo reply, whose source is the
        address that was pinged. If omitted, the source is selected from the
        first outgoing interface, then held constant through the routed path.

        The returned device ID is the device that answered ARP for the final
        destination. When ``expected_destination_device_id`` is supplied, the
        packet is only considered delivered if that exact device owns/resolves
        the destination address; this avoids treating duplicate-IP ARP answers
        as a successful reply to the wrong host.
        """
        current_device_id = source_device_id
        visited: set[str] = set()
        packet_source_ip = source_ip_override

        for _ in range(_MAX_HOPS):
            if current_device_id in visited:
                return (
                    PingResult(
                        success=False,
                        destination=destination_ip,
                        reason=PingFailureReason.NO_ROUTE,
                        detail="% Routing loop detected",
                    ),
                    None,
                    packet_source_ip,
                )
            visited.add(current_device_id)

            current_device = self.topology.get_device(current_device_id)

            if not _is_ready(current_device):
                reason = (
                    PingFailureReason.HOST_OFFLINE
                    if current_device_id == source_device_id
                    else PingFailureReason.DESTINATION_UNREACHABLE
                )
                return (
                    PingResult(
                        success=False,
                        destination=destination_ip,
                        reason=reason,
                        detail=f"% {current_device.hostname} is not powered on",
                    ),
                    None,
                    packet_source_ip,
                )

            table = build_routing_table(
                current_device,
                rip_routes=self._rip_engine.routes_for(current_device_id),
            )
            route = table.lookup(destination_ip)
            if route is None:
                return (
                    PingResult(
                        success=False,
                        destination=destination_ip,
                        reason=PingFailureReason.NO_ROUTE,
                        detail=f"% No route to {destination_ip} from {current_device.hostname}",
                    ),
                    None,
                    packet_source_ip,
                )

            hop = self._resolve_next_hop(current_device, table, route, destination_ip)
            if isinstance(hop, PingResult):
                return hop, None, packet_source_ip
            outgoing_interface_name, arp_target_ip, is_final_hop = hop

            outgoing_iface = current_device.get_interface(outgoing_interface_name)
            if not outgoing_iface.admin_up:
                return (
                    PingResult(
                        success=False,
                        destination=destination_ip,
                        reason=PingFailureReason.INTERFACE_DOWN,
                        detail=f"% Interface {outgoing_interface_name} on {current_device.hostname} is down",
                    ),
                    None,
                    packet_source_ip,
                )

            link = self.topology.get_link(current_device_id, outgoing_interface_name)
            if link is None or not link.up:
                return (
                    PingResult(
                        success=False,
                        destination=destination_ip,
                        reason=PingFailureReason.LINK_DOWN,
                        detail=f"% Link down on {current_device.hostname} {outgoing_interface_name}",
                    ),
                    None,
                    packet_source_ip,
                )

            if packet_source_ip is None:
                packet_source_ip = outgoing_iface.ipv4_address

            if packet_source_ip is not None and not self._acl_permits(
                current_device, outgoing_interface_name, "out", packet_source_ip
            ):
                return (
                    PingResult(
                        success=False,
                        destination=destination_ip,
                        reason=PingFailureReason.ACL_DENIED,
                        detail=(
                            f"% Denied by outbound access list on {current_device.hostname} "
                            f"{outgoing_interface_name}"
                        ),
                    ),
                    None,
                    packet_source_ip,
                )

            resolution = self.resolve_arp(current_device_id, outgoing_interface_name, arp_target_ip)
            if resolution is None:
                return (
                    PingResult(
                        success=False,
                        destination=destination_ip,
                        reason=PingFailureReason.ARP_UNRESOLVED,
                        detail=f"% Unable to resolve MAC address for {arp_target_ip}",
                    ),
                    None,
                    packet_source_ip,
                )

            self.topology.l2_forward(
                current_device_id,
                outgoing_interface_name,
                outgoing_iface.mac_address,
                resolution.mac_address,
            )

            receiving_device = self.topology.get_device(resolution.peer_device_id)
            if packet_source_ip is not None and not self._acl_permits(
                receiving_device,
                resolution.peer_interface_name,
                "in",
                packet_source_ip,
            ):
                return (
                    PingResult(
                        success=False,
                        destination=destination_ip,
                        reason=PingFailureReason.ACL_DENIED,
                        detail=(
                            f"% Denied by inbound access list on {receiving_device.hostname} "
                            f"{resolution.peer_interface_name}"
                        ),
                    ),
                    None,
                    packet_source_ip,
                )

            if is_final_hop:
                if not _is_ready(receiving_device):
                    return (
                        PingResult(
                            success=False,
                            destination=destination_ip,
                            reason=PingFailureReason.DESTINATION_UNREACHABLE,
                            detail=f"% {receiving_device.hostname} is not powered on",
                        ),
                        None,
                        packet_source_ip,
                    )
                if (
                    expected_destination_device_id is not None
                    and resolution.peer_device_id != expected_destination_device_id
                ):
                    return (
                        PingResult(
                            success=False,
                            destination=destination_ip,
                            reason=PingFailureReason.DESTINATION_UNREACHABLE,
                            detail=(
                                f"% Address {destination_ip} resolved to {receiving_device.hostname}, "
                                "not the expected destination device"
                            ),
                        ),
                        None,
                        packet_source_ip,
                    )
                return (
                    PingResult(
                        success=True,
                        destination=destination_ip,
                        detail=f"Reply from {destination_ip}: bytes=32 time<1ms",
                    ),
                    resolution.peer_device_id,
                    packet_source_ip,
                )

            current_device_id = resolution.peer_device_id

        return (
            PingResult(
                success=False,
                destination=destination_ip,
                reason=PingFailureReason.NO_ROUTE,
                detail="% TTL exceeded - too many hops",
            ),
            None,
            packet_source_ip,
        )

    @staticmethod
    def _acl_permits(
        device: Device, interface_name: str, direction: Literal["in", "out"], source_ip: str
    ) -> bool:
        """Whether traffic from ``source_ip`` is permitted across
        ``interface_name`` in ``direction`` on ``device``.

        Only :class:`~netsim.devices.router.Router` has access control
        lists in this project (see ``devices/acl.py``) - any other
        device type (Host, Switch) has nothing to check, so this
        always permits for them, exactly like the VLAN/static-routing
        capability checks elsewhere in this codebase.

        Args:
            device: The device whose interface to check.
            interface_name: Which interface.
            direction: ``"in"`` or ``"out"``.
            source_ip: The packet's real source address.

        Returns:
            ``True`` if permitted (or no ACL applies at all).
        """
        if not isinstance(device, Router):
            return True
        acl = device.get_interface_acl(interface_name, direction)
        if acl is None:
            return True
        return acl.evaluate(source_ip)

    def _resolve_next_hop(
        self, device: Device, table: RoutingTable, route: Route, destination_ip: str
    ) -> tuple[str, str, bool] | PingResult:
        """Determine (outgoing interface, IP to ARP for, is-this-the-final-hop) for a matched route.

        For a directly connected route, that's simply the
        destination itself. For a route with a next hop, the next hop
        address must itself be recursively reachable via one of this
        device's *connected* routes - real routers require this too
        (you can't point a static route at an address you have no way
        to actually reach).
        """
        if route.next_hop is None:
            return (route.interface_name, destination_ip, True)

        next_hop_route = table.lookup(route.next_hop)
        if next_hop_route is None or next_hop_route.next_hop is not None:
            return PingResult(
                success=False,
                destination=destination_ip,
                reason=PingFailureReason.NO_ROUTE,
                detail=f"% Next hop {route.next_hop} is unreachable from {device.hostname}",
            )
        return (next_hop_route.interface_name, str(route.next_hop), False)

    def format_arp_table(self, device_id: str) -> list[str]:
        """Render a device's ARP cache as IOS-style ``show arp`` text.

        Args:
            device_id: Which device's ARP cache to render.

        Returns:
            One line per entry (empty list if the cache is empty).
        """
        entries = self.arp_table(device_id)
        header = f"{'Protocol':<10}{'Address':<18}{'Hardware Addr':<20}"
        if not entries:
            return [header]
        lines = [header]
        for ip_address, mac_address in sorted(entries.items()):
            lines.append(f"{'Internet':<10}{ip_address:<18}{mac_address:<20}")
        return lines

    def format_routing_table(self, device_id: str) -> list[str]:
        """Render a device's routing table as IOS-style ``show ip route`` text.

        Args:
            device_id: Which device's routing table to render.

        Returns:
            One line per route (plus a legend line), reflecting live
            device configuration and RIP-learned state (as of the
            last :meth:`converge_rip` call) at the time of the call.
        """
        table = self.routing_table(device_id)
        lines = ["Codes: C - connected, S - static, R - RIP"]
        source_codes = {"CONNECTED": "C", "STATIC": "S", "DEFAULT": "S*", "RIP": "R"}
        for route in table.routes():
            code = source_codes.get(route.source.name, "?")
            if route.next_hop is None:
                lines.append(f"{code}    {route.network} is directly connected, {route.interface_name}")
            else:
                distance = ADMINISTRATIVE_DISTANCE.get(route.source, 0)
                lines.append(f"{code}    {route.network} [{distance}/{route.metric}] via {route.next_hop}")
        return lines
