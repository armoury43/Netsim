"""The terminal and GUI are wired against one shared runtime factory."""

from netsim.cli.modes import CliMode
from netsim.runtime import build_runtime


def test_runtime_has_device_network_and_lab_commands() -> None:
    runtime = build_runtime()
    commands = {command.name for command in runtime.registry.all_commands()}

    assert runtime.session.device is runtime.workspace.active_device
    assert runtime.session.network is runtime.workspace
    assert runtime.session.workspace is runtime.workspace
    assert {"ping", "show devices", "show topology", "lab verify", "lab save"} <= commands


def test_runtime_terminal_commands_use_the_same_workspace() -> None:
    runtime = build_runtime()
    outcome = runtime.session.execute_line("show devices")

    assert outcome.error is None
    assert any("Router" in line for line in outcome.output)
    assert any("PC1" in line for line in outcome.output)
    assert runtime.session.mode_stack.current.mode is CliMode.USER_EXEC
