"""The network topology model.

This is the "separate topology/lab API" the project brief asks for:
completely independent of :mod:`netsim.cli` (nothing here imports it,
and nothing in it is aware a CLI exists) so a future GUI or lab-loading
system can build and inspect topologies exactly the way
:mod:`netsim.network.engine` does. It *does* import real device
classes from :mod:`netsim.devices` directly - per the project's layer
diagram, the network engine consumes device models, rather than
devices depending on it.

A :class:`Topology` owns two things: which devices exist (keyed by
their own :attr:`~netsim.devices.base.Device.device_id`, never
duplicated), and which interfaces are linked to which. It validates
every connection against the rules the brief calls out explicitly
(nonexistent device/interface, self-connection, duplicate connection).

Three L2 queries build on one shared traversal core
(:meth:`Topology._traverse`):

- :meth:`l2_reachable_peers` - "who can this interface reach" (used by
  ARP), VLAN-scoped flooding, no side effects.
- :meth:`l2_broadcast` - the same flood, but as an explicit broadcast
  primitive that also causes real MAC learning on every switch it
  crosses - matching how a real broadcast frame (like an ARP request)
  actually teaches switches where the sender lives.
- :meth:`l2_forward` - a single addressed (unicast) frame: uses a
  switch's MAC table for directed, single-port delivery once the
  destination is known, falling back to flooding only while it isn't.

All three understand access *and* trunk switchports: an access port
belongs to exactly one VLAN; a trunk port carries every VLAN in its
allow-list, preserving whichever VLAN a frame is already carrying
across the hop (no byte-level 802.1Q tagging is modeled - the VLAN is
tracked as traversal state instead). A Router is always a
reachability *endpoint*; only a :class:`~netsim.devices.switch.Switch`
is ever traversed *through*.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from netsim.devices.base import Device
from netsim.devices.interface import Interface
from netsim.devices.switch import Switch
from netsim.network.errors import (
    DeviceAlreadyInTopologyError,
    DeviceNotInTopologyError,
    InterfaceAlreadyConnectedError,
    InterfaceNotInTopologyError,
    SelfConnectionError,
)
from netsim.network.link import Endpoint, Link


class Topology:
    """A collection of devices and the links between their interfaces."""

    def __init__(self) -> None:
        self._devices: dict[str, Device] = {}
        self._links: list[Link] = []

    def add_device(self, device: Device) -> None:
        """Register a device with this topology.

        Args:
            device: The device to add, keyed by its own ``device_id``.

        Raises:
            ValueError: If this exact device ID is already registered.
        """
        if device.device_id in self._devices:
            raise DeviceAlreadyInTopologyError(device.device_id)
        self._devices[device.device_id] = device

    def remove_device(self, device_id: str) -> Device:
        """Remove a device and every link attached to it.

        Returns the removed device. Dynamic caches are owned by
        :class:`~netsim.network.engine.NetworkEngine`, so callers that
        mutate a live topology should invalidate or recreate that engine.
        """
        device = self.get_device(device_id)
        self._links = [
            link
            for link in self._links
            if link.endpoint_a.device_id != device_id and link.endpoint_b.device_id != device_id
        ]
        del self._devices[device_id]
        return device

    def get_device(self, device_id: str) -> Device:
        """Look up a device by ID.

        Raises:
            DeviceNotInTopologyError: If no device with that ID was added.
        """
        try:
            return self._devices[device_id]
        except KeyError:
            raise DeviceNotInTopologyError(device_id) from None

    def devices(self) -> Mapping[str, Device]:
        """Read-only view of every registered device, keyed by device ID."""
        return MappingProxyType(self._devices)

    def connect(
        self,
        device_a_id: str,
        interface_a_name: str,
        device_b_id: str,
        interface_b_name: str,
    ) -> Link:
        """Create a link between two interfaces.

        Args:
            device_a_id: Device ID of the first endpoint.
            interface_a_name: Interface name on the first device.
            device_b_id: Device ID of the second endpoint.
            interface_b_name: Interface name on the second device.

        Returns:
            The newly created (initially up) :class:`Link`.

        Raises:
            DeviceNotInTopologyError: If either device isn't registered.
            InterfaceNotInTopologyError: If either interface doesn't
                exist on its device.
            SelfConnectionError: If both endpoints name the exact same
                device+interface.
            InterfaceAlreadyConnectedError: If either interface already
                has a link.
        """
        self._require_interface(device_a_id, interface_a_name)
        self._require_interface(device_b_id, interface_b_name)

        endpoint_a = Endpoint(device_a_id, interface_a_name)
        endpoint_b = Endpoint(device_b_id, interface_b_name)

        if endpoint_a == endpoint_b:
            raise SelfConnectionError(device_a_id, interface_a_name)

        if self.get_link(device_a_id, interface_a_name) is not None:
            raise InterfaceAlreadyConnectedError(device_a_id, interface_a_name)
        if self.get_link(device_b_id, interface_b_name) is not None:
            raise InterfaceAlreadyConnectedError(device_b_id, interface_b_name)

        link = Link(endpoint_a=endpoint_a, endpoint_b=endpoint_b)
        self._links.append(link)
        return link

    def disconnect(self, device_id: str, interface_name: str) -> None:
        """Remove the link attached to an interface, if any (a no-op if none exists)."""
        self._links = [link for link in self._links if not link.involves(device_id, interface_name)]

    def get_link(self, device_id: str, interface_name: str) -> Link | None:
        """Find the link attached to an interface, or None if unconnected."""
        for link in self._links:
            if link.involves(device_id, interface_name):
                return link
        return None

    def links(self) -> list[Link]:
        """Every link currently in the topology."""
        return list(self._links)

    def _require_interface(self, device_id: str, interface_name: str) -> None:
        """Raise if the device or interface doesn't exist."""
        device = self.get_device(device_id)
        if interface_name not in device.interfaces:
            raise InterfaceNotInTopologyError(device_id, interface_name)

    def l2_reachable_peers(self, device_id: str, interface_name: str) -> list[tuple[str, str]]:
        """Every other real endpoint reachable at Layer 2 from an interface.

        VLAN-scoped flooding through any switches encountered (access
        *and* trunk ports both understood - see the module docstring),
        with no side effects on any switch's MAC table. This is the
        "who could possibly answer" search ARP resolution uses; use
        :meth:`l2_broadcast` instead when the flood should also cause
        real learning (i.e. it represents an actual frame being sent,
        not just a reachability query).

        Args:
            device_id: Starting device ID.
            interface_name: Starting interface name.

        Returns:
            ``(device_id, interface_name)`` pairs for every reachable
            non-switch interface, without duplicates.
        """
        return [
            (endpoint.device_id, endpoint.interface_name)
            for endpoint in self._traverse(device_id, interface_name, learn_source_mac=None, destination_mac=None)
        ]

    def l2_broadcast(self, device_id: str, interface_name: str, source_mac: str) -> list[tuple[str, str]]:
        """Simulate sending a broadcast frame (e.g. an ARP request).

        Same VLAN-scoped flood as :meth:`l2_reachable_peers`, but -
        matching how a real broadcast frame behaves - every switch it
        passes through learns ``source_mac`` on its arrival port, a
        real, observable side effect on that switch's
        :attr:`~netsim.devices.switch.Switch.mac_table`.

        Args:
            device_id: Sending device ID.
            interface_name: Sending interface name.
            source_mac: MAC address of the sender, learned along the way.

        Returns:
            ``(device_id, interface_name)`` pairs for every endpoint
            the broadcast reaches.
        """
        return [
            (endpoint.device_id, endpoint.interface_name)
            for endpoint in self._traverse(device_id, interface_name, learn_source_mac=source_mac, destination_mac=None)
        ]

    def l2_forward(
        self, device_id: str, interface_name: str, source_mac: str, destination_mac: str
    ) -> tuple[str, str] | None:
        """Simulate sending one unicast frame toward ``destination_mac``.

        Every :class:`~netsim.devices.switch.Switch` it passes through
        learns ``source_mac`` on its arrival port. If a switch already
        has a MAC-table entry for ``destination_mac`` that is still
        valid for the frame's current VLAN (see the module docstring),
        the frame goes *only* there; if that entry exists but is no
        longer usable (its port is down, unplugged, or now in a
        different VLAN), delivery fails outright rather than silently
        flooding - exactly like a real switch black-holing traffic to
        a stale MAC-table entry. Flooding only happens when there is
        no entry for ``destination_mac`` at all yet.

        Args:
            device_id: Sending device ID.
            interface_name: Sending interface name.
            source_mac: MAC address of the sender (learned along the way).
            destination_mac: MAC address being forwarded toward.

        Returns:
            ``(device_id, interface_name)`` of the interface holding
            ``destination_mac``, or ``None`` if unreachable.
        """
        matches = self._traverse(
            device_id, interface_name, learn_source_mac=source_mac, destination_mac=destination_mac
        )
        if not matches:
            return None
        endpoint = matches[0]
        return (endpoint.device_id, endpoint.interface_name)

    def _traverse(
        self,
        device_id: str,
        interface_name: str,
        *,
        learn_source_mac: str | None,
        destination_mac: str | None,
    ) -> list[Endpoint]:
        """The one BFS every L2 query above is built on.

        Args:
            device_id: Starting device ID.
            interface_name: Starting interface name.
            learn_source_mac: If given, every switch traversed learns
                this MAC on its arrival port (broadcast/unicast
                sends); ``None`` for a pure reachability query with no
                side effects.
            destination_mac: If given, only endpoints whose interface
                holds this exact MAC are returned, and switches use
                MAC-table-directed single-port delivery when they
                already know where it is; ``None`` floods everywhere
                and returns every endpoint reached (broadcast/reachability).

        Returns:
            Matching endpoints - every reachable one when
            ``destination_mac`` is ``None``, at most one otherwise.
        """
        origin_link = self.get_link(device_id, interface_name)
        if origin_link is None or not origin_link.up:
            return []

        origin = Endpoint(device_id, interface_name)
        visited: set[Endpoint] = {origin}

        frontier: list[tuple[Endpoint, int | None]] = [(origin_link.other_end(origin), None)]
        reached: list[Endpoint] = []

        while frontier:
            current, vlan = frontier.pop()
            if current in visited:
                continue
            visited.add(current)

            device = self._devices.get(current.device_id)
            if device is None:
                continue

            if isinstance(device, Switch):
                result = self._cross_switch(device, current, vlan, learn_source_mac, destination_mac, visited)
                if result is not None:
                    frontier.extend(result)
            elif destination_mac is None or device.get_interface(current.interface_name).mac_address == destination_mac:
                reached.append(current)

        return reached

    def _cross_switch(
        self,
        switch: Switch,
        arrival: Endpoint,
        vlan: int | None,
        learn_source_mac: str | None,
        destination_mac: str | None,
        visited: set[Endpoint],
    ) -> list[tuple[Endpoint, int]] | None:
        """Process a frame arriving at one switch port, returning the
        next hop(s) (with the VLAN each carries), or None/[] if it
        can't proceed from here."""
        arriving_iface = switch.get_interface(arrival.interface_name)
        if not arriving_iface.admin_up:
            return []
        current_vlan = self._resolve_arrival_vlan(arriving_iface, vlan)
        if current_vlan is None:
            return []

        if learn_source_mac is not None:
            switch.learn_mac(learn_source_mac, arrival.interface_name)

        if destination_mac is not None:
            known_port = switch.mac_table.get(destination_mac)
            if known_port is not None and known_port != arrival.interface_name:

                far_end = self._resolve_known_port(switch, known_port, current_vlan, visited)
                return [(far_end, current_vlan)] if far_end is not None else []

        return [
            (endpoint, current_vlan)
            for endpoint in self._flood_candidates(switch, arrival, current_vlan, visited)
        ]

    @staticmethod
    def _resolve_arrival_vlan(arriving_iface: Interface, inherited_vlan: int | None) -> int | None:
        """Which VLAN a frame arriving on this port belongs to, or
        None if that can't be determined (port has no switchport
        config, or it's a trunk port with no VLAN carried into it)."""
        switchport = arriving_iface.switchport
        if switchport is None:
            return None
        if switchport.mode == "access":
            return switchport.access_vlan
        if switchport.mode == "trunk":
            if inherited_vlan is None or inherited_vlan not in switchport.trunk_allowed_vlans:
                return None
            return inherited_vlan
        return None

    def _resolve_known_port(
        self, switch: Switch, known_port: str, vlan: int, visited: set[Endpoint]
    ) -> Endpoint | None:
        """The far endpoint of a switch's MAC-table-directed egress
        port, or None if that entry isn't currently usable (down,
        unplugged, or no longer valid for this VLAN)."""
        known_iface = switch.get_interface(known_port)
        if not self._port_permits_vlan(known_iface, vlan):
            return None
        sibling_link = self.get_link(switch.device_id, known_port)
        if sibling_link is None or not sibling_link.up:
            return None
        far_end = sibling_link.other_end(Endpoint(switch.device_id, known_port))
        return None if far_end in visited else far_end

    def _flood_candidates(
        self, switch: Switch, arrival: Endpoint, vlan: int, visited: set[Endpoint]
    ) -> list[Endpoint]:
        """Every up, VLAN-permitted port on this switch except the
        arrival port - never forwards a frame back out where it came from."""
        candidates: list[Endpoint] = []
        for other_name, other_iface in switch.interfaces.items():
            if other_name == arrival.interface_name:
                continue
            if not other_iface.admin_up or not self._port_permits_vlan(other_iface, vlan):
                continue

            sibling_link = self.get_link(switch.device_id, other_name)
            if sibling_link is None or not sibling_link.up:
                continue

            far_end = sibling_link.other_end(Endpoint(switch.device_id, other_name))
            if far_end not in visited:
                candidates.append(far_end)
        return candidates

    @staticmethod
    def _port_permits_vlan(iface: Interface, vlan: int) -> bool:
        """Whether this switchport would carry traffic for ``vlan``:
        an access port only carries its own VLAN; a trunk port carries
        every VLAN in its allow-list."""
        switchport = iface.switchport
        if switchport is None:
            return False
        if switchport.mode == "access":
            return switchport.access_vlan == vlan
        if switchport.mode == "trunk":
            return vlan in switchport.trunk_allowed_vlans
        return False
