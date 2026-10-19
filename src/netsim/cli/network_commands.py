"""Network-aware CLI commands: ``ping``, ``show arp``, ``show ip route``.

Mirrors :mod:`netsim.cli.device_commands` exactly: every handler here
reaches the network engine exclusively through
:class:`~netsim.cli.network_interface.NetworkContext`, never through a
concrete :class:`~netsim.network.engine.NetworkEngine` import. Nothing
here builds a :class:`~netsim.network.topology.Topology` or does any
routing/ARP work itself - all of that already happened in
:mod:`netsim.network`; these handlers only format its output for
display, exactly like ``show running-config`` does for device state.

:func:`register_network_commands` takes an *existing* registry
(typically the one :func:`netsim.cli.device_commands.build_device_registry`
already built) and adds these three commands to it, rather than
building a whole separate registry - there's nothing about ping/arp/
routing commands that conflicts with the device command set, so
there's no reason to duplicate the rest of it.
"""

from __future__ import annotations

from netsim.cli.command import Argument, Command, CommandContext, CommandResult
from netsim.devices.addressing import parse_ipv4_address
from netsim.cli.device_commands import _as_full_device
from netsim.cli.device_interface import FullDeviceContext
from netsim.cli.errors import NetworkUnavailableError
from netsim.cli.modes import CliMode
from netsim.cli.network_interface import NetworkContext, PingResultContext
from netsim.cli.registry import CommandRegistry


def _require_network(context: CommandContext) -> NetworkContext:
    """Narrow ``context.network`` to :class:`NetworkContext`.

    Raises:
        NetworkUnavailableError: If this session has no network engine attached.
    """
    if context.network is None:
        raise NetworkUnavailableError()
    return context.network


def _format_ping_result(result: PingResultContext) -> list[str]:
    """Render a ping outcome as IOS-style ``ping`` transcript text."""
    lines = [
        f"Sending 1, 100-byte ICMP Echo to {result.destination}, timeout is 2 seconds:",
    ]
    if result.success:
        lines.append("!")
        lines.append("Success rate is 100 percent (1/1)")
    else:
        lines.append(".")
        lines.append("Success rate is 0 percent (0/1)")
        if result.detail:
            lines.append(result.detail)
    return lines


def _validate_destination(raw: str) -> str:
    """Validate ping's destination at the CLI boundary as IPv4 input."""
    return str(parse_ipv4_address(raw))


def _ping(context: CommandContext) -> CommandResult:
    device = _as_full_device(context.device)
    network = _require_network(context)
    result = network.ping(device.device_id, context.args["destination"])
    return CommandResult(output=_format_ping_result(result))


def _show_arp(context: CommandContext) -> CommandResult:
    device = _as_full_device(context.device)
    network = _require_network(context)
    return CommandResult(output=network.format_arp_table(device.device_id))


def _show_ip_route(context: CommandContext) -> CommandResult:
    device = _as_full_device(context.device)
    network = _require_network(context)
    return CommandResult(output=network.format_routing_table(device.device_id))


def register_network_commands(registry: CommandRegistry) -> None:
    """Add ``ping``, ``show arp``, and ``show ip route`` to an existing registry.

    Args:
        registry: The registry to extend - typically the one built by
            :func:`netsim.cli.device_commands.build_device_registry`.
    """
    registry.register(
        Command(
            name="ping",
            handler=_ping,
            allowed_modes=frozenset({CliMode.USER_EXEC, CliMode.PRIVILEGED_EXEC}),
            arguments=(
                Argument(
                    name="destination",
                    validator=_validate_destination,
                    help_text="Destination IPv4 address",
                ),
            ),
            help_text="Send an ICMP echo request",
        )
    )
    registry.register(
        Command(
            name="show arp",
            handler=_show_arp,
            allowed_modes=frozenset(CliMode),
            help_text="Show the ARP cache",
        )
    )
    registry.register(
        Command(
            name="show ip route",
            handler=_show_ip_route,
            allowed_modes=frozenset(CliMode),
            help_text="Show the IP routing table",
        )
    )
