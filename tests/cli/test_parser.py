"""Tests for netsim.cli.parser."""

from __future__ import annotations

import unittest

from netsim.cli.command import Argument, Command, CommandContext, CommandResult
from netsim.cli.errors import (
    AmbiguousCommandError,
    ArgumentValidationError,
    IncompleteCommandError,
    UnknownCommandError,
)
from netsim.cli.modes import CliMode
from netsim.cli.parser import ParsedCommand, parse_line, tokenize
from netsim.cli.registry import CommandRegistry
from netsim.core.exceptions import ValidationError


def _noop(context: CommandContext) -> CommandResult:
    return CommandResult()


def _ipv4(raw: str) -> str:
    parts = raw.split(".")
    if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        raise ValidationError(f"{raw!r} is not a valid IPv4 address", field="ip", value=raw)
    return raw


class TestTokenize(unittest.TestCase):
    def test_splits_on_whitespace(self) -> None:
        self.assertEqual(tokenize("show ip route"), ["show", "ip", "route"])

    def test_collapses_repeated_whitespace(self) -> None:
        self.assertEqual(tokenize("show   ip    route"), ["show", "ip", "route"])

    def test_blank_line_yields_no_tokens(self) -> None:
        self.assertEqual(tokenize("   "), [])

    def test_comment_line_yields_no_tokens(self) -> None:
        self.assertEqual(tokenize("! this is a comment"), [])

    def test_strips_leading_and_trailing_whitespace(self) -> None:
        self.assertEqual(tokenize("  enable  "), ["enable"])


class TestParseLine(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = CommandRegistry()
        self.registry.register(
            Command(name="enable", handler=_noop, allowed_modes=frozenset({CliMode.USER_EXEC}))
        )
        self.registry.register(
            Command(
                name="ip address",
                handler=_noop,
                allowed_modes=frozenset({CliMode.INTERFACE_CONFIG}),
                arguments=(
                    Argument(name="ip", validator=_ipv4),
                    Argument(name="mask", validator=_ipv4),
                ),
            )
        )
        self.registry.register(
            Command(
                name="description",
                handler=_noop,
                allowed_modes=frozenset({CliMode.INTERFACE_CONFIG}),
                arguments=(Argument(name="text", required=False),),
            )
        )

    def test_blank_line_returns_none(self) -> None:
        self.assertIsNone(parse_line("   ", CliMode.USER_EXEC, self.registry))

    def test_comment_line_returns_none(self) -> None:
        self.assertIsNone(parse_line("! comment", CliMode.USER_EXEC, self.registry))

    def test_resolves_simple_command(self) -> None:
        parsed = parse_line("enable", CliMode.USER_EXEC, self.registry)
        assert parsed is not None
        self.assertIsInstance(parsed, ParsedCommand)
        self.assertEqual(parsed.command.name, "enable")
        self.assertEqual(parsed.args, {})

    def test_validates_and_converts_arguments(self) -> None:
        parsed = parse_line(
            "ip address 10.0.0.1 255.255.255.0",
            CliMode.INTERFACE_CONFIG,
            self.registry,
        )
        assert parsed is not None
        self.assertEqual(parsed.args["ip"], "10.0.0.1")
        self.assertEqual(parsed.args["mask"], "255.255.255.0")

    def test_optional_argument_may_be_omitted(self) -> None:
        parsed = parse_line("description", CliMode.INTERFACE_CONFIG, self.registry)
        assert parsed is not None
        self.assertNotIn("text", parsed.args)

    def test_optional_argument_is_included_when_given(self) -> None:
        parsed = parse_line(
            "description uplink to core", CliMode.INTERFACE_CONFIG, self.registry
        )
        assert parsed is not None

        self.assertIn("text", parsed.args)

    def test_raises_on_unrecognized_command(self) -> None:
        with self.assertRaises(UnknownCommandError):
            parse_line("frobnicate", CliMode.USER_EXEC, self.registry)

    def test_raises_on_missing_required_argument(self) -> None:
        with self.assertRaises(ArgumentValidationError):
            parse_line("ip address 10.0.0.1", CliMode.INTERFACE_CONFIG, self.registry)

    def test_raises_on_invalid_argument_value(self) -> None:
        with self.assertRaises(ArgumentValidationError) as ctx:
            parse_line(
                "ip address 999.1.1.1 255.255.255.0",
                CliMode.INTERFACE_CONFIG,
                self.registry,
            )
        self.assertIn("ip address <ip> <mask>", str(ctx.exception))

    def test_raises_on_too_many_arguments(self) -> None:
        with self.assertRaises(ArgumentValidationError):
            parse_line(
                "ip address 10.0.0.1 255.255.255.0 extra",
                CliMode.INTERFACE_CONFIG,
                self.registry,
            )

    def test_raises_ambiguous_command_error(self) -> None:
        registry = CommandRegistry()
        registry.register(
            Command(name="show", handler=_noop, allowed_modes=frozenset({CliMode.USER_EXEC}))
        )
        registry.register(
            Command(name="shutdown", handler=_noop, allowed_modes=frozenset({CliMode.USER_EXEC}))
        )
        with self.assertRaises(AmbiguousCommandError):
            parse_line("sh", CliMode.USER_EXEC, registry)

    def test_raises_incomplete_command_error(self) -> None:
        registry = CommandRegistry()
        registry.register(
            Command(
                name="configure terminal",
                handler=_noop,
                allowed_modes=frozenset({CliMode.PRIVILEGED_EXEC}),
            )
        )
        with self.assertRaises(IncompleteCommandError):
            parse_line("configure", CliMode.PRIVILEGED_EXEC, registry)

if __name__ == "__main__":
    unittest.main()
