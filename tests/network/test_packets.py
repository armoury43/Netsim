"""Tests for the packet-layer dataclasses: netsim.network.ethernet/ipv4/arp/icmp."""

from __future__ import annotations

import unittest

from netsim.network.arp import ArpMessage, ArpOperation
from netsim.network.ethernet import ETHERTYPE_ARP, ETHERTYPE_IPV4, EthernetFrame
from netsim.network.icmp import IcmpMessage, IcmpType
from netsim.network.ipv4 import IPV4_PROTOCOL_ICMP, IPv4Packet


class TestEthernetFrame(unittest.TestCase):
    def test_construction_and_fields(self) -> None:
        frame = EthernetFrame(
            src_mac="02:00:00:00:00:01",
            dst_mac="02:00:00:00:00:02",
            ethertype=ETHERTYPE_IPV4,
            payload="placeholder",
        )
        self.assertEqual(frame.src_mac, "02:00:00:00:00:01")
        self.assertEqual(frame.ethertype, ETHERTYPE_IPV4)

    def test_ethertypes_are_distinct(self) -> None:
        self.assertNotEqual(ETHERTYPE_IPV4, ETHERTYPE_ARP)


class TestIPv4Packet(unittest.TestCase):
    def test_construction_and_defaults(self) -> None:
        packet = IPv4Packet(
            src_ip="10.0.0.1", dst_ip="10.0.0.2", protocol=IPV4_PROTOCOL_ICMP, payload="placeholder"
        )
        self.assertEqual(packet.src_ip, "10.0.0.1")
        self.assertEqual(packet.ttl, 64)

    def test_ttl_can_be_overridden(self) -> None:
        packet = IPv4Packet(
            src_ip="10.0.0.1", dst_ip="10.0.0.2", protocol=IPV4_PROTOCOL_ICMP, payload=None, ttl=1
        )
        self.assertEqual(packet.ttl, 1)


class TestArpMessage(unittest.TestCase):
    def test_request_construction(self) -> None:
        message = ArpMessage(
            operation=ArpOperation.REQUEST,
            sender_ip="10.0.0.1",
            sender_mac="02:00:00:00:00:01",
            target_ip="10.0.0.2",
            target_mac=None,
        )
        self.assertEqual(message.operation, ArpOperation.REQUEST)
        self.assertIsNone(message.target_mac)

    def test_reply_construction(self) -> None:
        message = ArpMessage(
            operation=ArpOperation.REPLY,
            sender_ip="10.0.0.2",
            sender_mac="02:00:00:00:00:02",
            target_ip="10.0.0.1",
            target_mac="02:00:00:00:00:01",
        )
        self.assertEqual(message.operation, ArpOperation.REPLY)
        self.assertIsNotNone(message.target_mac)


class TestIcmpMessage(unittest.TestCase):
    def test_echo_request(self) -> None:
        message = IcmpMessage(type=IcmpType.ECHO_REQUEST, identifier=1, sequence=1)
        self.assertEqual(message.type, IcmpType.ECHO_REQUEST)

    def test_echo_reply(self) -> None:
        message = IcmpMessage(type=IcmpType.ECHO_REPLY, identifier=1, sequence=1)
        self.assertEqual(message.type, IcmpType.ECHO_REPLY)

if __name__ == "__main__":
    unittest.main()
