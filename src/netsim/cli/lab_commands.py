"""CLI commands for workspace, device, and lab lifecycle management."""

from __future__ import annotations

from typing import cast

from netsim.cli.command import Argument, Command, CommandContext, CommandResult
from netsim.cli.lab_interface import LabContext
from netsim.cli.modes import CliMode
from netsim.cli.registry import CommandRegistry
from netsim.core.exceptions import ValidationError
from netsim.labs.scenarios import list_scenarios

_EXEC_MODES = frozenset({CliMode.USER_EXEC, CliMode.PRIVILEGED_EXEC})


def _workspace(context: CommandContext) -> LabContext:
    if context.workspace is None:
        raise ValidationError("Lab commands require an active lab workspace", field="workspace")
    return cast(LabContext, context.workspace)


def _show_devices(context: CommandContext) -> CommandResult:
    return CommandResult(output=["Hostname         Type     State        Device ID", *_workspace(context).devices_summary()])


def _show_topology(context: CommandContext) -> CommandResult:
    return CommandResult(output=_workspace(context).topology_summary())


def _device_add(context: CommandContext) -> CommandResult:
    workspace = _workspace(context)
    raw_interfaces = context.args.get("interfaces")
    interface_names = None
    if raw_interfaces is not None:
        interface_names = [name.strip() for name in str(raw_interfaces).split(",")]
        if any(not name for name in interface_names):
            raise ValidationError("Interfaces must be comma-separated names without empty entries", field="interfaces")
    device = workspace.create_device(
        str(context.args["type"]), str(context.args["hostname"]), interface_names
    )
    return CommandResult(
        output=[f"Created {device.device_type.name.lower()} {device.hostname} ({device.device_id})."]
    )


def _device_remove(context: CommandContext) -> CommandResult:
    removed = _workspace(context).remove_device(str(context.args["hostname"]))
    return CommandResult(output=[f"Removed {removed.hostname} and its connected links."])


def _device_select(context: CommandContext) -> CommandResult:
    device = _workspace(context).select_device(str(context.args["hostname"]))
    return CommandResult(output=[f"Selected {device.hostname}."])


def _connect(context: CommandContext) -> CommandResult:
    args = context.args
    link = _workspace(context).connect(
        str(args["device_a"]), str(args["interface_a"]),
        str(args["device_b"]), str(args["interface_b"]),
    )
    return CommandResult(output=[
        f"Connected {args['device_a']}:{args['interface_a']} <-> "
        f"{args['device_b']}:{args['interface_b']} (link up)."
    ])


def _disconnect(context: CommandContext) -> CommandResult:
    args = context.args
    changed = _workspace(context).disconnect(str(args["hostname"]), str(args["interface"]))
    if not changed:
        return CommandResult(output=[f"No link is connected to {args['hostname']}:{args['interface']}."])
    return CommandResult(output=[f"Disconnected {args['hostname']}:{args['interface']}."])


def _set_link_state(context: CommandContext, up: bool) -> CommandResult:
    args = context.args
    workspace = _workspace(context)
    workspace.set_link_state(str(args["hostname"]), str(args["interface"]), up)
    state = "up" if up else "down"
    return CommandResult(output=[f"Link on {args['hostname']}:{args['interface']} set {state}."])


def _link_up(context: CommandContext) -> CommandResult:
    return _set_link_state(context, True)


def _link_down(context: CommandContext) -> CommandResult:
    return _set_link_state(context, False)


def _lab_save(context: CommandContext) -> CommandResult:
    path = _workspace(context).save(str(context.args["path"]))
    return CommandResult(output=[f"Saved lab to {path}."])


def _lab_load(context: CommandContext) -> CommandResult:
    workspace = _workspace(context)
    path = workspace.load(str(context.args["path"]))
    selected = workspace.active_device.hostname if workspace.active_device is not None else "none"
    return CommandResult(output=[f"Loaded lab from {path}.", f"Active device: {selected}."])


def _lab_reset(context: CommandContext) -> CommandResult:
    workspace = _workspace(context)
    workspace.reset()
    selected = workspace.active_device.hostname if workspace.active_device is not None else "none"
    return CommandResult(output=[f"Reset lab to the last saved/loaded checkpoint. Active device: {selected}."])


def _lab_scenarios(context: CommandContext) -> CommandResult:
    lines = ["Available scenarios:"]
    for scenario in list_scenarios():
        lines.append(f"  {scenario.scenario_id:<20} {scenario.title} — {scenario.description}")
    return CommandResult(output=lines)


def _lab_scenario(context: CommandContext) -> CommandResult:
    workspace = _workspace(context)
    task = workspace.load_scenario(str(context.args["scenario_id"]))
    return CommandResult(output=[
        f"Loaded scenario: {workspace.name}.",
        f"Task: {task}",
        "Use 'lab verify' when you have finished configuring the lab.",
    ])


def _lab_verify(context: CommandContext) -> CommandResult:
    report = _workspace(context).verify()
    lines = [
        f"{'PASS' if report.passed else 'FAIL'}: {report.passed_count}/{len(report.checks)} checks passed."
    ]
    for check in report.checks:
        lines.append(f"{'PASS' if check.passed else 'FAIL'} {check.name}: {check.detail}")
    return CommandResult(output=lines)


def register_lab_commands(registry: CommandRegistry) -> None:
    """Register workspace and lab lifecycle commands in an existing registry."""
    registry.register(Command(
        name="show devices", handler=_show_devices, allowed_modes=_EXEC_MODES,
        help_text="List devices in the current lab",
    ))
    registry.register(Command(
        name="show topology", handler=_show_topology, allowed_modes=_EXEC_MODES,
        help_text="Show devices, links, and link state",
    ))
    registry.register(Command(
        name="device add", handler=_device_add, allowed_modes=_EXEC_MODES,
        arguments=(
            Argument("type", help_text="router, switch, or host"),
            Argument("hostname", help_text="Unique device hostname"),
            Argument("interfaces", required=False, help_text="Optional comma-separated interface names"),
        ),
        help_text="Create a virtual router, switch, or host",
    ))
    registry.register(Command(
        name="device remove", handler=_device_remove, allowed_modes=_EXEC_MODES,
        arguments=(Argument("hostname", help_text="Hostname or device ID"),),
        help_text="Remove a device and its links",
    ))
    registry.register(Command(
        name="device select", handler=_device_select, allowed_modes=_EXEC_MODES,
        arguments=(Argument("hostname", help_text="Hostname or device ID"),),
        help_text="Select the device controlled by this CLI session",
    ))
    registry.register(Command(
        name="connect", handler=_connect, allowed_modes=_EXEC_MODES,
        arguments=(
            Argument("device_a", help_text="First device hostname"),
            Argument("interface_a", help_text="Interface on first device"),
            Argument("device_b", help_text="Second device hostname"),
            Argument("interface_b", help_text="Interface on second device"),
        ),
        help_text="Connect two virtual interfaces",
    ))
    registry.register(Command(
        name="disconnect", handler=_disconnect, allowed_modes=_EXEC_MODES,
        arguments=(
            Argument("hostname", help_text="Device hostname"),
            Argument("interface", help_text="Interface whose link should be removed"),
        ),
        help_text="Disconnect a virtual interface",
    ))
    registry.register(Command(
        name="link up", handler=_link_up, allowed_modes=_EXEC_MODES,
        arguments=(Argument("hostname"), Argument("interface")),
        help_text="Bring the cable/link attached to an interface up",
    ))
    registry.register(Command(
        name="link down", handler=_link_down, allowed_modes=_EXEC_MODES,
        arguments=(Argument("hostname"), Argument("interface")),
        help_text="Take the cable/link attached to an interface down",
    ))
    registry.register(Command(
        name="lab save", handler=_lab_save, allowed_modes=_EXEC_MODES,
        arguments=(Argument("path", help_text="Destination JSON file path"),),
        help_text="Save the current lab to a JSON file",
    ))
    registry.register(Command(
        name="lab load", handler=_lab_load, allowed_modes=_EXEC_MODES,
        arguments=(Argument("path", help_text="Source JSON file path"),),
        help_text="Load a lab JSON file",
    ))
    registry.register(Command(
        name="lab reset", handler=_lab_reset, allowed_modes=_EXEC_MODES,
        help_text="Restore the last saved or loaded lab checkpoint",
    ))
    registry.register(Command(
        name="lab list-scenarios", handler=_lab_scenarios, allowed_modes=_EXEC_MODES,
        help_text="List built-in training scenarios",
    ))
    registry.register(Command(
        name="lab scenario", handler=_lab_scenario, allowed_modes=_EXEC_MODES,
        arguments=(Argument("scenario_id", help_text="Scenario identifier"),),
        help_text="Load a built-in training scenario",
    ))
    registry.register(Command(
        name="lab verify", handler=_lab_verify, allowed_modes=_EXEC_MODES,
        help_text="Check topology integrity and active scenario requirements",
    ))
