"""Tests for netsim.cli.device_interface.

The CLI must only ever talk to a device through this Protocol. These
tests use a minimal fake double (not a real Router/Switch, which don't
exist until Stage 3) to prove the contract is usable in isolation.
"""

from __future__ import annotations

import unittest

from netsim.cli.device_interface import DeviceContext


class FakeDevice:
    """Minimal stand-in used only to prove DeviceContext is satisfiable
    without any real networking logic - exactly what a real Router or
    Switch will provide once Stage 3 exists."""

    def __init__(self, hostname: str = "Router") -> None:
        self._hostname = hostname

    @property
    def hostname(self) -> str:
        return self._hostname

    def set_hostname(self, hostname: str) -> None:
        self._hostname = hostname


class IncompleteDevice:
    """Missing set_hostname - must NOT satisfy the protocol."""

    @property
    def hostname(self) -> str:
        return "Router"


class TestDeviceContextProtocol(unittest.TestCase):
    def test_fake_device_satisfies_protocol(self) -> None:
        device: DeviceContext = FakeDevice()
        self.assertIsInstance(device, DeviceContext)

    def test_incomplete_device_does_not_satisfy_protocol(self) -> None:
        self.assertNotIsInstance(IncompleteDevice(), DeviceContext)

    def test_hostname_round_trips_through_interface_only(self) -> None:
        device: DeviceContext = FakeDevice(hostname="R1")
        self.assertEqual(device.hostname, "R1")
        device.set_hostname("R2")
        self.assertEqual(device.hostname, "R2")

if __name__ == "__main__":
    unittest.main()
