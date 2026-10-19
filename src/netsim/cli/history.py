"""Command history.

A small, self-contained ring buffer. Deliberately has no idea what a
"command" is - it stores whatever strings it's given - so it has no
dependency on :mod:`netsim.cli.command` or :mod:`netsim.cli.registry`.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

DEFAULT_MAX_SIZE = 500


class CommandHistory:
    """Bounded, ordered history of command-line entries.

    Args:
        max_size: Maximum number of entries retained. Oldest entries
            are dropped once this is exceeded.
    """

    def __init__(self, max_size: int = DEFAULT_MAX_SIZE) -> None:
        self._entries: deque[str] = deque(maxlen=max_size)

    def add(self, line: str) -> None:
        """Record one entry, unless it is blank.

        Args:
            line: The raw line to record. Leading/trailing whitespace
                is stripped; whitespace-only or empty input is ignored.
        """
        stripped = line.strip()
        if stripped:
            self._entries.append(stripped)

    def all(self) -> list[str]:
        """Every recorded entry, oldest first."""
        return list(self._entries)

    def last(self, n: int) -> list[str]:
        """The ``n`` most recent entries, oldest first.

        Args:
            n: How many entries to return. If more than the number of
                stored entries, all entries are returned.
        """
        if n <= 0:
            return []
        return list(self._entries)[-n:]

    def clear(self) -> None:
        """Discard all recorded entries."""
        self._entries.clear()

    def save_to_file(self, path: Path) -> None:
        """Persist history to a file, one entry per line.

        Args:
            path: Destination file. Parent directories are created if
                missing.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(self._entries) + ("\n" if self._entries else ""), encoding="utf-8")

    def load_from_file(self, path: Path) -> None:
        """Replace current history with entries loaded from a file.

        Args:
            path: Source file, one entry per line. If it does not
                exist, this is a no-op (a fresh session simply has no
                prior history).
        """
        if not path.exists():
            return
        self._entries.clear()
        for line in path.read_text(encoding="utf-8").splitlines():
            self.add(line)
