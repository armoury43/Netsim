"""Tests for netsim.network.arp.ArpCache (ArpMessage is covered in test_packets.py)."""

from __future__ import annotations

import unittest

from netsim.network.arp import ArpCache


class TestArpCache(unittest.TestCase):
    def test_starts_empty(self) -> None:
        cache = ArpCache()
        self.assertEqual(dict(cache.entries()), {})

    def test_get_unknown_ip_returns_none(self) -> None:
        cache = ArpCache()
        self.assertIsNone(cache.get("10.0.0.1"))

    def test_learn_and_get(self) -> None:
        cache = ArpCache()
        cache.learn("10.0.0.1", "02:00:00:00:00:01")
        self.assertEqual(cache.get("10.0.0.1"), "02:00:00:00:00:01")

    def test_relearning_overwrites(self) -> None:
        cache = ArpCache()
        cache.learn("10.0.0.1", "02:00:00:00:00:01")
        cache.learn("10.0.0.1", "02:00:00:00:00:99")
        self.assertEqual(cache.get("10.0.0.1"), "02:00:00:00:00:99")

    def test_remove(self) -> None:
        cache = ArpCache()
        cache.learn("10.0.0.1", "02:00:00:00:00:01")
        cache.remove("10.0.0.1")
        self.assertIsNone(cache.get("10.0.0.1"))

    def test_remove_unknown_ip_is_a_no_op(self) -> None:
        cache = ArpCache()
        cache.remove("10.0.0.1")

    def test_clear(self) -> None:
        cache = ArpCache()
        cache.learn("10.0.0.1", "02:00:00:00:00:01")
        cache.learn("10.0.0.2", "02:00:00:00:00:02")
        cache.clear()
        self.assertEqual(dict(cache.entries()), {})

    def test_entries_is_read_only(self) -> None:
        cache = ArpCache()
        with self.assertRaises(TypeError):
            cache.entries()["10.0.0.1"] = "02:00:00:00:00:01"

if __name__ == "__main__":
    unittest.main()
