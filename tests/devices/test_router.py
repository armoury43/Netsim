"""Tests for netsim.devices.router.Router."""

from __future__ import annotations

import unittest

from netsim.devices.router import Router
from netsim.devices.types import DeviceType


class TestRouterDefaults(unittest.TestCase):
    def test_device_type_is_router(self) -> None:
        router = Router()
        self.assertEqual(router.device_type, DeviceType.ROUTER)

    def test_default_hostname(self) -> None:
        router = Router()
        self.assertEqual(router.hostname, "Router")

    def test_has_default_interfaces(self) -> None:
        router = Router()
        self.assertGreaterEqual(len(router.interfaces), 2)
        for name in router.interfaces:
            self.assertTrue(name.startswith("GigabitEthernet"))

    def test_custom_hostname_and_interfaces(self) -> None:
        router = Router(hostname="Tehran-R1", interface_names=["GigabitEthernet0/0"])
        self.assertEqual(router.hostname, "Tehran-R1")
        self.assertEqual(set(router.interfaces.keys()), {"GigabitEthernet0/0"})

    def test_router_interfaces_have_no_switchport_config(self) -> None:
        router = Router()
        for iface in router.interfaces.values():
            self.assertIsNone(iface.switchport)


class TestRouterConnectedNetworks(unittest.TestCase):
    def test_no_connected_networks_by_default(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        self.assertEqual(router.connected_networks(), [])

    def test_configured_and_up_interface_contributes_a_network(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")
        router.get_interface("GigabitEthernet0/0").set_admin_up(True)

        networks = [str(n) for n in router.connected_networks()]
        self.assertEqual(networks, ["10.0.0.0/24"])

    def test_configured_but_shutdown_interface_is_not_connected(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")

        self.assertEqual(router.connected_networks(), [])

    def test_multiple_up_interfaces_each_contribute(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0", "GigabitEthernet0/1"])
        router.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")
        router.get_interface("GigabitEthernet0/0").set_admin_up(True)
        router.configure_ipv4("GigabitEthernet0/1", "192.168.1.1", "255.255.255.0")
        router.get_interface("GigabitEthernet0/1").set_admin_up(True)

        networks = {str(n) for n in router.connected_networks()}
        self.assertEqual(networks, {"10.0.0.0/24", "192.168.1.0/24"})

if __name__ == "__main__":
    unittest.main()
