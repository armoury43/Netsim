"""Tests for netsim.devices.mac."""

from __future__ import annotations

import unittest

from netsim.devices.mac import MAC_PATTERN, generate_mac_address, is_valid_mac


class TestGenerateMacAddress(unittest.TestCase):
    def test_returns_correctly_formatted_address(self) -> None:
        mac = generate_mac_address()
        self.assertRegex(mac, MAC_PATTERN)

    def test_sets_locally_administered_bit(self) -> None:
        mac = generate_mac_address()
        first_octet = int(mac.split(":")[0], 16)
        self.assertEqual(first_octet & 0b00000010, 0b00000010)

    def test_clears_multicast_bit(self) -> None:
        mac = generate_mac_address()
        first_octet = int(mac.split(":")[0], 16)
        self.assertEqual(first_octet & 0b00000001, 0)

    def test_successive_calls_are_unique(self) -> None:
        macs = {generate_mac_address() for _ in range(200)}
        self.assertEqual(len(macs), 200)


class TestIsValidMac(unittest.TestCase):
    def test_generated_address_is_valid(self) -> None:
        self.assertTrue(is_valid_mac(generate_mac_address()))

    def test_rejects_malformed_strings(self) -> None:
        for bad in ["", "not-a-mac", "AA:BB:CC:DD:EE", "AA:BB:CC:DD:EE:GG", "AABBCCDDEEFF"]:
            with self.subTest(bad=bad):
                self.assertFalse(is_valid_mac(bad))

if __name__ == "__main__":
    unittest.main()
