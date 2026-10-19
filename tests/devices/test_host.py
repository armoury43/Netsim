"""Tests for netsim.devices.host.Host."""

from __future__ import annotations

import unittest

from netsim.devices.host import Host
from netsim.devices.types import DeviceType
from netsim.core.exceptions import ValidationError


class TestHostDefaults(unittest.TestCase):
    def test_device_type_is_host(self) -> None:
        host = Host()
        self.assertEqual(host.device_type, DeviceType.HOST)

    def test_default_hostname(self) -> None:
        host = Host()
        self.assertEqual(host.hostname, "PC")

    def test_has_a_single_default_interface(self) -> None:
        host = Host()
        self.assertEqual(len(host.interfaces), 1)

    def test_default_gateway_is_none_initially(self) -> None:
        host = Host()
        self.assertIsNone(host.default_gateway)


class TestHostDefaultGateway(unittest.TestCase):
    def test_set_default_gateway(self) -> None:
        host = Host()
        host.set_default_gateway("10.0.0.1")
        self.assertEqual(host.default_gateway, "10.0.0.1")

    def test_malformed_default_gateway_raises(self) -> None:
        host = Host()
        with self.assertRaises(ValidationError):
            host.set_default_gateway("999.1.1.1")

    def test_clear_default_gateway(self) -> None:
        host = Host()
        host.set_default_gateway("10.0.0.1")
        host.clear_default_gateway()
        self.assertIsNone(host.default_gateway)


class TestHostIPv4Configuration(unittest.TestCase):
    def test_configure_ipv4_on_its_interface(self) -> None:
        host = Host()
        interface_name = next(iter(host.interfaces))
        host.configure_ipv4(interface_name, "192.168.1.10", "255.255.255.0")
        self.assertEqual(host.get_interface(interface_name).ipv4_address, "192.168.1.10")


class TestHostConnectivityState(unittest.TestCase):
    def test_not_online_when_created(self) -> None:
        host = Host()
        self.assertFalse(host.is_online())

    def test_not_online_when_ready_but_interface_down(self) -> None:
        host = Host()
        host.boot()
        self.assertFalse(host.is_online())

    def test_not_online_when_interface_up_but_no_ip(self) -> None:
        host = Host()
        host.boot()
        interface_name = next(iter(host.interfaces))
        host.get_interface(interface_name).set_admin_up(True)
        self.assertFalse(host.is_online())

    def test_online_when_ready_with_ip_and_interface_up(self) -> None:
        host = Host()
        host.boot()
        interface_name = next(iter(host.interfaces))
        host.configure_ipv4(interface_name, "192.168.1.10", "255.255.255.0")
        host.get_interface(interface_name).set_admin_up(True)
        self.assertTrue(host.is_online())

    def test_not_online_when_powered_off_even_with_full_config(self) -> None:
        host = Host()
        host.boot()
        interface_name = next(iter(host.interfaces))
        host.configure_ipv4(interface_name, "192.168.1.10", "255.255.255.0")
        host.get_interface(interface_name).set_admin_up(True)
        host.power_off()
        self.assertFalse(host.is_online())

if __name__ == "__main__":
    unittest.main()
