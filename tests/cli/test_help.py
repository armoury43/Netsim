"""Tests for netsim.cli.help."""

from __future__ import annotations

import unittest

from netsim.cli.command import Argument, Command, CommandContext, CommandResult
from netsim.cli.help import format_command_list, format_query
from netsim.cli.modes import CliMode
from netsim.cli.registry import CommandRegistry


def _noop(context: CommandContext) -> CommandResult:
    return CommandResult()


class TestFormatCommandList(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = CommandRegistry()
        self.registry.register(
            Command(
                name="enable",
                handler=_noop,
                allowed_modes=frozenset({CliMode.USER_EXEC}),
                help_text="Enter privileged EXEC mode",
            )
        )
        self.registry.register(
            Command(
                name="exit",
                handler=_noop,
                allowed_modes=frozenset({CliMode.USER_EXEC}),
                help_text="Exit the current mode",
            )
        )
        self.registry.register(
            Command(
                name="configure terminal",
                handler=_noop,
                allowed_modes=frozenset({CliMode.PRIVILEGED_EXEC}),
                help_text="Enter global configuration mode",
            )
        )

    def test_lists_only_commands_available_in_given_mode(self) -> None:
        text = format_command_list(CliMode.USER_EXEC, self.registry)
        self.assertIn("enable", text)
        self.assertIn("exit", text)
        self.assertNotIn("configure terminal", text)

    def test_includes_help_text(self) -> None:
        text = format_command_list(CliMode.USER_EXEC, self.registry)
        self.assertIn("Enter privileged EXEC mode", text)

    def test_hidden_commands_are_excluded(self) -> None:
        self.registry.register(
            Command(
                name="secret-debug",
                handler=_noop,
                allowed_modes=frozenset({CliMode.USER_EXEC}),
                hidden=True,
            )
        )
        text = format_command_list(CliMode.USER_EXEC, self.registry)
        self.assertNotIn("secret-debug", text)

    def test_empty_mode_produces_message_not_error(self) -> None:
        empty_registry = CommandRegistry()
        text = format_command_list(CliMode.VLAN_CONFIG, empty_registry)
        self.assertIsInstance(text, str)


class TestFormatQuery(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = CommandRegistry()
        self.registry.register(
            Command(
                name="enable",
                handler=_noop,
                allowed_modes=frozenset({CliMode.USER_EXEC}),
                help_text="Enter privileged EXEC mode",
            )
        )
        self.registry.register(
            Command(
                name="configure terminal",
                handler=_noop,
                allowed_modes=frozenset({CliMode.PRIVILEGED_EXEC}),
                help_text="Enter global configuration mode",
            )
        )

    def test_query_with_no_tokens_lists_all_commands_for_mode(self) -> None:
        text = format_query([], CliMode.USER_EXEC, self.registry)
        self.assertIn("enable", text)

    def test_query_with_partial_word_lists_matching_completions(self) -> None:
        text = format_query(["en"], CliMode.USER_EXEC, self.registry)
        self.assertIn("enable", text)

    def test_query_shows_help_text_when_word_completes_a_full_command(self) -> None:
        text = format_query(["en"], CliMode.USER_EXEC, self.registry)
        self.assertIn("Enter privileged EXEC mode", text)

    def test_query_with_no_matches_reports_unknown(self) -> None:
        text = format_query(["zz"], CliMode.USER_EXEC, self.registry)
        self.assertIn("Unknown", text)

    def test_query_for_second_word_of_multiword_command(self) -> None:
        text = format_query(["configure", ""], CliMode.PRIVILEGED_EXEC, self.registry)
        self.assertIn("terminal", text)

if __name__ == "__main__":
    unittest.main()
