"""Built-in commands for navigation, help, history, and application metadata.

This command set contains CLI mechanics and a small protocol-based hostname
operation. Network and device-specific behavior belongs in the integrated
command modules and is delegated to the device or network interfaces.
"""

from __future__ import annotations

from netsim import __version__
from netsim.cli.command import Argument, Command, CommandContext, CommandResult
from netsim.cli.modes import CliMode, ModeContext
from netsim.cli.registry import CommandRegistry
from netsim.core.exceptions import ValidationError

_CONFIG_MODES = frozenset(
    {CliMode.GLOBAL_CONFIG, CliMode.INTERFACE_CONFIG, CliMode.ROUTER_CONFIG, CliMode.VLAN_CONFIG}
)


def _vlan_id(raw: str) -> int:
    """Generic syntax validation for a VLAN ID argument: an integer in
    the legal 802.1Q range. Does not check against any real VLAN
    database - there isn't one yet."""
    if not raw.isdigit():
        raise ValidationError(f"{raw!r} is not a valid VLAN ID", field="vlan_id", value=raw)
    value = int(raw)
    if not (1 <= value <= 4094):
        raise ValidationError("VLAN ID must be between 1 and 4094", field="vlan_id", value=raw)
    return value


def _enable(context: CommandContext) -> CommandResult:
    return CommandResult(mode_push=ModeContext(mode=CliMode.PRIVILEGED_EXEC))


def _disable(context: CommandContext) -> CommandResult:
    return CommandResult(mode_pop=True)


def _configure_terminal(context: CommandContext) -> CommandResult:
    return CommandResult(mode_push=ModeContext(mode=CliMode.GLOBAL_CONFIG))


def _interface(context: CommandContext) -> CommandResult:
    return CommandResult(
        mode_push=ModeContext(
            mode=CliMode.INTERFACE_CONFIG, params={"interface": context.args["name"]}
        )
    )


def _router(context: CommandContext) -> CommandResult:
    return CommandResult(
        mode_push=ModeContext(
            mode=CliMode.ROUTER_CONFIG, params={"protocol": context.args["protocol"]}
        )
    )


def _vlan(context: CommandContext) -> CommandResult:
    return CommandResult(
        mode_push=ModeContext(
            mode=CliMode.VLAN_CONFIG, params={"vlan_id": str(context.args["id"])}
        )
    )


def _hostname(context: CommandContext) -> CommandResult:

    assert context.device is not None, "hostname requires an attached device"
    context.device.set_hostname(context.args["name"])
    return CommandResult(output=[f"Hostname set to {context.args['name']}"])


def _exit(context: CommandContext) -> CommandResult:
    return CommandResult(mode_pop=True)


def _end(context: CommandContext) -> CommandResult:
    return CommandResult(mode_pop_to_privileged=True)


def _show_version(context: CommandContext) -> CommandResult:

    return CommandResult(
        output=[
            "NetSim — Virtual Network Lab",
            "IOS-inspired CLI and in-memory network simulator",
            f"Version: {__version__} (Alpha)",
        ]
    )


def _show_history(context: CommandContext) -> CommandResult:
    return CommandResult(output=list(context.history))


def build_default_registry() -> CommandRegistry:
    """Build a :class:`CommandRegistry` populated with the default
    built-in command set.

    Returns:
        A fresh registry. Callers that want additional commands (e.g.
        a future ``netsim.devices``-aware command set) register them
        on the same instance afterward - nothing here needs to change
        to support that.
    """
    registry = CommandRegistry()

    registry.register(
        Command(
            name="enable",
            handler=_enable,
            allowed_modes=frozenset({CliMode.USER_EXEC}),
            help_text="Enter privileged EXEC mode",
        )
    )
    registry.register(
        Command(
            name="disable",
            handler=_disable,
            allowed_modes=frozenset({CliMode.PRIVILEGED_EXEC}),
            help_text="Exit privileged EXEC mode",
        )
    )
    registry.register(
        Command(
            name="configure terminal",
            handler=_configure_terminal,
            allowed_modes=frozenset({CliMode.PRIVILEGED_EXEC}),
            help_text="Enter global configuration mode",
        )
    )
    registry.register(
        Command(
            name="interface",
            handler=_interface,
            allowed_modes=frozenset({CliMode.GLOBAL_CONFIG}),
            arguments=(Argument(name="name", help_text="Interface name"),),
            help_text="Enter interface configuration mode",
        )
    )
    registry.register(
        Command(
            name="router",
            handler=_router,
            allowed_modes=frozenset({CliMode.GLOBAL_CONFIG}),
            arguments=(Argument(name="protocol", help_text="Routing protocol"),),
            help_text="Enter router configuration mode",
        )
    )
    registry.register(
        Command(
            name="vlan",
            handler=_vlan,
            allowed_modes=frozenset({CliMode.GLOBAL_CONFIG}),
            arguments=(Argument(name="id", validator=_vlan_id, help_text="VLAN ID (1-4094)"),),
            help_text="Enter VLAN configuration mode",
        )
    )
    registry.register(
        Command(
            name="hostname",
            handler=_hostname,
            allowed_modes=frozenset({CliMode.GLOBAL_CONFIG}),
            arguments=(Argument(name="name", help_text="New hostname"),),
            help_text="Set the device hostname",
        )
    )
    registry.register(
        Command(
            name="exit",
            handler=_exit,
            allowed_modes=frozenset(CliMode),
            aliases=("quit",),
            help_text="Exit the current mode",
        )
    )
    registry.register(
        Command(
            name="end",
            handler=_end,
            allowed_modes=_CONFIG_MODES,
            help_text="Return to privileged EXEC mode",
        )
    )
    registry.register(
        Command(
            name="show version",
            handler=_show_version,
            allowed_modes=frozenset(CliMode),
            help_text="Show the netsim CLI engine version",
        )
    )
    registry.register(
        Command(
            name="show history",
            handler=_show_history,
            allowed_modes=frozenset(CliMode),
            help_text="Show command history for this session",
        )
    )

    return registry
