"""Autocomplete architecture.

:func:`complete` is a pure function: tokens in, candidate next-words
out. It has no idea it might one day be wired to a readline tab-key
binding or a GUI dropdown - that wiring is :mod:`netsim.cli.terminal`'s
job (or a future GUI's). Keeping the algorithm free of any I/O makes
it trivial to unit test and safe to reuse from multiple front-ends.
"""

from __future__ import annotations

from netsim.cli.modes import CliMode
from netsim.cli.registry import CommandRegistry


def complete(tokens: list[str], mode: CliMode, registry: CommandRegistry) -> list[str]:
    """Suggest possible next words for the given input-so-far.

    Args:
        tokens: Every word typed so far. The **last** element is the
            word currently being completed (possibly ``""``, meaning
            the user just typed a trailing space and is starting a new
            word). Elements before that are already-typed words, which
            may themselves be abbreviations.
        mode: The CLI's current mode - only commands available in this
            mode are considered.
        registry: The registry to search.

    Returns:
        Sorted, de-duplicated list of complete words that could come
        next. Empty if nothing matches.
    """
    prefix_tokens = tokens[:-1]
    partial = tokens[-1] if tokens else ""

    results: set[str] = set()
    for command in registry.commands_for_mode(mode):
        for variant in command.all_name_variants():
            variant_tokens = variant.split()
            if len(variant_tokens) <= len(prefix_tokens):
                continue
            if not _prefix_matches(prefix_tokens, variant_tokens):
                continue
            candidate_word = variant_tokens[len(prefix_tokens)]
            if candidate_word.lower().startswith(partial.lower()):
                results.add(candidate_word)

    return sorted(results)


def _prefix_matches(prefix_tokens: list[str], variant_tokens: list[str]) -> bool:
    """True if each already-typed token is a case-insensitive prefix of
    the corresponding word in a candidate command name/alias."""
    return all(
        variant_tokens[i].lower().startswith(tok.lower())
        for i, tok in enumerate(prefix_tokens)
    )
