"""Tests for netsim.core.exceptions."""

from __future__ import annotations

import unittest

from netsim.core.exceptions import (
    CommandError,
    ConfigDirectoryError,
    ConfigurationError,
    DeviceError,
    LabError,
    NetsimError,
    NetworkSimulationError,
    ValidationError,
)


class TestNetsimError(unittest.TestCase):
    def test_message_is_stored_and_stringifies(self) -> None:
        error = NetsimError("something went wrong")
        self.assertEqual(error.message, "something went wrong")
        self.assertEqual(str(error), "something went wrong")

    def test_is_a_regular_exception(self) -> None:
        with self.assertRaises(NetsimError):
            raise NetsimError("boom")


class TestExceptionHierarchy(unittest.TestCase):
    """All specific exceptions must derive from NetsimError so callers
    can catch broadly if they want to."""

    def test_all_subclasses_derive_from_netsim_error(self) -> None:
        subclasses = [
            ConfigurationError,
            ConfigDirectoryError,
            ValidationError,
            CommandError,
            DeviceError,
            NetworkSimulationError,
            LabError,
        ]
        for subclass in subclasses:
            with self.subTest(subclass=subclass):
                self.assertTrue(issubclass(subclass, NetsimError))

    def test_config_directory_error_is_a_configuration_error(self) -> None:
        self.assertTrue(issubclass(ConfigDirectoryError, ConfigurationError))


class TestValidationError(unittest.TestCase):
    def test_carries_field_and_value_for_diagnostics(self) -> None:
        error = ValidationError(
            "not a valid IPv4 address", field="ip_address", value="999.1.1.1"
        )
        self.assertEqual(error.field, "ip_address")
        self.assertEqual(error.value, "999.1.1.1")
        self.assertIn("not a valid IPv4 address", str(error))

    def test_field_and_value_are_optional(self) -> None:
        error = ValidationError("generic failure")
        self.assertIsNone(error.field)
        self.assertIsNone(error.value)

if __name__ == "__main__":
    unittest.main()
