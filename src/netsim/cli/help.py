"""Renders help text for `help` and context-sensitive `?` queries.

Everything here reads from :class:`netsim.cli.command.Command` metadata
(``name``, ``help_text``, ``allowed_modes``) and the resolution/
completion algorithms already defined elsewhere - there is no
duplicate knowledge of what commands exist.
"""

from __future__ import annotations

from netsim.cli.command import Command
from netsim.cli.completion import complete
from netsim.cli.modes import CliMode
from netsim.cli.registry import CommandRegistry

_NO_COMMANDS_MESSAGE = "% No commands available in this mode."
_UNKNOWN_MESSAGE = "% Unknown command."


def format_command_list(mode: CliMode, registry: CommandRegistry) -> str:
    """Render every non-hidden command available in a mode as an aligned table.

    Args:
        mode: The mode to list commands for.
        registry: The registry to read from.

    Returns:
        Multi-line text, one command per line, or a placeholder
        message if none are available.
    """
    commands = [c for c in registry.commands_for_mode(mode) if not c.hidden]
    if not commands:
        return _NO_COMMANDS_MESSAGE
    return _format_table((c.name, c.help_text) for c in commands)


def format_query(tokens: list[str], mode: CliMode, registry: CommandRegistry) -> str:
    """Render `?` output for the given input-so-far.

    Args:
        tokens: Tokens typed before the ``?``, in the same shape
            :func:`netsim.cli.completion.complete` expects (last
            element is the partial word, possibly ``""``).
        mode: The CLI's current mode.
        registry: The registry to read from.

    Returns:
        Multi-line text listing possible next words (with help text
        where a word completes a full command), or an "unknown"
        message if nothing matches.
    """
    if not tokens:
        return format_command_list(mode, registry)

    candidate_words = complete(tokens, mode, registry)
    if not candidate_words:
        return _UNKNOWN_MESSAGE

    prefix_tokens = tokens[:-1]
    rows: list[tuple[str, str]] = []
    for word in candidate_words:
        full_tokens = [*prefix_tokens, word]
        matching_command = _find_exact_variant(full_tokens, mode, registry)
        help_text = matching_command.help_text if matching_command else ""
        rows.append((word, help_text))

    return _format_table(rows)


def _find_exact_variant(tokens: list[str], mode: CliMode, registry: CommandRegistry) -> Command | None:
    """Find a command whose full name/alias exactly equals ``tokens``."""
    joined = " ".join(tokens)
    for command in registry.commands_for_mode(mode):
        if joined in command.all_name_variants():
            return command
    return None


def _format_table(rows: object) -> str:
    """Render (word, description) pairs as an aligned two-column table."""
    rows = list(rows)
    if not rows:
        return _NO_COMMANDS_MESSAGE
    width = max(len(word) for word, _ in rows)
    lines = []
    for word, description in rows:
        if description:
            lines.append(f"  {word.ljust(width)}  {description}")
        else:
            lines.append(f"  {word}")
    return "\n".join(lines)
