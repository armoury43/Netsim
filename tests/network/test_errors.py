"""Tests for netsim.network.errors."""

from __future__ import annotations

import unittest

from netsim.core.exceptions import NetworkSimulationError
from netsim.network.errors import (
    DeviceNotInTopologyError,
    InterfaceAlreadyConnectedError,
    InterfaceNotInTopologyError,
    LinkNotFoundError,
    SelfConnectionError,
)


class TestNetworkErrorHierarchy(unittest.TestCase):
    def test_all_derive_from_network_simulation_error(self) -> None:
        for subclass in (
            DeviceNotInTopologyError,
            InterfaceNotInTopologyError,
            SelfConnectionError,
            InterfaceAlreadyConnectedError,
            LinkNotFoundError,
        ):
            with self.subTest(subclass=subclass):
                self.assertTrue(issubclass(subclass, NetworkSimulationError))


class TestErrorMessages(unittest.TestCase):
    def test_device_not_in_topology_names_the_device(self) -> None:
        error = DeviceNotInTopologyError("abc-123")
        self.assertIn("abc-123", str(error))

    def test_self_connection_error_names_interface(self) -> None:
        error = SelfConnectionError("R1", "GigabitEthernet0/0")
        self.assertIn("GigabitEthernet0/0", str(error))

    def test_interface_already_connected_names_interface(self) -> None:
        error = InterfaceAlreadyConnectedError("R1", "GigabitEthernet0/0")
        self.assertIn("GigabitEthernet0/0", str(error))

if __name__ == "__main__":
    unittest.main()
