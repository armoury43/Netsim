"""Project-wide exception hierarchy.

Every custom exception raised anywhere in ``netsim`` should ultimately
derive from :class:`NetsimError`. This lets front-ends (CLI, GUI) and
tests catch "anything netsim-specific went wrong" in one place, while
still allowing fine-grained handling of specific failure categories.

Design note: exceptions here are *data-carrying* on purpose. A CLI
front-end needs enough structured information (e.g. what was typed,
what was expected) to print a realistic, actionable error message —
not just a free-text string.
"""

from __future__ import annotations


class NetsimError(Exception):
    """Base class for all errors raised by netsim.

    Args:
        message: Human-readable description of the failure.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


class ConfigurationError(NetsimError):
    """Raised when application configuration is invalid or cannot be loaded."""


class ConfigDirectoryError(ConfigurationError):
    """Raised when the configuration directory cannot be created or accessed."""


class ValidationError(NetsimError):
    """Raised when a value fails validation (e.g. malformed IP address).

    Args:
        message: Human-readable description of the failure.
        field: Optional name of the field/parameter that failed validation.
        value: Optional offending value, kept for diagnostics/tests.
    """

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        value: object | None = None,
    ) -> None:
        super().__init__(message)
        self.field = field
        self.value = value


class CommandError(NetsimError):
    """Base class for CLI command-related errors (raised in later stages)."""


class DeviceError(NetsimError):
    """Base class for device-related errors (raised in later stages)."""


class NetworkSimulationError(NetsimError):
    """Base class for network engine errors (raised in later stages)."""


class LabError(NetsimError):
    """Base class for lab storage/import/export errors (raised in later stages)."""
