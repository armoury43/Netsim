"""Tests for the Stage 6 additions to netsim.network.routing.

test_routing.py (Stage 4) is untouched. This covers: administrative
distance now resolving same-prefix ties between route sources
(needed for RIP to coexist correctly with connected/static routes),
and build_routing_table() accepting externally-supplied RIP routes
without importing anything from the network engine.
"""

from __future__ import annotations

import ipaddress
import unittest

from netsim.devices.router import Router
from netsim.network.routing import ADMINISTRATIVE_DISTANCE, Route, RouteSource, RoutingTable, build_routing_table


def _network(cidr: str) -> ipaddress.IPv4Network:
    return ipaddress.ip_network(cidr)


class TestAdministrativeDistance(unittest.TestCase):
    def test_connected_has_lowest_distance(self) -> None:
        self.assertLess(ADMINISTRATIVE_DISTANCE[RouteSource.CONNECTED], ADMINISTRATIVE_DISTANCE[RouteSource.STATIC])
        self.assertLess(ADMINISTRATIVE_DISTANCE[RouteSource.STATIC], ADMINISTRATIVE_DISTANCE[RouteSource.RIP])


class TestRoutingTableAdministrativeDistanceTieBreak(unittest.TestCase):
    def test_connected_preferred_over_rip_for_identical_prefix(self) -> None:
        table = RoutingTable()
        table.add_route(
            Route(network=_network("10.0.0.0/24"), interface_name="Gi0/0", next_hop=None, source=RouteSource.CONNECTED)
        )
        table.add_route(
            Route(network=_network("10.0.0.0/24"), interface_name=None, next_hop="10.0.0.9", source=RouteSource.RIP, metric=3)
        )
        route = table.lookup("10.0.0.5")
        assert route is not None
        self.assertEqual(route.source, RouteSource.CONNECTED)

    def test_static_preferred_over_rip_for_identical_prefix(self) -> None:
        table = RoutingTable()
        table.add_route(
            Route(network=_network("192.168.5.0/24"), interface_name=None, next_hop="10.0.0.1", source=RouteSource.STATIC)
        )
        table.add_route(
            Route(network=_network("192.168.5.0/24"), interface_name=None, next_hop="10.0.0.9", source=RouteSource.RIP, metric=2)
        )
        route = table.lookup("192.168.5.5")
        assert route is not None
        self.assertEqual(route.source, RouteSource.STATIC)

    def test_longer_prefix_still_wins_regardless_of_source(self) -> None:

        table = RoutingTable()
        table.add_route(
            Route(network=_network("10.0.0.0/8"), interface_name="Gi0/0", next_hop=None, source=RouteSource.CONNECTED)
        )
        table.add_route(
            Route(network=_network("10.0.0.0/24"), interface_name=None, next_hop="10.0.0.9", source=RouteSource.RIP, metric=5)
        )
        route = table.lookup("10.0.0.5")
        assert route is not None
        self.assertEqual(route.source, RouteSource.RIP)


class TestBuildRoutingTableWithRipRoutes(unittest.TestCase):
    def test_rip_routes_are_included_when_supplied(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")
        router.get_interface("GigabitEthernet0/0").set_admin_up(True)

        rip_route = Route(
            network=_network("192.168.5.0/24"), interface_name=None, next_hop="10.0.0.2", source=RouteSource.RIP, metric=2
        )
        table = build_routing_table(router, rip_routes=[rip_route])

        route = table.lookup("192.168.5.5")
        assert route is not None
        self.assertEqual(route.source, RouteSource.RIP)
        self.assertEqual(route.metric, 2)

    def test_omitting_rip_routes_behaves_exactly_as_before(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")
        router.get_interface("GigabitEthernet0/0").set_admin_up(True)

        table = build_routing_table(router)

        self.assertIsNone(table.lookup("192.168.5.5"))

    def test_connected_route_still_wins_over_supplied_rip_route_for_own_subnet(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")
        router.get_interface("GigabitEthernet0/0").set_admin_up(True)

        rip_route = Route(
            network=_network("10.0.0.0/24"), interface_name=None, next_hop="10.0.0.99", source=RouteSource.RIP, metric=1
        )
        table = build_routing_table(router, rip_routes=[rip_route])

        route = table.lookup("10.0.0.5")
        assert route is not None
        self.assertEqual(route.source, RouteSource.CONNECTED)

if __name__ == "__main__":
    unittest.main()
