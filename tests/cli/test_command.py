"""Tests for netsim.cli.command."""

from __future__ import annotations

import unittest

from netsim.cli.command import Argument, Command, CommandContext, CommandResult
from netsim.cli.modes import CliMode
from netsim.core.exceptions import ValidationError


def _noop_handler(context: CommandContext) -> CommandResult:
    return CommandResult(output=["ok"])


class TestArgument(unittest.TestCase):
    def test_required_by_default(self) -> None:
        arg = Argument(name="ip")
        self.assertTrue(arg.required)

    def test_validator_defaults_to_identity(self) -> None:
        arg = Argument(name="ip")
        self.assertEqual(arg.validate("1.2.3.4"), "1.2.3.4")

    def test_custom_validator_is_used(self) -> None:
        def positive_int(raw: str) -> int:
            value = int(raw)
            if value <= 0:
                raise ValidationError(f"{raw!r} must be positive", field="vlan_id", value=raw)
            return value

        arg = Argument(name="vlan_id", validator=positive_int)
        self.assertEqual(arg.validate("10"), 10)
        with self.assertRaises(ValidationError):
            arg.validate("-1")


class TestCommand(unittest.TestCase):
    def test_name_tokens_splits_on_whitespace(self) -> None:
        cmd = Command(
            name="configure terminal",
            handler=_noop_handler,
            allowed_modes=frozenset({CliMode.PRIVILEGED_EXEC}),
        )
        self.assertEqual(cmd.name_tokens, ("configure", "terminal"))

    def test_aliases_default_to_empty_tuple(self) -> None:
        cmd = Command(
            name="exit",
            handler=_noop_handler,
            allowed_modes=frozenset({CliMode.USER_EXEC}),
        )
        self.assertEqual(cmd.aliases, ())

    def test_usage_with_no_arguments(self) -> None:
        cmd = Command(
            name="configure terminal",
            handler=_noop_handler,
            allowed_modes=frozenset({CliMode.PRIVILEGED_EXEC}),
        )
        self.assertEqual(cmd.usage(), "configure terminal")

    def test_usage_with_required_and_optional_arguments(self) -> None:
        cmd = Command(
            name="ip address",
            handler=_noop_handler,
            allowed_modes=frozenset({CliMode.INTERFACE_CONFIG}),
            arguments=(
                Argument(name="ip", required=True),
                Argument(name="mask", required=True),
                Argument(name="secondary", required=False),
            ),
        )
        self.assertEqual(cmd.usage(), "ip address <ip> <mask> [secondary]")

    def test_all_name_variants_includes_name_and_aliases(self) -> None:
        cmd = Command(
            name="exit",
            handler=_noop_handler,
            allowed_modes=frozenset({CliMode.USER_EXEC}),
            aliases=("quit", "logout"),
        )
        self.assertEqual(cmd.all_name_variants(), ("exit", "quit", "logout"))


class TestCommandContextAndResult(unittest.TestCase):
    def test_command_result_defaults(self) -> None:
        result = CommandResult()
        self.assertEqual(result.output, [])
        self.assertIsNone(result.mode_push)
        self.assertFalse(result.mode_pop)
        self.assertFalse(result.mode_pop_to_privileged)
        self.assertFalse(result.should_exit_cli)

    def test_command_context_carries_parsed_args_and_raw_tokens(self) -> None:
        ctx = CommandContext(
            device=None,
            args={"name": "Gi0/0"},
            raw_tokens=("interface", "Gi0/0"),
        )
        self.assertEqual(ctx.args["name"], "Gi0/0")
        self.assertEqual(ctx.raw_tokens, ("interface", "Gi0/0"))
        self.assertIsNone(ctx.device)

    def test_command_context_history_defaults_to_empty(self) -> None:
        ctx = CommandContext(device=None, args={}, raw_tokens=())
        self.assertEqual(ctx.history, ())

    def test_command_context_can_carry_history(self) -> None:
        ctx = CommandContext(
            device=None, args={}, raw_tokens=(), history=("enable", "configure terminal")
        )
        self.assertEqual(ctx.history, ("enable", "configure terminal"))

if __name__ == "__main__":
    unittest.main()
