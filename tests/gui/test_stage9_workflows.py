"""Interactive GUI workflow tests that run under a virtual X display in CI."""

from __future__ import annotations

from pathlib import Path

try:
    import tkinter as tk
except ImportError:
    tk = None

import pytest

import netsim.gui.app as gui_module
from netsim.gui.app import ConnectDialog, NetworkSimulatorApp


@pytest.fixture
def gui_workflow_app(monkeypatch, tmp_path):
    if tk is None:
        pytest.skip("Tkinter is not installed")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config-home"))
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display is unavailable: {exc}")
    root.withdraw()
    app = NetworkSimulatorApp(root)
    try:
        yield app
    finally:
        root.destroy()


def test_gui_device_link_terminal_and_connect_dialog_workflow(gui_workflow_app, monkeypatch) -> None:
    app = gui_workflow_app
    requested_names = iter(("SW1", "PC2"))
    monkeypatch.setattr(gui_module.simpledialog, "askstring", lambda *args, **kwargs: next(requested_names))

    app.add_device("switch")
    switch = app.workspace.resolve_device("SW1")
    assert app.workspace.active_device is switch
    app.add_device("host")
    pc2 = app.workspace.resolve_device("PC2")
    router = app.workspace.resolve_device("Router")

    assert app._connect_devices(router, "GigabitEthernet0/1", switch, "FastEthernet0/1")
    assert app._connect_devices(switch, "FastEthernet0/2", pc2, "Ethernet0")
    assert len(app.workspace.topology.links()) == 3

    assert app.select_device("PC2") is None
    assert app.session.device is pc2
    assert app._find_selected_link() is not None
    app.set_selected_link_state(False)
    assert app._find_selected_link() is not None and not app._find_selected_link().up
    app.set_selected_link_state(True)
    assert app._find_selected_link() is not None and app._find_selected_link().up
    app.disconnect_selected_link()
    assert len(app.workspace.topology.links()) == 2

    dialog = ConnectDialog(app.root, list(app.workspace.devices), app._connect_devices)
    dialog._device_vars[0].set(next(label for label, device in dialog._device_by_label.items() if device.hostname == "SW1"))
    dialog._device_vars[1].set(next(label for label, device in dialog._device_by_label.items() if device.hostname == "PC2"))
    dialog._refresh_interfaces(0)
    dialog._refresh_interfaces(1)
    dialog._interface_vars[0].set("FastEthernet0/2")
    dialog._interface_vars[1].set("Ethernet0")
    dialog._submit()
    app.root.update_idletasks()
    assert len(app.workspace.topology.links()) == 3

    app.command_var.set("show devices")
    app.execute_command()
    assert "PC2" in app.terminal_output.get("1.0", tk.END)
    assert app._history_older() == "break"
    assert app.command_var.get() == "show devices"
    assert app._history_newer() == "break"
    assert app.command_var.get() == ""

    monkeypatch.setattr(gui_module.messagebox, "askyesno", lambda *args, **kwargs: True)
    app.remove_selected_device()
    assert "PC2" not in [device.hostname for device in app.workspace.devices]
    assert len(app.workspace.topology.links()) == 2


def test_gui_scenario_save_open_reset_new_lab_and_appearance(gui_workflow_app, monkeypatch, tmp_path) -> None:
    app = gui_workflow_app
    scenario_label = next(iter(app.scenario_ids))
    app.scenario_var.set(scenario_label)
    app.load_scenario()
    assert app.workspace.active_scenario is not None

    app.verify_lab()
    assert "FAIL:" in app.verify_output.get("1.0", tk.END)

    lab_path = tmp_path / "lab with spaces.json"
    monkeypatch.setattr(gui_module.filedialog, "asksaveasfilename", lambda *args, **kwargs: str(lab_path))
    app.save_lab()
    assert lab_path.is_file()

    monkeypatch.setattr(gui_module.messagebox, "askyesno", lambda *args, **kwargs: True)
    app.workspace.create_device("host", "TEMP")
    app.reset_lab()
    assert "TEMP" not in [device.hostname for device in app.workspace.devices]

    app.workspace.create_device("host", "TEMP2")
    monkeypatch.setattr(gui_module.filedialog, "askopenfilename", lambda *args, **kwargs: str(lab_path))
    app.open_lab()
    assert "TEMP2" not in [device.hostname for device in app.workspace.devices]
    assert app.workspace.active_scenario is not None

    app.new_lab()
    assert app.workspace.devices == ()
    assert app.workspace.active_scenario is None

    chosen_colors = iter(("#123456", "#abcdef", "#00aa00", "#ff0000"))
    monkeypatch.setattr(gui_module.colorchooser, "askcolor", lambda *args, **kwargs: (None, next(chosen_colors)))
    app.open_appearance()
    assert (tmp_path / "config-home" / "netsim" / "config.yaml").is_file()
