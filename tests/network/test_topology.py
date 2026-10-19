"""Tests for netsim.network.topology.Topology."""

from __future__ import annotations

import unittest

from netsim.devices.host import Host
from netsim.devices.router import Router
from netsim.devices.switch import Switch
from netsim.network.errors import (
    DeviceNotInTopologyError,
    InterfaceAlreadyConnectedError,
    InterfaceNotInTopologyError,
    SelfConnectionError,
)
from netsim.network.topology import Topology


class TestDeviceRegistry(unittest.TestCase):
    def test_add_and_get_device(self) -> None:
        topology = Topology()
        router = Router()
        topology.add_device(router)
        self.assertIs(topology.get_device(router.device_id), router)

    def test_get_unknown_device_raises(self) -> None:
        topology = Topology()
        with self.assertRaises(DeviceNotInTopologyError):
            topology.get_device("does-not-exist")

    def test_devices_view_contains_all_added_devices(self) -> None:
        topology = Topology()
        router = Router()
        switch = Switch()
        topology.add_device(router)
        topology.add_device(switch)
        self.assertEqual(set(topology.devices().keys()), {router.device_id, switch.device_id})


class TestConnectValidation(unittest.TestCase):
    def setUp(self) -> None:
        self.topology = Topology()
        self.r1 = Router(interface_names=["GigabitEthernet0/0"])
        self.r2 = Router(interface_names=["GigabitEthernet0/0"])
        self.topology.add_device(self.r1)
        self.topology.add_device(self.r2)

    def test_valid_connection_creates_a_link(self) -> None:
        link = self.topology.connect(
            self.r1.device_id, "GigabitEthernet0/0", self.r2.device_id, "GigabitEthernet0/0"
        )
        self.assertTrue(link.up)

    def test_rejects_nonexistent_device(self) -> None:
        with self.assertRaises(DeviceNotInTopologyError):
            self.topology.connect(
                "bogus-device", "GigabitEthernet0/0", self.r2.device_id, "GigabitEthernet0/0"
            )

    def test_rejects_nonexistent_interface(self) -> None:
        with self.assertRaises(InterfaceNotInTopologyError):
            self.topology.connect(
                self.r1.device_id, "GigabitEthernet9/9", self.r2.device_id, "GigabitEthernet0/0"
            )

    def test_rejects_self_connection(self) -> None:
        r3 = Router(interface_names=["GigabitEthernet0/0", "GigabitEthernet0/1"])
        self.topology.add_device(r3)
        with self.assertRaises(SelfConnectionError):
            self.topology.connect(
                r3.device_id, "GigabitEthernet0/0", r3.device_id, "GigabitEthernet0/0"
            )

    def test_allows_connecting_two_different_interfaces_on_same_device(self) -> None:
        r3 = Router(interface_names=["GigabitEthernet0/0", "GigabitEthernet0/1"])
        self.topology.add_device(r3)
        link = self.topology.connect(
            r3.device_id, "GigabitEthernet0/0", r3.device_id, "GigabitEthernet0/1"
        )
        self.assertTrue(link.up)

    def test_rejects_duplicate_connection_on_already_linked_interface(self) -> None:
        self.topology.connect(
            self.r1.device_id, "GigabitEthernet0/0", self.r2.device_id, "GigabitEthernet0/0"
        )
        r3 = Router(interface_names=["GigabitEthernet0/0"])
        self.topology.add_device(r3)
        with self.assertRaises(InterfaceAlreadyConnectedError):
            self.topology.connect(
                self.r1.device_id, "GigabitEthernet0/0", r3.device_id, "GigabitEthernet0/0"
            )


class TestGetLink(unittest.TestCase):
    def test_get_link_finds_it_from_either_side(self) -> None:
        topology = Topology()
        r1 = Router(interface_names=["GigabitEthernet0/0"])
        r2 = Router(interface_names=["GigabitEthernet0/0"])
        topology.add_device(r1)
        topology.add_device(r2)
        topology.connect(r1.device_id, "GigabitEthernet0/0", r2.device_id, "GigabitEthernet0/0")

        self.assertIsNotNone(topology.get_link(r1.device_id, "GigabitEthernet0/0"))
        self.assertIsNotNone(topology.get_link(r2.device_id, "GigabitEthernet0/0"))

    def test_get_link_returns_none_when_unconnected(self) -> None:
        topology = Topology()
        r1 = Router(interface_names=["GigabitEthernet0/0"])
        topology.add_device(r1)
        self.assertIsNone(topology.get_link(r1.device_id, "GigabitEthernet0/0"))


class TestDisconnect(unittest.TestCase):
    def test_disconnect_removes_the_link(self) -> None:
        topology = Topology()
        r1 = Router(interface_names=["GigabitEthernet0/0"])
        r2 = Router(interface_names=["GigabitEthernet0/0"])
        topology.add_device(r1)
        topology.add_device(r2)
        topology.connect(r1.device_id, "GigabitEthernet0/0", r2.device_id, "GigabitEthernet0/0")

        topology.disconnect(r1.device_id, "GigabitEthernet0/0")

        self.assertIsNone(topology.get_link(r1.device_id, "GigabitEthernet0/0"))
        self.assertIsNone(topology.get_link(r2.device_id, "GigabitEthernet0/0"))

    def test_disconnect_frees_interface_for_reconnection(self) -> None:
        topology = Topology()
        r1 = Router(interface_names=["GigabitEthernet0/0"])
        r2 = Router(interface_names=["GigabitEthernet0/0"])
        r3 = Router(interface_names=["GigabitEthernet0/0"])
        for r in (r1, r2, r3):
            topology.add_device(r)
        topology.connect(r1.device_id, "GigabitEthernet0/0", r2.device_id, "GigabitEthernet0/0")
        topology.disconnect(r1.device_id, "GigabitEthernet0/0")

        link = topology.connect(
            r1.device_id, "GigabitEthernet0/0", r3.device_id, "GigabitEthernet0/0"
        )
        self.assertTrue(link.up)


class TestL2ReachablePeersDirectLink(unittest.TestCase):
    def test_two_routers_directly_linked_reach_each_other(self) -> None:
        topology = Topology()
        r1 = Router(interface_names=["GigabitEthernet0/0"])
        r2 = Router(interface_names=["GigabitEthernet0/0"])
        topology.add_device(r1)
        topology.add_device(r2)
        topology.connect(r1.device_id, "GigabitEthernet0/0", r2.device_id, "GigabitEthernet0/0")

        peers = topology.l2_reachable_peers(r1.device_id, "GigabitEthernet0/0")

        self.assertEqual(peers, [(r2.device_id, "GigabitEthernet0/0")])

    def test_no_link_means_no_reachable_peers(self) -> None:
        topology = Topology()
        r1 = Router(interface_names=["GigabitEthernet0/0"])
        topology.add_device(r1)
        self.assertEqual(topology.l2_reachable_peers(r1.device_id, "GigabitEthernet0/0"), [])

    def test_down_link_means_no_reachable_peers(self) -> None:
        topology = Topology()
        r1 = Router(interface_names=["GigabitEthernet0/0"])
        r2 = Router(interface_names=["GigabitEthernet0/0"])
        topology.add_device(r1)
        topology.add_device(r2)
        link = topology.connect(
            r1.device_id, "GigabitEthernet0/0", r2.device_id, "GigabitEthernet0/0"
        )
        link.set_up(False)

        self.assertEqual(topology.l2_reachable_peers(r1.device_id, "GigabitEthernet0/0"), [])


class TestL2ReachablePeersThroughSwitch(unittest.TestCase):
    def setUp(self) -> None:
        self.topology = Topology()
        self.pc1 = Host(hostname="PC1")
        self.pc2 = Host(hostname="PC2")
        self.switch = Switch(interface_names=["FastEthernet0/1", "FastEthernet0/2"])
        for d in (self.pc1, self.pc2, self.switch):
            self.topology.add_device(d)
        self.topology.connect(self.pc1.device_id, "Ethernet0", self.switch.device_id, "FastEthernet0/1")
        self.topology.connect(self.pc2.device_id, "Ethernet0", self.switch.device_id, "FastEthernet0/2")

        self.pc1.get_interface("Ethernet0").set_admin_up(True)
        self.pc2.get_interface("Ethernet0").set_admin_up(True)
        self.switch.get_interface("FastEthernet0/1").set_admin_up(True)
        self.switch.get_interface("FastEthernet0/2").set_admin_up(True)

    def test_two_hosts_on_same_switch_same_vlan_reach_each_other(self) -> None:
        peers = self.topology.l2_reachable_peers(self.pc1.device_id, "Ethernet0")
        self.assertEqual(peers, [(self.pc2.device_id, "Ethernet0")])

    def test_reachability_is_symmetric(self) -> None:
        peers = self.topology.l2_reachable_peers(self.pc2.device_id, "Ethernet0")
        self.assertEqual(peers, [(self.pc1.device_id, "Ethernet0")])

    def test_different_vlan_blocks_reachability(self) -> None:
        self.switch.get_interface("FastEthernet0/2").switchport.access_vlan = 20
        peers = self.topology.l2_reachable_peers(self.pc1.device_id, "Ethernet0")
        self.assertEqual(peers, [])

    def test_shutdown_switch_port_blocks_reachability(self) -> None:
        self.switch.get_interface("FastEthernet0/2").set_admin_up(False)
        peers = self.topology.l2_reachable_peers(self.pc1.device_id, "Ethernet0")
        self.assertEqual(peers, [])

    def test_three_hosts_on_same_switch_all_reach_each_other(self) -> None:
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

        peers = topology.l2_reachable_peers(pc1.device_id, "Ethernet0")

        self.assertEqual(set(peers), {(pc2.device_id, "Ethernet0"), (pc3.device_id, "Ethernet0")})


class TestL2ReachablePeersMultiSwitch(unittest.TestCase):
    def test_reaches_across_two_switches(self) -> None:
        topology = Topology()
        pc1 = Host(hostname="PC1")
        pc2 = Host(hostname="PC2")
        sw1 = Switch(interface_names=["FastEthernet0/1", "FastEthernet0/2"])
        sw2 = Switch(interface_names=["FastEthernet0/1", "FastEthernet0/2"])
        for d in (pc1, pc2, sw1, sw2):
            topology.add_device(d)

        topology.connect(pc1.device_id, "Ethernet0", sw1.device_id, "FastEthernet0/1")
        topology.connect(sw1.device_id, "FastEthernet0/2", sw2.device_id, "FastEthernet0/1")
        topology.connect(pc2.device_id, "Ethernet0", sw2.device_id, "FastEthernet0/2")

        pc1.get_interface("Ethernet0").set_admin_up(True)
        pc2.get_interface("Ethernet0").set_admin_up(True)
        for sw in (sw1, sw2):
            for name in sw.interfaces:
                sw.get_interface(name).set_admin_up(True)

        peers = topology.l2_reachable_peers(pc1.device_id, "Ethernet0")
        self.assertEqual(peers, [(pc2.device_id, "Ethernet0")])

if __name__ == "__main__":
    unittest.main()
