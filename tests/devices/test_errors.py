"""Tests for netsim.devices.errors."""

from __future__ import annotations

import unittest

from netsim.devices.errors import (
    DuplicateIPAddressError,
    DuplicateInterfaceError,
    InterfaceNotFoundError,
    InvalidLifecycleTransitionError,
    UnsupportedCapabilityError,
)
from netsim.core.exceptions import DeviceError


class TestDeviceErrorHierarchy(unittest.TestCase):
    def test_all_derive_from_device_error(self) -> None:
        for subclass in (
            InterfaceNotFoundError,
            DuplicateInterfaceError,
            InvalidLifecycleTransitionError,
            DuplicateIPAddressError,
            UnsupportedCapabilityError,
        ):
            with self.subTest(subclass=subclass):
                self.assertTrue(issubclass(subclass, DeviceError))


class TestInterfaceNotFoundError(unittest.TestCase):
    def test_message_names_the_interface(self) -> None:
        error = InterfaceNotFoundError("GigabitEthernet0/9")
        self.assertIn("GigabitEthernet0/9", str(error))

if __name__ == "__main__":
    unittest.main()
