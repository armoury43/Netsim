"""Tests for netsim.cli.history."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from netsim.cli.history import CommandHistory


class TestCommandHistoryBasics(unittest.TestCase):
    def test_starts_empty(self) -> None:
        history = CommandHistory()
        self.assertEqual(history.all(), [])

    def test_add_appends_entries_in_order(self) -> None:
        history = CommandHistory()
        history.add("enable")
        history.add("configure terminal")
        self.assertEqual(history.all(), ["enable", "configure terminal"])

    def test_blank_entries_are_not_recorded(self) -> None:
        history = CommandHistory()
        history.add("   ")
        history.add("")
        self.assertEqual(history.all(), [])

    def test_last_returns_most_recent_n_entries(self) -> None:
        history = CommandHistory()
        for cmd in ["a", "b", "c", "d"]:
            history.add(cmd)
        self.assertEqual(history.last(2), ["c", "d"])

    def test_clear_empties_history(self) -> None:
        history = CommandHistory()
        history.add("enable")
        history.clear()
        self.assertEqual(history.all(), [])


class TestCommandHistoryMaxLen(unittest.TestCase):
    def test_oldest_entries_are_dropped_beyond_max_size(self) -> None:
        history = CommandHistory(max_size=3)
        for cmd in ["a", "b", "c", "d"]:
            history.add(cmd)
        self.assertEqual(history.all(), ["b", "c", "d"])


class TestCommandHistoryPersistence(unittest.TestCase):
    def test_save_and_load_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.txt"
            history = CommandHistory()
            history.add("enable")
            history.add("configure terminal")
            history.save_to_file(path)

            loaded = CommandHistory()
            loaded.load_from_file(path)
            self.assertEqual(loaded.all(), ["enable", "configure terminal"])

    def test_load_from_missing_file_is_a_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "does-not-exist.txt"
            history = CommandHistory()
            history.load_from_file(path)
            self.assertEqual(history.all(), [])

if __name__ == "__main__":
    unittest.main()
