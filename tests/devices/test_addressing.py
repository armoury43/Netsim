"""Tests for netsim.devices.addressing."""

from __future__ import annotations

import ipaddress
import unittest

from netsim.devices.addressing import parse_ipv4_address, parse_ipv4_mask
from netsim.core.exceptions import ValidationError


class TestParseIPv4Address(unittest.TestCase):
    def test_valid_address_parses(self) -> None:
        addr = parse_ipv4_address("10.0.0.1")
        self.assertEqual(addr, ipaddress.IPv4Address("10.0.0.1"))

    def test_malformed_address_raises(self) -> None:
        with self.assertRaises(ValidationError):
            parse_ipv4_address("999.1.1.1")

    def test_non_numeric_octet_raises(self) -> None:
        with self.assertRaises(ValidationError):
            parse_ipv4_address("abc.def.ghi.jkl")

    def test_too_few_octets_raises(self) -> None:
        with self.assertRaises(ValidationError):
            parse_ipv4_address("10.0.0")

    def test_error_names_the_offending_value(self) -> None:
        try:
            parse_ipv4_address("999.1.1.1")
        except ValidationError as exc:
            self.assertEqual(exc.value, "999.1.1.1")
        else:
            self.fail("expected ValidationError")


class TestParseIPv4Mask(unittest.TestCase):
    def test_valid_dotted_mask_parses_to_prefix_length(self) -> None:
        self.assertEqual(parse_ipv4_mask("255.255.255.0"), 24)
        self.assertEqual(parse_ipv4_mask("255.255.255.252"), 30)
        self.assertEqual(parse_ipv4_mask("255.0.0.0"), 8)

    def test_all_zeros_mask_is_prefix_zero(self) -> None:
        self.assertEqual(parse_ipv4_mask("0.0.0.0"), 0)

    def test_all_ones_mask_is_prefix_32(self) -> None:
        self.assertEqual(parse_ipv4_mask("255.255.255.255"), 32)

    def test_non_contiguous_mask_raises(self) -> None:
        with self.assertRaises(ValidationError):
            parse_ipv4_mask("255.0.255.0")

    def test_malformed_mask_raises(self) -> None:
        with self.assertRaises(ValidationError):
            parse_ipv4_mask("not-a-mask")

    def test_bare_prefix_length_is_accepted(self) -> None:
        self.assertEqual(parse_ipv4_mask("24"), 24)

    def test_out_of_range_bare_prefix_raises(self) -> None:
        with self.assertRaises(ValidationError):
            parse_ipv4_mask("33")

if __name__ == "__main__":
    unittest.main()
