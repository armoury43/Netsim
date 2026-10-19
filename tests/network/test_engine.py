"""Tests for netsim.network.engine.NetworkEngine.

These are integration tests by design (real Topology + real Router/
Switch/Host, no test doubles) - Stage 4's entire point is devices
actually communicating, so faking any of them would test nothing.
"""

from __future__ import annotations

import ipaddress
import unittest

from netsim.core.exceptions import ValidationError
from netsim.devices.acl import AclRule
from netsim.devices.host import Host
from netsim.devices.router import Router
from netsim.devices.switch import Switch
from netsim.network.engine import NetworkEngine
from netsim.network.icmp import PingFailureReason
from netsim.network.topology import Topology


def _up(*interfaces) -> None:
    for iface in interfaces:
        iface.set_admin_up(True)


class TestArpResolution(unittest.TestCase):
    def setUp(self) -> None:
        self.topology = Topology()
        self.pc1 = Host(hostname="PC1")
        self.pc2 = Host(hostname="PC2")
        self.topology.add_device(self.pc1)
        self.topology.add_device(self.pc2)
        self.topology.connect(self.pc1.device_id, "Ethernet0", self.pc2.device_id, "Ethernet0")
        self.pc1.configure_ipv4("Ethernet0", "10.0.0.1", "255.255.255.0")
        self.pc2.configure_ipv4("Ethernet0", "10.0.0.2", "255.255.255.0")
        _up(self.pc1.get_interface("Ethernet0"), self.pc2.get_interface("Ethernet0"))
        self.engine = NetworkEngine(self.topology)

    def test_resolve_returns_peer_mac(self) -> None:
        resolution = self.engine.resolve_arp(self.pc1.device_id, "Ethernet0", "10.0.0.2")
        assert resolution is not None
        self.assertEqual(resolution.mac_address, self.pc2.get_interface("Ethernet0").mac_address)

    def test_resolve_populates_requesters_cache(self) -> None:
        self.engine.resolve_arp(self.pc1.device_id, "Ethernet0", "10.0.0.2")
        self.assertEqual(
            self.engine.arp_table(self.pc1.device_id)["10.0.0.2"],
            self.pc2.get_interface("Ethernet0").mac_address,
        )

    def test_resolve_also_teaches_the_peer_the_requesters_mapping(self) -> None:

        self.engine.resolve_arp(self.pc1.device_id, "Ethernet0", "10.0.0.2")
        self.assertEqual(
            self.engine.arp_table(self.pc2.device_id)["10.0.0.1"],
            self.pc1.get_interface("Ethernet0").mac_address,
        )

    def test_resolve_unknown_ip_returns_none(self) -> None:
        resolution = self.engine.resolve_arp(self.pc1.device_id, "Ethernet0", "10.0.0.99")
        self.assertIsNone(resolution)

    def test_resolve_fails_when_link_down(self) -> None:
        self.topology.get_link(self.pc1.device_id, "Ethernet0").set_up(False)
        resolution = self.engine.resolve_arp(self.pc1.device_id, "Ethernet0", "10.0.0.2")
        self.assertIsNone(resolution)

    def test_stale_cache_entry_is_dropped_when_no_longer_resolvable(self) -> None:
        self.engine.resolve_arp(self.pc1.device_id, "Ethernet0", "10.0.0.2")
        self.assertIn("10.0.0.2", self.engine.arp_table(self.pc1.device_id))

        self.topology.get_link(self.pc1.device_id, "Ethernet0").set_up(False)
        self.engine.resolve_arp(self.pc1.device_id, "Ethernet0", "10.0.0.2")

        self.assertNotIn("10.0.0.2", self.engine.arp_table(self.pc1.device_id))


class TestArpResolutionCausesRealSwitchLearning(unittest.TestCase):
    """The Stage 5 completion requirement: an ARP request is genuinely
    a broadcast frame, so resolving it - on its own, before any ping
    or explicit data-plane send - must already teach every switch
    along the path the requester's real MAC address."""

    def setUp(self) -> None:
        self.topology = Topology()
        self.pc1 = Host(hostname="PC1")
        self.pc2 = Host(hostname="PC2")
        self.switch = Switch(interface_names=["FastEthernet0/1", "FastEthernet0/2"])
        for d in (self.pc1, self.pc2, self.switch):
            self.topology.add_device(d)
        self.topology.connect(self.pc1.device_id, "Ethernet0", self.switch.device_id, "FastEthernet0/1")
        self.topology.connect(self.pc2.device_id, "Ethernet0", self.switch.device_id, "FastEthernet0/2")
        self.pc1.configure_ipv4("Ethernet0", "10.0.0.1", "255.255.255.0")
        self.pc2.configure_ipv4("Ethernet0", "10.0.0.2", "255.255.255.0")
        _up(
            self.pc1.get_interface("Ethernet0"),
            self.pc2.get_interface("Ethernet0"),
            self.switch.get_interface("FastEthernet0/1"),
            self.switch.get_interface("FastEthernet0/2"),
        )
        self.engine = NetworkEngine(self.topology)

    def test_arp_resolution_alone_teaches_the_switch_the_requesters_mac(self) -> None:
        self.assertEqual(dict(self.switch.mac_table), {})

        self.engine.resolve_arp(self.pc1.device_id, "Ethernet0", "10.0.0.2")

        self.assertEqual(
            self.switch.mac_table[self.pc1.get_interface("Ethernet0").mac_address],
            "FastEthernet0/1",
        )

    def test_a_second_resolution_can_then_use_known_unicast_forwarding(self) -> None:

        self.engine.resolve_arp(self.pc1.device_id, "Ethernet0", "10.0.0.2")
        self.assertIn(self.pc1.get_interface("Ethernet0").mac_address, self.switch.mac_table)

        result = self.topology.l2_forward(
            self.pc2.device_id,
            "Ethernet0",
            self.pc2.get_interface("Ethernet0").mac_address,
            self.pc1.get_interface("Ethernet0").mac_address,
        )
        self.assertEqual(result, (self.pc1.device_id, "Ethernet0"))


class TestPingDestinationValidation(unittest.TestCase):
    def test_invalid_destination_is_a_netsim_validation_error_not_raw_valueerror(self) -> None:
        topology = Topology()
        pc1 = Host(hostname="PC1")
        topology.add_device(pc1)
        engine = NetworkEngine(topology)

        for invalid in ("not-an-ip", "256.0.0.1", "2001:db8::1", "10.0.0.1/24"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValidationError):
                    engine.ping(pc1.device_id, invalid)


class TestPingHostToHostDirect(unittest.TestCase):
    def test_successful_ping_between_directly_connected_hosts(self) -> None:
        topology = Topology()
        pc1 = Host(hostname="PC1")
        pc2 = Host(hostname="PC2")
        topology.add_device(pc1)
        topology.add_device(pc2)
        topology.connect(pc1.device_id, "Ethernet0", pc2.device_id, "Ethernet0")
        pc1.configure_ipv4("Ethernet0", "10.0.0.1", "255.255.255.0")
        pc2.configure_ipv4("Ethernet0", "10.0.0.2", "255.255.255.0")
        _up(pc1.get_interface("Ethernet0"), pc2.get_interface("Ethernet0"))
        pc1.boot()
        pc2.boot()

        result = NetworkEngine(topology).ping(pc1.device_id, "10.0.0.2")

        self.assertTrue(result.success)
        self.assertIsNone(result.reason)


class TestPingHostToRouterAndBack(unittest.TestCase):
    def setUp(self) -> None:
        self.topology = Topology()
        self.host = Host(hostname="PC1")
        self.router = Router(interface_names=["GigabitEthernet0/0"])
        self.topology.add_device(self.host)
        self.topology.add_device(self.router)
        self.topology.connect(self.host.device_id, "Ethernet0", self.router.device_id, "GigabitEthernet0/0")
        self.host.configure_ipv4("Ethernet0", "10.0.0.10", "255.255.255.0")
        self.router.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")
        _up(self.host.get_interface("Ethernet0"), self.router.get_interface("GigabitEthernet0/0"))
        self.host.boot()
        self.router.boot()
        self.engine = NetworkEngine(self.topology)

    def test_host_pings_router(self) -> None:
        result = self.engine.ping(self.host.device_id, "10.0.0.1")
        self.assertTrue(result.success)

    def test_router_pings_host(self) -> None:
        result = self.engine.ping(self.router.device_id, "10.0.0.10")
        self.assertTrue(result.success)


class TestPingRouterToRouter(unittest.TestCase):
    def test_directly_linked_routers_ping_each_other(self) -> None:
        topology = Topology()
        r1 = Router(interface_names=["GigabitEthernet0/0"])
        r2 = Router(interface_names=["GigabitEthernet0/0"])
        topology.add_device(r1)
        topology.add_device(r2)
        topology.connect(r1.device_id, "GigabitEthernet0/0", r2.device_id, "GigabitEthernet0/0")
        r1.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.252")
        r2.configure_ipv4("GigabitEthernet0/0", "10.0.0.2", "255.255.255.252")
        _up(r1.get_interface("GigabitEthernet0/0"), r2.get_interface("GigabitEthernet0/0"))
        r1.boot()
        r2.boot()

        engine = NetworkEngine(topology)
        self.assertTrue(engine.ping(r1.device_id, "10.0.0.2").success)
        self.assertTrue(engine.ping(r2.device_id, "10.0.0.1").success)


class TestPingSwitchMediated(unittest.TestCase):
    def test_two_hosts_through_a_switch(self) -> None:
        topology = Topology()
        pc1 = Host(hostname="PC1")
        pc2 = Host(hostname="PC2")
        switch = Switch(interface_names=["FastEthernet0/1", "FastEthernet0/2"])
        for d in (pc1, pc2, switch):
            topology.add_device(d)
        topology.connect(pc1.device_id, "Ethernet0", switch.device_id, "FastEthernet0/1")
        topology.connect(pc2.device_id, "Ethernet0", switch.device_id, "FastEthernet0/2")
        pc1.configure_ipv4("Ethernet0", "10.0.0.1", "255.255.255.0")
        pc2.configure_ipv4("Ethernet0", "10.0.0.2", "255.255.255.0")
        _up(
            pc1.get_interface("Ethernet0"),
            pc2.get_interface("Ethernet0"),
            switch.get_interface("FastEthernet0/1"),
            switch.get_interface("FastEthernet0/2"),
        )
        pc1.boot()
        pc2.boot()
        switch.boot()

        result = NetworkEngine(topology).ping(pc1.device_id, "10.0.0.2")
        self.assertTrue(result.success)

    def test_ping_causes_the_switch_to_learn_real_mac_addresses(self) -> None:

        topology = Topology()
        pc1 = Host(hostname="PC1")
        pc2 = Host(hostname="PC2")
        switch = Switch(interface_names=["FastEthernet0/1", "FastEthernet0/2"])
        for d in (pc1, pc2, switch):
            topology.add_device(d)
        topology.connect(pc1.device_id, "Ethernet0", switch.device_id, "FastEthernet0/1")
        topology.connect(pc2.device_id, "Ethernet0", switch.device_id, "FastEthernet0/2")
        pc1.configure_ipv4("Ethernet0", "10.0.0.1", "255.255.255.0")
        pc2.configure_ipv4("Ethernet0", "10.0.0.2", "255.255.255.0")
        _up(
            pc1.get_interface("Ethernet0"),
            pc2.get_interface("Ethernet0"),
            switch.get_interface("FastEthernet0/1"),
            switch.get_interface("FastEthernet0/2"),
        )
        pc1.boot()
        pc2.boot()
        switch.boot()
        self.assertEqual(dict(switch.mac_table), {})

        NetworkEngine(topology).ping(pc1.device_id, "10.0.0.2")

        self.assertEqual(
            switch.mac_table[pc1.get_interface("Ethernet0").mac_address], "FastEthernet0/1"
        )


class TestPingMultiHopThroughTwoRouters(unittest.TestCase):
    """PC1 -> Switch -> R1 -> R2 -> PC2, exactly the scenario named in
    the Stage 4 brief - requires static routes since no dynamic
    routing protocol exists yet."""

    def test_full_topology_end_to_end(self) -> None:
        topology = Topology()
        pc1 = Host(hostname="PC1")
        pc2 = Host(hostname="PC2")
        switch = Switch(interface_names=["FastEthernet0/1", "FastEthernet0/2"])
        r1 = Router(interface_names=["GigabitEthernet0/0", "GigabitEthernet0/1"])
        r2 = Router(interface_names=["GigabitEthernet0/0", "GigabitEthernet0/1"])
        for d in (pc1, pc2, switch, r1, r2):
            topology.add_device(d)

        topology.connect(pc1.device_id, "Ethernet0", switch.device_id, "FastEthernet0/1")
        topology.connect(r1.device_id, "GigabitEthernet0/0", switch.device_id, "FastEthernet0/2")
        topology.connect(r1.device_id, "GigabitEthernet0/1", r2.device_id, "GigabitEthernet0/0")
        topology.connect(r2.device_id, "GigabitEthernet0/1", pc2.device_id, "Ethernet0")

        pc1.configure_ipv4("Ethernet0", "192.168.1.10", "255.255.255.0")
        pc1.set_default_gateway("192.168.1.1")
        r1.configure_ipv4("GigabitEthernet0/0", "192.168.1.1", "255.255.255.0")
        r1.configure_ipv4("GigabitEthernet0/1", "10.0.0.1", "255.255.255.252")
        r2.configure_ipv4("GigabitEthernet0/0", "10.0.0.2", "255.255.255.252")
        r2.configure_ipv4("GigabitEthernet0/1", "192.168.2.1", "255.255.255.0")
        pc2.configure_ipv4("Ethernet0", "192.168.2.10", "255.255.255.0")
        pc2.set_default_gateway("192.168.2.1")

        r1.add_static_route("192.168.2.0", "255.255.255.0", "10.0.0.2")
        r2.add_static_route("192.168.1.0", "255.255.255.0", "10.0.0.1")

        for device, interfaces in [
            (pc1, ["Ethernet0"]),
            (pc2, ["Ethernet0"]),
            (switch, ["FastEthernet0/1", "FastEthernet0/2"]),
            (r1, ["GigabitEthernet0/0", "GigabitEthernet0/1"]),
            (r2, ["GigabitEthernet0/0", "GigabitEthernet0/1"]),
        ]:
            for name in interfaces:
                device.get_interface(name).set_admin_up(True)
            device.boot()

        engine = NetworkEngine(topology)
        result = engine.ping(pc1.device_id, "192.168.2.10")

        self.assertTrue(result.success, msg=result.detail)


class TestPingFailureInterfaceDown(unittest.TestCase):
    def test_source_interface_shutdown_removes_its_connected_route(self) -> None:

        topology = Topology()
        pc1 = Host(hostname="PC1")
        pc2 = Host(hostname="PC2")
        topology.add_device(pc1)
        topology.add_device(pc2)
        topology.connect(pc1.device_id, "Ethernet0", pc2.device_id, "Ethernet0")
        pc1.configure_ipv4("Ethernet0", "10.0.0.1", "255.255.255.0")
        pc2.configure_ipv4("Ethernet0", "10.0.0.2", "255.255.255.0")
        pc2.get_interface("Ethernet0").set_admin_up(True)
        pc1.boot()
        pc2.boot()

        result = NetworkEngine(topology).ping(pc1.device_id, "10.0.0.2")

        self.assertFalse(result.success)
        self.assertEqual(result.reason, PingFailureReason.NO_ROUTE)

    def test_engine_still_defends_against_a_down_outgoing_interface(self) -> None:

        topology = Topology()
        pc1 = Host(hostname="PC1")
        pc2 = Host(hostname="PC2")
        topology.add_device(pc1)
        topology.add_device(pc2)
        topology.connect(pc1.device_id, "Ethernet0", pc2.device_id, "Ethernet0")
        pc1.configure_ipv4("Ethernet0", "10.0.0.1", "255.255.255.0")
        pc2.configure_ipv4("Ethernet0", "10.0.0.2", "255.255.255.0")
        _up(pc1.get_interface("Ethernet0"), pc2.get_interface("Ethernet0"))
        pc1.boot()
        pc2.boot()

        engine = NetworkEngine(topology)

        self.assertTrue(engine.ping(pc1.device_id, "10.0.0.2").success)

        pc1.get_interface("Ethernet0").set_admin_up(False)
        result = engine.ping(pc1.device_id, "10.0.0.2")
        self.assertFalse(result.success)


class TestPingFailureLinkDown(unittest.TestCase):
    def test_link_down_between_hosts(self) -> None:
        topology = Topology()
        pc1 = Host(hostname="PC1")
        pc2 = Host(hostname="PC2")
        topology.add_device(pc1)
        topology.add_device(pc2)
        link = topology.connect(pc1.device_id, "Ethernet0", pc2.device_id, "Ethernet0")
        pc1.configure_ipv4("Ethernet0", "10.0.0.1", "255.255.255.0")
        pc2.configure_ipv4("Ethernet0", "10.0.0.2", "255.255.255.0")
        _up(pc1.get_interface("Ethernet0"), pc2.get_interface("Ethernet0"))
        pc1.boot()
        pc2.boot()
        link.set_up(False)

        result = NetworkEngine(topology).ping(pc1.device_id, "10.0.0.2")

        self.assertFalse(result.success)
        self.assertEqual(result.reason, PingFailureReason.LINK_DOWN)


class TestPingFailureNoRoute(unittest.TestCase):
    def test_unrelated_subnets_with_no_router_between_them(self) -> None:

        topology = Topology()
        pc1 = Host(hostname="PC1")
        pc2 = Host(hostname="PC2")
        topology.add_device(pc1)
        topology.add_device(pc2)
        topology.connect(pc1.device_id, "Ethernet0", pc2.device_id, "Ethernet0")
        pc1.configure_ipv4("Ethernet0", "192.168.1.10", "255.255.255.0")
        pc2.configure_ipv4("Ethernet0", "192.168.2.10", "255.255.255.0")
        _up(pc1.get_interface("Ethernet0"), pc2.get_interface("Ethernet0"))
        pc1.boot()
        pc2.boot()

        result = NetworkEngine(topology).ping(pc1.device_id, "192.168.2.10")

        self.assertFalse(result.success)
        self.assertEqual(result.reason, PingFailureReason.NO_ROUTE)

    def test_missing_static_route_for_far_subnet(self) -> None:
        topology = Topology()
        pc1 = Host(hostname="PC1")
        r1 = Router(interface_names=["GigabitEthernet0/0"])
        topology.add_device(pc1)
        topology.add_device(r1)
        topology.connect(pc1.device_id, "Ethernet0", r1.device_id, "GigabitEthernet0/0")
        pc1.configure_ipv4("Ethernet0", "10.0.0.10", "255.255.255.0")
        pc1.set_default_gateway("10.0.0.1")
        r1.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")
        _up(pc1.get_interface("Ethernet0"), r1.get_interface("GigabitEthernet0/0"))
        pc1.boot()
        r1.boot()

        result = NetworkEngine(topology).ping(pc1.device_id, "192.168.99.5")

        self.assertFalse(result.success)
        self.assertEqual(result.reason, PingFailureReason.NO_ROUTE)


class TestPingFailureArpUnresolved(unittest.TestCase):
    def test_correct_subnet_but_no_device_has_that_address(self) -> None:
        topology = Topology()
        pc1 = Host(hostname="PC1")
        pc2 = Host(hostname="PC2")
        topology.add_device(pc1)
        topology.add_device(pc2)
        topology.connect(pc1.device_id, "Ethernet0", pc2.device_id, "Ethernet0")
        pc1.configure_ipv4("Ethernet0", "10.0.0.1", "255.255.255.0")
        pc2.configure_ipv4("Ethernet0", "10.0.0.2", "255.255.255.0")
        _up(pc1.get_interface("Ethernet0"), pc2.get_interface("Ethernet0"))
        pc1.boot()
        pc2.boot()

        result = NetworkEngine(topology).ping(pc1.device_id, "10.0.0.50")

        self.assertFalse(result.success)
        self.assertEqual(result.reason, PingFailureReason.ARP_UNRESOLVED)


class TestPingFailureHostOffline(unittest.TestCase):
    def test_source_never_booted(self) -> None:
        topology = Topology()
        pc1 = Host(hostname="PC1")
        pc2 = Host(hostname="PC2")
        topology.add_device(pc1)
        topology.add_device(pc2)
        topology.connect(pc1.device_id, "Ethernet0", pc2.device_id, "Ethernet0")
        pc1.configure_ipv4("Ethernet0", "10.0.0.1", "255.255.255.0")
        pc2.configure_ipv4("Ethernet0", "10.0.0.2", "255.255.255.0")
        _up(pc1.get_interface("Ethernet0"), pc2.get_interface("Ethernet0"))
        pc2.boot()

        result = NetworkEngine(topology).ping(pc1.device_id, "10.0.0.2")

        self.assertFalse(result.success)
        self.assertEqual(result.reason, PingFailureReason.HOST_OFFLINE)


class TestPingFailureDestinationUnreachable(unittest.TestCase):
    def test_destination_host_powered_off(self) -> None:
        topology = Topology()
        pc1 = Host(hostname="PC1")
        pc2 = Host(hostname="PC2")
        topology.add_device(pc1)
        topology.add_device(pc2)
        topology.connect(pc1.device_id, "Ethernet0", pc2.device_id, "Ethernet0")
        pc1.configure_ipv4("Ethernet0", "10.0.0.1", "255.255.255.0")
        pc2.configure_ipv4("Ethernet0", "10.0.0.2", "255.255.255.0")
        _up(pc1.get_interface("Ethernet0"), pc2.get_interface("Ethernet0"))
        pc1.boot()

        result = NetworkEngine(topology).ping(pc1.device_id, "10.0.0.2")

        self.assertFalse(result.success)
        self.assertEqual(result.reason, PingFailureReason.DESTINATION_UNREACHABLE)


class TestAclEnforcement(unittest.TestCase):
    """ACL evaluation is real: the CLI/device layer stores rules and
    interface application (see test_router_acl_stage7.py); this is
    where ping() actually consults them against live traffic."""

    def _build(self):
        topology = Topology()
        pc1 = Host(hostname="PC1")
        r1 = Router(hostname="R1", interface_names=["GigabitEthernet0/0", "GigabitEthernet0/1"])
        pc2 = Host(hostname="PC2")
        topology.add_device(pc1)
        topology.add_device(r1)
        topology.add_device(pc2)
        topology.connect(pc1.device_id, "Ethernet0", r1.device_id, "GigabitEthernet0/0")
        topology.connect(r1.device_id, "GigabitEthernet0/1", pc2.device_id, "Ethernet0")
        pc1.configure_ipv4("Ethernet0", "10.0.0.10", "255.255.255.0")
        r1.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")
        r1.configure_ipv4("GigabitEthernet0/1", "192.168.1.1", "255.255.255.0")
        pc2.configure_ipv4("Ethernet0", "192.168.1.10", "255.255.255.0")
        pc1.set_default_gateway("10.0.0.1")
        pc2.set_default_gateway("192.168.1.1")
        _up(
            pc1.get_interface("Ethernet0"),
            r1.get_interface("GigabitEthernet0/0"),
            r1.get_interface("GigabitEthernet0/1"),
            pc2.get_interface("Ethernet0"),
        )
        pc1.boot()
        r1.boot()
        pc2.boot()
        return topology, pc1, r1, pc2

    def test_ping_succeeds_with_no_acl_applied(self) -> None:
        topology, pc1, r1, pc2 = self._build()
        result = NetworkEngine(topology).ping(pc1.device_id, "192.168.1.10")
        self.assertTrue(result.success)

    def test_outbound_acl_deny_blocks_ping(self) -> None:
        topology, pc1, r1, pc2 = self._build()
        acl = r1.get_or_create_access_list(1)
        acl.add_rule(AclRule(action="deny", source_network=ipaddress.ip_network("10.0.0.0/24")))
        r1.set_interface_acl("GigabitEthernet0/1", "out", 1)

        result = NetworkEngine(topology).ping(pc1.device_id, "192.168.1.10")

        self.assertFalse(result.success)
        self.assertEqual(result.reason, PingFailureReason.ACL_DENIED)

    def test_outbound_acl_permit_allows_ping(self) -> None:
        topology, pc1, r1, pc2 = self._build()
        acl = r1.get_or_create_access_list(1)
        acl.add_rule(AclRule(action="permit", source_network=ipaddress.ip_network("10.0.0.0/24")))
        r1.set_interface_acl("GigabitEthernet0/1", "out", 1)

        result = NetworkEngine(topology).ping(pc1.device_id, "192.168.1.10")

        self.assertTrue(result.success)

    def test_inbound_acl_deny_on_receiving_interface_blocks_ping(self) -> None:
        topology, pc1, r1, pc2 = self._build()
        acl = r1.get_or_create_access_list(2)
        acl.add_rule(AclRule(action="deny", source_network=ipaddress.ip_network("10.0.0.0/24")))
        r1.set_interface_acl("GigabitEthernet0/0", "in", 2)

        result = NetworkEngine(topology).ping(pc1.device_id, "192.168.1.10")

        self.assertFalse(result.success)
        self.assertEqual(result.reason, PingFailureReason.ACL_DENIED)

    def test_acl_permits_a_different_source_but_denies_the_real_one(self) -> None:
        topology, pc1, r1, pc2 = self._build()
        acl = r1.get_or_create_access_list(1)

        acl.add_rule(AclRule(action="permit", source_network=ipaddress.ip_network("172.16.0.0/16")))
        r1.set_interface_acl("GigabitEthernet0/1", "out", 1)

        result = NetworkEngine(topology).ping(pc1.device_id, "192.168.1.10")

        self.assertFalse(result.success)
        self.assertEqual(result.reason, PingFailureReason.ACL_DENIED)

    def test_acl_on_unrelated_interface_does_not_affect_this_path(self) -> None:
        topology, pc1, r1, pc2 = self._build()
        acl = r1.get_or_create_access_list(1)
        acl.add_rule(AclRule(action="deny", source_network=ipaddress.ip_network("10.0.0.0/24")))

        acl.add_rule(AclRule(action="permit", source_network=ipaddress.ip_network("192.168.1.0/24")))
        r1.set_interface_acl("GigabitEthernet0/0", "out", 1)

        result = NetworkEngine(topology).ping(pc1.device_id, "192.168.1.10")

        self.assertTrue(result.success)

    def test_inbound_acl_can_block_echo_reply_after_request_arrives(self) -> None:
        topology, pc1, r1, pc2 = self._build()
        acl = r1.get_or_create_access_list(8)
        acl.add_rule(AclRule(action="deny", source_network=ipaddress.ip_network("192.168.1.10/32")))
        acl.add_rule(AclRule(action="permit", source_network=ipaddress.ip_network("10.0.0.0/24")))

        r1.set_interface_acl("GigabitEthernet0/1", "in", 8)

        result = NetworkEngine(topology).ping(pc1.device_id, "192.168.1.10")

        self.assertFalse(result.success)
        self.assertEqual(result.reason, PingFailureReason.ACL_DENIED)
        self.assertIn("inbound access list", result.detail)

    def test_outbound_acl_can_block_echo_reply_on_return_interface(self) -> None:
        topology, pc1, r1, pc2 = self._build()
        acl = r1.get_or_create_access_list(9)
        acl.add_rule(AclRule(action="deny", source_network=ipaddress.ip_network("192.168.1.10/32")))
        acl.add_rule(AclRule(action="permit", source_network=ipaddress.ip_network("10.0.0.0/24")))

        r1.set_interface_acl("GigabitEthernet0/0", "out", 9)

        result = NetworkEngine(topology).ping(pc1.device_id, "192.168.1.10")

        self.assertFalse(result.success)
        self.assertEqual(result.reason, PingFailureReason.ACL_DENIED)
        self.assertIn("outbound access list", result.detail)

    def test_referenced_but_undefined_acl_number_permits_everything(self) -> None:

        topology, pc1, r1, pc2 = self._build()
        r1.set_interface_acl("GigabitEthernet0/1", "out", 99)

        result = NetworkEngine(topology).ping(pc1.device_id, "192.168.1.10")

        self.assertTrue(result.success)

    def test_original_source_ip_is_preserved_across_multiple_routers(self) -> None:
        topology = Topology()
        pc1 = Host(hostname="PC1")
        r1 = Router(hostname="R1", interface_names=["GigabitEthernet0/0", "GigabitEthernet0/1"])
        r2 = Router(hostname="R2", interface_names=["GigabitEthernet0/0", "GigabitEthernet0/1"])
        pc2 = Host(hostname="PC2")
        for device in (pc1, r1, r2, pc2):
            topology.add_device(device)

        topology.connect(pc1.device_id, "Ethernet0", r1.device_id, "GigabitEthernet0/0")
        topology.connect(r1.device_id, "GigabitEthernet0/1", r2.device_id, "GigabitEthernet0/0")
        topology.connect(r2.device_id, "GigabitEthernet0/1", pc2.device_id, "Ethernet0")

        pc1.configure_ipv4("Ethernet0", "10.0.0.10", "255.255.255.0")
        r1.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")
        r1.configure_ipv4("GigabitEthernet0/1", "172.16.12.1", "255.255.255.252")
        r2.configure_ipv4("GigabitEthernet0/0", "172.16.12.2", "255.255.255.252")
        r2.configure_ipv4("GigabitEthernet0/1", "192.168.2.1", "255.255.255.0")
        pc2.configure_ipv4("Ethernet0", "192.168.2.10", "255.255.255.0")
        pc1.set_default_gateway("10.0.0.1")
        pc2.set_default_gateway("192.168.2.1")
        r1.add_static_route("192.168.2.0", "255.255.255.0", "172.16.12.2")
        r2.add_static_route("10.0.0.0", "255.255.255.0", "172.16.12.1")

        _up(
            pc1.get_interface("Ethernet0"),
            r1.get_interface("GigabitEthernet0/0"),
            r1.get_interface("GigabitEthernet0/1"),
            r2.get_interface("GigabitEthernet0/0"),
            r2.get_interface("GigabitEthernet0/1"),
            pc2.get_interface("Ethernet0"),
        )
        for device in (pc1, r1, r2, pc2):
            device.boot()

        acl = r2.get_or_create_access_list(20)
        acl.add_rule(AclRule(action="permit", source_network=ipaddress.ip_network("10.0.0.0/24")))
        r2.set_interface_acl("GigabitEthernet0/0", "in", 20)

        result = NetworkEngine(topology).ping(pc1.device_id, "192.168.2.10")
        self.assertTrue(result.success, result.detail)


class TestFormattedOutput(unittest.TestCase):
    """These back the CLI's `show arp` / `show ip route` commands -
    verifying the formatted text contains real, not fabricated, data."""

    def setUp(self) -> None:
        self.topology = Topology()
        self.pc1 = Host(hostname="PC1")
        self.r1 = Router(interface_names=["GigabitEthernet0/0"])
        self.topology.add_device(self.pc1)
        self.topology.add_device(self.r1)
        self.topology.connect(self.pc1.device_id, "Ethernet0", self.r1.device_id, "GigabitEthernet0/0")
        self.pc1.configure_ipv4("Ethernet0", "10.0.0.10", "255.255.255.0")
        self.r1.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")
        _up(self.pc1.get_interface("Ethernet0"), self.r1.get_interface("GigabitEthernet0/0"))
        self.pc1.boot()
        self.r1.boot()
        self.engine = NetworkEngine(self.topology)

    def test_arp_table_text_reflects_real_resolution(self) -> None:
        self.engine.ping(self.pc1.device_id, "10.0.0.1")
        lines = self.engine.format_arp_table(self.pc1.device_id)
        joined = "\n".join(lines)
        self.assertIn("10.0.0.1", joined)
        self.assertIn(self.r1.get_interface("GigabitEthernet0/0").mac_address, joined)

    def test_arp_table_text_empty_before_any_resolution(self) -> None:
        lines = self.engine.format_arp_table(self.pc1.device_id)
        joined = "\n".join(lines)
        self.assertNotIn("10.0.0.1", joined)

    def test_routing_table_text_reflects_real_connected_route(self) -> None:
        lines = self.engine.format_routing_table(self.r1.device_id)
        joined = "\n".join(lines)
        self.assertIn("10.0.0.0/24", joined)
        self.assertIn("GigabitEthernet0/0", joined)

    def test_routing_table_text_reflects_static_route(self) -> None:
        self.r1.add_static_route("192.168.5.0", "255.255.255.0", "10.0.0.99")
        lines = self.engine.format_routing_table(self.r1.device_id)
        joined = "\n".join(lines)
        self.assertIn("192.168.5.0/24", joined)
        self.assertIn("10.0.0.99", joined)

if __name__ == "__main__":
    unittest.main()
