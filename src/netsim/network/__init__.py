"""Network simulation engine: topology, links, protocols, routing.

Layering: :mod:`~netsim.network.link` and :mod:`~netsim.network.topology`
model the physical/L2 shape of a network, independent of any protocol.
:mod:`~netsim.network.ethernet`, :mod:`~netsim.network.ipv4`,
:mod:`~netsim.network.arp`, and :mod:`~netsim.network.icmp` are the
packet-layer dataclasses. :mod:`~netsim.network.routing` builds a
:class:`~netsim.network.routing.RoutingTable` from real device state
(never duplicating :meth:`Router.connected_interfaces()
<netsim.devices.router.Router.connected_interfaces>`).
:mod:`~netsim.network.engine` is the facade tying all of it together
into :meth:`NetworkEngine.ping`.

This package freely imports concrete device classes from
:mod:`netsim.devices` (per the project's layering: the network engine
consumes device models). Nothing in :mod:`netsim.devices` imports this
package. Nothing in :mod:`netsim.cli` imports this package either -
the boundary is :mod:`netsim.cli.network_interface`'s ``NetworkContext``
protocol, structurally satisfied by :class:`NetworkEngine` without any
import in either direction.
"""

from netsim.network.arp import ArpCache, ArpMessage, ArpOperation
from netsim.network.engine import ArpResolution, NetworkEngine
from netsim.network.errors import (
    DeviceNotInTopologyError,
    InterfaceAlreadyConnectedError,
    InterfaceNotInTopologyError,
    LinkNotFoundError,
    SelfConnectionError,
)
from netsim.network.ethernet import ETHERTYPE_ARP, ETHERTYPE_IPV4, EthernetFrame
from netsim.network.icmp import IcmpMessage, IcmpType, PingFailureReason, PingResult
from netsim.network.ipv4 import IPV4_PROTOCOL_ICMP, IPv4Packet
from netsim.network.link import Endpoint, Link
from netsim.network.routing import Route, RoutingTable, RouteSource, build_routing_table
from netsim.network.topology import Topology

__all__ = [
    "ArpCache",
    "ArpMessage",
    "ArpOperation",
    "ArpResolution",
    "NetworkEngine",
    "DeviceNotInTopologyError",
    "InterfaceAlreadyConnectedError",
    "InterfaceNotInTopologyError",
    "LinkNotFoundError",
    "SelfConnectionError",
    "ETHERTYPE_ARP",
    "ETHERTYPE_IPV4",
    "EthernetFrame",
    "IcmpMessage",
    "IcmpType",
    "PingFailureReason",
    "PingResult",
    "IPV4_PROTOCOL_ICMP",
    "IPv4Packet",
    "Endpoint",
    "Link",
    "Route",
    "RoutingTable",
    "RouteSource",
    "build_routing_table",
    "Topology",
]
