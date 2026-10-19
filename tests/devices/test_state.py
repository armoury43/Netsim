"""Tests for netsim.devices.state."""

from __future__ import annotations

import unittest

from netsim.devices.errors import InvalidLifecycleTransitionError
from netsim.devices.state import DeviceState, validate_transition


class TestDeviceStateEnum(unittest.TestCase):
    def test_four_required_states_exist(self) -> None:
        expected = {"CREATED", "POWERED_OFF", "BOOTING", "READY"}
        actual = {member.name for member in DeviceState}
        self.assertEqual(actual, expected)


class TestValidateTransition(unittest.TestCase):
    def test_created_to_booting_is_valid(self) -> None:
        validate_transition(DeviceState.CREATED, DeviceState.BOOTING)

    def test_created_to_powered_off_is_invalid(self) -> None:

        with self.assertRaises(InvalidLifecycleTransitionError):
            validate_transition(DeviceState.CREATED, DeviceState.POWERED_OFF)

    def test_booting_to_ready_is_valid(self) -> None:
        validate_transition(DeviceState.BOOTING, DeviceState.READY)

    def test_ready_to_powered_off_is_valid(self) -> None:
        validate_transition(DeviceState.READY, DeviceState.POWERED_OFF)

    def test_powered_off_to_booting_is_valid(self) -> None:
        validate_transition(DeviceState.POWERED_OFF, DeviceState.BOOTING)

    def test_ready_to_booting_is_invalid(self) -> None:
        with self.assertRaises(InvalidLifecycleTransitionError):
            validate_transition(DeviceState.READY, DeviceState.BOOTING)

    def test_created_to_ready_is_invalid_without_booting(self) -> None:
        with self.assertRaises(InvalidLifecycleTransitionError):
            validate_transition(DeviceState.CREATED, DeviceState.READY)

    def test_powered_off_to_ready_is_invalid_without_booting(self) -> None:
        with self.assertRaises(InvalidLifecycleTransitionError):
            validate_transition(DeviceState.POWERED_OFF, DeviceState.READY)

    def test_booting_to_powered_off_is_invalid(self) -> None:
        with self.assertRaises(InvalidLifecycleTransitionError):
            validate_transition(DeviceState.BOOTING, DeviceState.POWERED_OFF)

if __name__ == "__main__":
    unittest.main()
