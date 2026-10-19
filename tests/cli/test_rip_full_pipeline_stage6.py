"""Full-pipeline Stage 6 verification: CLI -> Router RIP configuration
-> persistent Router configuration -> NetworkEngine RIP convergence ->
learned routes -> routing table construction -> NetworkEngine.ping().

Every router in these tests is configured entirely through its own
CliSession (never by calling Router methods directly) - this is the
"do not fake any route output" requirement made concrete: everything
that ends up in a routing table, an ARP cache, or a ping result here
was put there by typing CLI commands.
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


def _registry():
    registry = build_device_registry()
    register_network_commands(registry)
    return registry


def _configure_router_via_cli(session: CliSession, lines: list[str]) -> None:
    for line in lines:
        outcome = session.execute_line(line)
        assert outcome.error is None, f"{line!r} -> {outcome.error}"


class TestFullRipPipelineThroughCli(unittest.TestCase):
    """router rip -> network -> save -> reload -> convergence -> ping,
    entirely through the CLI, across three real routers."""

    def _build_topology(self):
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
        return topology, r1, r2, r3, host1, host3

    def test_full_pipeline_configure_save_reload_converge_ping(self) -> None:
        topology, r1, r2, r3, host1, host3 = self._build_topology()
        engine = NetworkEngine(topology)
        registry = _registry()

        session_r1 = CliSession(registry=registry, device=r1, network=engine)
        _configure_router_via_cli(
            session_r1,
            [
                "enable",
                "configure terminal",
                "interface GigabitEthernet0/0",
                "ip address 10.0.0.1 255.255.255.252",
                "no shutdown",
                "exit",
                "interface GigabitEthernet0/1",
                "ip address 192.168.1.1 255.255.255.0",
                "no shutdown",
                "exit",
                "router rip",
                "network 10.0.0.0 255.0.0.0",
                "network 192.168.1.0 255.255.255.0",
                "end",
            ],
        )

        session_r2 = CliSession(registry=registry, device=r2, network=engine)
        _configure_router_via_cli(
            session_r2,
            [
                "enable",
                "configure terminal",
                "interface GigabitEthernet0/0",
                "ip address 10.0.0.2 255.255.255.252",
                "no shutdown",
                "exit",
                "interface GigabitEthernet0/1",
                "ip address 10.0.0.5 255.255.255.252",
                "no shutdown",
                "exit",
                "router rip",
                "network 10.0.0.0 255.0.0.0",
                "end",
            ],
        )

        session_r3 = CliSession(registry=registry, device=r3, network=engine)
        _configure_router_via_cli(
            session_r3,
            [
                "enable",
                "configure terminal",
                "interface GigabitEthernet0/0",
                "ip address 10.0.0.6 255.255.255.252",
                "no shutdown",
                "exit",
                "interface GigabitEthernet0/1",
                "ip address 192.168.3.1 255.255.255.0",
                "no shutdown",
                "exit",
                "router rip",
                "network 10.0.0.0 255.0.0.0",
                "network 192.168.3.0 255.255.255.0",
                "end",
            ],
        )

        host1.configure_ipv4("Ethernet0", "192.168.1.10", "255.255.255.0")
        host1.set_default_gateway("192.168.1.1")
        host1.get_interface("Ethernet0").set_admin_up(True)
        host3.configure_ipv4("Ethernet0", "192.168.3.10", "255.255.255.0")
        host3.set_default_gateway("192.168.3.1")
        host3.get_interface("Ethernet0").set_admin_up(True)
        for r in (r1, r2, r3):
            r.boot()
        host1.boot()
        host3.boot()

        pre_convergence = session_r1.execute_line("ping 192.168.3.10")
        self.assertIn("Success rate is 0 percent", "\n".join(pre_convergence.output))

        session_r1.execute_line("enable")
        session_r1.execute_line("copy running-config startup-config")

        show_before = session_r1.execute_line("show ip route")
        self.assertIn("192.168.1.0/24", "\n".join(show_before.output))

        reload_outcome = session_r1.execute_line("reload")
        self.assertIsNone(reload_outcome.error)
        self.assertEqual(r1.hostname, "R1")
        networks_after_reload = {str(n) for n in r1.rip_networks}
        self.assertIn("10.0.0.0/8", networks_after_reload)
        self.assertIn("192.168.1.0/24", networks_after_reload)

        rounds = engine.converge_rip()
        self.assertGreaterEqual(rounds, 0)

        show_after = session_r1.execute_line("show ip route")
        joined = "\n".join(show_after.output)
        self.assertIn("192.168.3.0/24", joined)
        self.assertIn("[120/2]", joined)

        ping_outcome = session_r1.execute_line("ping 192.168.3.10")
        self.assertIn("Success rate is 100 percent", "\n".join(ping_outcome.output))

        session_host1 = CliSession(registry=registry, device=host1, network=engine)
        host_ping = session_host1.execute_line("ping 192.168.3.10")
        self.assertIn("Success rate is 100 percent", "\n".join(host_ping.output))


class TestInvalidIncompleteAmbiguousRipCliInput(unittest.TestCase):
    def setUp(self) -> None:
        self.router = Router(interface_names=["GigabitEthernet0/0"])
        self.session = CliSession(registry=_registry(), device=self.router)
        self.session.execute_line("enable")
        self.session.execute_line("configure terminal")

    def test_network_missing_both_arguments(self) -> None:
        self.session.execute_line("router rip")
        outcome = self.session.execute_line("network")
        self.assertIsNotNone(outcome.error)
        assert outcome.error is not None
        self.assertIn("Invalid command", outcome.error)
        self.assertIn("network <network> <mask>", outcome.error)

    def test_network_missing_mask_argument(self) -> None:
        self.session.execute_line("router rip")
        outcome = self.session.execute_line("network 10.0.0.0")
        self.assertIsNotNone(outcome.error)
        assert outcome.error is not None
        self.assertIn("Missing required argument", outcome.error)

    def test_network_too_many_arguments(self) -> None:
        self.session.execute_line("router rip")
        outcome = self.session.execute_line("network 10.0.0.0 255.0.0.0 extra-garbage")
        self.assertIsNotNone(outcome.error)

    def test_network_outside_router_config_mode_is_unrecognized(self) -> None:

        outcome = self.session.execute_line("network 10.0.0.0 255.0.0.0")
        self.assertIsNotNone(outcome.error)
        assert outcome.error is not None
        self.assertIn("Unrecognized command", outcome.error)

    def test_router_protocol_argument_is_not_abbreviation_matched(self) -> None:

        self.session.execute_line("router ri")
        outcome = self.session.execute_line("network 10.0.0.0 255.0.0.0")
        self.assertIsNotNone(outcome.error)
        assert outcome.error is not None
        self.assertIn("not supported", outcome.error)
        self.assertEqual(self.router.rip_networks, frozenset())

    def test_abbreviated_network_command_still_resolves(self) -> None:

        self.session.execute_line("router rip")
        outcome = self.session.execute_line("net 10.0.0.0 255.0.0.0")
        self.assertIsNone(outcome.error)
        self.assertIn("10.0.0.0/8", {str(n) for n in self.router.rip_networks})

    def test_malformed_mask_shows_realistic_error(self) -> None:
        self.session.execute_line("router rip")
        outcome = self.session.execute_line("network 10.0.0.0 999.999.999.999")
        self.assertIsNotNone(outcome.error)
        assert outcome.error is not None
        self.assertIn("not a valid subnet mask", outcome.error)

if __name__ == "__main__":
    unittest.main()
