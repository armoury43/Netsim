"""Errors raised by lab serialization and workspace operations."""

from __future__ import annotations

from netsim.core.exceptions import LabError


class LabFormatError(LabError):
    """A lab document is malformed, unsupported, or internally inconsistent."""


class LabStorageError(LabError):
    """A lab document could not be read or written."""


class LabOperationError(LabError):
    """A requested workspace operation cannot be completed."""
