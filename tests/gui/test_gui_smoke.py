"""Small GUI integration checks; display-free CI skips these automatically."""

from __future__ import annotations

try:
    import tkinter as tk
except ImportError:
    tk = None

import pytest

from netsim.gui.app import NetworkSimulatorApp


@pytest.fixture

def gui_app():
    if tk is None:
        pytest.skip("Tkinter is not installed")
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display is unavailable: {exc}")
    root.withdraw()
    app = NetworkSimulatorApp(root)
    root.update_idletasks()
    try:
        yield app
    finally:
        root.destroy()


def test_gui_builds_and_uses_real_cli_session(gui_app: NetworkSimulatorApp) -> None:
    gui_app.command_var.set("show devices")
    gui_app.execute_command()
    gui_app.root.update_idletasks()
    text = gui_app.terminal_output.get("1.0", tk.END)

    assert "Router" in text
    assert "PC1" in text
    assert gui_app.session.workspace is gui_app.workspace
    assert gui_app.workspace.active_device is not None


def test_gui_can_load_and_verify_a_builtin_scenario(gui_app: NetworkSimulatorApp) -> None:
    gui_app.scenario_var.set(next(iter(gui_app.scenario_ids)))
    gui_app.load_scenario()
    gui_app.verify_lab()
    gui_app.root.update_idletasks()
    report = gui_app.verify_output.get("1.0", tk.END)

    assert gui_app.workspace.active_scenario is not None
    assert "PASS:" in report or "FAIL:" in report
    assert "PC1" in report


def test_gui_link_controls_operate_on_the_workspace(gui_app: NetworkSimulatorApp) -> None:
    from netsim.network.topology import Topology
    from netsim.runtime import build_runtime

    gui_app._replace_runtime(build_runtime(topology=Topology(), name="GUI Link Test"))
    router = gui_app.workspace.create_device("router", "R1")
    host = gui_app.workspace.create_device("host", "PC1")
    gui_app._refresh_all()

    assert gui_app._connect_devices(router, "GigabitEthernet0/0", host, "Ethernet0")
    assert len(gui_app.workspace.topology.links()) == 1
    gui_app.set_selected_link_state(False)
    assert gui_app.workspace.topology.links()[0].up is False
    gui_app.disconnect_selected_link()
    assert gui_app.workspace.topology.links() == []
