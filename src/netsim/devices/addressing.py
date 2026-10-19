"""IPv4 parsing/validation helpers shared by every device type.

Built entirely on the standard library :mod:`ipaddress` module rather
than hand-rolled parsing - it already correctly handles every edge
case of dotted-quad validation and mask/prefix conversion. This module
only adapts its exceptions into netsim's own
:class:`~netsim.core.exceptions.ValidationError` so callers throughout
the device layer (and, transitively, the CLI session boundary) get a
single, consistent error type.
"""

from __future__ import annotations

import ipaddress

from netsim.core.exceptions import ValidationError


def parse_ipv4_address(raw: str) -> ipaddress.IPv4Address:
    """Parse and validate a dotted-quad IPv4 address.

    Args:
        raw: The address as typed, e.g. ``"10.0.0.1"``.

    Returns:
        The parsed address.

    Raises:
        ValidationError: If ``raw`` is not a valid IPv4 address.
    """
    try:
        return ipaddress.IPv4Address(raw)
    except (ipaddress.AddressValueError, ValueError) as exc:
        raise ValidationError(
            f"{raw!r} is not a valid IPv4 address", field="ip_address", value=raw
        ) from exc


def parse_ipv4_mask(raw: str) -> int:
    """Parse a subnet mask or prefix length into a prefix length.

    Accepts either a dotted-decimal subnet mask (``"255.255.255.0"``,
    the form used by ``ip address <ip> <mask>``) or a bare prefix
    length (``"24"``), for flexibility in tests and future commands
    that accept CIDR notation directly.

    Args:
        raw: The mask/prefix as typed.

    Returns:
        The equivalent prefix length (0-32).

    Raises:
        ValidationError: If ``raw`` is not a valid dotted mask (must be
            a contiguous run of leading one-bits) and not a valid
            bare prefix length.
    """
    if raw.isdigit():
        prefix = int(raw)
        if not (0 <= prefix <= 32):
            raise ValidationError(
                f"{raw!r} is not a valid prefix length (must be 0-32)",
                field="mask",
                value=raw,
            )
        return prefix

    try:

        network = ipaddress.ip_network(f"0.0.0.0/{raw}")
        return network.prefixlen
    except (ipaddress.NetmaskValueError, ValueError) as exc:
        raise ValidationError(
            f"{raw!r} is not a valid subnet mask", field="mask", value=raw
        ) from exc
