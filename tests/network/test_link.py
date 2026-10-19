"""Tests for netsim.network.link."""

from __future__ import annotations

import unittest

from netsim.network.link import Endpoint, Link


class TestEndpoint(unittest.TestCase):
    def test_equality_by_device_and_interface(self) -> None:
        a = Endpoint(device_id="R1", interface_name="GigabitEthernet0/0")
        b = Endpoint(device_id="R1", interface_name="GigabitEthernet0/0")
        self.assertEqual(a, b)

    def test_inequality_for_different_interface(self) -> None:
        a = Endpoint(device_id="R1", interface_name="GigabitEthernet0/0")
        b = Endpoint(device_id="R1", interface_name="GigabitEthernet0/1")
        self.assertNotEqual(a, b)


class TestLink(unittest.TestCase):
    def setUp(self) -> None:
        self.a = Endpoint(device_id="R1", interface_name="GigabitEthernet0/0")
        self.b = Endpoint(device_id="R2", interface_name="GigabitEthernet0/0")

    def test_starts_up(self) -> None:
        link = Link(endpoint_a=self.a, endpoint_b=self.b)
        self.assertTrue(link.up)

    def test_set_up_false(self) -> None:
        link = Link(endpoint_a=self.a, endpoint_b=self.b)
        link.set_up(False)
        self.assertFalse(link.up)

    def test_set_up_true_again(self) -> None:
        link = Link(endpoint_a=self.a, endpoint_b=self.b)
        link.set_up(False)
        link.set_up(True)
        self.assertTrue(link.up)

    def test_involves_true_for_either_endpoint(self) -> None:
        link = Link(endpoint_a=self.a, endpoint_b=self.b)
        self.assertTrue(link.involves("R1", "GigabitEthernet0/0"))
        self.assertTrue(link.involves("R2", "GigabitEthernet0/0"))

    def test_involves_false_for_unrelated_endpoint(self) -> None:
        link = Link(endpoint_a=self.a, endpoint_b=self.b)
        self.assertFalse(link.involves("R3", "GigabitEthernet0/0"))

    def test_other_end_from_a_returns_b(self) -> None:
        link = Link(endpoint_a=self.a, endpoint_b=self.b)
        self.assertEqual(link.other_end(self.a), self.b)

    def test_other_end_from_b_returns_a(self) -> None:
        link = Link(endpoint_a=self.a, endpoint_b=self.b)
        self.assertEqual(link.other_end(self.b), self.a)

    def test_other_end_raises_for_unrelated_endpoint(self) -> None:
        link = Link(endpoint_a=self.a, endpoint_b=self.b)
        unrelated = Endpoint(device_id="R3", interface_name="GigabitEthernet0/0")
        with self.assertRaises(ValueError):
            link.other_end(unrelated)

if __name__ == "__main__":
    unittest.main()
