"""Tests for the Stage 4 additions to netsim.devices.router.Router.

test_router.py (Stage 3) is untouched and still covers
connected_networks() itself - these tests cover the new
connected_interfaces() method it's now implemented in terms of, plus
static route storage.
"""

from __future__ import annotations

import unittest

from netsim.core.exceptions import ValidationError
from netsim.devices.router import Router


class TestConnectedInterfaces(unittest.TestCase):
    def test_pairs_interface_name_with_its_network(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")
        router.get_interface("GigabitEthernet0/0").set_admin_up(True)

        pairs = router.connected_interfaces()

        self.assertEqual(len(pairs), 1)
        name, network = pairs[0]
        self.assertEqual(name, "GigabitEthernet0/0")
        self.assertEqual(str(network), "10.0.0.0/24")

    def test_connected_networks_is_a_view_over_connected_interfaces(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")
        router.get_interface("GigabitEthernet0/0").set_admin_up(True)

        self.assertEqual(
            router.connected_networks(),
            [network for _, network in router.connected_interfaces()],
        )

    def test_excludes_shutdown_interfaces(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")
        self.assertEqual(router.connected_interfaces(), [])


class TestStaticRoutes(unittest.TestCase):
    def test_starts_with_no_static_routes(self) -> None:
        router = Router()
        self.assertEqual(dict(router.static_routes), {})

    def test_add_static_route(self) -> None:
        router = Router()
        router.add_static_route("192.168.2.0", "255.255.255.0", "10.0.0.2")

        routes = router.static_routes
        self.assertIn("192.168.2.0/24", routes)
        route = routes["192.168.2.0/24"]
        self.assertEqual(str(route.network), "192.168.2.0/24")
        self.assertEqual(str(route.next_hop), "10.0.0.2")

    def test_add_static_route_rejects_malformed_next_hop(self) -> None:
        router = Router()
        with self.assertRaises(ValidationError):
            router.add_static_route("192.168.2.0", "255.255.255.0", "999.1.1.1")

    def test_add_static_route_rejects_malformed_mask(self) -> None:
        router = Router()
        with self.assertRaises(ValidationError):
            router.add_static_route("192.168.2.0", "not-a-mask", "10.0.0.2")

    def test_re_adding_same_network_replaces_it(self) -> None:
        router = Router()
        router.add_static_route("192.168.2.0", "255.255.255.0", "10.0.0.2")
        router.add_static_route("192.168.2.0", "255.255.255.0", "10.0.0.9")

        self.assertEqual(len(router.static_routes), 1)
        self.assertEqual(str(router.static_routes["192.168.2.0/24"].next_hop), "10.0.0.9")

    def test_remove_static_route(self) -> None:
        router = Router()
        router.add_static_route("192.168.2.0", "255.255.255.0", "10.0.0.2")
        router.remove_static_route("192.168.2.0", "255.255.255.0")
        self.assertEqual(dict(router.static_routes), {})

    def test_static_routes_property_is_read_only(self) -> None:
        router = Router()
        with self.assertRaises(TypeError):
            router.static_routes["x"] = None

if __name__ == "__main__":
    unittest.main()
