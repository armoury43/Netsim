"""Tests for netsim.network.rip.RipEngine.

Pure unit/integration tests against real Topology + Router objects -
no test doubles, matching every other network-layer test file. These
exercise the RIP algorithm itself, independent of NetworkEngine/ping -
see test_engine_rip_stage6.py for the full pipeline (CLI -> Router
config -> convergence -> ping).
"""

from __future__ import annotations

import ipaddress
import unittest

from netsim.devices.router import Router
from netsim.network.rip import INFINITY_METRIC, MAX_METRIC, RipEngine, RipLearnedRoute
from netsim.network.topology import Topology


def _up(*interfaces) -> None:
    for iface in interfaces:
        iface.set_admin_up(True)


def _build_chain():
    """R1 -- R2 -- R3 -- R4 chain, three /30 links, all RIP-enabled on
    10.0.0.0/8. Four routers (not three) so there's a genuinely
    2-hop-deep network to test: R2's own link to R3 is only 1 hop from
    R1 (R2 is directly attached to it), but R3's link to R4 is 2 hops
    from R1 (through both R2 and R3) - exactly what "metric increases
    hop by hop" needs to demonstrate."""
    topology = Topology()
    r1 = Router(hostname="R1", interface_names=["GigabitEthernet0/0"])
    r2 = Router(hostname="R2", interface_names=["GigabitEthernet0/0", "GigabitEthernet0/1"])
    r3 = Router(hostname="R3", interface_names=["GigabitEthernet0/0", "GigabitEthernet0/1"])
    r4 = Router(hostname="R4", interface_names=["GigabitEthernet0/0"])
    for d in (r1, r2, r3, r4):
        topology.add_device(d)
    topology.connect(r1.device_id, "GigabitEthernet0/0", r2.device_id, "GigabitEthernet0/0")
    topology.connect(r2.device_id, "GigabitEthernet0/1", r3.device_id, "GigabitEthernet0/0")
    topology.connect(r3.device_id, "GigabitEthernet0/1", r4.device_id, "GigabitEthernet0/0")

    r1.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.252")
    r2.configure_ipv4("GigabitEthernet0/0", "10.0.0.2", "255.255.255.252")
    r2.configure_ipv4("GigabitEthernet0/1", "10.0.0.5", "255.255.255.252")
    r3.configure_ipv4("GigabitEthernet0/0", "10.0.0.6", "255.255.255.252")
    r3.configure_ipv4("GigabitEthernet0/1", "10.0.0.9", "255.255.255.252")
    r4.configure_ipv4("GigabitEthernet0/0", "10.0.0.10", "255.255.255.252")

    for r, names in [
        (r1, ["GigabitEthernet0/0"]),
        (r2, ["GigabitEthernet0/0", "GigabitEthernet0/1"]),
        (r3, ["GigabitEthernet0/0", "GigabitEthernet0/1"]),
        (r4, ["GigabitEthernet0/0"]),
    ]:
        for name in names:
            r.get_interface(name).set_admin_up(True)
    return topology, r1, r2, r3, r4


class TestDirectlyConnectedRouters(unittest.TestCase):
    def setUp(self) -> None:
        self.topology = Topology()
        self.r1 = Router(hostname="R1", interface_names=["GigabitEthernet0/0"])
        self.r2 = Router(hostname="R2", interface_names=["GigabitEthernet0/0"])
        self.topology.add_device(self.r1)
        self.topology.add_device(self.r2)
        self.topology.connect(self.r1.device_id, "GigabitEthernet0/0", self.r2.device_id, "GigabitEthernet0/0")
        self.r1.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.252")
        self.r2.configure_ipv4("GigabitEthernet0/0", "10.0.0.2", "255.255.255.252")
        _up(self.r1.get_interface("GigabitEthernet0/0"), self.r2.get_interface("GigabitEthernet0/0"))
        self.r1.enable_rip("10.0.0.0", "255.255.255.252")
        self.r2.enable_rip("10.0.0.0", "255.255.255.252")

    def test_neither_router_learns_anything_about_its_own_directly_connected_link(self) -> None:
        engine = RipEngine(self.topology)
        engine.converge()
        self.assertEqual(engine.routes_for(self.r1.device_id), [])
        self.assertEqual(engine.routes_for(self.r2.device_id), [])


class TestThirdNetworkPropagation(unittest.TestCase):
    def test_network_via_non_participating_neighbor_still_propagates(self) -> None:

        topology = Topology()
        r1 = Router(hostname="R1", interface_names=["GigabitEthernet0/0"])
        r2 = Router(hostname="R2", interface_names=["GigabitEthernet0/0", "GigabitEthernet0/1"])
        lan_router = Router(hostname="LanRouter", interface_names=["GigabitEthernet0/0"])
        topology.add_device(r1)
        topology.add_device(r2)
        topology.add_device(lan_router)
        topology.connect(r1.device_id, "GigabitEthernet0/0", r2.device_id, "GigabitEthernet0/0")
        topology.connect(r2.device_id, "GigabitEthernet0/1", lan_router.device_id, "GigabitEthernet0/0")
        r1.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.252")
        r2.configure_ipv4("GigabitEthernet0/0", "10.0.0.2", "255.255.255.252")
        r2.configure_ipv4("GigabitEthernet0/1", "192.168.1.1", "255.255.255.0")
        lan_router.configure_ipv4("GigabitEthernet0/0", "192.168.1.2", "255.255.255.0")
        _up(
            r1.get_interface("GigabitEthernet0/0"),
            r2.get_interface("GigabitEthernet0/0"),
            r2.get_interface("GigabitEthernet0/1"),
            lan_router.get_interface("GigabitEthernet0/0"),
        )
        r1.enable_rip("10.0.0.0", "255.255.255.252")
        r2.enable_rip("10.0.0.0", "255.255.255.252")
        r2.enable_rip("192.168.1.0", "255.255.255.0")

        engine = RipEngine(topology)
        engine.converge()

        r1_routes = {str(r.network): r for r in engine.routes_for(r1.device_id)}
        self.assertIn("192.168.1.0/24", r1_routes)
        self.assertEqual(r1_routes["192.168.1.0/24"].metric, 1)


class TestMultiHopPropagation(unittest.TestCase):
    """R1 -- R2 -- R3 -- R4 chain: the R2-R3 link is only 1 hop from
    R1 (R2 is directly attached to it) - the R3-R4 link is the
    genuinely 2-hop-deep network, reached only through both R2 and R3."""

    def test_r1_learns_r3_r4_link_at_metric_two(self) -> None:
        topology, r1, r2, r3, r4 = _build_chain()
        for r in (r1, r2, r3, r4):
            r.enable_rip("10.0.0.0", "255.0.0.0")

        engine = RipEngine(topology)
        engine.converge()

        r1_routes = {str(r.network): r for r in engine.routes_for(r1.device_id)}
        self.assertIn("10.0.0.8/30", r1_routes)
        self.assertEqual(r1_routes["10.0.0.8/30"].metric, 2)

    def test_r1_learns_r2_r3_link_at_metric_one(self) -> None:

        topology, r1, r2, r3, r4 = _build_chain()
        for r in (r1, r2, r3, r4):
            r.enable_rip("10.0.0.0", "255.0.0.0")

        engine = RipEngine(topology)
        engine.converge()

        r1_routes = {str(r.network): r for r in engine.routes_for(r1.device_id)}
        self.assertIn("10.0.0.4/30", r1_routes)
        self.assertEqual(r1_routes["10.0.0.4/30"].metric, 1)

    def test_r4_learns_r1_r2_link_at_metric_two_symmetrically(self) -> None:
        topology, r1, r2, r3, r4 = _build_chain()
        for r in (r1, r2, r3, r4):
            r.enable_rip("10.0.0.0", "255.0.0.0")

        engine = RipEngine(topology)
        engine.converge()

        r4_routes = {str(r.network): r for r in engine.routes_for(r4.device_id)}
        self.assertIn("10.0.0.0/30", r4_routes)
        self.assertEqual(r4_routes["10.0.0.0/30"].metric, 2)

    def test_r2_learns_r3_r4_link_at_metric_one(self) -> None:
        topology, r1, r2, r3, r4 = _build_chain()
        for r in (r1, r2, r3, r4):
            r.enable_rip("10.0.0.0", "255.0.0.0")

        engine = RipEngine(topology)
        engine.converge()

        r2_routes = {str(r.network): r for r in engine.routes_for(r2.device_id)}
        self.assertIn("10.0.0.8/30", r2_routes)
        self.assertEqual(r2_routes["10.0.0.8/30"].metric, 1)

    def test_next_hop_for_learned_route_is_the_adjacent_router(self) -> None:
        topology, r1, r2, r3, r4 = _build_chain()
        for r in (r1, r2, r3, r4):
            r.enable_rip("10.0.0.0", "255.0.0.0")

        engine = RipEngine(topology)
        engine.converge()

        r1_routes = {str(r.network): r for r in engine.routes_for(r1.device_id)}

        self.assertEqual(str(r1_routes["10.0.0.8/30"].next_hop), "10.0.0.2")


class TestConvergenceIsDeterministic(unittest.TestCase):
    def test_repeated_convergence_from_fresh_engines_yields_identical_results(self) -> None:
        topology_a, r1_a, r2_a, r3_a, r4_a = _build_chain()
        for r in (r1_a, r2_a, r3_a, r4_a):
            r.enable_rip("10.0.0.0", "255.0.0.0")

        topology_b, r1_b, r2_b, r3_b, r4_b = _build_chain()
        for r in (r1_b, r2_b, r3_b, r4_b):
            r.enable_rip("10.0.0.0", "255.0.0.0")

        engine_a = RipEngine(topology_a)
        engine_a.converge()
        engine_b = RipEngine(topology_b)
        engine_b.converge()

        routes_a = {(str(r.network), r.metric) for r in engine_a.routes_for(r1_a.device_id)}
        routes_b = {(str(r.network), r.metric) for r in engine_b.routes_for(r1_b.device_id)}
        self.assertEqual(routes_a, routes_b)

    def test_converge_returns_bounded_round_count(self) -> None:
        topology = Topology()
        r1 = Router(hostname="R1", interface_names=["GigabitEthernet0/0"])
        r2 = Router(hostname="R2", interface_names=["GigabitEthernet0/0"])
        topology.add_device(r1)
        topology.add_device(r2)
        topology.connect(r1.device_id, "GigabitEthernet0/0", r2.device_id, "GigabitEthernet0/0")
        r1.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.252")
        r2.configure_ipv4("GigabitEthernet0/0", "10.0.0.2", "255.255.255.252")
        _up(r1.get_interface("GigabitEthernet0/0"), r2.get_interface("GigabitEthernet0/0"))
        r1.enable_rip("10.0.0.0", "255.255.255.252")
        r2.enable_rip("10.0.0.0", "255.255.255.252")

        engine = RipEngine(topology)
        rounds = engine.converge(max_rounds=16)
        self.assertLessEqual(rounds, 16)

    def test_second_convergence_call_is_a_stable_no_op(self) -> None:
        topology, r1, r2, r3, r4 = _build_chain()
        for r in (r1, r2, r3, r4):
            r.enable_rip("10.0.0.0", "255.0.0.0")

        engine = RipEngine(topology)
        engine.converge()
        first_result = {(str(r.network), r.metric) for r in engine.routes_for(r1.device_id)}

        engine.converge()
        second_result = {(str(r.network), r.metric) for r in engine.routes_for(r1.device_id)}

        self.assertEqual(first_result, second_result)


class TestDisabledOrUnconfiguredRip(unittest.TestCase):
    def test_router_with_no_rip_configuration_learns_nothing(self) -> None:
        topology, r1, r2, r3, r4 = _build_chain()

        engine = RipEngine(topology)
        engine.converge()

        self.assertEqual(engine.routes_for(r1.device_id), [])
        self.assertEqual(engine.routes_for(r4.device_id), [])

    def test_interface_outside_any_network_statement_does_not_participate(self) -> None:
        topology = Topology()
        r1 = Router(hostname="R1", interface_names=["GigabitEthernet0/0"])
        r2 = Router(hostname="R2", interface_names=["GigabitEthernet0/0"])
        topology.add_device(r1)
        topology.add_device(r2)
        topology.connect(r1.device_id, "GigabitEthernet0/0", r2.device_id, "GigabitEthernet0/0")
        r1.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.252")
        r2.configure_ipv4("GigabitEthernet0/0", "10.0.0.2", "255.255.255.252")
        _up(r1.get_interface("GigabitEthernet0/0"), r2.get_interface("GigabitEthernet0/0"))

        r1.enable_rip("192.168.99.0", "255.255.255.0")
        r2.enable_rip("10.0.0.0", "255.255.255.252")

        engine = RipEngine(topology)
        engine.converge()

        self.assertEqual(engine.routes_for(r2.device_id), [])


class TestSplitHorizon(unittest.TestCase):
    def test_route_is_not_advertised_back_out_the_interface_it_was_learned_from(self) -> None:
        topology, r1, r2, r3, r4 = _build_chain()
        for r in (r1, r2, r3, r4):
            r.enable_rip("10.0.0.0", "255.0.0.0")

        engine = RipEngine(topology)
        engine.converge()

        advertisement_back_to_r3 = engine._advertisement_from(r2, "GigabitEthernet0/1")
        self.assertNotIn("10.0.0.8/30", advertisement_back_to_r3)

        advertisement_toward_r1 = engine._advertisement_from(r2, "GigabitEthernet0/0")
        self.assertIn("10.0.0.8/30", advertisement_toward_r1)
        self.assertEqual(advertisement_toward_r1["10.0.0.8/30"], 2)


class TestUnreachableMetricHandling(unittest.TestCase):
    def test_max_metric_plus_one_equals_infinity(self) -> None:
        self.assertEqual(MAX_METRIC + 1, INFINITY_METRIC)

    def test_route_at_max_metric_is_not_advertised_further(self) -> None:
        topology = Topology()
        r1 = Router(hostname="R1", interface_names=["GigabitEthernet0/0", "GigabitEthernet0/1"])
        topology.add_device(r1)
        r1.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.252")
        r1.configure_ipv4("GigabitEthernet0/1", "10.0.0.5", "255.255.255.252")
        _up(r1.get_interface("GigabitEthernet0/0"), r1.get_interface("GigabitEthernet0/1"))
        r1.enable_rip("10.0.0.0", "255.0.0.0")

        engine = RipEngine(topology)

        engine._learned[r1.device_id] = {
            "192.168.50.0/24": RipLearnedRoute(
                network=ipaddress.ip_network("192.168.50.0/24"),
                metric=MAX_METRIC,
                next_hop=ipaddress.ip_address("10.0.0.2"),
                learned_via_interface="GigabitEthernet0/0",
            )
        }

        advertisement = engine._advertisement_from(r1, "GigabitEthernet0/1")
        self.assertNotIn("192.168.50.0/24", advertisement)

if __name__ == "__main__":
    unittest.main()
