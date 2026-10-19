"""Virtual router configuration model.

The router stores interface configuration, static routes, RIP network
statements, standard IPv4 ACL rules, and per-interface ACL bindings. Learned
RIP routes and packet-path decisions belong to the network engine; the router
model stores configuration but does not implement protocol exchange or apply
ACLs to simulated traffic directly.
"""

from __future__ import annotations

import copy
import ipaddress
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping, cast

from netsim.core.exceptions import ValidationError
from netsim.devices.acl import ANY_NETWORK, AccessList, AclRule
from netsim.devices.addressing import parse_ipv4_address, parse_ipv4_mask
from netsim.devices.base import Device
from netsim.devices.types import DeviceType

_DEFAULT_INTERFACES = ["GigabitEthernet0/0", "GigabitEthernet0/1"]


@dataclass(frozen=True)
class StaticRoute:
    """A single manually-configured route.

    Attributes:
        network: Destination network.
        next_hop: IPv4 address of the next router to forward toward.
            Resolving *how* to reach that address (which of this
            router's own interfaces/connected networks covers it) is
            the network engine's job at lookup time, not stored here.
    """

    network: ipaddress.IPv4Network
    next_hop: ipaddress.IPv4Address


class Router(Device):
    """A virtual router.

    Args:
        hostname: Initial hostname. Defaults to ``"Router"``, matching
            an unconfigured real device's default prompt.
        interface_names: Interface names to build. Defaults to two
            GigabitEthernet interfaces if not given.
    """

    def __init__(
        self,
        hostname: str = "Router",
        interface_names: list[str] | None = None,
    ) -> None:
        super().__init__(
            hostname=hostname,
            device_type=DeviceType.ROUTER,
            interface_names=list(interface_names) if interface_names is not None else list(_DEFAULT_INTERFACES),
        )
        self._static_routes: dict[str, StaticRoute] = {}
        self._rip_networks: set[ipaddress.IPv4Network] = set()
        self._access_lists: dict[int, AccessList] = {}
        self._interface_acl_in: dict[str, int] = {}
        self._interface_acl_out: dict[str, int] = {}

    def connected_interfaces(self) -> list[tuple[str, ipaddress.IPv4Network]]:
        """(interface name, network) pairs this router is directly attached to.

        An interface contributes a pair only when it has both an IPv4
        address configured *and* is administratively up. This is the
        single source of truth for connected-route awareness -
        :meth:`connected_networks` and
        :func:`netsim.network.routing.build_connected_routes` are both
        thin views over this, so the underlying logic exists in
        exactly one place.

        Returns:
            Pairs in interface-name order.
        """
        pairs: list[tuple[str, ipaddress.IPv4Network]] = []
        for name in sorted(self.interfaces):
            iface = self.interfaces[name]
            if iface.admin_up and iface.network is not None:
                pairs.append((name, iface.network))
        return pairs

    def connected_networks(self) -> list[ipaddress.IPv4Network]:
        """IPv4 networks this router is directly attached to.

        Returns:
            Directly connected networks, one per qualifying interface,
            in interface-name order.
        """
        return [network for _, network in self.connected_interfaces()]

    @property
    def static_routes(self) -> Mapping[str, StaticRoute]:
        """Read-only view of configured static routes, keyed by network (e.g. ``"192.168.2.0/24"``)."""
        return MappingProxyType(self._static_routes)

    def add_static_route(self, network: str, mask: str, next_hop: str) -> None:
        """Configure a static route.

        Args:
            network: Destination network address, e.g. ``"192.168.2.0"``.
            mask: Dotted-decimal subnet mask (or bare prefix length).
            next_hop: IPv4 address of the next-hop router.

        Raises:
            ValidationError: If ``mask`` or ``next_hop`` is malformed.
        """
        prefix_length = parse_ipv4_mask(mask)
        parsed_next_hop = parse_ipv4_address(next_hop)
        parsed_network = ipaddress.ip_network(f"{network}/{prefix_length}", strict=False)
        self._static_routes[str(parsed_network)] = StaticRoute(
            network=parsed_network, next_hop=parsed_next_hop
        )

    def remove_static_route(self, network: str, mask: str) -> None:
        """Remove a previously configured static route, if present.

        Args:
            network: Destination network address.
            mask: Dotted-decimal subnet mask (or bare prefix length).
        """
        prefix_length = parse_ipv4_mask(mask)
        parsed_network = ipaddress.ip_network(f"{network}/{prefix_length}", strict=False)
        self._static_routes.pop(str(parsed_network), None)

    @property
    def rip_networks(self) -> frozenset[ipaddress.IPv4Network]:
        """Read-only view of networks RIP is enabled on (``router rip`` /
        ``network <address> <mask>`` statements)."""
        return frozenset(self._rip_networks)

    def enable_rip(self, network: str, mask: str) -> None:
        """Enable RIP on any interface whose connected network falls
        within the given network (backs ``network <address> <mask>``
        under ``router rip``).

        Deliberately takes an explicit network + mask rather than real
        IOS's classful-only ``network <address>`` syntax, for
        consistency with how this project already treats ``ip route``
        and ``ip address`` - a documented simplification, not a
        protocol behavior change.

        Args:
            network: Network address, e.g. ``"10.0.0.0"``.
            mask: Dotted-decimal subnet mask (or bare prefix length).

        Raises:
            ValidationError: If ``mask`` is malformed.
        """
        prefix_length = parse_ipv4_mask(mask)
        parsed_network = ipaddress.ip_network(f"{network}/{prefix_length}", strict=False)
        self._rip_networks.add(parsed_network)

    def disable_rip(self, network: str, mask: str) -> None:
        """Remove a previously configured RIP network statement, if present.

        Args:
            network: Network address.
            mask: Dotted-decimal subnet mask (or bare prefix length).
        """
        prefix_length = parse_ipv4_mask(mask)
        parsed_network = ipaddress.ip_network(f"{network}/{prefix_length}", strict=False)
        self._rip_networks.discard(parsed_network)

    def rip_enabled_interfaces(self) -> list[str]:
        """Which of this router's own interfaces currently participate in RIP.

        An interface participates when it's connected (up, with an
        IPv4 address) *and* its network falls within one of the
        configured :attr:`rip_networks` - pure derivation from live
        state, matching how :meth:`connected_interfaces` itself works.

        Returns:
            Interface names, in the same order as :meth:`connected_interfaces`.
        """
        return [
            name
            for name, network in self.connected_interfaces()
            if any(network.subnet_of(rip_network) for rip_network in self._rip_networks)
        ]

    @property
    def access_lists(self) -> Mapping[int, AccessList]:
        """Read-only view of configured access lists, keyed by number."""
        return MappingProxyType(self._access_lists)

    def get_or_create_access_list(self, number: int) -> AccessList:
        """Return the access list with this number, creating it if it
        doesn't exist yet (backs ``access-list <number> permit|deny ...``).

        Args:
            number: The ACL number.

        Returns:
            The (possibly newly created) :class:`~netsim.devices.acl.AccessList`.
        """
        if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= 99:
            raise ValidationError(
                "Standard ACL number must be between 1 and 99", field="number", value=number
            )
        if number not in self._access_lists:
            self._access_lists[number] = AccessList(number=number)
        return self._access_lists[number]

    def add_access_list_rule(self, number: int, action: str, network: str, mask: str | None = None) -> None:
        """Add one rule to an access list, creating the list if needed
        (backs ``access-list <number> permit|deny <network> <mask>``
        and ``access-list <number> permit|deny any``).

        This is the primitive-typed, validated entry point the CLI
        uses - the same "let the device layer validate" pattern as
        :meth:`add_static_route`/:meth:`enable_rip` - rather than
        requiring a caller to construct an
        :class:`~netsim.devices.acl.AclRule` directly.

        Args:
            number: The ACL number.
            action: ``"permit"`` or ``"deny"``.
            network: A destination network address, or the literal
                string ``"any"`` to match every address.
            mask: Dotted-decimal subnet mask (or bare prefix length).
                Required unless ``network`` is ``"any"``.

        Raises:
            ValidationError: If ``action`` isn't ``"permit"``/``"deny"``,
                if ``mask`` is missing when required, or if ``mask``
                is malformed.
        """
        if action not in ("permit", "deny"):
            raise ValidationError(
                f"{action!r} is not a valid ACL action (must be 'permit' or 'deny')",
                field="action",
                value=action,
            )

        if network == "any":
            if mask is not None:
                raise ValidationError(
                    "Do not specify a subnet mask when the network is 'any'",
                    field="mask",
                    value=mask,
                )
            source_network = ANY_NETWORK
        else:
            if mask is None:
                raise ValidationError(
                    "A subnet mask is required unless the network is 'any'",
                    field="mask",
                    value=network,
                )

            parsed_address = parse_ipv4_address(network)
            prefix_length = parse_ipv4_mask(mask)
            source_network = ipaddress.ip_network(f"{parsed_address}/{prefix_length}", strict=False)

        acl = self.get_or_create_access_list(number)
        acl.add_rule(AclRule(action=cast(Literal["permit", "deny"], action), source_network=source_network))

    def set_interface_acl(self, interface_name: str, direction: Literal["in", "out"], number: int) -> None:
        """Apply an access list to an interface in a direction (backs
        ``ip access-group <number> in|out``).

        Args:
            interface_name: Which interface to apply it to.
            direction: ``"in"`` or ``"out"``.
            number: The ACL number to apply. The ACL may be referenced
                before rules are added; in this simulator, such an empty
                ACL does not filter traffic until rules are configured.

        Raises:
            InterfaceNotFoundError: If ``interface_name`` doesn't exist
                on this router.
            ValidationError: If ``direction`` isn't ``"in"`` or ``"out"``.
        """
        self.get_interface(interface_name)
        if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= 99:
            raise ValidationError(
                "Standard ACL number must be between 1 and 99", field="number", value=number
            )
        if direction not in ("in", "out"):
            raise ValidationError(
                f"{direction!r} is not a valid ACL direction (must be 'in' or 'out')",
                field="direction",
                value=direction,
            )
        if direction == "in":
            self._interface_acl_in[interface_name] = number
        else:
            self._interface_acl_out[interface_name] = number

    def remove_interface_acl(
        self,
        interface_name: str,
        direction: Literal["in", "out"],
        number: int | None = None,
    ) -> None:
        """Remove an ACL binding from an interface.

        When ``number`` is provided (as it is by the ``no ip access-group``
        CLI command), remove the binding only if that ACL number is currently
        applied in the selected direction. Omitting it preserves the simpler
        two-argument API and removes any binding in that direction.
        """
        self.get_interface(interface_name)
        if direction not in ("in", "out"):
            raise ValidationError(
                f"{direction!r} is not a valid ACL direction (must be 'in' or 'out')",
                field="direction",
                value=direction,
            )
        table = self._interface_acl_in if direction == "in" else self._interface_acl_out
        current_number = table.get(interface_name)
        if current_number is not None and (number is None or number == current_number):
            table.pop(interface_name, None)

    @property
    def interface_acl_in(self) -> Mapping[str, int]:
        """Read-only interface-to-ACL-number bindings for inbound traffic."""
        return MappingProxyType(self._interface_acl_in)

    @property
    def interface_acl_out(self) -> Mapping[str, int]:
        """Read-only interface-to-ACL-number bindings for outbound traffic."""
        return MappingProxyType(self._interface_acl_out)

    def get_interface_acl(self, interface_name: str, direction: Literal["in", "out"]) -> AccessList | None:
        """The access list currently applied to an interface in a
        direction, or ``None`` if none is applied.

        Args:
            interface_name: Which interface to check.
            direction: ``"in"`` or ``"out"``.

        Returns:
            The applied :class:`~netsim.devices.acl.AccessList`, or
            ``None`` if no ACL is applied. A referenced but empty ACL
            permits traffic in this simulator; once at least one rule
            exists, unmatched sources are denied by the implicit deny.
        """
        table = self._interface_acl_in if direction == "in" else self._interface_acl_out
        number = table.get(interface_name)
        if number is None:
            return None
        return self.get_or_create_access_list(number)

    def _capture_extra_config(self) -> dict[str, object]:
        return {
            "static_routes": dict(self._static_routes),
            "rip_networks": set(self._rip_networks),

            "access_lists": copy.deepcopy(self._access_lists),
            "interface_acl_in": dict(self._interface_acl_in),
            "interface_acl_out": dict(self._interface_acl_out),
        }

    def _restore_extra_config(self, extra: dict[str, object]) -> None:
        self._static_routes = dict(cast(dict[str, StaticRoute], extra.get("static_routes", {})))
        self._rip_networks = set(cast(set[ipaddress.IPv4Network], extra.get("rip_networks", set())))
        self._access_lists = copy.deepcopy(
            cast(dict[int, AccessList], extra.get("access_lists", {}))
        )
        self._interface_acl_in = dict(cast(dict[str, int], extra.get("interface_acl_in", {})))
        self._interface_acl_out = dict(cast(dict[str, int], extra.get("interface_acl_out", {})))
