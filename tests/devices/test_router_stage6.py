"""Tests for the Stage 6 additions to netsim.devices.router.Router.

test_router.py (Stage 3) and test_router_stage4.py (Stage 4) are
untouched. This covers: static routes now correctly participating in
save/reload (closing the gap found while designing Stage 6), and RIP
configuration (network statements, enabled-interface derivation).
"""

from __future__ import annotations

import unittest

from netsim.core.exceptions import ValidationError
from netsim.devices.router import Router


class TestStaticRoutesSurviveSaveAndReload(unittest.TestCase):
    def test_saved_static_route_survives_reload(self) -> None:
        router = Router()
        router.add_static_route("192.168.2.0", "255.255.255.0", "10.0.0.2")
        router.save_config()
        router.remove_static_route("192.168.2.0", "255.255.255.0")

        router.reload()

        self.assertIn("192.168.2.0/24", router.static_routes)

    def test_unsaved_static_route_is_discarded_on_reload(self) -> None:

        router = Router()
        router.save_config()
        router.add_static_route("192.168.2.0", "255.255.255.0", "10.0.0.2")

        router.reload()

        self.assertEqual(dict(router.static_routes), {})

    def test_reload_without_any_save_discards_static_routes(self) -> None:
        router = Router()
        router.add_static_route("192.168.2.0", "255.255.255.0", "10.0.0.2")

        router.reload()

        self.assertEqual(dict(router.static_routes), {})


class TestRipConfiguration(unittest.TestCase):
    def test_starts_with_no_rip_networks(self) -> None:
        router = Router()
        self.assertEqual(router.rip_networks, frozenset())

    def test_enable_rip_adds_a_network(self) -> None:
        router = Router()
        router.enable_rip("10.0.0.0", "255.0.0.0")
        networks = {str(n) for n in router.rip_networks}
        self.assertIn("10.0.0.0/8", networks)

    def test_disable_rip_removes_a_network(self) -> None:
        router = Router()
        router.enable_rip("10.0.0.0", "255.0.0.0")
        router.disable_rip("10.0.0.0", "255.0.0.0")
        self.assertEqual(router.rip_networks, frozenset())

    def test_disable_unknown_network_is_a_no_op(self) -> None:
        router = Router()
        router.disable_rip("10.0.0.0", "255.0.0.0")

    def test_enable_rip_rejects_malformed_mask(self) -> None:
        router = Router()
        with self.assertRaises(ValidationError):
            router.enable_rip("10.0.0.0", "not-a-mask")


class TestRipEnabledInterfaces(unittest.TestCase):
    def test_interface_within_enabled_network_participates(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")
        router.get_interface("GigabitEthernet0/0").set_admin_up(True)
        router.enable_rip("10.0.0.0", "255.0.0.0")

        self.assertEqual(router.rip_enabled_interfaces(), ["GigabitEthernet0/0"])

    def test_interface_outside_enabled_network_does_not_participate(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.configure_ipv4("GigabitEthernet0/0", "192.168.1.1", "255.255.255.0")
        router.get_interface("GigabitEthernet0/0").set_admin_up(True)
        router.enable_rip("10.0.0.0", "255.0.0.0")

        self.assertEqual(router.rip_enabled_interfaces(), [])

    def test_shutdown_interface_does_not_participate(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")
        router.enable_rip("10.0.0.0", "255.0.0.0")

        self.assertEqual(router.rip_enabled_interfaces(), [])

    def test_exact_network_match_participates(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")
        router.get_interface("GigabitEthernet0/0").set_admin_up(True)
        router.enable_rip("10.0.0.0", "255.255.255.0")

        self.assertEqual(router.rip_enabled_interfaces(), ["GigabitEthernet0/0"])

    def test_multiple_enabled_networks(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0", "GigabitEthernet0/1"])
        router.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")
        router.configure_ipv4("GigabitEthernet0/1", "192.168.1.1", "255.255.255.0")
        router.get_interface("GigabitEthernet0/0").set_admin_up(True)
        router.get_interface("GigabitEthernet0/1").set_admin_up(True)
        router.enable_rip("10.0.0.0", "255.0.0.0")
        router.enable_rip("192.168.1.0", "255.255.255.0")

        self.assertEqual(
            set(router.rip_enabled_interfaces()), {"GigabitEthernet0/0", "GigabitEthernet0/1"}
        )


class TestRipNetworksSurviveSaveAndReload(unittest.TestCase):
    def test_saved_rip_network_survives_reload(self) -> None:
        router = Router()
        router.enable_rip("10.0.0.0", "255.0.0.0")
        router.save_config()
        router.disable_rip("10.0.0.0", "255.0.0.0")

        router.reload()

        networks = {str(n) for n in router.rip_networks}
        self.assertIn("10.0.0.0/8", networks)

    def test_unsaved_rip_network_is_discarded_on_reload(self) -> None:
        router = Router()
        router.save_config()
        router.enable_rip("10.0.0.0", "255.0.0.0")

        router.reload()

        self.assertEqual(router.rip_networks, frozenset())

    def test_static_routes_and_rip_networks_both_survive_together(self) -> None:
        router = Router()
        router.add_static_route("192.168.9.0", "255.255.255.0", "10.0.0.9")
        router.enable_rip("10.0.0.0", "255.0.0.0")
        router.save_config()
        router.remove_static_route("192.168.9.0", "255.255.255.0")
        router.disable_rip("10.0.0.0", "255.0.0.0")

        router.reload()

        self.assertIn("192.168.9.0/24", router.static_routes)
        self.assertIn("10.0.0.0/8", {str(n) for n in router.rip_networks})

if __name__ == "__main__":
    unittest.main()
