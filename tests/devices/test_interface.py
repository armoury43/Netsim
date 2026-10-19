"""Tests for netsim.devices.interface."""

from __future__ import annotations

import unittest

from netsim.devices.interface import Interface, SwitchportConfig
from netsim.core.exceptions import ValidationError


class TestInterfaceNameValidation(unittest.TestCase):
    def test_valid_names_accepted(self) -> None:
        for name in ["GigabitEthernet0/0", "FastEthernet0/1", "Ethernet0", "Vlan10", "Loopback0"]:
            with self.subTest(name=name):
                Interface(name=name)

    def test_invalid_name_rejected(self) -> None:
        for bad_name in ["", "0/0", "Gi 0/0", "Gig!Eth0/0", "   "]:
            with self.subTest(bad_name=bad_name):
                with self.assertRaises(ValidationError):
                    Interface(name=bad_name)


class TestInterfaceDefaults(unittest.TestCase):
    def test_starts_administratively_down(self) -> None:
        iface = Interface(name="GigabitEthernet0/0")
        self.assertFalse(iface.admin_up)

    def test_starts_with_no_description(self) -> None:
        iface = Interface(name="GigabitEthernet0/0")
        self.assertEqual(iface.description, "")

    def test_starts_with_no_ipv4_address(self) -> None:
        iface = Interface(name="GigabitEthernet0/0")
        self.assertIsNone(iface.ipv4_address)
        self.assertIsNone(iface.ipv4_prefix_length)

    def test_switchport_is_none_by_default(self) -> None:
        iface = Interface(name="GigabitEthernet0/0")
        self.assertIsNone(iface.switchport)


class TestInterfaceDescription(unittest.TestCase):
    def test_set_description(self) -> None:
        iface = Interface(name="GigabitEthernet0/0")
        iface.set_description("WAN_TO_SHIRAZ")
        self.assertEqual(iface.description, "WAN_TO_SHIRAZ")

    def test_description_can_be_cleared(self) -> None:
        iface = Interface(name="GigabitEthernet0/0")
        iface.set_description("uplink")
        iface.set_description("")
        self.assertEqual(iface.description, "")


class TestInterfaceAdminState(unittest.TestCase):
    def test_set_admin_up_true(self) -> None:
        iface = Interface(name="GigabitEthernet0/0")
        iface.set_admin_up(True)
        self.assertTrue(iface.admin_up)

    def test_set_admin_up_false(self) -> None:
        iface = Interface(name="GigabitEthernet0/0")
        iface.set_admin_up(True)
        iface.set_admin_up(False)
        self.assertFalse(iface.admin_up)

    def test_status_summary_reflects_admin_state(self) -> None:
        iface = Interface(name="GigabitEthernet0/0")
        self.assertIn("administratively down", iface.status_summary())
        iface.set_admin_up(True)
        self.assertEqual(iface.status_summary(), "up")


class TestInterfaceIPv4Configuration(unittest.TestCase):
    def test_set_ipv4_address_with_dotted_mask(self) -> None:
        iface = Interface(name="GigabitEthernet0/0")
        iface.set_ipv4_address("10.0.0.1", "255.255.255.252")
        self.assertEqual(iface.ipv4_address, "10.0.0.1")
        self.assertEqual(iface.ipv4_prefix_length, 30)

    def test_malformed_ip_raises_validation_error(self) -> None:
        iface = Interface(name="GigabitEthernet0/0")
        with self.assertRaises(ValidationError):
            iface.set_ipv4_address("999.1.1.1", "255.255.255.0")

    def test_malformed_mask_raises_validation_error(self) -> None:
        iface = Interface(name="GigabitEthernet0/0")
        with self.assertRaises(ValidationError):
            iface.set_ipv4_address("10.0.0.1", "not-a-mask")

    def test_clear_ipv4_address(self) -> None:
        iface = Interface(name="GigabitEthernet0/0")
        iface.set_ipv4_address("10.0.0.1", "255.255.255.0")
        iface.clear_ipv4_address()
        self.assertIsNone(iface.ipv4_address)
        self.assertIsNone(iface.ipv4_prefix_length)

    def test_network_property(self) -> None:
        iface = Interface(name="GigabitEthernet0/0")
        iface.set_ipv4_address("10.0.0.5", "255.255.255.0")
        self.assertEqual(str(iface.network), "10.0.0.0/24")

    def test_network_is_none_without_ip(self) -> None:
        iface = Interface(name="GigabitEthernet0/0")
        self.assertIsNone(iface.network)


class TestInterfaceCopyIndependence(unittest.TestCase):
    def test_deepcopy_produces_independent_interface(self) -> None:
        import copy

        original = Interface(name="GigabitEthernet0/0")
        original.set_ipv4_address("10.0.0.1", "255.255.255.0")

        clone = copy.deepcopy(original)
        clone.set_ipv4_address("192.168.1.1", "255.255.255.0")

        self.assertEqual(original.ipv4_address, "10.0.0.1")
        self.assertEqual(clone.ipv4_address, "192.168.1.1")


class TestSwitchportConfig(unittest.TestCase):
    def test_defaults_to_access_mode_vlan_1(self) -> None:
        config = SwitchportConfig()
        self.assertEqual(config.mode, "access")
        self.assertEqual(config.access_vlan, 1)

    def test_interface_can_carry_switchport_config(self) -> None:
        iface = Interface(name="FastEthernet0/1", switchport=SwitchportConfig(access_vlan=10))
        assert iface.switchport is not None
        self.assertEqual(iface.switchport.access_vlan, 10)

if __name__ == "__main__":
    unittest.main()
