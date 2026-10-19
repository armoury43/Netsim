"""Tests for netsim.network.topology.Topology.l2_forward.

Unlike l2_reachable_peers (used for ARP's broadcast-style search),
l2_forward simulates a single unicast frame: it should use a switch's
already-learned MAC table entry to go straight to one port when known,
fall back to flooding only when the destination is genuinely unknown,
and always learn the source MAC on every switch port it passes
through - exactly like real switch hardware.
"""

from __future__ import annotations

import unittest

from netsim.devices.host import Host
from netsim.devices.switch import Switch
from netsim.network.topology import Topology


def _up(*interfaces) -> None:
    for iface in interfaces:
        iface.set_admin_up(True)


class TestL2ForwardDirectLink(unittest.TestCase):
    def test_forwards_across_a_direct_link(self) -> None:
        topology = Topology()
        pc1 = Host(hostname="PC1")
        pc2 = Host(hostname="PC2")
        topology.add_device(pc1)
        topology.add_device(pc2)
        topology.connect(pc1.device_id, "Ethernet0", pc2.device_id, "Ethernet0")
        _up(pc1.get_interface("Ethernet0"), pc2.get_interface("Ethernet0"))

        src_mac = pc1.get_interface("Ethernet0").mac_address
        dst_mac = pc2.get_interface("Ethernet0").mac_address

        result = topology.l2_forward(pc1.device_id, "Ethernet0", src_mac, dst_mac)

        self.assertEqual(result, (pc2.device_id, "Ethernet0"))

    def test_unknown_destination_mac_is_unreachable(self) -> None:
        topology = Topology()
        pc1 = Host(hostname="PC1")
        pc2 = Host(hostname="PC2")
        topology.add_device(pc1)
        topology.add_device(pc2)
        topology.connect(pc1.device_id, "Ethernet0", pc2.device_id, "Ethernet0")
        _up(pc1.get_interface("Ethernet0"), pc2.get_interface("Ethernet0"))

        result = topology.l2_forward(
            pc1.device_id, "Ethernet0", pc1.get_interface("Ethernet0").mac_address, "02:00:00:00:99:99"
        )
        self.assertIsNone(result)

    def test_down_link_blocks_forwarding(self) -> None:
        topology = Topology()
        pc1 = Host(hostname="PC1")
        pc2 = Host(hostname="PC2")
        topology.add_device(pc1)
        topology.add_device(pc2)
        link = topology.connect(pc1.device_id, "Ethernet0", pc2.device_id, "Ethernet0")
        _up(pc1.get_interface("Ethernet0"), pc2.get_interface("Ethernet0"))
        link.set_up(False)

        result = topology.l2_forward(
            pc1.device_id,
            "Ethernet0",
            pc1.get_interface("Ethernet0").mac_address,
            pc2.get_interface("Ethernet0").mac_address,
        )
        self.assertIsNone(result)


class TestL2ForwardLearning(unittest.TestCase):
    def setUp(self) -> None:
        self.topology = Topology()
        self.pc1 = Host(hostname="PC1")
        self.pc2 = Host(hostname="PC2")
        self.pc3 = Host(hostname="PC3")
        self.switch = Switch(interface_names=["FastEthernet0/1", "FastEthernet0/2", "FastEthernet0/3"])
        for d in (self.pc1, self.pc2, self.pc3, self.switch):
            self.topology.add_device(d)
        self.topology.connect(self.pc1.device_id, "Ethernet0", self.switch.device_id, "FastEthernet0/1")
        self.topology.connect(self.pc2.device_id, "Ethernet0", self.switch.device_id, "FastEthernet0/2")
        self.topology.connect(self.pc3.device_id, "Ethernet0", self.switch.device_id, "FastEthernet0/3")
        _up(
            self.pc1.get_interface("Ethernet0"),
            self.pc2.get_interface("Ethernet0"),
            self.pc3.get_interface("Ethernet0"),
            self.switch.get_interface("FastEthernet0/1"),
            self.switch.get_interface("FastEthernet0/2"),
            self.switch.get_interface("FastEthernet0/3"),
        )
        self.src_mac = self.pc1.get_interface("Ethernet0").mac_address
        self.dst_mac = self.pc2.get_interface("Ethernet0").mac_address

    def test_forwards_to_correct_endpoint_through_switch(self) -> None:
        result = self.topology.l2_forward(self.pc1.device_id, "Ethernet0", self.src_mac, self.dst_mac)
        self.assertEqual(result, (self.pc2.device_id, "Ethernet0"))

    def test_switch_learns_source_mac_on_arrival_port(self) -> None:
        self.assertEqual(dict(self.switch.mac_table), {})

        self.topology.l2_forward(self.pc1.device_id, "Ethernet0", self.src_mac, self.dst_mac)

        self.assertEqual(self.switch.mac_table[self.src_mac], "FastEthernet0/1")

    def test_unknown_destination_still_learns_source_via_flooding(self) -> None:

        self.topology.l2_forward(self.pc1.device_id, "Ethernet0", self.src_mac, self.dst_mac)
        self.assertIn(self.src_mac, self.switch.mac_table)

    def test_second_forward_uses_learned_port_not_flood(self) -> None:

        self.topology.l2_forward(
            self.pc2.device_id, "Ethernet0", self.dst_mac, self.src_mac
        )
        self.assertEqual(self.switch.mac_table[self.dst_mac], "FastEthernet0/2")

        result = self.topology.l2_forward(self.pc1.device_id, "Ethernet0", self.src_mac, self.dst_mac)
        self.assertEqual(result, (self.pc2.device_id, "Ethernet0"))

    def test_flooding_reaches_destination_among_multiple_ports(self) -> None:

        pc3_mac = self.pc3.get_interface("Ethernet0").mac_address
        result = self.topology.l2_forward(self.pc1.device_id, "Ethernet0", self.src_mac, pc3_mac)
        self.assertEqual(result, (self.pc3.device_id, "Ethernet0"))


class TestL2ForwardVlanIsolation(unittest.TestCase):
    def test_different_vlan_is_unreachable(self) -> None:
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

        result = topology.l2_forward(
            pc1.device_id,
            "Ethernet0",
            pc1.get_interface("Ethernet0").mac_address,
            pc2.get_interface("Ethernet0").mac_address,
        )
        self.assertIsNone(result)

if __name__ == "__main__":
    unittest.main()
