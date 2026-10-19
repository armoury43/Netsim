"""CLI commands that operate on configured virtual devices.

Handlers use structural device-capability protocols instead of importing
concrete router, switch, or host classes. Generic navigation commands are
reused from :mod:`netsim.cli.builtin_commands`; device-aware commands delegate
validation and state changes to the device models.
"""

from __future__ import annotations

from netsim.cli.builtin_commands import (
    _CONFIG_MODES,
    _disable,
    _enable,
    _end,
    _exit,
    _hostname,
    _router,
    _show_history,
    _show_version,
    _vlan_id,
    _configure_terminal,
)
from netsim.cli.command import Argument, Command, CommandContext, CommandResult
from netsim.cli.device_interface import (
    AclCapableDeviceContext,
    FullDeviceContext,
    MacTableCapableDeviceContext,
    RipCapableDeviceContext,
    StaticRoutingCapableDeviceContext,
    VlanCapableDeviceContext,
)
from netsim.cli.modes import CliMode, ModeContext
from netsim.cli.registry import CommandRegistry
from netsim.core.exceptions import ValidationError
from netsim.devices.errors import UnsupportedCapabilityError

_INTERFACE_CONFIG_MODE = frozenset({CliMode.INTERFACE_CONFIG})


def _vlan_list(raw: str) -> set[int]:
    """Parse a comma-separated VLAN list, e.g. ``"10,20,30"``.

    CLI-level syntax validation only (well-formed, in-range VLAN IDs)
    - the same class of check the existing single-VLAN ``_vlan_id``
    validator does, not device-specific business logic.
    """
    vlans: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part.isdigit():
            raise ValidationError(f"{raw!r} is not a valid VLAN list", field="vlans", value=raw)
        vlan_id = int(part)
        if not (1 <= vlan_id <= 4094):
            raise ValidationError("VLAN ID must be between 1 and 4094", field="vlans", value=raw)
        vlans.add(vlan_id)
    return vlans


def _acl_number(raw: str) -> int:
    """Parse a standard ACL number - CLI-level syntax validation only
    (well-formed, in the legal 1-99 standard-ACL range), same class of
    check as ``_vlan_id``/``_vlan_list``, not device-specific business
    logic."""
    if not raw.isdigit():
        raise ValidationError(f"{raw!r} is not a valid ACL number", field="number", value=raw)
    number = int(raw)
    if not (1 <= number <= 99):
        raise ValidationError(
            "Standard ACL numbers must be between 1 and 99", field="number", value=raw
        )
    return number


def _as_full_device(device: object) -> FullDeviceContext:
    """Narrow ``context.device`` to :class:`FullDeviceContext`.

    Every handler in this module that needs interface/configuration
    access calls this first. It exists so a session that was somehow
    built with a device that only satisfies the minimal
    ``DeviceContext`` (or no device at all) fails with one clear,
    consistent message instead of an ``AttributeError`` deep inside a
    handler.

    Raises:
        UnsupportedCapabilityError: If ``device`` doesn't satisfy
            :class:`FullDeviceContext`.
    """
    if not isinstance(device, FullDeviceContext):
        raise UnsupportedCapabilityError(
            "% This session's device does not support interface/configuration commands"
        )
    return device


def _interface(context: CommandContext) -> CommandResult:
    device = _as_full_device(context.device)
    interface = device.get_interface(context.args["name"])
    return CommandResult(
        mode_push=ModeContext(mode=CliMode.INTERFACE_CONFIG, params={"interface": interface.name})
    )


def _vlan(context: CommandContext) -> CommandResult:
    device = context.device
    vlan_id = context.args["id"]
    if not isinstance(device, VlanCapableDeviceContext):
        raise UnsupportedCapabilityError(
            "% VLAN configuration is not supported on this device type"
        )
    device.get_or_create_vlan(vlan_id)
    return CommandResult(mode_push=ModeContext(mode=CliMode.VLAN_CONFIG, params={"vlan_id": str(vlan_id)}))


def _current_interface(context: CommandContext) -> str:
    """Interface name for the mode the CLI is currently in, per
    ModeContext.params - see CommandContext.mode_params."""
    return context.mode_params["interface"]


def _description(context: CommandContext) -> CommandResult:
    device = _as_full_device(context.device)
    interface = device.get_interface(_current_interface(context))
    interface.set_description(context.args.get("text", ""))
    return CommandResult()


def _ip_address(context: CommandContext) -> CommandResult:
    device = _as_full_device(context.device)

    device.configure_ipv4(_current_interface(context), context.args["ip"], context.args["mask"])
    return CommandResult()


def _shutdown(context: CommandContext) -> CommandResult:
    device = _as_full_device(context.device)
    device.get_interface(_current_interface(context)).set_admin_up(False)
    return CommandResult()


def _no_shutdown(context: CommandContext) -> CommandResult:
    device = _as_full_device(context.device)
    device.get_interface(_current_interface(context)).set_admin_up(True)
    return CommandResult()


def _switchport_access_vlan(context: CommandContext) -> CommandResult:
    device = _as_full_device(context.device)

    device.get_interface(_current_interface(context)).set_switchport_access_vlan(context.args["vlan_id"])
    return CommandResult()


def _switchport_mode_trunk(context: CommandContext) -> CommandResult:
    device = _as_full_device(context.device)
    device.get_interface(_current_interface(context)).set_switchport_trunk()
    return CommandResult()


def _switchport_trunk_allowed_vlan(context: CommandContext) -> CommandResult:
    device = _as_full_device(context.device)
    device.get_interface(_current_interface(context)).set_switchport_trunk(
        allowed_vlans=context.args["vlans"]
    )
    return CommandResult()


def _show_running_config(context: CommandContext) -> CommandResult:
    device = _as_full_device(context.device)
    return CommandResult(output=device.render_running_config().splitlines())


def _show_startup_config(context: CommandContext) -> CommandResult:
    device = _as_full_device(context.device)
    return CommandResult(output=device.render_startup_config().splitlines())


def _show_interfaces(context: CommandContext) -> CommandResult:
    device = _as_full_device(context.device)
    lines: list[str] = []
    for name in sorted(device.interfaces):
        iface = device.interfaces[name]
        lines.append(f"{iface.name} is {iface.status_summary()}")
        if iface.description:
            lines.append(f"  Description: {iface.description}")
        if iface.ipv4_address is not None:
            lines.append(f"  Internet address: {iface.ipv4_address}/{iface.ipv4_prefix_length}")
    return CommandResult(output=lines)


def _show_ip_interface_brief(context: CommandContext) -> CommandResult:
    device = _as_full_device(context.device)
    lines = [f"{'Interface':<22}{'IP-Address':<16}{'Status':<24}{'Protocol'}"]
    for name in sorted(device.interfaces):
        iface = device.interfaces[name]
        ip_address = iface.ipv4_address or "unassigned"
        status = "up" if iface.admin_up else "administratively down"
        protocol = "up" if iface.admin_up else "down"
        lines.append(f"{name:<22}{ip_address:<16}{status:<24}{protocol}")
    return CommandResult(output=lines)


def _copy_running_config_startup_config(context: CommandContext) -> CommandResult:
    device = _as_full_device(context.device)
    device.save_config()
    return CommandResult(output=["Building configuration...", "[OK]"])


def _reload(context: CommandContext) -> CommandResult:
    device = _as_full_device(context.device)
    device.reload()

    if context.network is not None:
        context.network.forget_rip_routes(device.device_id)
    return CommandResult(output=["Reload complete."])


def _show_mac_address_table(context: CommandContext) -> CommandResult:
    device = context.device
    if not isinstance(device, MacTableCapableDeviceContext):
        raise UnsupportedCapabilityError("% This device does not support a MAC address table")
    lines = [f"{'Mac Address':<20}{'Port'}"]
    for mac_address, port in sorted(device.mac_table.items()):
        lines.append(f"{mac_address:<20}{port}")
    return CommandResult(output=lines)


def _ip_route(context: CommandContext) -> CommandResult:
    device = context.device
    if not isinstance(device, StaticRoutingCapableDeviceContext):
        raise UnsupportedCapabilityError("% Static routing is not supported on this device type")

    device.add_static_route(context.args["network"], context.args["mask"], context.args["next_hop"])
    return CommandResult()


def _network(context: CommandContext) -> CommandResult:

    protocol = context.mode_params.get("protocol", "")
    if protocol.lower() != "rip":
        raise UnsupportedCapabilityError(
            f"% Routing protocol {protocol!r} is not supported by this network command"
        )
    device = context.device
    if not isinstance(device, RipCapableDeviceContext):
        raise UnsupportedCapabilityError("% RIP is not supported on this device type")

    device.enable_rip(context.args["network"], context.args["mask"])
    return CommandResult()


def _access_list(context: CommandContext) -> CommandResult:
    device = context.device
    if not isinstance(device, AclCapableDeviceContext):
        raise UnsupportedCapabilityError("% Access control lists are not supported on this device type")

    device.add_access_list_rule(
        context.args["number"],
        context.args["action"],
        context.args["network"],
        context.args.get("mask"),
    )
    return CommandResult()


def _ip_access_group(context: CommandContext) -> CommandResult:
    device = context.device
    if not isinstance(device, AclCapableDeviceContext):
        raise UnsupportedCapabilityError("% Access control lists are not supported on this device type")
    interface_name = _current_interface(context)

    device.set_interface_acl(interface_name, context.args["direction"], context.args["number"])
    return CommandResult()


def _no_ip_access_group(context: CommandContext) -> CommandResult:
    device = context.device
    if not isinstance(device, AclCapableDeviceContext):
        raise UnsupportedCapabilityError("% Access control lists are not supported on this device type")
    interface_name = _current_interface(context)
    device.remove_interface_acl(
        interface_name,
        context.args["direction"],
        context.args["number"],
    )
    return CommandResult()


def build_device_registry() -> CommandRegistry:
    """Build a :class:`CommandRegistry` for a session with a real device attached.

    Returns:
        A fresh registry containing the reused navigation commands and
        the device-aware commands implemented across the current stages.
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
    registry.register(
        Command(
            name="description",
            handler=_description,
            allowed_modes=_INTERFACE_CONFIG_MODE,
            arguments=(Argument(name="text", required=False, help_text="Interface description"),),
            help_text="Set the interface description",
        )
    )
    registry.register(
        Command(
            name="ip address",
            handler=_ip_address,
            allowed_modes=_INTERFACE_CONFIG_MODE,
            arguments=(Argument(name="ip", help_text="IPv4 address"), Argument(name="mask", help_text="Subnet mask")),
            help_text="Set the interface's IPv4 address",
        )
    )
    registry.register(
        Command(
            name="shutdown",
            handler=_shutdown,
            allowed_modes=_INTERFACE_CONFIG_MODE,
            help_text="Administratively disable the interface",
        )
    )
    registry.register(
        Command(
            name="no shutdown",
            handler=_no_shutdown,
            allowed_modes=_INTERFACE_CONFIG_MODE,
            help_text="Administratively enable the interface",
        )
    )
    registry.register(
        Command(
            name="switchport access vlan",
            handler=_switchport_access_vlan,
            allowed_modes=_INTERFACE_CONFIG_MODE,
            arguments=(Argument(name="vlan_id", validator=_vlan_id, help_text="Access VLAN ID (1-4094)"),),
            help_text="Assign this port to an access VLAN",
        )
    )
    registry.register(
        Command(
            name="switchport mode trunk",
            handler=_switchport_mode_trunk,
            allowed_modes=_INTERFACE_CONFIG_MODE,
            help_text="Configure this port as a trunk",
        )
    )
    registry.register(
        Command(
            name="switchport trunk allowed vlan",
            handler=_switchport_trunk_allowed_vlan,
            allowed_modes=_INTERFACE_CONFIG_MODE,
            arguments=(Argument(name="vlans", validator=_vlan_list, help_text="Comma-separated VLAN list"),),
            help_text="Set the VLANs allowed across this trunk",
        )
    )
    registry.register(
        Command(
            name="show running-config",
            handler=_show_running_config,
            allowed_modes=frozenset(CliMode),
            help_text="Show the current running configuration",
        )
    )
    registry.register(
        Command(
            name="show startup-config",
            handler=_show_startup_config,
            allowed_modes=frozenset(CliMode),
            help_text="Show the saved startup configuration",
        )
    )
    registry.register(
        Command(
            name="show interfaces",
            handler=_show_interfaces,
            allowed_modes=frozenset(CliMode),
            help_text="Show interface status and configuration",
        )
    )
    registry.register(
        Command(
            name="show ip interface brief",
            handler=_show_ip_interface_brief,
            allowed_modes=frozenset(CliMode),
            help_text="Show a summary of interface IP status",
        )
    )
    registry.register(
        Command(
            name="copy running-config startup-config",
            handler=_copy_running_config_startup_config,
            allowed_modes=frozenset({CliMode.PRIVILEGED_EXEC}),
            help_text="Save the running configuration as startup configuration",
        )
    )
    registry.register(
        Command(
            name="reload",
            handler=_reload,
            allowed_modes=frozenset({CliMode.PRIVILEGED_EXEC}),
            help_text="Reload the device, restoring startup configuration",
        )
    )
    registry.register(
        Command(
            name="show mac address-table",
            handler=_show_mac_address_table,
            allowed_modes=frozenset(CliMode),
            help_text="Show the learned MAC address table",
        )
    )
    registry.register(
        Command(
            name="ip route",
            handler=_ip_route,
            allowed_modes=frozenset({CliMode.GLOBAL_CONFIG}),
            arguments=(
                Argument(name="network", help_text="Destination network"),
                Argument(name="mask", help_text="Subnet mask"),
                Argument(name="next_hop", help_text="Next-hop IPv4 address"),
            ),
            help_text="Configure a static route",
        )
    )
    registry.register(
        Command(
            name="network",
            handler=_network,
            allowed_modes=frozenset({CliMode.ROUTER_CONFIG}),
            arguments=(
                Argument(name="network", help_text="Network to run RIP on"),
                Argument(name="mask", help_text="Subnet mask"),
            ),
            help_text="Enable RIP on interfaces within this network",
        )
    )
    registry.register(
        Command(
            name="access-list",
            handler=_access_list,
            allowed_modes=frozenset({CliMode.GLOBAL_CONFIG}),
            arguments=(
                Argument(name="number", validator=_acl_number, help_text="ACL number (1-99)"),
                Argument(name="action", help_text="permit or deny"),
                Argument(name="network", help_text="Source network, or 'any'"),
                Argument(name="mask", required=False, help_text="Subnet mask (omit for 'any')"),
            ),
            help_text="Configure a standard access list",
        )
    )
    registry.register(
        Command(
            name="ip access-group",
            handler=_ip_access_group,
            allowed_modes=_INTERFACE_CONFIG_MODE,
            arguments=(
                Argument(name="number", validator=_acl_number, help_text="ACL number (1-99)"),
                Argument(name="direction", help_text="in or out"),
            ),
            help_text="Apply an access list to this interface",
        )
    )
    registry.register(
        Command(
            name="no ip access-group",
            handler=_no_ip_access_group,
            allowed_modes=_INTERFACE_CONFIG_MODE,
            arguments=(
                Argument(name="number", validator=_acl_number, help_text="ACL number (1-99)"),
                Argument(name="direction", help_text="in or out"),
            ),
            help_text="Remove an access list from this interface",
        )
    )

    return registry
