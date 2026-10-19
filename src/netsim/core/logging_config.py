"""Centralized logging setup for netsim.

Every module should obtain its logger via ``logging.getLogger(__name__)``
as usual; this module is only responsible for *configuring* the root
``netsim`` logger once, in one place, so behavior is consistent across
the CLI, GUI, and test suite.

Nothing in the rest of the codebase should call ``logging.basicConfig``
directly — that would fight with this module and with the host
application (e.g. if netsim is imported as a library).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

LOGGER_NAME = "netsim"

_DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"

_configured = False


def configure_logging(
    *,
    level: int = logging.INFO,
    log_file: Path | None = None,
    stream=sys.stderr,
    force: bool = False,
) -> logging.Logger:
    """Configure the ``netsim`` logger tree.

    Safe to call multiple times: by default, only the first call has an
    effect, so importing netsim as a library doesn't clobber a host
    application's logging setup. Pass ``force=True`` to reconfigure
    (mainly useful in tests).

    Args:
        level: Minimum severity to emit, e.g. ``logging.DEBUG``.
        log_file: Optional path to also write logs to a file. Parent
            directories are created if missing.
        stream: Stream for the console handler (defaults to stderr, so
            stdout stays clean for CLI/user-facing output).
        force: If True, remove existing handlers and reconfigure.

    Returns:
        The configured ``netsim`` logger.
    """
    global _configured

    logger = logging.getLogger(LOGGER_NAME)

    if _configured and not force:
        return logger

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(fmt=_DEFAULT_FORMAT, datefmt=_DEFAULT_DATEFMT)

    console_handler = logging.StreamHandler(stream)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    _configured = True
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a logger nested under the ``netsim`` logger tree.

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        A standard library :class:`logging.Logger`.
    """
    return logging.getLogger(name)


def reset_logging_state_for_tests() -> None:
    """Reset the module-level "already configured" flag.

    Intended for use in the test suite only, so each test that cares
    about logging configuration can start from a clean slate.
    """
    global _configured
    _configured = False
