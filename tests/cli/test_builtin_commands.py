"""Tests for netsim.cli.builtin_commands.

These are integration-style tests: real CliSession, real registry
built by build_default_registry(), a fake device double standing in
for a Stage-3 Router/Switch. They prove the whole CLI engine works
end to end without any actual networking logic anywhere in netsim.cli.
"""

from __future__ import annotations

import unittest

from netsim.cli.builtin_commands import build_default_registry
from netsim.cli.modes import CliMode
from netsim.cli.session import CliSession


class FakeDevice:
    def __init__(self, hostname: str = "Router") -> None:
        self._hostname = hostname

    @property
    def hostname(self) -> str:
        return self._hostname

    def set_hostname(self, hostname: str) -> None:
        self._hostname = hostname


class TestBuiltinRegistryContents(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = build_default_registry()

    def test_expected_commands_are_registered(self) -> None:
        expected_names = {
            "enable",
            "disable",
            "configure terminal",
            "interface",
            "router",
            "vlan",
            "hostname",
            "exit",
            "end",
            "show version",
            "show history",
        }
        actual_names = {c.name for c in self.registry.all_commands()}
        self.assertTrue(expected_names.issubset(actual_names))

    def test_configure_terminal_only_available_in_privileged_exec(self) -> None:
        cmd = self.registry.get_exact("configure terminal")
        assert cmd is not None
        self.assertEqual(cmd.allowed_modes, frozenset({CliMode.PRIVILEGED_EXEC}))

    def test_interface_only_available_in_global_config(self) -> None:
        cmd = self.registry.get_exact("interface")
        assert cmd is not None
        self.assertEqual(cmd.allowed_modes, frozenset({CliMode.GLOBAL_CONFIG}))


class TestFullNavigationFlow(unittest.TestCase):
    def setUp(self) -> None:
        self.session = CliSession(registry=build_default_registry(), device=FakeDevice())

    def test_full_walk_down_and_back_up_the_mode_tree(self) -> None:
        steps = [
            ("enable", "Router#"),
            ("configure terminal", "Router(config)#"),
            ("interface GigabitEthernet0/0", "Router(config-if)#"),
            ("exit", "Router(config)#"),
            ("router rip", "Router(config-router)#"),
            ("end", "Router#"),
            ("configure terminal", "Router(config)#"),
            ("vlan 10", "Router(config-vlan)#"),
            ("end", "Router#"),
            ("disable", "Router>"),
        ]
        for command, expected_prompt in steps:
            outcome = self.session.execute_line(command)
            self.assertIsNone(outcome.error, msg=f"{command!r} -> {outcome.error}")
            self.assertEqual(self.session.prompt(), expected_prompt, msg=command)

    def test_vlan_id_argument_is_validated_as_integer(self) -> None:
        self.session.execute_line("enable")
        self.session.execute_line("configure terminal")
        outcome = self.session.execute_line("vlan not-a-number")
        self.assertIsNotNone(outcome.error)


class TestHostnameCommandUsesDeviceInterface(unittest.TestCase):
    def test_hostname_change_propagates_to_prompt(self) -> None:
        device = FakeDevice(hostname="Router")
        session = CliSession(registry=build_default_registry(), device=device)
        session.execute_line("enable")
        session.execute_line("configure terminal")
        session.execute_line("hostname BranchRouter")

        self.assertEqual(device.hostname, "BranchRouter")
        self.assertEqual(session.prompt(), "BranchRouter(config)#")


class TestRealisticErrorMessage(unittest.TestCase):
    """Mirrors the exact style of error demanded by the project brief:
    an unrecognized/malformed command should explain correct syntax,
    using the generic argument-validation machinery - not any
    hardcoded, networking-specific error text inside the CLI."""

    def test_missing_required_argument_shows_correct_syntax(self) -> None:
        session = CliSession(registry=build_default_registry(), device=FakeDevice())
        session.execute_line("enable")
        session.execute_line("configure terminal")

        outcome = session.execute_line("hostname")

        assert outcome.error is not None
        self.assertIn("Invalid command", outcome.error)
        self.assertIn("hostname <name>", outcome.error)


class TestShowHistoryCommand(unittest.TestCase):
    def test_show_history_lists_prior_commands(self) -> None:
        session = CliSession(registry=build_default_registry(), device=FakeDevice())
        session.execute_line("enable")
        outcome = session.execute_line("show history")

        joined = "\n".join(outcome.output)
        self.assertIn("enable", joined)
        self.assertIn("show history", joined)


class TestShowVersionCommand(unittest.TestCase):
    def test_show_version_returns_current_product_identity(self) -> None:
        from netsim import __version__

        session = CliSession(registry=build_default_registry(), device=FakeDevice())
        outcome = session.execute_line("show version")
        joined = "\n".join(outcome.output)
        self.assertIn("NetSim — Virtual Network Lab", joined)
        self.assertIn(f"Version: {__version__} (Alpha)", joined)
        self.assertNotIn("Stage: 2", joined)

if __name__ == "__main__":
    unittest.main()
