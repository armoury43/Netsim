"""CLI-specific exceptions.

All of these derive from :class:`netsim.core.exceptions.CommandError`,
so callers outside the CLI can catch "any CLI problem" broadly via the
core hierarchy, while :class:`CliSession` catches them specifically to
turn them into user-facing text instead of letting them propagate as
crashes.

Message formatting matters here: these strings are what the user sees
at the prompt, so they follow the "invalid command -> correct syntax"
convention described in the project brief rather than raw Python
repr/traceback text.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from netsim.core.exceptions import CommandError

if TYPE_CHECKING:
    from netsim.cli.command import Command


class CliError(CommandError):
    """Base class for all CLI engine errors."""


class UnknownCommandError(CliError):
    """Raised when no registered command matches the typed input at all.

    Args:
        tokens: The tokens the user typed.
        suggestion: Optional closest-match command name, for a
            "did you mean" hint.
    """

    def __init__(self, tokens: list[str], suggestion: str | None = None) -> None:
        typed = " ".join(tokens)
        message = f"% Unrecognized command: {typed!r}"
        if suggestion:
            message += f"\nDid you mean: {suggestion}?"
        super().__init__(message)
        self.tokens = tokens
        self.suggestion = suggestion


class AmbiguousCommandError(CliError):
    """Raised when a typed abbreviation matches more than one command.

    Args:
        tokens: The tokens the user typed.
        candidates: All commands the input could have meant.
    """

    def __init__(self, tokens: list[str], candidates: list["Command"]) -> None:
        typed = " ".join(tokens)
        names = ", ".join(sorted(c.name for c in candidates))
        message = f"% Ambiguous command: {typed!r}\nCould mean: {names}"
        super().__init__(message)
        self.tokens = tokens
        self.candidates = candidates


class IncompleteCommandError(CliError):
    """Raised when the typed input is a valid prefix of a longer command
    but doesn't yet contain enough words to resolve to one.

    Args:
        tokens: The tokens the user typed.
        candidates: Commands the input could still complete into.
    """

    def __init__(self, tokens: list[str], candidates: list["Command"]) -> None:
        typed = " ".join(tokens)
        message = f"% Incomplete command: {typed!r}"
        super().__init__(message)
        self.tokens = tokens
        self.candidates = candidates


class ArgumentValidationError(CliError):
    """Raised when a resolved command's arguments are missing, extra,
    or fail validation.

    Args:
        reason: Short description of what went wrong.
        command: The command whose usage should be shown.
    """

    def __init__(self, reason: str, command: "Command") -> None:
        message = f"Invalid command.\n{reason}\n\nCorrect syntax:\n\n  {command.usage()}"
        super().__init__(message)
        self.reason = reason
        self.command = command


class ModeStackError(CliError):
    """Raised for invalid mode transitions or pops."""


class NetworkUnavailableError(CliError):
    """Raised when a command needs the network engine (ping, show arp,
    show ip route) but this session has none attached."""

    def __init__(self) -> None:
        super().__init__("% No network engine is attached to this session")
