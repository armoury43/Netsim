"""Tests for the Stage 6 RIP integration into netsim.network.engine.NetworkEngine.

test_engine.py (Stage 4/5) is untouched. This is the full pipeline
below the CLI: Router RIP config -> NetworkEngine.converge_rip() ->
routing table construction -> ping()/show ip route.
"""

from __future__ import annotations

import unittest

from netsim.devices.host import Host
from netsim.devices.router import Router
from netsim.network.engine import NetworkEngine
from netsim.network.icmp import PingFailureReason
from netsim.network.topology import Topology


def _up(*interfaces) -> None:
    for iface in interfaces:
        iface.set_admin_up(True)


def _build_three_router_topology():
    """R1 -- R2 -- R3 backbone, with a real host on a stub LAN behind
    each end router (Host1 behind R1, Host3 behind R3) - neither stub
    network is directly known to the other end without RIP."""
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


class TestPingBeforeAndAfterConvergence(unittest.TestCase):
    def test_ping_fails_with_no_route_before_convergence(self) -> None:
        topology, r1, r2, r3, host1, host3 = _build_three_router_topology()
        engine = NetworkEngine(topology)

        result = engine.ping(r1.device_id, "192.168.3.10")

        self.assertFalse(result.success)
        self.assertEqual(result.reason, PingFailureReason.NO_ROUTE)

    def test_ping_succeeds_after_convergence(self) -> None:
        topology, r1, r2, r3, host1, host3 = _build_three_router_topology()
        engine = NetworkEngine(topology)

        engine.converge_rip()
        result = engine.ping(r1.device_id, "192.168.3.10")

        self.assertTrue(result.success, msg=result.detail)

    def test_host_to_host_across_the_whole_backbone_succeeds_after_convergence(self) -> None:

        topology, r1, r2, r3, host1, host3 = _build_three_router_topology()
        engine = NetworkEngine(topology)

        engine.converge_rip()
        result = engine.ping(host1.device_id, "192.168.3.10")

        self.assertTrue(result.success, msg=result.detail)

    def test_reverse_direction_also_succeeds_after_convergence(self) -> None:
        topology, r1, r2, r3, host1, host3 = _build_three_router_topology()
        engine = NetworkEngine(topology)

        engine.converge_rip()
        result = engine.ping(r3.device_id, "192.168.1.10")

        self.assertTrue(result.success, msg=result.detail)

    def test_converge_rip_returns_a_round_count(self) -> None:
        topology, r1, r2, r3, host1, host3 = _build_three_router_topology()
        engine = NetworkEngine(topology)

        rounds = engine.converge_rip()

        self.assertIsInstance(rounds, int)
        self.assertGreaterEqual(rounds, 0)


class TestRipAndStaticCoexist(unittest.TestCase):
    def test_static_route_wins_over_rip_for_identical_prefix(self) -> None:
        topology, r1, r2, r3, host1, host3 = _build_three_router_topology()
        engine = NetworkEngine(topology)
        engine.converge_rip()

        rip_learned = engine.routing_table(r1.device_id).lookup("192.168.3.10")
        assert rip_learned is not None
        self.assertEqual(rip_learned.source.name, "RIP")

        r1.add_static_route("192.168.3.0", "255.255.255.0", "10.0.0.2")

        route = engine.routing_table(r1.device_id).lookup("192.168.3.10")
        assert route is not None
        self.assertEqual(route.source.name, "STATIC")

    def test_ping_still_succeeds_with_both_configured(self) -> None:
        topology, r1, r2, r3, host1, host3 = _build_three_router_topology()
        r1.add_static_route("192.168.3.0", "255.255.255.0", "10.0.0.2")
        engine = NetworkEngine(topology)
        engine.converge_rip()

        result = engine.ping(r1.device_id, "192.168.3.10")
        self.assertTrue(result.success, msg=result.detail)


class TestShowIpRouteRendersRealRipState(unittest.TestCase):
    def test_rip_route_appears_with_r_code_and_real_metric(self) -> None:
        topology, r1, r2, r3, host1, host3 = _build_three_router_topology()
        engine = NetworkEngine(topology)
        engine.converge_rip()

        lines = engine.format_routing_table(r1.device_id)
        joined = "\n".join(lines)

        self.assertIn("192.168.3.0/24", joined)
        self.assertIn("R", joined)

        self.assertIn("[120/2]", joined)

    def test_no_rip_route_shown_before_convergence(self) -> None:
        topology, r1, r2, r3, host1, host3 = _build_three_router_topology()
        engine = NetworkEngine(topology)

        lines = engine.format_routing_table(r1.device_id)
        joined = "\n".join(lines)

        self.assertNotIn("192.168.3.0/24", joined)


class TestRipConfigVsLearnedRoutesAcrossReload(unittest.TestCase):
    """Static routes and RIP configuration are persistent device
    config (survive reload, per the Router-level tests already added
    in test_router_stage6.py). RIP-learned routes are ephemeral
    NetworkEngine state - Device.reload() alone has no way to touch
    them (and must not: Device stays completely independent of
    NetworkEngine), so clearing them is a separate, explicit step -
    see NetworkEngine.forget_rip_routes() and the CLI's reload command."""

    def test_learned_routes_present_before_any_reload(self) -> None:
        topology, r1, r2, r3, host1, host3 = _build_three_router_topology()
        engine = NetworkEngine(topology)
        engine.converge_rip()

        self.assertIsNotNone(engine.routing_table(r1.device_id).lookup("192.168.3.10"))

    def test_device_reload_alone_does_not_clear_engine_side_learned_routes(self) -> None:

        topology, r1, r2, r3, host1, host3 = _build_three_router_topology()
        engine = NetworkEngine(topology)
        engine.converge_rip()

        r1.reload()

        self.assertIsNotNone(engine.routing_table(r1.device_id).lookup("192.168.3.10"))

    def test_forget_rip_routes_clears_learned_state(self) -> None:
        topology, r1, r2, r3, host1, host3 = _build_three_router_topology()
        engine = NetworkEngine(topology)
        engine.converge_rip()
        self.assertIsNotNone(engine.routing_table(r1.device_id).lookup("192.168.3.10"))

        engine.forget_rip_routes(r1.device_id)

        self.assertIsNone(engine.routing_table(r1.device_id).lookup("192.168.3.10"))

    def test_static_routes_and_rip_config_survive_reload_plus_forget(self) -> None:
        topology, r1, r2, r3, host1, host3 = _build_three_router_topology()
        r1.add_static_route("172.16.0.0", "255.255.0.0", "10.0.0.2")
        r1.save_config()
        engine = NetworkEngine(topology)
        engine.converge_rip()

        r1.reload()
        engine.forget_rip_routes(r1.device_id)

        self.assertIn("172.16.0.0/16", r1.static_routes)
        networks = {str(n) for n in r1.rip_networks}
        self.assertIn("10.0.0.0/8", networks)
        self.assertIn("192.168.1.0/24", networks)

        self.assertIsNone(engine.routing_table(r1.device_id).lookup("192.168.3.10"))

    def test_reconvergence_relearns_routes_from_configured_neighbors(self) -> None:

        topology, r1, r2, r3, host1, host3 = _build_three_router_topology()
        r1.save_config()
        engine = NetworkEngine(topology)
        engine.converge_rip()
        r1.reload()
        engine.forget_rip_routes(r1.device_id)
        self.assertIsNone(engine.routing_table(r1.device_id).lookup("192.168.3.10"))

        engine.converge_rip()

        route = engine.routing_table(r1.device_id).lookup("192.168.3.10")
        self.assertIsNotNone(route)
        assert route is not None
        self.assertEqual(route.source.name, "RIP")
        self.assertEqual(route.metric, 2)

    def test_ping_works_again_after_reconvergence(self) -> None:
        topology, r1, r2, r3, host1, host3 = _build_three_router_topology()
        r1.save_config()
        engine = NetworkEngine(topology)
        engine.converge_rip()
        r1.reload()
        engine.forget_rip_routes(r1.device_id)

        self.assertFalse(engine.ping(r1.device_id, "192.168.3.10").success)

        engine.converge_rip()

        self.assertTrue(engine.ping(r1.device_id, "192.168.3.10").success)

if __name__ == "__main__":
    unittest.main()
