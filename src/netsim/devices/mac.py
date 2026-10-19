"""MAC-address utilities for virtual network interfaces.

A MAC address is an interface property rather than topology state. Addresses
are generated at interface construction and remain stable for that interface's
lifetime unless explicitly changed.
"""

from __future__ import annotations

import random
import re

MAC_PATTERN = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")


def generate_mac_address(rng: random.Random | None = None) -> str:
    """Generate a random, locally-administered unicast MAC address.

    Args:
        rng: Optional random source (mainly for reproducible tests).
            Defaults to a fresh :class:`random.Random` instance.

    Returns:
        A MAC address string like ``"02:1A:B3:9F:44:0C"``.
    """
    generator = rng if rng is not None else random.Random()
    first_octet = generator.randint(0, 255)
    first_octet &= 0b11111100
    first_octet |= 0b00000010
    octets = [first_octet] + [generator.randint(0, 255) for _ in range(5)]
    return ":".join(f"{octet:02X}" for octet in octets)


def is_valid_mac(value: str) -> bool:
    """Whether ``value`` is a syntactically valid MAC address string."""
    return bool(MAC_PATTERN.match(value))
