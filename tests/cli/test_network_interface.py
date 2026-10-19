"""Tests for netsim.cli.network_interface.

Like test_device_interface_stage3.py, these check structural
satisfaction against the real NetworkEngine (not a test double) - the
whole point is proving the CLI and network engine connect without
either importing the other.
"""

from __future__ import annotations

import unittest

from netsim.cli.network_interface import NetworkContext, PingResultContext
from netsim.devices.host import Host
from netsim.network.engine import NetworkEngine
from netsim.network.icmp import PingFailureReason, PingResult
from netsim.network.topology import Topology


class TestPingResultContextProtocol(unittest.TestCase):
    def test_real_ping_result_satisfies_protocol(self) -> None:
        result = PingResult(success=True, destination="10.0.0.1")
        self.assertIsInstance(result, PingResultContext)

    def test_failed_ping_result_satisfies_protocol_too(self) -> None:
        result = PingResult(
            success=False,
            destination="10.0.0.1",
            reason=PingFailureReason.NO_ROUTE,
            detail="% No route",
        )
        self.assertIsInstance(result, PingResultContext)


class TestNetworkContextProtocol(unittest.TestCase):
    def test_network_engine_satisfies_protocol(self) -> None:
        topology = Topology()
        topology.add_device(Host())
        engine = NetworkEngine(topology)
        self.assertIsInstance(engine, NetworkContext)

if __name__ == "__main__":
    unittest.main()
