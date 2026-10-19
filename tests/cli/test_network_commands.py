"""Tests for netsim.cli.network_commands.

Full-stack integration tests: real CliSession, real device_commands
registry extended with network commands, a real NetworkEngine over a
real Topology with real Router/Host devices. Nothing here is faked -
this is the same guarantee test_device_commands.py established for
Stage 3, extended to prove ping/show arp/show ip route actually
reflect simulated network state end to end.
"""

from __future__ import annotations

import unittest

from netsim.cli.device_commands import build_device_registry
from netsim.cli.network_commands import register_network_commands
from netsim.cli.session import CliSession
from netsim.devices.host import Host
from netsim.devices.router import Router
from netsim.network.engine import NetworkEngine
from netsim.network.topology import Topology


def _build_registry():
    registry = build_device_registry()
    register_network_commands(registry)
    return registry


class TestRegistryContents(unittest.TestCase):
    def test_network_commands_registered_alongside_device_commands(self) -> None:
        registry = _build_registry()
        names = {c.name for c in registry.all_commands()}
        self.assertIn("ping", names)
        self.assertIn("show arp", names)
        self.assertIn("show ip route", names)

        self.assertIn("hostname", names)
        self.assertIn("interface", names)


class TestPingCommand(unittest.TestCase):
    def setUp(self) -> None:
        self.topology = Topology()
        self.pc1 = Host(hostname="PC1")
        self.pc2 = Host(hostname="PC2")
        self.topology.add_device(self.pc1)
        self.topology.add_device(self.pc2)
        self.topology.connect(self.pc1.device_id, "Ethernet0", self.pc2.device_id, "Ethernet0")
        self.pc1.configure_ipv4("Ethernet0", "10.0.0.1", "255.255.255.0")
        self.pc2.configure_ipv4("Ethernet0", "10.0.0.2", "255.255.255.0")
        self.pc1.get_interface("Ethernet0").set_admin_up(True)
        self.pc2.get_interface("Ethernet0").set_admin_up(True)
        self.pc1.boot()
        self.pc2.boot()
        self.engine = NetworkEngine(self.topology)
        self.session = CliSession(registry=_build_registry(), device=self.pc1, network=self.engine)

    def test_successful_ping_reports_success(self) -> None:
        outcome = self.session.execute_line("ping 10.0.0.2")
        joined = "\n".join(outcome.output)
        self.assertIn("Success rate is 100 percent", joined)
        self.assertIsNone(outcome.error)

    def test_failed_ping_reports_failure_not_success(self) -> None:
        outcome = self.session.execute_line("ping 192.168.99.99")
        joined = "\n".join(outcome.output)
        self.assertIn("Success rate is 0 percent", joined)
        self.assertNotIn("100 percent", joined)

    def test_ping_without_network_engine_gives_clear_error(self) -> None:
        session = CliSession(registry=_build_registry(), device=self.pc1, network=None)
        outcome = session.execute_line("ping 10.0.0.2")
        self.assertIsNotNone(outcome.error)
        assert outcome.error is not None
        self.assertIn("network engine", outcome.error.lower())

    def test_ping_requires_a_destination_argument(self) -> None:
        outcome = self.session.execute_line("ping")
        self.assertIsNotNone(outcome.error)

    def test_invalid_ipv4_destinations_are_reported_as_cli_errors(self) -> None:
        for invalid in (
            "not-an-ip",
            "256.1.1.1",
            "2001:db8::1",
            "☃\x00broken",
            "1.2.3.4/24",
        ):
            with self.subTest(invalid=invalid):
                outcome = self.session.execute_line(f"ping {invalid}")
                self.assertIsNotNone(outcome.error)
                self.assertIn("valid IPv4 address", outcome.error)
                self.assertEqual(outcome.output, ())


class TestShowArpCommand(unittest.TestCase):
    def test_reflects_real_resolution_after_a_ping(self) -> None:
        topology = Topology()
        pc1 = Host(hostname="PC1")
        pc2 = Host(hostname="PC2")
        topology.add_device(pc1)
        topology.add_device(pc2)
        topology.connect(pc1.device_id, "Ethernet0", pc2.device_id, "Ethernet0")
        pc1.configure_ipv4("Ethernet0", "10.0.0.1", "255.255.255.0")
        pc2.configure_ipv4("Ethernet0", "10.0.0.2", "255.255.255.0")
        pc1.get_interface("Ethernet0").set_admin_up(True)
        pc2.get_interface("Ethernet0").set_admin_up(True)
        pc1.boot()
        pc2.boot()
        engine = NetworkEngine(topology)
        session = CliSession(registry=_build_registry(), device=pc1, network=engine)

        session.execute_line("ping 10.0.0.2")
        outcome = session.execute_line("show arp")

        joined = "\n".join(outcome.output)
        self.assertIn("10.0.0.2", joined)
        self.assertIn(pc2.get_interface("Ethernet0").mac_address, joined)

    def test_empty_before_any_resolution(self) -> None:
        topology = Topology()
        pc1 = Host(hostname="PC1")
        topology.add_device(pc1)
        engine = NetworkEngine(topology)
        session = CliSession(registry=_build_registry(), device=pc1, network=engine)

        outcome = session.execute_line("show arp")

        self.assertNotIn(".", "\n".join(outcome.output).replace("Protocol", ""))


class TestShowIpRouteCommand(unittest.TestCase):
    def test_reflects_real_connected_and_static_routes(self) -> None:
        topology = Topology()
        router = Router(interface_names=["GigabitEthernet0/0"])
        topology.add_device(router)
        router.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")
        router.get_interface("GigabitEthernet0/0").set_admin_up(True)
        router.add_static_route("192.168.5.0", "255.255.255.0", "10.0.0.99")
        engine = NetworkEngine(topology)
        session = CliSession(registry=_build_registry(), device=router, network=engine)

        outcome = session.execute_line("show ip route")

        joined = "\n".join(outcome.output)
        self.assertIn("10.0.0.0/24", joined)
        self.assertIn("192.168.5.0/24", joined)
        self.assertIn("10.0.0.99", joined)


class TestFullPingWalkthrough(unittest.TestCase):
    """Mirrors the exact CLI usage pattern from the brief:
    Router# ping 10.0.0.2"""

    def test_router_pings_directly_connected_host(self) -> None:
        topology = Topology()
        router = Router(hostname="Router", interface_names=["GigabitEthernet0/0"])
        host = Host(hostname="PC1")
        topology.add_device(router)
        topology.add_device(host)
        topology.connect(router.device_id, "GigabitEthernet0/0", host.device_id, "Ethernet0")
        router.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")
        host.configure_ipv4("Ethernet0", "10.0.0.2", "255.255.255.0")
        router.get_interface("GigabitEthernet0/0").set_admin_up(True)
        host.get_interface("Ethernet0").set_admin_up(True)
        router.boot()
        host.boot()

        engine = NetworkEngine(topology)
        session = CliSession(registry=_build_registry(), device=router, network=engine)
        session.execute_line("enable")

        outcome = session.execute_line("ping 10.0.0.2")

        self.assertIn("Success rate is 100 percent", "\n".join(outcome.output))

if __name__ == "__main__":
    unittest.main()
