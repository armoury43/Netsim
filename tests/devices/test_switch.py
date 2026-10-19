"""Tests for netsim.devices.switch.Switch."""

from __future__ import annotations

import unittest

from netsim.devices.errors import UnsupportedCapabilityError
from netsim.devices.switch import Switch
from netsim.devices.types import DeviceType


class TestSwitchDefaults(unittest.TestCase):
    def test_device_type_is_switch(self) -> None:
        switch = Switch()
        self.assertEqual(switch.device_type, DeviceType.SWITCH)

    def test_default_hostname(self) -> None:
        switch = Switch()
        self.assertEqual(switch.hostname, "Switch")

    def test_has_default_interfaces(self) -> None:
        switch = Switch()
        self.assertGreaterEqual(len(switch.interfaces), 4)
        for name in switch.interfaces:
            self.assertTrue(name.startswith("FastEthernet"))

    def test_every_interface_has_switchport_config(self) -> None:
        switch = Switch()
        for iface in switch.interfaces.values():
            self.assertIsNotNone(iface.switchport)

    def test_interfaces_default_to_access_vlan_1(self) -> None:
        switch = Switch()
        for iface in switch.interfaces.values():
            assert iface.switchport is not None
            self.assertEqual(iface.switchport.mode, "access")
            self.assertEqual(iface.switchport.access_vlan, 1)


class TestSwitchVlanDatabase(unittest.TestCase):
    def test_vlan_1_exists_by_default(self) -> None:
        switch = Switch()
        self.assertIn(1, switch.vlans)

    def test_get_or_create_vlan_creates_new_entry(self) -> None:
        switch = Switch()
        vlan = switch.get_or_create_vlan(10)
        self.assertEqual(vlan.vlan_id, 10)
        self.assertIn(10, switch.vlans)

    def test_get_or_create_vlan_returns_existing_entry(self) -> None:
        switch = Switch()
        first = switch.get_or_create_vlan(10)
        second = switch.get_or_create_vlan(10)
        self.assertIs(first, second)

    def test_new_vlan_gets_a_default_name(self) -> None:
        switch = Switch()
        vlan = switch.get_or_create_vlan(20)
        self.assertEqual(vlan.name, "VLAN0020")

    def test_vlans_property_is_read_only(self) -> None:
        switch = Switch()
        with self.assertRaises(TypeError):
            switch.vlans[99] = None

    def test_invalid_vlan_id_rejected(self) -> None:
        switch = Switch()
        with self.assertRaises(Exception):
            switch.get_or_create_vlan(0)
        with self.assertRaises(Exception):
            switch.get_or_create_vlan(4095)


class TestSwitchMacTableFoundation(unittest.TestCase):
    def test_starts_empty(self) -> None:
        switch = Switch()
        self.assertEqual(dict(switch.mac_table), {})

    def test_learn_mac_records_interface(self) -> None:
        switch = Switch(interface_names=["FastEthernet0/1"])
        switch.learn_mac("AA:BB:CC:00:00:01", "FastEthernet0/1")
        self.assertEqual(switch.mac_table["AA:BB:CC:00:00:01"], "FastEthernet0/1")

    def test_learn_mac_on_unknown_interface_raises(self) -> None:
        switch = Switch(interface_names=["FastEthernet0/1"])
        with self.assertRaises(Exception):
            switch.learn_mac("AA:BB:CC:00:00:01", "FastEthernet0/99")

    def test_relearning_updates_interface(self) -> None:
        switch = Switch(interface_names=["FastEthernet0/1", "FastEthernet0/2"])
        switch.learn_mac("AA:BB:CC:00:00:01", "FastEthernet0/1")
        switch.learn_mac("AA:BB:CC:00:00:01", "FastEthernet0/2")
        self.assertEqual(switch.mac_table["AA:BB:CC:00:00:01"], "FastEthernet0/2")


class TestSwitchCapabilityIsUsableFromCli(unittest.TestCase):
    """Sanity check for the capability-check pattern used by the CLI
    layer (see netsim.cli.device_commands): a Switch satisfies the
    VLAN-capable structural protocol, without either module importing
    the other."""

    def test_switch_exposes_get_or_create_vlan(self) -> None:
        switch = Switch()
        self.assertTrue(hasattr(switch, "get_or_create_vlan"))

if __name__ == "__main__":
    unittest.main()
