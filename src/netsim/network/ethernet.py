"""Ethernet frame model used by the in-memory network engine.

Frames keep source and destination MAC addresses separate from the payload,
which may be an ARP message or an IPv4 packet. Frames represent simulated
network state; they are not byte-encoded frames transmitted on a physical NIC.
"""

from __future__ import annotations

from dataclasses import dataclass

ETHERTYPE_IPV4 = "0x0800"
ETHERTYPE_ARP = "0x0806"


@dataclass(frozen=True)
class EthernetFrame:
    """An Ethernet (L2) frame.

    Attributes:
        src_mac: Source MAC address.
        dst_mac: Destination MAC address.
        ethertype: One of the ``ETHERTYPE_*`` constants, identifying
            the payload type.
        payload: The encapsulated message - an
            :class:`~netsim.network.arp.ArpMessage` when
            ``ethertype == ETHERTYPE_ARP``, or an
            :class:`~netsim.network.ipv4.IPv4Packet` when
            ``ethertype == ETHERTYPE_IPV4``. Left as ``object`` rather
            than a union of every possible payload type so future protocols do not require changing this class.
    """

    src_mac: str
    dst_mac: str
    ethertype: str
    payload: object
