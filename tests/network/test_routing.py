"""Tests for netsim.network.routing."""

from __future__ import annotations

import ipaddress
import unittest

from netsim.devices.host import Host
from netsim.devices.router import Router
from netsim.network.routing import Route, RouteSource, RoutingTable, build_routing_table


def _network(cidr: str) -> ipaddress.IPv4Network:
    return ipaddress.ip_network(cidr)


class TestRoutingTableLookup(unittest.TestCase):
    def test_empty_table_has_no_route(self) -> None:
        table = RoutingTable()
        self.assertIsNone(table.lookup("10.0.0.1"))

    def test_finds_matching_route(self) -> None:
        table = RoutingTable()
        table.add_route(
            Route(network=_network("10.0.0.0/24"), interface_name="Gi0/0", next_hop=None, source=RouteSource.CONNECTED)
        )
        route = table.lookup("10.0.0.5")
        self.assertIsNotNone(route)
        assert route is not None
        self.assertEqual(route.interface_name, "Gi0/0")

    def test_no_match_returns_none(self) -> None:
        table = RoutingTable()
        table.add_route(
            Route(network=_network("10.0.0.0/24"), interface_name="Gi0/0", next_hop=None, source=RouteSource.CONNECTED)
        )
        self.assertIsNone(table.lookup("192.168.1.1"))

    def test_longest_prefix_match_wins(self) -> None:
        table = RoutingTable()
        table.add_route(
            Route(network=_network("10.0.0.0/8"), interface_name="Gi0/0", next_hop="10.0.0.254", source=RouteSource.STATIC)
        )
        table.add_route(
            Route(network=_network("10.0.0.0/24"), interface_name="Gi0/1", next_hop=None, source=RouteSource.CONNECTED)
        )
        route = table.lookup("10.0.0.5")
        assert route is not None
        self.assertEqual(route.interface_name, "Gi0/1")

    def test_default_route_matches_anything_when_nothing_more_specific(self) -> None:
        table = RoutingTable()
        table.add_route(
            Route(network=_network("0.0.0.0/0"), interface_name="Eth0", next_hop="10.0.0.1", source=RouteSource.DEFAULT)
        )
        route = table.lookup("8.8.8.8")
        assert route is not None
        self.assertEqual(route.source, RouteSource.DEFAULT)

    def test_routes_view_returns_everything_added(self) -> None:
        table = RoutingTable()
        route = Route(network=_network("10.0.0.0/24"), interface_name="Gi0/0", next_hop=None, source=RouteSource.CONNECTED)
        table.add_route(route)
        self.assertEqual(table.routes(), [route])


class TestBuildRoutingTableForRouter(unittest.TestCase):
    def test_includes_connected_routes(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")
        router.get_interface("GigabitEthernet0/0").set_admin_up(True)

        table = build_routing_table(router)
        route = table.lookup("10.0.0.5")

        assert route is not None
        self.assertEqual(route.source, RouteSource.CONNECTED)
        self.assertEqual(route.interface_name, "GigabitEthernet0/0")
        self.assertIsNone(route.next_hop)

    def test_includes_static_routes(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")
        router.get_interface("GigabitEthernet0/0").set_admin_up(True)
        router.add_static_route("192.168.2.0", "255.255.255.0", "10.0.0.2")

        table = build_routing_table(router)
        route = table.lookup("192.168.2.5")

        assert route is not None
        self.assertEqual(route.source, RouteSource.STATIC)
        self.assertEqual(str(route.next_hop), "10.0.0.2")

    def test_shutdown_interface_contributes_no_connected_route(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")

        table = build_routing_table(router)
        self.assertIsNone(table.lookup("10.0.0.5"))


class TestBuildRoutingTableForHost(unittest.TestCase):
    def test_includes_own_connected_network(self) -> None:
        host = Host()
        interface_name = next(iter(host.interfaces))
        host.configure_ipv4(interface_name, "192.168.1.10", "255.255.255.0")
        host.get_interface(interface_name).set_admin_up(True)

        table = build_routing_table(host)
        route = table.lookup("192.168.1.20")

        assert route is not None
        self.assertEqual(route.source, RouteSource.CONNECTED)

    def test_includes_default_gateway_as_default_route(self) -> None:
        host = Host()
        interface_name = next(iter(host.interfaces))
        host.configure_ipv4(interface_name, "192.168.1.10", "255.255.255.0")
        host.get_interface(interface_name).set_admin_up(True)
        host.set_default_gateway("192.168.1.1")

        table = build_routing_table(host)
        route = table.lookup("8.8.8.8")

        assert route is not None
        self.assertEqual(route.source, RouteSource.DEFAULT)
        self.assertEqual(str(route.next_hop), "192.168.1.1")

    def test_no_default_gateway_means_no_route_off_subnet(self) -> None:
        host = Host()
        interface_name = next(iter(host.interfaces))
        host.configure_ipv4(interface_name, "192.168.1.10", "255.255.255.0")
        host.get_interface(interface_name).set_admin_up(True)

        table = build_routing_table(host)
        self.assertIsNone(table.lookup("8.8.8.8"))

    def test_own_subnet_preferred_over_default_route(self) -> None:
        host = Host()
        interface_name = next(iter(host.interfaces))
        host.configure_ipv4(interface_name, "192.168.1.10", "255.255.255.0")
        host.get_interface(interface_name).set_admin_up(True)
        host.set_default_gateway("192.168.1.1")

        table = build_routing_table(host)
        route = table.lookup("192.168.1.20")

        assert route is not None
        self.assertEqual(route.source, RouteSource.CONNECTED)

    def test_default_route_excluded_when_interface_is_down(self) -> None:

        host = Host()
        interface_name = next(iter(host.interfaces))
        host.configure_ipv4(interface_name, "192.168.1.10", "255.255.255.0")
        host.set_default_gateway("192.168.1.1")

        table = build_routing_table(host)
        self.assertIsNone(table.lookup("8.8.8.8"))

if __name__ == "__main__":
    unittest.main()
