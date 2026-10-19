"""Tests for the CLI reload command performing a full device +
NetworkEngine reset (Stage 6): Device.reload() restores persistent
configuration only, while RIP-learned routes are cleared through the
NetworkEngine integration this command also drives, matching the same
CLI-owns-the-device+engine-integration pattern as ping/show commands.
"""

from __future__ import annotations

import unittest

from netsim.cli.device_commands import build_device_registry
from netsim.cli.session import CliSession
from netsim.devices.host import Host
from netsim.devices.router import Router
from netsim.network.engine import NetworkEngine
from netsim.network.topology import Topology


def _up(*interfaces) -> None:
    for iface in interfaces:
        iface.set_admin_up(True)


def _build_three_router_topology():
    """Same topology as test_engine_rip_stage6.py - duplicated
    intentionally rather than imported, keeping tests/network/ and
    tests/cli/ independent of each other, matching how other test
    files in this project never import fixtures across that boundary.
    R1 -- R2 -- R3 backbone, with a real host on a stub LAN behind
    each end router."""
    topology = Topology()
    r1 = Router(hostname="R1", interface_names=["GigabitEthernet0/0", "GigabitEthernet0/1"])
    r2 = Router(hostname="R2", interface_names=["GigabitEthernet0/0", "GigabitEthernet0/1"])
    r3 = Router(hostname="R3", interface_names=["GigabitEthernet0/0", "GigabitEthernet0/1"])
    host1 = Host(hostname="Host1")
    host3 = Host(hostname="Host3")
    for d in (r1, r2, r3, host1, host3):
        topology.add_device(d)
    topology.connect(r1.device_id, "GigabitEthernet0/0", r2.device_id, "GigabitEthernet0/0")
    topology.connect(r2.device_id, "GigabitEthernet0/1", r3.device_id, "GigabitEthernet0/0")
    topology.connect(r1.device_id, "GigabitEthernet0/1", host1.device_id, "Ethernet0")
    topology.connect(r3.device_id, "GigabitEthernet0/1", host3.device_id, "Ethernet0")

    r1.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.252")
    r1.configure_ipv4("GigabitEthernet0/1", "192.168.1.1", "255.255.255.0")
    r2.configure_ipv4("GigabitEthernet0/0", "10.0.0.2", "255.255.255.252")
    r2.configure_ipv4("GigabitEthernet0/1", "10.0.0.5", "255.255.255.252")
    r3.configure_ipv4("GigabitEthernet0/0", "10.0.0.6", "255.255.255.252")
    r3.configure_ipv4("GigabitEthernet0/1", "192.168.3.1", "255.255.255.0")
    host1.configure_ipv4("Ethernet0", "192.168.1.10", "255.255.255.0")
    host1.set_default_gateway("192.168.1.1")
    host3.configure_ipv4("Ethernet0", "192.168.3.10", "255.255.255.0")
    host3.set_default_gateway("192.168.3.1")

    for r in (r1, r2, r3):
        for name in r.interfaces:
            r.get_interface(name).set_admin_up(True)
        r.boot()
    for h in (host1, host3):
        h.get_interface("Ethernet0").set_admin_up(True)
        h.boot()

    r1.enable_rip("10.0.0.0", "255.0.0.0")
    r1.enable_rip("192.168.1.0", "255.255.255.0")
    r2.enable_rip("10.0.0.0", "255.0.0.0")
    r3.enable_rip("10.0.0.0", "255.0.0.0")
    r3.enable_rip("192.168.3.0", "255.255.255.0")

    return topology, r1, r2, r3, host1, host3


class TestCliReloadPerformsFullReset(unittest.TestCase):
    """The full pipeline, driven entirely through the CLI: reload must
    reset both persistent device config appropriately and the
    network engine's dynamic RIP state, exactly like a real reboot."""

    def test_cli_reload_clears_learned_routes_when_network_engine_attached(self) -> None:
        topology, r1, r2, r3, host1, host3 = _build_three_router_topology()
        engine = NetworkEngine(topology)
        engine.converge_rip()
        self.assertIsNotNone(engine.routing_table(r1.device_id).lookup("192.168.3.10"))

        session = CliSession(registry=build_device_registry(), device=r1, network=engine)
        session.execute_line("enable")
        outcome = session.execute_line("reload")

        self.assertIsNone(outcome.error)
        self.assertIsNone(engine.routing_table(r1.device_id).lookup("192.168.3.10"))

    def test_cli_reload_preserves_static_and_rip_configuration(self) -> None:
        topology, r1, r2, r3, host1, host3 = _build_three_router_topology()
        r1.add_static_route("172.16.0.0", "255.255.0.0", "10.0.0.2")
        r1.save_config()
        engine = NetworkEngine(topology)
        engine.converge_rip()

        session = CliSession(registry=build_device_registry(), device=r1, network=engine)
        session.execute_line("enable")
        session.execute_line("reload")

        self.assertIn("172.16.0.0/16", r1.static_routes)
        self.assertIn("10.0.0.0/8", {str(n) for n in r1.rip_networks})

    def test_cli_reload_without_network_engine_still_works(self) -> None:

        r1 = Router(hostname="R1", interface_names=["GigabitEthernet0/0"])
        session = CliSession(registry=build_device_registry(), device=r1, network=None)
        session.execute_line("enable")

        outcome = session.execute_line("reload")

        self.assertIsNone(outcome.error)

    def test_ping_fails_then_succeeds_again_through_full_cli_reload_cycle(self) -> None:
        topology, r1, r2, r3, host1, host3 = _build_three_router_topology()
        r1.save_config()
        engine = NetworkEngine(topology)
        engine.converge_rip()

        session = CliSession(registry=build_device_registry(), device=r1, network=engine)
        session.execute_line("enable")
        session.execute_line("reload")

        self.assertFalse(engine.ping(r1.device_id, "192.168.3.10").success)

        engine.converge_rip()

        self.assertTrue(engine.ping(r1.device_id, "192.168.3.10").success)

if __name__ == "__main__":
    unittest.main()
