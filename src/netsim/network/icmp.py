"""ICMP Echo (ping) message and result types.

:class:`IcmpMessage` is the packet-layer piece (constructed by
:mod:`netsim.network.engine` when simulating a ping). Ping *results*
are deliberately not exceptions - :class:`PingResult` is a plain data
value with a :class:`PingFailureReason`, because a failed ping is a
completely ordinary, expected outcome (not an error in the
programming sense), and the CLI's ``ping`` command needs to print a
specific, meaningful reason rather than catch-and-format a generic
error string.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class IcmpType(Enum):
    """Which kind of ICMP message this is."""

    ECHO_REQUEST = auto()
    ECHO_REPLY = auto()


@dataclass(frozen=True)
class IcmpMessage:
    """A single ICMP Echo Request or Echo Reply.

    Attributes:
        type: :attr:`IcmpType.ECHO_REQUEST` or :attr:`IcmpType.ECHO_REPLY`.
        identifier: Identifies which ping session this belongs to
            (mirrors real ICMP echo semantics).
        sequence: Sequence number within that session.
    """

    type: IcmpType
    identifier: int
    sequence: int


class PingFailureReason(Enum):
    """Why a simulated ping failed. Each maps to a specific, meaningful
    condition in the simulated network - never a generic catch-all."""

    HOST_OFFLINE = auto()
    """The source device itself is not powered on and READY."""

    INTERFACE_DOWN = auto()
    """The outgoing interface is administratively down."""

    NO_ROUTE = auto()
    """No route (connected, static, or default) covers the destination."""

    LINK_DOWN = auto()
    """A route/ARP path exists, but the physical link along it is down."""

    ARP_UNRESOLVED = auto()
    """The next hop's MAC address could not be resolved."""

    DESTINATION_UNREACHABLE = auto()
    """A route and ARP resolution succeeded, but the destination itself
    is not actually reachable (e.g. offline, or its own interface
    down) - the general "got there, nobody answered" case."""

    ACL_DENIED = auto()
    """An access control list applied to an interface along the path
    (outbound on the sender's side, or inbound on the receiver's side)
    denied this traffic based on its source address."""


@dataclass(frozen=True)
class PingResult:
    """The outcome of a single simulated ping.

    Attributes:
        success: Whether the echo reply was received.
        destination: The IP address that was pinged.
        reason: Why it failed, if it did.
        detail: Human-readable elaboration for CLI display.
    """

    success: bool
    destination: str
    reason: PingFailureReason | None = None
    detail: str = ""
