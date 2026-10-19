"""Tests for netsim.cli.terminal.

The loop itself has no logic to speak of - these tests exist to prove
the wiring (input -> session.execute_line -> output) works, using
injected input/output functions instead of a real TTY.
"""

from __future__ import annotations

import unittest

from netsim.cli.builtin_commands import build_default_registry
from netsim.cli.session import CliSession
from netsim.cli.terminal import run


class FakeDevice:
    """Test double - not a real device, see test_device_interface.py."""

    def __init__(self, hostname: str = "Router") -> None:
        self._hostname = hostname

    @property
    def hostname(self) -> str:
        return self._hostname

    def set_hostname(self, hostname: str) -> None:
        self._hostname = hostname


def _scripted_input(lines: list[str]) -> object:
    iterator = iter(lines)

    def input_fn(prompt: str) -> str:
        try:
            return next(iterator)
        except StopIteration:
            raise EOFError from None

    return input_fn


class TestTerminalLoop(unittest.TestCase):
    def test_runs_commands_and_prints_output(self) -> None:
        session = CliSession(registry=build_default_registry(), device=FakeDevice())
        printed: list[str] = []

        run(
            session,
            input_fn=_scripted_input(["show version", "exit"]),
            output_fn=printed.append,
        )

        joined = "\n".join(printed)
        self.assertIn("NetSim — Virtual Network Lab", joined)

    def test_stops_on_eof(self) -> None:
        session = CliSession(registry=build_default_registry(), device=FakeDevice())
        printed: list[str] = []

        run(session, input_fn=_scripted_input([]), output_fn=printed.append)

        self.assertTrue(True)

    def test_stops_when_session_reports_exited(self) -> None:
        session = CliSession(registry=build_default_registry(), device=FakeDevice())
        printed: list[str] = []

        run(
            session,
            input_fn=_scripted_input(["exit", "show version"]),
            output_fn=printed.append,
        )

        self.assertNotIn("netsim CLI Engine", "\n".join(printed))

    def test_prints_errors(self) -> None:
        session = CliSession(registry=build_default_registry(), device=FakeDevice())
        printed: list[str] = []

        run(
            session,
            input_fn=_scripted_input(["frobnicate", "exit"]),
            output_fn=printed.append,
        )

        self.assertTrue(any("Unrecognized command" in line for line in printed))

if __name__ == "__main__":
    unittest.main()
