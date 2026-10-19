"""ARP messages and the per-device ARP cache.

:class:`ArpMessage` represents a single request or reply on the wire
(constructed by :mod:`netsim.network.engine` when it simulates
resolving an address - see that module for the actual
request/reply/learn orchestration, which needs
:class:`~netsim.network.topology.Topology` and so can't live here
without creating a dependency cycle). :class:`ArpCache` is the learned
IP-to-MAC state a single device accumulates; the network engine owns
one per device (devices themselves don't store one - see the engine
module's docstring for why).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from types import MappingProxyType
from typing import Mapping


class ArpOperation(Enum):
    """Whether an ARP message is a request or a reply."""

    REQUEST = auto()
    REPLY = auto()


@dataclass(frozen=True)
class ArpMessage:
    """A single ARP request or reply.

    Attributes:
        operation: :attr:`ArpOperation.REQUEST` or :attr:`ArpOperation.REPLY`.
        sender_ip: IP address of whoever sent this message.
        sender_mac: MAC address of whoever sent this message.
        target_ip: IP address being asked about.
        target_mac: MAC address being supplied (a reply) or ``None``
            (a request, where the answer is exactly what's unknown).
    """

    operation: ArpOperation
    sender_ip: str
    sender_mac: str
    target_ip: str
    target_mac: str | None


class ArpCache:
    """One device's learned IP-to-MAC address mappings."""

    def __init__(self) -> None:
        self._entries: dict[str, str] = {}

    def get(self, ip_address: str) -> str | None:
        """Look up a previously learned MAC address, or None if unknown."""
        return self._entries.get(ip_address)

    def learn(self, ip_address: str, mac_address: str) -> None:
        """Record (or update) the MAC address for an IP address."""
        self._entries[ip_address] = mac_address

    def remove(self, ip_address: str) -> None:
        """Forget a learned mapping, if present (a no-op otherwise)."""
        self._entries.pop(ip_address, None)

    def clear(self) -> None:
        """Forget every learned mapping."""
        self._entries.clear()

    def entries(self) -> Mapping[str, str]:
        """Read-only view of every learned mapping, keyed by IP address."""
        return MappingProxyType(self._entries)
