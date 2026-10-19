"""Structured topology and training-lab verification results."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LabCheckResult:
    """One check emitted by a lab verifier."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class LabVerificationReport:
    """The complete outcome of verifying a lab."""

    checks: tuple[LabCheckResult, ...]

    @property
    def passed(self) -> bool:
        """Whether every check passed (an empty report is not success)."""
        return bool(self.checks) and all(check.passed for check in self.checks)

    @property
    def passed_count(self) -> int:
        return sum(check.passed for check in self.checks)

    @property
    def failed_count(self) -> int:
        return sum(not check.passed for check in self.checks)
