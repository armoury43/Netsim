"""Interactive terminal loop.

This is intentionally the thinnest possible layer: it reads a line,
hands it to :meth:`netsim.cli.session.CliSession.execute_line`, and
prints whatever comes back. All actual behavior - parsing, validation,
mode transitions, help, history - lives in the engine modules and is
already fully tested without any terminal involved. ``input_fn`` and
``output_fn`` are injectable so this loop itself stays testable without
a real TTY.
"""

from __future__ import annotations

from typing import Callable

from netsim.cli.session import CliSession


def run(
    session: CliSession,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> None:
    """Run an interactive read-execute-print loop until the session exits.

    Args:
        session: The session driving mode/history/device state.
        input_fn: Called with the prompt string to obtain one line of
            input. Defaults to the built-in :func:`input`. Should raise
            :class:`EOFError` (as :func:`input` does on Ctrl-D) when
            there is no more input.
        output_fn: Called once per output/error line. Defaults to
            :func:`print`.
    """
    while True:
        try:
            line = input_fn(f"{session.prompt()} ")
        except EOFError:
            output_fn("")
            return

        outcome = session.execute_line(line)

        for text in outcome.output:
            output_fn(text)
        if outcome.error is not None:
            output_fn(outcome.error)

        if outcome.exited:
            return
