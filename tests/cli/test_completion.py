"""Tests for netsim.cli.completion.

The `complete` function is pure: given the tokens typed so far (last
token possibly empty, representing a trailing space) it returns the
possible next words. It has no knowledge of readline, stdin, or any
terminal - a future terminal.py binds this to actual key presses.
"""

from __future__ import annotations

import unittest

from netsim.cli.command import Command, CommandContext, CommandResult
from netsim.cli.completion import complete
from netsim.cli.modes import CliMode
from netsim.cli.registry import CommandRegistry


def _noop(context: CommandContext) -> CommandResult:
    return CommandResult()


class TestComplete(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = CommandRegistry()
        self.registry.register(
            Command(name="enable", handler=_noop, allowed_modes=frozenset({CliMode.USER_EXEC}))
        )
        self.registry.register(
            Command(
                name="configure terminal",
                handler=_noop,
                allowed_modes=frozenset({CliMode.PRIVILEGED_EXEC}),
            )
        )
        self.registry.register(
            Command(
                name="exit",
                handler=_noop,
                allowed_modes=frozenset({CliMode.USER_EXEC, CliMode.PRIVILEGED_EXEC}),
            )
        )

    def test_empty_input_lists_all_first_words_for_mode(self) -> None:
        result = complete([], CliMode.USER_EXEC, self.registry)
        self.assertEqual(set(result), {"enable", "exit"})

    def test_partial_first_word_filters_candidates(self) -> None:
        result = complete(["en"], CliMode.USER_EXEC, self.registry)
        self.assertEqual(result, ["enable"])

    def test_no_match_returns_empty_list(self) -> None:
        result = complete(["zz"], CliMode.USER_EXEC, self.registry)
        self.assertEqual(result, [])

    def test_trailing_space_after_full_first_word_offers_second_word(self) -> None:
        result = complete(["configure", ""], CliMode.PRIVILEGED_EXEC, self.registry)
        self.assertEqual(result, ["terminal"])

    def test_abbreviated_first_word_with_trailing_space_still_resolves(self) -> None:
        result = complete(["conf", ""], CliMode.PRIVILEGED_EXEC, self.registry)
        self.assertEqual(result, ["terminal"])

    def test_partial_second_word_filters(self) -> None:
        result = complete(["configure", "t"], CliMode.PRIVILEGED_EXEC, self.registry)
        self.assertEqual(result, ["terminal"])

    def test_respects_current_mode(self) -> None:

        result = complete(["conf"], CliMode.USER_EXEC, self.registry)
        self.assertEqual(result, [])

    def test_ambiguous_prefix_returns_all_matches_sorted(self) -> None:
        self.registry.register(
            Command(name="enter", handler=_noop, allowed_modes=frozenset({CliMode.USER_EXEC}))
        )
        result = complete(["en"], CliMode.USER_EXEC, self.registry)
        self.assertEqual(result, ["enable", "enter"])

if __name__ == "__main__":
    unittest.main()
