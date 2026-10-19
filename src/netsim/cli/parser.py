"""Turns a raw typed line into a validated, ready-to-run command.

:func:`parse_line` is the only thing in the CLI that combines
tokenization, registry resolution, and argument validation into one
call. It raises the appropriate :mod:`netsim.cli.errors` subclass on
any failure rather than returning an error value, so callers
(:class:`netsim.cli.session.CliSession`) can use a single ``except
CliError`` to turn any parse failure into user-facing text.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Any

from netsim.cli.command import Command
from netsim.cli.errors import (
    AmbiguousCommandError,
    ArgumentValidationError,
    IncompleteCommandError,
    UnknownCommandError,
)
from netsim.cli.modes import CliMode
from netsim.cli.registry import (
    AmbiguousCommand,
    CommandRegistry,
    IncompleteCommand,
    ResolvedCommand,
    UnknownCommand,
)
from netsim.core.exceptions import ValidationError


@dataclass(frozen=True)
class ParsedCommand:
    """The result of successfully parsing one line of input.

    Attributes:
        command: The resolved command.
        args: Validated argument values, keyed by argument name.
        raw_tokens: Every token in the original line, unmodified.
    """

    command: Command
    args: dict[str, Any]
    raw_tokens: tuple[str, ...]


def tokenize(line: str) -> list[str]:
    """Split a line of input into whitespace-separated tokens.

    Blank lines and comment lines (starting with ``!``, matching the
    convention used for running-config comments) tokenize to an empty
    list, signaling "nothing to do" to the caller.

    Args:
        line: The raw line as typed by the user.

    Returns:
        The tokens, or an empty list for blank/comment input.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("!"):
        return []
    return stripped.split()


def parse_line(line: str, mode: CliMode, registry: CommandRegistry) -> ParsedCommand | None:
    """Parse and validate one line of input.

    Args:
        line: The raw line as typed by the user.
        mode: The CLI's current mode.
        registry: The command registry to resolve against.

    Returns:
        A :class:`ParsedCommand`, or ``None`` for blank/comment input.

    Raises:
        UnknownCommandError: No command matches the input at all.
        AmbiguousCommandError: The input's abbreviation matches more
            than one command.
        IncompleteCommandError: The input is a valid but incomplete
            prefix of a longer command.
        ArgumentValidationError: The command resolved, but its
            arguments are missing, extra, or fail validation.
    """
    tokens = tokenize(line)
    if not tokens:
        return None

    outcome = registry.resolve(tokens, mode)

    if isinstance(outcome, UnknownCommand):
        suggestion = _suggest(tokens, mode, registry)
        raise UnknownCommandError(tokens=tokens, suggestion=suggestion)

    if isinstance(outcome, AmbiguousCommand):
        raise AmbiguousCommandError(tokens=tokens, candidates=outcome.candidates)

    if isinstance(outcome, IncompleteCommand):
        raise IncompleteCommandError(tokens=tokens, candidates=outcome.candidates)

    assert isinstance(outcome, ResolvedCommand)
    args = _validate_arguments(outcome.command, outcome.remaining_args)
    return ParsedCommand(command=outcome.command, args=args, raw_tokens=tuple(tokens))


def _validate_arguments(command: Command, remaining: list[str]) -> dict[str, Any]:
    """Match remaining tokens positionally against a command's argument specs.

    All but the last declared argument consume exactly one token each.
    The *last* declared argument greedily consumes every remaining
    token, joined by single spaces - this matches real network-OS
    commands that take free text (e.g. an interface ``description``),
    without needing a distinct "greedy argument" flag in
    :class:`~netsim.cli.command.Argument`. A command with no arguments
    at all rejects any extra tokens outright.

    Raises:
        ArgumentValidationError: On missing required arguments, extra
            arguments where none are accepted, or a value that fails
            its validator.
    """
    argument_count = len(command.arguments)

    if argument_count == 0:
        if remaining:
            raise ArgumentValidationError(
                reason="This command does not accept any arguments.",
                command=command,
            )
        return {}

    args: dict[str, Any] = {}
    for index, spec in enumerate(command.arguments):
        is_last = index == argument_count - 1
        if index < len(remaining):
            raw_value = " ".join(remaining[index:]) if is_last else remaining[index]
            try:
                args[spec.name] = spec.validate(raw_value)
            except ValidationError as exc:
                raise ArgumentValidationError(reason=str(exc), command=command) from exc
        elif spec.required:
            raise ArgumentValidationError(
                reason=f"Missing required argument <{spec.name}>.",
                command=command,
            )
    return args


def _suggest(tokens: list[str], mode: CliMode, registry: CommandRegistry) -> str | None:
    """Best-effort "did you mean" suggestion for an unrecognized command.

    Purely cosmetic: never changes parse behavior, only the error
    message. Matches against the first word of every command/alias
    available in the current mode.
    """
    first_word_to_name: dict[str, str] = {}
    for command in registry.commands_for_mode(mode):
        for variant in command.all_name_variants():
            first_word = variant.split()[0]
            first_word_to_name.setdefault(first_word, command.name)

    matches = difflib.get_close_matches(tokens[0], first_word_to_name.keys(), n=1)
    if not matches:
        return None
    return first_word_to_name[matches[0]]
