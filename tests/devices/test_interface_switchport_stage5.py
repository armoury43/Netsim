"""Tests for the Stage 5 switchport-configuration methods on Interface.

Kept separate from test_interface.py (Stage 3, untouched) and
test_interface_mac.py (Stage 4, untouched). These back the new CLI
commands (switchport access vlan / switchport mode trunk / switchport
trunk allowed vlan) with validated, testable methods rather than
requiring callers to mutate ``Interface.switchport`` directly.
"""

from __future__ import annotations

import unittest

from netsim.core.exceptions import ValidationError
from netsim.devices.interface import Interface, SwitchportConfig


class TestSetSwitchportAccessVlan(unittest.TestCase):
    def test_sets_access_vlan_on_a_switchport(self) -> None:
        iface = Interface(name="FastEthernet0/1", switchport=SwitchportConfig())
        iface.set_switchport_access_vlan(10)
        self.assertEqual(iface.switchport.mode, "access")
        self.assertEqual(iface.switchport.access_vlan, 10)

    def test_switches_a_trunk_port_back_to_access(self) -> None:
        iface = Interface(
            name="FastEthernet0/1", switchport=SwitchportConfig(mode="trunk", trunk_allowed_vlans={10, 20})
        )
        iface.set_switchport_access_vlan(30)
        self.assertEqual(iface.switchport.mode, "access")
        self.assertEqual(iface.switchport.access_vlan, 30)

    def test_rejects_out_of_range_vlan(self) -> None:
        iface = Interface(name="FastEthernet0/1", switchport=SwitchportConfig())
        with self.assertRaises(ValidationError):
            iface.set_switchport_access_vlan(0)
        with self.assertRaises(ValidationError):
            iface.set_switchport_access_vlan(4095)

    def test_rejects_a_non_switchport_interface(self) -> None:

        iface = Interface(name="GigabitEthernet0/0")
        with self.assertRaises(ValidationError):
            iface.set_switchport_access_vlan(10)


class TestSetSwitchportTrunk(unittest.TestCase):
    def test_switches_an_access_port_to_trunk(self) -> None:
        iface = Interface(name="GigabitEthernet0/1", switchport=SwitchportConfig(access_vlan=5))
        iface.set_switchport_trunk()
        self.assertEqual(iface.switchport.mode, "trunk")

    def test_trunk_with_no_allowed_vlans_given_leaves_existing_list_untouched(self) -> None:
        iface = Interface(
            name="GigabitEthernet0/1", switchport=SwitchportConfig(trunk_allowed_vlans={10})
        )
        iface.set_switchport_trunk()
        self.assertEqual(iface.switchport.trunk_allowed_vlans, {10})

    def test_trunk_with_allowed_vlans_sets_them(self) -> None:
        iface = Interface(name="GigabitEthernet0/1", switchport=SwitchportConfig())
        iface.set_switchport_trunk(allowed_vlans={10, 20, 30})
        self.assertEqual(iface.switchport.mode, "trunk")
        self.assertEqual(iface.switchport.trunk_allowed_vlans, {10, 20, 30})

    def test_rejects_out_of_range_allowed_vlan(self) -> None:
        iface = Interface(name="GigabitEthernet0/1", switchport=SwitchportConfig())
        with self.assertRaises(ValidationError):
            iface.set_switchport_trunk(allowed_vlans={10, 9999})

    def test_rejects_a_non_switchport_interface(self) -> None:
        iface = Interface(name="GigabitEthernet0/0")
        with self.assertRaises(ValidationError):
            iface.set_switchport_trunk()

if __name__ == "__main__":
    unittest.main()
