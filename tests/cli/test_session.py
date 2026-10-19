"""Tests for netsim.cli.session.

CliSession is the seam between "typed a line" and "mode/history/device
state changed". These tests build tiny throwaway command sets rather
than depending on netsim.cli.builtin_commands, so a change to the
built-in command set can't accidentally hide a session bug.
"""

from __future__ import annotations

import unittest

from netsim.cli.command import Argument, Command, CommandContext, CommandResult
from netsim.cli.device_interface import DeviceContext
from netsim.cli.modes import CliMode, ModeContext
from netsim.cli.registry import CommandRegistry
from netsim.cli.session import CliSession


class FakeDevice:
    def __init__(self, hostname: str = "Router") -> None:
        self._hostname = hostname
        self.set_hostname_calls: list[str] = []

    @property
    def hostname(self) -> str:
        return self._hostname

    def set_hostname(self, hostname: str) -> None:
        self.set_hostname_calls.append(hostname)
        self._hostname = hostname


def _enable_handler(context: CommandContext) -> CommandResult:
    return CommandResult(mode_push=ModeContext(mode=CliMode.PRIVILEGED_EXEC))


def _configure_terminal_handler(context: CommandContext) -> CommandResult:
    return CommandResult(mode_push=ModeContext(mode=CliMode.GLOBAL_CONFIG))


def _interface_handler(context: CommandContext) -> CommandResult:
    return CommandResult(
        mode_push=ModeContext(
            mode=CliMode.INTERFACE_CONFIG, params={"interface": context.args["name"]}
        )
    )


def _exit_handler(context: CommandContext) -> CommandResult:
    return CommandResult(mode_pop=True)


def _end_handler(context: CommandContext) -> CommandResult:
    return CommandResult(mode_pop_to_privileged=True)


def _hostname_handler(context: CommandContext) -> CommandResult:

    assert context.device is not None
    context.device.set_hostname(context.args["name"])
    return CommandResult(output=[f"Hostname set to {context.args['name']}"])


def _show_output_handler(context: CommandContext) -> CommandResult:
    return CommandResult(output=["line one", "line two"])


def build_registry() -> CommandRegistry:
    registry = CommandRegistry()
    registry.register(
        Command(name="enable", handler=_enable_handler, allowed_modes=frozenset({CliMode.USER_EXEC}))
    )
    registry.register(
        Command(
            name="configure terminal",
            handler=_configure_terminal_handler,
            allowed_modes=frozenset({CliMode.PRIVILEGED_EXEC}),
        )
    )
    registry.register(
        Command(
            name="interface",
            handler=_interface_handler,
            allowed_modes=frozenset({CliMode.GLOBAL_CONFIG}),
            arguments=(Argument(name="name"),),
        )
    )
    registry.register(
        Command(
            name="exit",
            handler=_exit_handler,
            allowed_modes=frozenset(CliMode),
            aliases=("quit",),
        )
    )
    registry.register(
        Command(
            name="end",
            handler=_end_handler,
            allowed_modes=frozenset(
                {CliMode.GLOBAL_CONFIG, CliMode.INTERFACE_CONFIG, CliMode.ROUTER_CONFIG, CliMode.VLAN_CONFIG}
            ),
        )
    )
    registry.register(
        Command(
            name="hostname",
            handler=_hostname_handler,
            allowed_modes=frozenset({CliMode.GLOBAL_CONFIG}),
            arguments=(Argument(name="name"),),
            help_text="Set the device hostname",
        )
    )
    registry.register(
        Command(
            name="show version",
            handler=_show_output_handler,
            allowed_modes=frozenset(CliMode),
        )
    )
    return registry


class TestCliSessionBasicExecution(unittest.TestCase):
    def setUp(self) -> None:
        self.device = FakeDevice(hostname="Router")
        self.session = CliSession(registry=build_registry(), device=self.device)

    def test_starts_in_user_exec_with_prompt(self) -> None:
        self.assertEqual(self.session.prompt(), "Router>")

    def test_executing_command_returns_its_output(self) -> None:
        outcome = self.session.execute_line("show version")
        self.assertEqual(list(outcome.output), ["line one", "line two"])
        self.assertIsNone(outcome.error)

    def test_blank_line_produces_empty_outcome(self) -> None:
        outcome = self.session.execute_line("   ")
        self.assertEqual(outcome.output, ())
        self.assertIsNone(outcome.error)

    def test_unknown_command_returns_error_not_exception(self) -> None:
        outcome = self.session.execute_line("frobnicate")
        self.assertIsNotNone(outcome.error)
        self.assertEqual(outcome.output, ())


class TestCliSessionModeTransitions(unittest.TestCase):
    def setUp(self) -> None:
        self.session = CliSession(registry=build_registry(), device=FakeDevice())

    def test_enable_moves_to_privileged_exec(self) -> None:
        self.session.execute_line("enable")
        self.assertEqual(self.session.prompt(), "Router#")

    def test_configure_terminal_moves_to_global_config(self) -> None:
        self.session.execute_line("enable")
        self.session.execute_line("configure terminal")
        self.assertEqual(self.session.prompt(), "Router(config)#")

    def test_interface_moves_to_interface_config(self) -> None:
        self.session.execute_line("enable")
        self.session.execute_line("configure terminal")
        self.session.execute_line("interface Gi0/0")
        self.assertEqual(self.session.prompt(), "Router(config-if)#")

    def test_exit_moves_back_one_level(self) -> None:
        self.session.execute_line("enable")
        self.session.execute_line("configure terminal")
        self.session.execute_line("interface Gi0/0")
        self.session.execute_line("exit")
        self.assertEqual(self.session.prompt(), "Router(config)#")

    def test_end_returns_directly_to_privileged_exec(self) -> None:
        self.session.execute_line("enable")
        self.session.execute_line("configure terminal")
        self.session.execute_line("interface Gi0/0")
        self.session.execute_line("end")
        self.assertEqual(self.session.prompt(), "Router#")

    def test_exit_at_base_mode_marks_session_exited(self) -> None:
        outcome = self.session.execute_line("exit")
        self.assertTrue(outcome.exited)

    def test_command_not_valid_in_current_mode_is_reported_as_error(self) -> None:

        outcome = self.session.execute_line("interface Gi0/0")
        self.assertIsNotNone(outcome.error)


class TestCliSessionDeviceInterfaceUsage(unittest.TestCase):
    def test_hostname_command_only_touches_device_through_interface(self) -> None:
        device = FakeDevice(hostname="Router")
        session = CliSession(registry=build_registry(), device=device)
        session.execute_line("enable")
        session.execute_line("configure terminal")

        outcome = session.execute_line("hostname CoreSwitch")

        self.assertEqual(device.set_hostname_calls, ["CoreSwitch"])
        self.assertIn("Hostname set to CoreSwitch", outcome.output)

    def test_prompt_reflects_device_hostname_after_change(self) -> None:
        device = FakeDevice(hostname="Router")
        session = CliSession(registry=build_registry(), device=device)
        session.execute_line("enable")
        session.execute_line("configure terminal")
        session.execute_line("hostname CoreSwitch")

        self.assertEqual(session.prompt(), "CoreSwitch(config)#")


class TestCliSessionHistory(unittest.TestCase):
    def test_valid_commands_are_recorded(self) -> None:
        session = CliSession(registry=build_registry(), device=FakeDevice())
        session.execute_line("enable")
        session.execute_line("show version")
        self.assertEqual(session.history.all(), ["enable", "show version"])

    def test_invalid_commands_are_still_recorded(self) -> None:
        session = CliSession(registry=build_registry(), device=FakeDevice())
        session.execute_line("frobnicate")
        self.assertEqual(session.history.all(), ["frobnicate"])

    def test_blank_lines_are_not_recorded(self) -> None:
        session = CliSession(registry=build_registry(), device=FakeDevice())
        session.execute_line("   ")
        self.assertEqual(session.history.all(), [])

    def test_help_queries_are_not_recorded(self) -> None:
        session = CliSession(registry=build_registry(), device=FakeDevice())
        session.execute_line("?")
        self.assertEqual(session.history.all(), [])


class TestCliSessionHelpQueries(unittest.TestCase):
    def setUp(self) -> None:
        self.session = CliSession(registry=build_registry(), device=FakeDevice())

    def test_bare_question_mark_lists_commands_for_current_mode(self) -> None:
        outcome = self.session.execute_line("?")
        joined = "\n".join(outcome.output)
        self.assertIn("enable", joined)
        self.assertIsNone(outcome.error)

    def test_partial_word_question_mark_filters(self) -> None:
        outcome = self.session.execute_line("en?")
        joined = "\n".join(outcome.output)
        self.assertIn("enable", joined)

    def test_help_query_does_not_change_mode_or_raise(self) -> None:
        self.session.execute_line("show?")
        self.assertEqual(self.session.prompt(), "Router>")

if __name__ == "__main__":
    unittest.main()
