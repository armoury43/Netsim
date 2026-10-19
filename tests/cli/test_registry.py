"""Tests for netsim.cli.registry."""

from __future__ import annotations

import unittest

from netsim.cli.command import Argument, Command, CommandContext, CommandResult
from netsim.cli.modes import CliMode
from netsim.cli.registry import (
    AmbiguousCommand,
    CommandRegistry,
    DuplicateCommandError,
    IncompleteCommand,
    ResolvedCommand,
    UnknownCommand,
)


def _noop(context: CommandContext) -> CommandResult:
    return CommandResult()


def make_command(name: str, modes: set[CliMode], **kwargs) -> Command:
    return Command(name=name, handler=_noop, allowed_modes=frozenset(modes), **kwargs)


class TestRegistration(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = CommandRegistry()

    def test_register_and_retrieve_by_exact_name(self) -> None:
        cmd = make_command("enable", {CliMode.USER_EXEC})
        self.registry.register(cmd)
        self.assertIs(self.registry.get_exact("enable"), cmd)

    def test_get_exact_returns_none_for_unknown_name(self) -> None:
        self.assertIsNone(self.registry.get_exact("bogus"))

    def test_duplicate_canonical_name_rejected(self) -> None:
        self.registry.register(make_command("enable", {CliMode.USER_EXEC}))
        with self.assertRaises(DuplicateCommandError):
            self.registry.register(make_command("enable", {CliMode.PRIVILEGED_EXEC}))

    def test_commands_for_mode_filters_by_allowed_modes(self) -> None:
        self.registry.register(make_command("enable", {CliMode.USER_EXEC}))
        self.registry.register(make_command("exit", {CliMode.USER_EXEC, CliMode.PRIVILEGED_EXEC}))
        self.registry.register(make_command("configure terminal", {CliMode.PRIVILEGED_EXEC}))

        user_exec_names = {c.name for c in self.registry.commands_for_mode(CliMode.USER_EXEC)}
        self.assertEqual(user_exec_names, {"enable", "exit"})

    def test_all_commands_returns_everything_registered(self) -> None:
        self.registry.register(make_command("enable", {CliMode.USER_EXEC}))
        self.registry.register(make_command("exit", {CliMode.USER_EXEC}))
        self.assertEqual(len(self.registry.all_commands()), 2)

    def test_extension_does_not_require_modifying_registry_class(self) -> None:

        def register_plugin_commands(registry: CommandRegistry) -> None:
            registry.register(make_command("ping", {CliMode.PRIVILEGED_EXEC}))

        registry = CommandRegistry()
        register_plugin_commands(registry)
        self.assertIsNotNone(registry.get_exact("ping"))


class TestResolveExactAndAbbreviated(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = CommandRegistry()
        self.registry.register(make_command("enable", {CliMode.USER_EXEC}))
        self.registry.register(
            make_command("configure terminal", {CliMode.PRIVILEGED_EXEC})
        )
        self.registry.register(make_command("exit", {CliMode.USER_EXEC}, aliases=("quit",)))

    def test_resolves_full_command(self) -> None:
        outcome = self.registry.resolve(["enable"], CliMode.USER_EXEC)
        self.assertIsInstance(outcome, ResolvedCommand)
        assert isinstance(outcome, ResolvedCommand)
        self.assertEqual(outcome.command.name, "enable")
        self.assertEqual(outcome.remaining_args, [])

    def test_resolves_unique_prefix_abbreviation(self) -> None:
        outcome = self.registry.resolve(["en"], CliMode.USER_EXEC)
        self.assertIsInstance(outcome, ResolvedCommand)
        assert isinstance(outcome, ResolvedCommand)
        self.assertEqual(outcome.command.name, "enable")

    def test_resolves_multi_word_command_with_abbreviated_words(self) -> None:
        outcome = self.registry.resolve(["conf", "t"], CliMode.PRIVILEGED_EXEC)
        self.assertIsInstance(outcome, ResolvedCommand)
        assert isinstance(outcome, ResolvedCommand)
        self.assertEqual(outcome.command.name, "configure terminal")

    def test_resolves_via_alias(self) -> None:
        outcome = self.registry.resolve(["quit"], CliMode.USER_EXEC)
        self.assertIsInstance(outcome, ResolvedCommand)
        assert isinstance(outcome, ResolvedCommand)
        self.assertEqual(outcome.command.name, "exit")

    def test_remaining_tokens_after_command_name_are_returned_as_args(self) -> None:
        self.registry.register(
            make_command(
                "ip address",
                {CliMode.INTERFACE_CONFIG},
                arguments=(Argument(name="ip"), Argument(name="mask")),
            )
        )
        outcome = self.registry.resolve(
            ["ip", "address", "10.0.0.1", "255.255.255.0"], CliMode.INTERFACE_CONFIG
        )
        assert isinstance(outcome, ResolvedCommand)
        self.assertEqual(outcome.remaining_args, ["10.0.0.1", "255.255.255.0"])

    def test_command_not_available_in_current_mode_is_unknown(self) -> None:

        outcome = self.registry.resolve(["configure", "terminal"], CliMode.USER_EXEC)
        self.assertIsInstance(outcome, UnknownCommand)

    def test_unrecognized_command_is_unknown(self) -> None:
        outcome = self.registry.resolve(["frobnicate"], CliMode.USER_EXEC)
        self.assertIsInstance(outcome, UnknownCommand)

    def test_empty_tokens_is_unknown(self) -> None:
        outcome = self.registry.resolve([], CliMode.USER_EXEC)
        self.assertIsInstance(outcome, UnknownCommand)


class TestResolveAmbiguous(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = CommandRegistry()
        self.registry.register(make_command("show", {CliMode.USER_EXEC}))
        self.registry.register(make_command("shutdown", {CliMode.USER_EXEC}))

    def test_ambiguous_prefix_reports_all_candidates(self) -> None:
        outcome = self.registry.resolve(["sh"], CliMode.USER_EXEC)
        self.assertIsInstance(outcome, AmbiguousCommand)
        assert isinstance(outcome, AmbiguousCommand)
        names = {c.name for c in outcome.candidates}
        self.assertEqual(names, {"show", "shutdown"})

    def test_unambiguous_when_only_one_matches_length(self) -> None:

        outcome = self.registry.resolve(["show"], CliMode.USER_EXEC)
        self.assertIsInstance(outcome, ResolvedCommand)


class TestResolveIncomplete(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = CommandRegistry()
        self.registry.register(
            make_command("configure terminal", {CliMode.PRIVILEGED_EXEC})
        )

    def test_partial_multiword_command_is_incomplete(self) -> None:
        outcome = self.registry.resolve(["configure"], CliMode.PRIVILEGED_EXEC)
        self.assertIsInstance(outcome, IncompleteCommand)
        assert isinstance(outcome, IncompleteCommand)
        self.assertEqual(outcome.candidates[0].name, "configure terminal")

    def test_abbreviated_partial_multiword_command_is_incomplete(self) -> None:
        outcome = self.registry.resolve(["conf"], CliMode.PRIVILEGED_EXEC)
        self.assertIsInstance(outcome, IncompleteCommand)

if __name__ == "__main__":
    unittest.main()
