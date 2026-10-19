"""Minimal IPv4 packet model for the simulator's supported protocols.

The model contains source/destination addresses, a protocol identifier, a
payload, and TTL. It represents the fields needed by the current in-memory
simulation and does not implement byte-level packet serialization,
fragmentation, options, or checksums.
"""

from __future__ import annotations

from dataclasses import dataclass

IPV4_PROTOCOL_ICMP = "ICMP"


@dataclass(frozen=True)
class IPv4Packet:
    """An IPv4 (L3) packet.

    Attributes:
        src_ip: Source IPv4 address.
        dst_ip: Destination IPv4 address.
        protocol: One of the ``IPV4_PROTOCOL_*`` constants.
        payload: The encapsulated message, e.g. an
            :class:`~netsim.network.icmp.IcmpMessage`.
        ttl: Time-to-live. Decremented at each simulated router hop;
            reaching zero is a valid failure condition when longer routed
            paths are simulated.
    """

    src_ip: str
    dst_ip: str
    protocol: str
    payload: object
    ttl: int = 64
