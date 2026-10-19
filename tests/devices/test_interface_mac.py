"""Tests for the Stage 4 mac_address addition to netsim.devices.interface.Interface.

Kept in a separate file from test_interface.py (Stage 3, untouched) so
it's obvious at a glance which tests are the original Stage 3 contract
and which are new - both files exercise the same class.
"""

from __future__ import annotations

import copy
import unittest

from netsim.core.exceptions import ValidationError
from netsim.devices.interface import Interface
from netsim.devices.mac import MAC_PATTERN


class TestInterfaceMacAddress(unittest.TestCase):
    def test_gets_a_valid_mac_address_at_construction(self) -> None:
        iface = Interface(name="GigabitEthernet0/0")
        self.assertRegex(iface.mac_address, MAC_PATTERN)

    def test_two_interfaces_get_different_addresses(self) -> None:
        a = Interface(name="GigabitEthernet0/0")
        b = Interface(name="GigabitEthernet0/1")
        self.assertNotEqual(a.mac_address, b.mac_address)

    def test_mac_address_is_stable_across_reads(self) -> None:
        iface = Interface(name="GigabitEthernet0/0")
        first_read = iface.mac_address
        second_read = iface.mac_address
        self.assertEqual(first_read, second_read)

    def test_set_mac_address_changes_it(self) -> None:
        iface = Interface(name="GigabitEthernet0/0")
        iface.set_mac_address("02:AA:BB:CC:DD:EE")
        self.assertEqual(iface.mac_address, "02:AA:BB:CC:DD:EE")

    def test_set_mac_address_rejects_malformed_value(self) -> None:
        iface = Interface(name="GigabitEthernet0/0")
        with self.assertRaises(ValidationError):
            iface.set_mac_address("not-a-mac")

    def test_deepcopy_preserves_but_does_not_share_mac_address(self) -> None:
        original = Interface(name="GigabitEthernet0/0")
        clone = copy.deepcopy(original)
        self.assertEqual(original.mac_address, clone.mac_address)

        clone.set_mac_address("02:11:22:33:44:55")
        self.assertNotEqual(original.mac_address, clone.mac_address)

if __name__ == "__main__":
    unittest.main()
