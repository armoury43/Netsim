"""Tests for netsim.cli.errors."""

from __future__ import annotations

import unittest

from netsim.cli.command import Argument, Command, CommandContext, CommandResult
from netsim.cli.errors import (
    AmbiguousCommandError,
    ArgumentValidationError,
    CliError,
    IncompleteCommandError,
    ModeStackError,
    UnknownCommandError,
)
from netsim.cli.modes import CliMode
from netsim.core.exceptions import CommandError


def _noop(context: CommandContext) -> CommandResult:
    return CommandResult()


class TestCliErrorHierarchy(unittest.TestCase):
    def test_cli_error_is_a_command_error(self) -> None:
        self.assertTrue(issubclass(CliError, CommandError))

    def test_all_cli_errors_derive_from_cli_error(self) -> None:
        for subclass in (
            UnknownCommandError,
            AmbiguousCommandError,
            IncompleteCommandError,
            ArgumentValidationError,
            ModeStackError,
        ):
            with self.subTest(subclass=subclass):
                self.assertTrue(issubclass(subclass, CliError))


class TestUnknownCommandError(unittest.TestCase):
    def test_message_includes_offending_input(self) -> None:
        error = UnknownCommandError(tokens=["ip", "adress"])
        self.assertIn("ip adress", str(error))

    def test_message_includes_suggestion_when_provided(self) -> None:
        error = UnknownCommandError(tokens=["ip", "adress"], suggestion="ip address")
        self.assertIn("ip address", str(error))


class TestAmbiguousCommandError(unittest.TestCase):
    def test_message_lists_candidate_names(self) -> None:
        show = Command(name="show", handler=_noop, allowed_modes=frozenset({CliMode.USER_EXEC}))
        shutdown = Command(
            name="shutdown", handler=_noop, allowed_modes=frozenset({CliMode.USER_EXEC})
        )
        error = AmbiguousCommandError(tokens=["sh"], candidates=[show, shutdown])
        message = str(error)
        self.assertIn("show", message)
        self.assertIn("shutdown", message)


class TestIncompleteCommandError(unittest.TestCase):
    def test_message_indicates_incomplete_input(self) -> None:
        cmd = Command(
            name="configure terminal",
            handler=_noop,
            allowed_modes=frozenset({CliMode.PRIVILEGED_EXEC}),
        )
        error = IncompleteCommandError(tokens=["configure"], candidates=[cmd])
        self.assertIn("incomplete", str(error).lower())


class TestArgumentValidationError(unittest.TestCase):
    def test_message_shows_correct_syntax(self) -> None:
        cmd = Command(
            name="ip address",
            handler=_noop,
            allowed_modes=frozenset({CliMode.INTERFACE_CONFIG}),
            arguments=(Argument(name="ip"), Argument(name="mask")),
        )
        error = ArgumentValidationError(reason="missing required argument", command=cmd)
        message = str(error)
        self.assertIn("Invalid command", message)
        self.assertIn("ip address <ip> <mask>", message)


class TestModeStackError(unittest.TestCase):
    def test_is_a_plain_cli_error(self) -> None:
        error = ModeStackError("cannot exit base mode")
        self.assertEqual(str(error), "cannot exit base mode")

if __name__ == "__main__":
    unittest.main()
