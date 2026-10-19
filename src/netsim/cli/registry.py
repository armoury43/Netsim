"""Command registry and resolution.

:class:`CommandRegistry` is deliberately dumb storage plus one lookup
algorithm (:meth:`CommandRegistry.resolve`). It knows nothing about
*which* commands exist - :mod:`netsim.cli.builtin_commands` (or any
future plugin) populates an instance by calling :meth:`register`.
Adding a new command anywhere in the codebase never requires changing
this file.

The resolution algorithm reproduces the IOS-style experience of typing
unambiguous abbreviations (``conf t`` for ``configure terminal``)
while still detecting genuine ambiguity and incomplete input, matching
the "realistic errors" requirement from the project brief.
"""

from __future__ import annotations

from dataclasses import dataclass

from netsim.cli.command import Command
from netsim.cli.errors import CliError
from netsim.cli.modes import CliMode


class DuplicateCommandError(CliError):
    """Raised when a command with an already-registered canonical name
    is registered again."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Command already registered: {name!r}")
        self.name = name


@dataclass(frozen=True)
class ResolvedCommand:
    """Input unambiguously identified exactly one command.

    Attributes:
        command: The matched command.
        remaining_args: Tokens after the command-name portion, to be
            validated by the parser against ``command.arguments``.
    """

    command: Command
    remaining_args: list[str]


@dataclass(frozen=True)
class AmbiguousCommand:
    """Input's leading token(s) are a valid prefix of more than one command.

    Attributes:
        tokens: The tokens as typed.
        candidates: Every command the input could have meant.
    """

    tokens: list[str]
    candidates: list[Command]


@dataclass(frozen=True)
class IncompleteCommand:
    """Input is a valid prefix of a longer command, but has too few words.

    Attributes:
        tokens: The tokens as typed.
        candidates: Commands the input could still complete into.
    """

    tokens: list[str]
    candidates: list[Command]


@dataclass(frozen=True)
class UnknownCommand:
    """Input does not match anything, even partially.

    Attributes:
        tokens: The tokens as typed.
    """

    tokens: list[str]

ResolveOutcome = ResolvedCommand | AmbiguousCommand | IncompleteCommand | UnknownCommand


class CommandRegistry:
    """Stores :class:`Command` definitions and resolves typed input against them."""

    def __init__(self) -> None:
        self._commands_by_name: dict[str, Command] = {}

    def register(self, command: Command) -> None:
        """Register a command.

        Args:
            command: The command to add.

        Raises:
            DuplicateCommandError: If a command with the same
                canonical ``name`` is already registered.
        """
        if command.name in self._commands_by_name:
            raise DuplicateCommandError(command.name)
        self._commands_by_name[command.name] = command

    def get_exact(self, name: str) -> Command | None:
        """Look up a command by its exact canonical name.

        Args:
            name: The canonical (full, un-abbreviated) command name.

        Returns:
            The command, or ``None`` if no command has that exact name.
        """
        return self._commands_by_name.get(name)

    def all_commands(self) -> list[Command]:
        """Every registered command, in registration order."""
        return list(self._commands_by_name.values())

    def commands_for_mode(self, mode: CliMode) -> list[Command]:
        """Commands available from a given mode, excluding hidden ones.

        Args:
            mode: The mode to filter by.

        Returns:
            Matching commands, sorted by canonical name.
        """
        return sorted(
            (c for c in self._commands_by_name.values() if mode in c.allowed_modes),
            key=lambda c: c.name,
        )

    def resolve(self, tokens: list[str], mode: CliMode) -> ResolveOutcome:
        """Resolve typed tokens to a command, IOS-abbreviation style.

        Each word of a command's name (or alias) is matched
        independently: the corresponding user token must be a
        case-insensitive prefix of it. The longest full match wins;
        if more than one command matches at the same (longest) length,
        that's ambiguous. If no full match exists but some command(s)
        would match given more words, that's incomplete rather than
        unknown.

        Args:
            tokens: Tokenized user input (see :func:`netsim.cli.parser.tokenize`).
            mode: The mode input is being resolved in - only commands
                whose ``allowed_modes`` includes this mode are considered.

        Returns:
            One of :class:`ResolvedCommand`, :class:`AmbiguousCommand`,
            :class:`IncompleteCommand`, or :class:`UnknownCommand`.
        """
        if not tokens:
            return UnknownCommand(tokens=tokens)

        candidates = self.commands_for_mode(mode)

        full_matches: list[tuple[Command, int]] = []
        partial_candidates: list[Command] = []

        for command in candidates:
            for variant in command.all_name_variants():
                variant_tokens = variant.split()
                length = len(variant_tokens)

                if len(tokens) >= length:
                    if _tokens_match(tokens[:length], variant_tokens):
                        full_matches.append((command, length))
                        break
                else:
                    if _tokens_match(tokens, variant_tokens[: len(tokens)]):
                        partial_candidates.append(command)
                        break

        if full_matches:
            max_length = max(length for _, length in full_matches)
            best = {id(cmd): cmd for cmd, length in full_matches if length == max_length}
            if len(best) > 1:
                return AmbiguousCommand(tokens=tokens, candidates=list(best.values()))
            command = next(iter(best.values()))
            remaining = tokens[max_length:]
            return ResolvedCommand(command=command, remaining_args=remaining)

        if partial_candidates:
            return IncompleteCommand(tokens=tokens, candidates=partial_candidates)

        return UnknownCommand(tokens=tokens)


def _tokens_match(input_tokens: list[str], name_tokens: list[str]) -> bool:
    """True if every input token is a case-insensitive prefix of the
    corresponding command-name token. Assumes equal length."""
    return all(
        bool(user_tok) and name_tok.lower().startswith(user_tok.lower())
        for user_tok, name_tok in zip(input_tokens, name_tokens)
    )
