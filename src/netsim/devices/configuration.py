"""Running-config vs. startup-config plumbing.

Real network OSes treat "running-config" as the live, in-memory
device state itself - there is no separate object for it. This module
reflects that: :class:`~netsim.devices.base.Device` *is* the running
configuration, and :func:`render_config_text` renders whatever state
(live or a captured snapshot) is handed to it into IOS-style text for
``show running-config`` / ``show startup-config``.

:class:`ConfigSnapshot` is the thing that gives ``startup-config`` its
own identity: it is an independent, deep-copied capture of hostname +
interfaces, taken by ``copy running-config startup-config`` and
restored by ``reload``. There is deliberately no config-text *parser*
here (turning ``show running-config`` output back into commands) -
that is real configuration-engine work for a later stage; snapshots
are captured/restored as structured Python objects, not text.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from netsim.devices.interface import Interface


@dataclass
class ConfigSnapshot:
    """An independent, point-in-time capture of a device's configuration.

    Attributes:
        hostname: The hostname at capture time.
        interfaces: Deep copies of every interface at capture time,
            keyed by interface name. Mutating the live device
            afterward never affects a previously captured snapshot.
    """

    hostname: str
    interfaces: dict[str, Interface] = field(default_factory=dict)

    def __post_init__(self) -> None:

        self.interfaces = {name: copy.deepcopy(iface) for name, iface in self.interfaces.items()}

    @classmethod
    def capture(cls, hostname: str, interfaces: dict[str, Interface]) -> "ConfigSnapshot":
        """Capture the given hostname/interfaces as an independent snapshot.

        Args:
            hostname: Hostname to capture.
            interfaces: Live interfaces to deep-copy into the snapshot.

        Returns:
            A new, independent :class:`ConfigSnapshot`.
        """
        return cls(hostname=hostname, interfaces=interfaces)


def render_config_text(hostname: str, interfaces: dict[str, Interface]) -> str:
    """Render hostname + interfaces as IOS-style configuration text.

    Used for both ``show running-config`` (given live state) and
    ``show startup-config`` (given a captured :class:`ConfigSnapshot`'s
    fields) - the rendering logic doesn't care which.

    Args:
        hostname: Device hostname.
        interfaces: Interfaces to render, keyed by name.

    Returns:
        Multi-line configuration text.
    """
    lines = ["!", f"hostname {hostname}", "!"]

    for name in sorted(interfaces):
        iface = interfaces[name]
        lines.append(f"interface {name}")
        if iface.description:
            lines.append(f" description {iface.description}")
        if iface.ipv4_address is not None:
            netmask = _prefix_to_dotted_mask(iface.ipv4_prefix_length or 0)
            lines.append(f" ip address {iface.ipv4_address} {netmask}")
        if not iface.admin_up:
            lines.append(" shutdown")
        lines.append("!")

    return "\n".join(lines)


def _prefix_to_dotted_mask(prefix_length: int) -> str:
    """Convert a prefix length (0-32) to a dotted-decimal subnet mask."""
    import ipaddress

    return str(ipaddress.ip_network(f"0.0.0.0/{prefix_length}").netmask)
