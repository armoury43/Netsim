"""Tests for the Stage 5 switching completion work.

Kept in a separate file from test_topology.py and
test_topology_forwarding.py (the inherited partial Stage 5 baseline,
both untouched) so it's obvious which tests are new. These cover what
was genuinely missing: trunk-mode VLAN-tag preservation across
switch-to-switch links, explicit broadcast forwarding (with real
learning, unlike plain l2_reachable_peers), a safety fix for
directed-forwarding VLAN mismatches, and a MAC-aging foundation.
"""

from __future__ import annotations

import unittest

from netsim.devices.host import Host
from netsim.devices.interface import SwitchportConfig
from netsim.devices.router import Router
from netsim.devices.switch import Switch
from netsim.network.topology import Topology


def _up(*interfaces) -> None:
    for iface in interfaces:
        iface.set_admin_up(True)


class TestTrunkForwarding(unittest.TestCase):
    """Two switches joined by a trunk link, each with an access port in
    VLAN 10 - traffic must cross the trunk and VLAN identity must be
    preserved, exactly like real 802.1Q trunking (without byte-level
    tagging - the VLAN is tracked as traversal state)."""

    def setUp(self) -> None:
        self.topology = Topology()
        self.pc1 = Host(hostname="PC1")
        self.pc2 = Host(hostname="PC2")
        self.sw1 = Switch(interface_names=["FastEthernet0/1", "GigabitEthernet0/1"])
        self.sw2 = Switch(interface_names=["FastEthernet0/1", "GigabitEthernet0/1"])
        for d in (self.pc1, self.pc2, self.sw1, self.sw2):
            self.topology.add_device(d)

        self.topology.connect(self.pc1.device_id, "Ethernet0", self.sw1.device_id, "FastEthernet0/1")
        self.topology.connect(self.sw1.device_id, "GigabitEthernet0/1", self.sw2.device_id, "GigabitEthernet0/1")
        self.topology.connect(self.pc2.device_id, "Ethernet0", self.sw2.device_id, "FastEthernet0/1")

        self.sw1.get_interface("FastEthernet0/1").switchport.access_vlan = 10
        self.sw2.get_interface("FastEthernet0/1").switchport.access_vlan = 10

        self.sw1.get_interface("GigabitEthernet0/1").switchport = SwitchportConfig(
            mode="trunk", trunk_allowed_vlans={10}
        )
        self.sw2.get_interface("GigabitEthernet0/1").switchport = SwitchportConfig(
            mode="trunk", trunk_allowed_vlans={10}
        )

        _up(
            self.pc1.get_interface("Ethernet0"),
            self.pc2.get_interface("Ethernet0"),
            self.sw1.get_interface("FastEthernet0/1"),
            self.sw1.get_interface("GigabitEthernet0/1"),
            self.sw2.get_interface("FastEthernet0/1"),
            self.sw2.get_interface("GigabitEthernet0/1"),
        )

    def test_reachable_across_trunk_when_vlan_allowed(self) -> None:
        peers = self.topology.l2_reachable_peers(self.pc1.device_id, "Ethernet0")
        self.assertEqual(peers, [(self.pc2.device_id, "Ethernet0")])

    def test_forward_unicast_across_trunk(self) -> None:
        src_mac = self.pc1.get_interface("Ethernet0").mac_address
        dst_mac = self.pc2.get_interface("Ethernet0").mac_address

        result = self.topology.l2_forward(self.pc1.device_id, "Ethernet0", src_mac, dst_mac)

        self.assertEqual(result, (self.pc2.device_id, "Ethernet0"))

    def test_trunk_not_allowing_vlan_blocks_reachability(self) -> None:
        self.sw1.get_interface("GigabitEthernet0/1").switchport.trunk_allowed_vlans = {99}
        peers = self.topology.l2_reachable_peers(self.pc1.device_id, "Ethernet0")
        self.assertEqual(peers, [])

    def test_different_access_vlans_on_either_side_of_an_allowing_trunk_are_isolated(self) -> None:

        self.sw2.get_interface("FastEthernet0/1").switchport.access_vlan = 20
        self.sw1.get_interface("GigabitEthernet0/1").switchport.trunk_allowed_vlans = {10, 20}
        self.sw2.get_interface("GigabitEthernet0/1").switchport.trunk_allowed_vlans = {10, 20}

        peers = self.topology.l2_reachable_peers(self.pc1.device_id, "Ethernet0")
        self.assertEqual(peers, [])

    def test_switch_to_switch_learning_happens_on_both_sides_of_trunk(self) -> None:
        src_mac = self.pc1.get_interface("Ethernet0").mac_address
        dst_mac = self.pc2.get_interface("Ethernet0").mac_address

        self.topology.l2_forward(self.pc1.device_id, "Ethernet0", src_mac, dst_mac)

        self.assertEqual(self.sw1.mac_table[src_mac], "FastEthernet0/1")
        self.assertEqual(self.sw2.mac_table[src_mac], "GigabitEthernet0/1")

    def test_host_directly_on_a_trunk_port_is_unreachable_not_a_crash(self) -> None:

        topology = Topology()
        pc = Host(hostname="PC")
        switch = Switch(interface_names=["GigabitEthernet0/1"])
        topology.add_device(pc)
        topology.add_device(switch)
        topology.connect(pc.device_id, "Ethernet0", switch.device_id, "GigabitEthernet0/1")
        switch.get_interface("GigabitEthernet0/1").switchport = SwitchportConfig(
            mode="trunk", trunk_allowed_vlans={10}
        )
        _up(pc.get_interface("Ethernet0"), switch.get_interface("GigabitEthernet0/1"))

        peers = topology.l2_reachable_peers(pc.device_id, "Ethernet0")
        self.assertEqual(peers, [])


class TestDirectedForwardingVlanSafety(unittest.TestCase):
    """A MAC-table entry learned under one VLAN context must never be
    used to deliver traffic arriving under a different VLAN context -
    closes the gap where reassigning a port's VLAN after learning
    could otherwise leak traffic across VLANs via the fast/directed
    path even though flooding correctly enforces isolation."""

    def test_known_port_in_different_vlan_is_not_used(self) -> None:
        topology = Topology()
        pc1 = Host(hostname="PC1")
        pc2 = Host(hostname="PC2")
        pc3 = Host(hostname="PC3")
        switch = Switch(interface_names=["FastEthernet0/1", "FastEthernet0/2", "FastEthernet0/3"])
        for d in (pc1, pc2, pc3, switch):
            topology.add_device(d)
        topology.connect(pc1.device_id, "Ethernet0", switch.device_id, "FastEthernet0/1")
        topology.connect(pc2.device_id, "Ethernet0", switch.device_id, "FastEthernet0/2")
        topology.connect(pc3.device_id, "Ethernet0", switch.device_id, "FastEthernet0/3")
        _up(
            pc1.get_interface("Ethernet0"),
            pc2.get_interface("Ethernet0"),
            pc3.get_interface("Ethernet0"),
            switch.get_interface("FastEthernet0/1"),
            switch.get_interface("FastEthernet0/2"),
            switch.get_interface("FastEthernet0/3"),
        )
        pc2_mac = pc2.get_interface("Ethernet0").mac_address

        switch.learn_mac(pc2_mac, "FastEthernet0/2")
        self.assertEqual(switch.mac_table[pc2_mac], "FastEthernet0/2")

        switch.get_interface("FastEthernet0/2").switchport.access_vlan = 20

        pc1_mac = pc1.get_interface("Ethernet0").mac_address
        result = topology.l2_forward(pc1.device_id, "Ethernet0", pc1_mac, pc2_mac)

        self.assertIsNone(result)


class TestBroadcastForwarding(unittest.TestCase):
    """l2_broadcast is the explicit broadcast primitive - same
    VLAN-scoped flooding shape as l2_reachable_peers, but (matching
    real broadcast frames, e.g. an ARP request) it also teaches every
    switch it passes through the sender's MAC address."""

    def test_reaches_every_endpoint_in_vlan(self) -> None:
        topology = Topology()
        pc1 = Host(hostname="PC1")
        pc2 = Host(hostname="PC2")
        pc3 = Host(hostname="PC3")
        switch = Switch(interface_names=["FastEthernet0/1", "FastEthernet0/2", "FastEthernet0/3"])
        for d in (pc1, pc2, pc3, switch):
            topology.add_device(d)
        topology.connect(pc1.device_id, "Ethernet0", switch.device_id, "FastEthernet0/1")
        topology.connect(pc2.device_id, "Ethernet0", switch.device_id, "FastEthernet0/2")
        topology.connect(pc3.device_id, "Ethernet0", switch.device_id, "FastEthernet0/3")
        for host in (pc1, pc2, pc3):
            host.get_interface("Ethernet0").set_admin_up(True)
        for name in switch.interfaces:
            switch.get_interface(name).set_admin_up(True)

        peers = topology.l2_broadcast(
            pc1.device_id, "Ethernet0", pc1.get_interface("Ethernet0").mac_address
        )

        self.assertEqual(
            set(peers), {(pc2.device_id, "Ethernet0"), (pc3.device_id, "Ethernet0")}
        )

    def test_broadcast_causes_real_learning_on_every_switch_it_crosses(self) -> None:
        topology = Topology()
        pc1 = Host(hostname="PC1")
        pc2 = Host(hostname="PC2")
        switch = Switch(interface_names=["FastEthernet0/1", "FastEthernet0/2"])
        for d in (pc1, pc2, switch):
            topology.add_device(d)
        topology.connect(pc1.device_id, "Ethernet0", switch.device_id, "FastEthernet0/1")
        topology.connect(pc2.device_id, "Ethernet0", switch.device_id, "FastEthernet0/2")
        _up(
            pc1.get_interface("Ethernet0"),
            pc2.get_interface("Ethernet0"),
            switch.get_interface("FastEthernet0/1"),
            switch.get_interface("FastEthernet0/2"),
        )
        src_mac = pc1.get_interface("Ethernet0").mac_address
        self.assertEqual(dict(switch.mac_table), {})

        topology.l2_broadcast(pc1.device_id, "Ethernet0", src_mac)

        self.assertEqual(switch.mac_table[src_mac], "FastEthernet0/1")

    def test_respects_vlan_isolation_like_l2_reachable_peers(self) -> None:
        topology = Topology()
        pc1 = Host(hostname="PC1")
        pc2 = Host(hostname="PC2")
        switch = Switch(interface_names=["FastEthernet0/1", "FastEthernet0/2"])
        for d in (pc1, pc2, switch):
            topology.add_device(d)
        topology.connect(pc1.device_id, "Ethernet0", switch.device_id, "FastEthernet0/1")
        topology.connect(pc2.device_id, "Ethernet0", switch.device_id, "FastEthernet0/2")
        _up(
            pc1.get_interface("Ethernet0"),
            pc2.get_interface("Ethernet0"),
            switch.get_interface("FastEthernet0/1"),
            switch.get_interface("FastEthernet0/2"),
        )
        switch.get_interface("FastEthernet0/2").switchport.access_vlan = 20

        peers = topology.l2_broadcast(
            pc1.device_id, "Ethernet0", pc1.get_interface("Ethernet0").mac_address
        )
        self.assertEqual(peers, [])

    def test_down_link_blocks_broadcast(self) -> None:
        topology = Topology()
        pc1 = Host(hostname="PC1")
        pc2 = Host(hostname="PC2")
        topology.add_device(pc1)
        topology.add_device(pc2)
        link = topology.connect(pc1.device_id, "Ethernet0", pc2.device_id, "Ethernet0")
        _up(pc1.get_interface("Ethernet0"), pc2.get_interface("Ethernet0"))
        link.set_up(False)

        peers = topology.l2_broadcast(
            pc1.device_id, "Ethernet0", pc1.get_interface("Ethernet0").mac_address
        )
        self.assertEqual(peers, [])


class TestIngressEgressSamePortPrevention(unittest.TestCase):
    """Explicit coverage for 'never forward back out the port a frame
    arrived on' - already an emergent property of both flood and
    directed paths, tested directly here."""

    def test_flood_never_includes_the_arrival_port(self) -> None:
        topology = Topology()
        pc1 = Host(hostname="PC1")
        pc2 = Host(hostname="PC2")
        switch = Switch(interface_names=["FastEthernet0/1", "FastEthernet0/2"])
        for d in (pc1, pc2, switch):
            topology.add_device(d)
        topology.connect(pc1.device_id, "Ethernet0", switch.device_id, "FastEthernet0/1")
        topology.connect(pc2.device_id, "Ethernet0", switch.device_id, "FastEthernet0/2")
        _up(
            pc1.get_interface("Ethernet0"),
            pc2.get_interface("Ethernet0"),
            switch.get_interface("FastEthernet0/1"),
            switch.get_interface("FastEthernet0/2"),
        )

        peers = topology.l2_reachable_peers(pc1.device_id, "Ethernet0")

        self.assertEqual(peers, [(pc2.device_id, "Ethernet0")])


class TestMacAgingFoundation(unittest.TestCase):
    """No time-based aging (no simulated clock exists) - but a clean,
    explicit foundation a future scheduler/CLI command can build on."""

    def test_forget_mac_removes_a_single_entry(self) -> None:
        switch = Switch(interface_names=["FastEthernet0/1"])
        switch.learn_mac("02:00:00:00:00:01", "FastEthernet0/1")

        switch.forget_mac("02:00:00:00:00:01")

        self.assertEqual(dict(switch.mac_table), {})

    def test_forget_unknown_mac_is_a_no_op(self) -> None:
        switch = Switch()
        switch.forget_mac("02:00:00:00:00:99")

    def test_clear_mac_table_removes_everything(self) -> None:
        switch = Switch(interface_names=["FastEthernet0/1", "FastEthernet0/2"])
        switch.learn_mac("02:00:00:00:00:01", "FastEthernet0/1")
        switch.learn_mac("02:00:00:00:00:02", "FastEthernet0/2")

        switch.clear_mac_table()

        self.assertEqual(dict(switch.mac_table), {})


class TestRouterUnaffectedByL2Forwarding(unittest.TestCase):
    """Router behavior stays entirely separate from Switch L2
    forwarding - a Router is always a reachability endpoint, never
    something L2 traffic passes through, trunk or not."""

    def test_router_between_two_switches_does_not_bridge_them(self) -> None:
        topology = Topology()
        sw1 = Switch(interface_names=["FastEthernet0/1"])
        sw2 = Switch(interface_names=["FastEthernet0/1"])
        router = Router(interface_names=["GigabitEthernet0/0", "GigabitEthernet0/1"])
        topology.add_device(sw1)
        topology.add_device(sw2)
        topology.add_device(router)
        topology.connect(sw1.device_id, "FastEthernet0/1", router.device_id, "GigabitEthernet0/0")
        topology.connect(router.device_id, "GigabitEthernet0/1", sw2.device_id, "FastEthernet0/1")
        _up(
            sw1.get_interface("FastEthernet0/1"),
            sw2.get_interface("FastEthernet0/1"),
            router.get_interface("GigabitEthernet0/0"),
            router.get_interface("GigabitEthernet0/1"),
        )

        peers = topology.l2_reachable_peers(sw1.device_id, "FastEthernet0/1")
        self.assertEqual(peers, [(router.device_id, "GigabitEthernet0/0")])

if __name__ == "__main__":
    unittest.main()
