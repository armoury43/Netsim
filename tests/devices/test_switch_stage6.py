"""Tests for the Stage 6 save/reload additions to netsim.devices.switch.Switch.

test_switch.py (Stage 3) is untouched. Covers: the VLAN database now
correctly participating in save/reload (same gap as Router's static
routes), while the MAC table deliberately does NOT - it's dynamic
learned state, like ARP cache, and real switches clear it on reboot too.
"""

from __future__ import annotations

import unittest

from netsim.devices.switch import Switch


class TestVlanDatabaseSurvivesSaveAndReload(unittest.TestCase):
    def test_saved_vlan_survives_reload(self) -> None:
        switch = Switch()
        switch.get_or_create_vlan(10, name="Engineering")
        switch.save_config()

        switch.reload()

        self.assertIn(10, switch.vlans)
        self.assertEqual(switch.vlans[10].name, "Engineering")

    def test_unsaved_vlan_is_discarded_on_reload(self) -> None:
        switch = Switch()
        switch.save_config()
        switch.get_or_create_vlan(20)

        switch.reload()

        self.assertNotIn(20, switch.vlans)

    def test_default_vlan_1_always_present_after_reload(self) -> None:
        switch = Switch()
        switch.reload()
        self.assertIn(1, switch.vlans)

    def test_reload_without_any_save_discards_extra_vlans(self) -> None:
        switch = Switch()
        switch.get_or_create_vlan(99)

        switch.reload()

        self.assertNotIn(99, switch.vlans)
        self.assertIn(1, switch.vlans)


class TestMacTableDoesNotSurviveReload(unittest.TestCase):
    """The MAC table is dynamic learned state, not configuration - like
    a real switch clearing its MAC table on reboot, and like this
    project's ARP cache never being treated as device configuration."""

    def test_learned_mac_is_cleared_by_reload_even_if_saved_after_learning(self) -> None:
        switch = Switch(interface_names=["FastEthernet0/1"])
        switch.learn_mac("02:00:00:00:00:01", "FastEthernet0/1")
        switch.save_config()

        switch.reload()

        self.assertEqual(dict(switch.mac_table), {})

    def test_learned_mac_is_cleared_by_reload_without_any_save(self) -> None:
        switch = Switch(interface_names=["FastEthernet0/1"])
        switch.learn_mac("02:00:00:00:00:01", "FastEthernet0/1")

        switch.reload()

        self.assertEqual(dict(switch.mac_table), {})


class TestSwitchportConfigSurvivesReload(unittest.TestCase):
    """Confirms existing behavior (via Interface's own deepcopy
    mechanism, unrelated to the Stage 6 hook) still works: access
    VLAN/trunk assignment on a port is part of interface state, which
    has always been captured by save/reload since Stage 3/4."""

    def test_access_vlan_assignment_survives_reload(self) -> None:
        switch = Switch(interface_names=["FastEthernet0/1"])
        switch.get_interface("FastEthernet0/1").set_switchport_access_vlan(30)
        switch.save_config()
        switch.get_interface("FastEthernet0/1").set_switchport_access_vlan(1)

        switch.reload()

        self.assertEqual(switch.get_interface("FastEthernet0/1").switchport.access_vlan, 30)

if __name__ == "__main__":
    unittest.main()
