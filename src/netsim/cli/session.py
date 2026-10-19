"""The seam between "a line was typed" and "state changed".

:class:`CliSession` is the only place in the CLI engine that:

- owns a :class:`netsim.cli.modes.ModeStack` and actually calls
  push/pop/pop_to_privileged on it,
- owns a :class:`netsim.cli.history.CommandHistory` and decides what
  gets recorded,
- and is the only thing that builds a
  :class:`netsim.cli.command.CommandContext` and hands a
  :class:`netsim.cli.device_interface.DeviceContext` to a handler.

Command handlers themselves never see the mode stack, the registry, or
the raw device object directly outside of ``context.device`` - they
only return a :class:`netsim.cli.command.CommandResult` describing
what they want, and this class is what makes it happen. That
indirection is what keeps handlers unit-testable without a running
session at all (see the built-in command handlers).
"""

from __future__ import annotations

from dataclasses import dataclass

from netsim.cli import help as help_module
from netsim.cli.command import CommandContext, CommandResult
from netsim.cli.device_interface import DeviceContext
from netsim.cli.errors import CliError
from netsim.cli.history import CommandHistory
from netsim.cli.modes import ModeStack
from netsim.cli.network_interface import NetworkContext
from netsim.cli.lab_interface import LabContext
from netsim.cli.parser import parse_line, tokenize
from netsim.cli.registry import CommandRegistry
from netsim.core.exceptions import NetsimError


@dataclass(frozen=True)
class ExecutionOutcome:
    """The result of running one line through :meth:`CliSession.execute_line`.

    Attributes:
        output: Lines of text produced (command output or help/query text).
        error: A user-facing error message, or ``None`` on success.
            Never a Python traceback - see the ``except NetsimError``
            handling in :meth:`CliSession.execute_line`.
        exited: True if the CLI session should terminate after this line.
    """

    output: tuple[str, ...] = ()
    error: str | None = None
    exited: bool = False


class CliSession:
    """One interactive CLI session bound to one device.

    Args:
        registry: The command registry to resolve input against.
        device: The device this session controls, satisfying
            :class:`DeviceContext`. May be ``None`` for a session with
            no device attached (e.g. a pure navigation/demo session).
        history: Optional pre-existing history to continue (e.g.
            loaded from disk). Defaults to a fresh, empty history.
        network: The network engine this session's device participates
            in, satisfying :class:`NetworkContext`. May be ``None``
            for a session with no network engine attached (e.g. Stage
            2/3-style navigation/config-only sessions) - commands that
            need it (ping, show arp, show ip route) report a clear
            error rather than crashing when it's absent.
    """

    def __init__(
        self,
        registry: CommandRegistry,
        device: DeviceContext | None,
        history: CommandHistory | None = None,
        network: NetworkContext | None = None,
        workspace: LabContext | None = None,
    ) -> None:
        self.registry = registry
        self.device = device
        self.history = history if history is not None else CommandHistory()
        self.mode_stack = ModeStack()
        self.network = network
        self.workspace = workspace

    def prompt(self) -> str:
        """The current prompt string, e.g. ``"Router(config-if)#"``."""
        hostname = self.device.hostname if self.device is not None else "netsim"
        return f"{hostname}{self.mode_stack.prompt_suffix()}"

    def execute_line(self, line: str) -> ExecutionOutcome:
        """Parse and run one line of input.

        Args:
            line: The raw line as typed by the user.

        Returns:
            An :class:`ExecutionOutcome`. Errors are returned as data,
            never raised - callers (a terminal loop, a test) never need
            a try/except around this call for expected CLI failures.
        """
        stripped = line.strip()
        if stripped.endswith("?"):
            return self._handle_query(stripped)

        if tokenize(line):
            self.history.add(line)

        try:
            parsed = parse_line(line, self.mode_stack.current.mode, self.registry)
        except CliError as exc:
            return ExecutionOutcome(error=str(exc))

        if parsed is None:
            return ExecutionOutcome()

        context = CommandContext(
            device=self.device,
            args=parsed.args,
            raw_tokens=parsed.raw_tokens,
            history=tuple(self.history.all()),
            mode_params=self.mode_stack.current.params,
            network=self.network,
            workspace=self.workspace,
        )

        try:
            result = parsed.command.handler(context)
        except NetsimError as exc:
            return ExecutionOutcome(error=str(exc))

        if self.workspace is not None:
            self.device = self.workspace.active_device

        return self._apply_result(result)

    def _apply_result(self, result: CommandResult) -> ExecutionOutcome:
        output = tuple(result.output)

        if result.mode_pop_to_privileged:
            self.mode_stack.pop_to_privileged()

        if result.mode_pop:
            if self.mode_stack.at_base_mode():
                return ExecutionOutcome(output=output, exited=True)
            self.mode_stack.pop()

        if result.mode_push is not None:
            self.mode_stack.push(result.mode_push)

        if result.should_exit_cli:
            return ExecutionOutcome(output=output, exited=True)

        return ExecutionOutcome(output=output)

    def _handle_query(self, stripped_line: str) -> ExecutionOutcome:
        """Handle a line ending in `?` - never touches history or mode."""
        before_question_mark = stripped_line[:-1]

        if before_question_mark == "":
            tokens: list[str] = []
        elif before_question_mark.endswith(" "):
            tokens = before_question_mark.split()
            tokens.append("")
        else:
            tokens = before_question_mark.split()

        text = help_module.format_query(tokens, self.mode_stack.current.mode, self.registry)
        return ExecutionOutcome(output=tuple(text.splitlines()))
