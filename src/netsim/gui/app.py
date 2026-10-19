"""Tkinter graphical front-end for netsim.

The GUI is a thin, synchronous client of the lab workspace and CLI session.
It does not implement network behavior itself: terminal commands use the same
parser, validation, command handlers, and NetworkEngine as text mode.
"""

from __future__ import annotations

import platform
import sys
from typing import Any, Callable, cast

try:
    import tkinter as tk
    from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk
except ImportError:
    tk = cast(Any, None)
    colorchooser = filedialog = messagebox = simpledialog = ttk = cast(Any, None)

from netsim import __version__
from netsim.core.config import Settings, load_settings, save_settings
from netsim.core.exceptions import NetsimError
from netsim.devices.base import Device
from netsim.gui.model import TopologyLinkView, build_topology_view
from netsim.labs.errors import LabError
from netsim.labs.scenarios import list_scenarios
from netsim.network.link import Link
from netsim.network.topology import Topology
from netsim.runtime import NetsimRuntime, build_runtime

_PALETTE = {
    "background": "#111827",
    "panel": "#1f2937",
    "panel_alt": "#273449",
    "button": "#334155",
    "button_hover": "#475569",
    "text": "#e5edf7",
    "muted": "#9caac0",
    "accent": "#38bdf8",
    "success": "#34d399",
    "warning": "#fbbf24",
    "error": "#fb7185",
    "router": "#2563eb",
    "switch": "#0f766e",
    "host": "#7c3aed",
    "link": "#64748b",
}


class NetworkSimulatorApp:
    """Main window and user actions for the graphical simulator."""

    def __init__(self, root: tk.Tk, runtime: NetsimRuntime | None = None) -> None:
        self.root = root
        self.runtime = runtime if runtime is not None else build_runtime()
        self.workspace = self.runtime.workspace
        self.session = self.runtime.session
        try:
            self.settings = load_settings()
        except NetsimError:
            self.settings = Settings()

        self.selected_link_key: tuple[str, str, str, str] | None = None
        self._device_ids: list[str] = []
        self._history_cursor = 0
        self._updating_devices = False
        if self.settings.theme.name == "default":
            self._custom_theme = {
                "background": _PALETTE["background"],
                "text": _PALETTE["text"],
                "prompt": _PALETTE["success"],
                "error": _PALETTE["error"],
            }
        else:
            self._custom_theme = {
                "background": self._valid_color(self.settings.theme.background_color, _PALETTE["background"]),
                "text": self._valid_color(self.settings.theme.text_color, _PALETTE["text"]),
                "prompt": self._valid_color(self.settings.theme.prompt_color, _PALETTE["success"]),
                "error": self._valid_color(self.settings.theme.error_color, _PALETTE["error"]),
            }

        self.root.title(f"netsim — Graphical Network Lab v{__version__}")
        self.root.geometry("1200x780")
        self.root.minsize(1020, 650)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_widgets()
        self._apply_theme()
        self._clear_verification()
        self._refresh_all()
        self._append_terminal(
            f"netsim v{__version__} graphical workspace ready.",
            "Tip: select a device, then use the terminal exactly like the CLI (try 'enable' and 'show ip interface brief').",
        )

    def _build_widgets(self) -> None:
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(2, weight=1)

        self.header = tk.Frame(self.root, padx=18, pady=12)
        self.header.grid(row=0, column=0, sticky="ew")
        self.header.grid_columnconfigure(0, weight=1)
        self.title_label = tk.Label(
            self.header, text="NETSIM", font=("TkDefaultFont", 20, "bold"), anchor="w"
        )
        self.title_label.grid(row=0, column=0, sticky="w")
        self.subtitle_label = tk.Label(
            self.header,
            text="Virtual network lab · topology, device CLI, verification",
            font=("TkDefaultFont", 10),
            anchor="w",
        )
        self.subtitle_label.grid(row=1, column=0, sticky="w", pady=(3, 0))
        self.lab_name_label = tk.Label(self.header, text=self.workspace.name, font=("TkDefaultFont", 12, "bold"))
        self.lab_name_label.grid(row=0, column=1, rowspan=2, sticky="e", padx=(18, 0))

        self.toolbar = tk.Frame(self.root, padx=12, pady=8)
        self.toolbar.grid(row=1, column=0, sticky="ew")
        self.toolbar.grid_columnconfigure(20, weight=1)
        self._button(self.toolbar, "New", self.new_lab).grid(row=0, column=0, padx=3)
        self._button(self.toolbar, "Open…", self.open_lab).grid(row=0, column=1, padx=3)
        self._button(self.toolbar, "Save…", self.save_lab).grid(row=0, column=2, padx=3)
        self._button(self.toolbar, "Reset", self.reset_lab).grid(row=0, column=3, padx=3)
        self._button(self.toolbar, "Verify lab", self.verify_lab, accent=True).grid(row=0, column=4, padx=(8, 3))

        self.scenario_var = tk.StringVar()
        scenario_values = [f"{scenario.scenario_id} — {scenario.title}" for scenario in list_scenarios()]
        self.scenario_ids = {value: value.split(" — ", 1)[0] for value in scenario_values}
        self.scenario_combo = ttk.Combobox(
            self.toolbar, textvariable=self.scenario_var, values=scenario_values, state="readonly", width=29
        )
        self.scenario_combo.grid(row=0, column=5, padx=(14, 3))
        if scenario_values:
            self.scenario_combo.current(0)
        self._button(self.toolbar, "Load scenario", self.load_scenario).grid(row=0, column=6, padx=3)
        self._button(self.toolbar, "Appearance", self.open_appearance).grid(row=0, column=7, padx=(12, 3))

        self.body = tk.Frame(self.root, padx=10, pady=10)
        self.body.grid(row=2, column=0, sticky="nsew")
        self.body.grid_rowconfigure(0, weight=1)
        self.body.grid_columnconfigure(1, weight=1)
        self.body.grid_columnconfigure(2, weight=1, minsize=340)

        self.sidebar = tk.Frame(self.body, width=220, padx=10, pady=10)
        self.sidebar.grid(row=0, column=0, sticky="nsw", padx=(0, 8))
        self.sidebar.grid_propagate(False)
        self.device_heading = tk.Label(self.sidebar, text="DEVICES", font=("TkDefaultFont", 10, "bold"), anchor="w")
        self.device_heading.pack(fill="x", pady=(0, 8))
        self.device_list = tk.Listbox(
            self.sidebar,
            borderwidth=0,
            highlightthickness=1,
            activestyle="none",
            exportselection=False,
            selectmode=tk.SINGLE,
            font=("TkDefaultFont", 10),
        )
        self.device_list.pack(fill="both", expand=True)
        self.device_list.bind("<<ListboxSelect>>", self._on_device_list_select)
        self.device_list.bind("<Double-Button-1>", self._on_device_list_select)

        self.device_buttons = tk.Frame(self.sidebar, pady=10)
        self.device_buttons.pack(fill="x")
        for label, kind in (("+ Router", "router"), ("+ Switch", "switch"), ("+ PC", "host")):
            self._button(self.device_buttons, label, lambda selected_kind=kind: self.add_device(selected_kind)).pack(fill="x", pady=2)
        self._button(self.device_buttons, "Connect interfaces…", self.open_connect_dialog).pack(fill="x", pady=(9, 2))
        self._button(self.device_buttons, "Disconnect selected link", self.disconnect_selected_link).pack(fill="x", pady=2)
        self.link_buttons = tk.Frame(self.sidebar)
        self.link_buttons.pack(fill="x", pady=(0, 8))
        self._button(self.link_buttons, "Link up", lambda: self.set_selected_link_state(True)).pack(side="left", expand=True, fill="x", padx=(0, 2))
        self._button(self.link_buttons, "Link down", lambda: self.set_selected_link_state(False)).pack(side="left", expand=True, fill="x", padx=(2, 0))
        self._button(self.sidebar, "Remove selected device", self.remove_selected_device, danger=True).pack(fill="x", pady=(2, 0))

        self.topology_panel = tk.Frame(self.body, padx=8, pady=8)
        self.topology_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 8))
        self.topology_panel.grid_rowconfigure(1, weight=1)
        self.topology_panel.grid_columnconfigure(0, weight=1)
        self.topology_heading = tk.Label(self.topology_panel, text="TOPOLOGY", font=("TkDefaultFont", 10, "bold"), anchor="w")
        self.topology_heading.grid(row=0, column=0, sticky="ew", pady=(2, 8))
        self.canvas = tk.Canvas(self.topology_panel, highlightthickness=0, borderwidth=0, takefocus=True)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda _event: self._draw_topology())

        self.right_panel = tk.Frame(self.body, width=360, padx=10, pady=10)
        self.right_panel.grid(row=0, column=2, sticky="nsew")
        self.right_panel.grid_propagate(False)
        self.right_panel.grid_columnconfigure(0, weight=1)
        self.right_panel.grid_columnconfigure(1, weight=0)
        self.right_panel.grid_rowconfigure(1, weight=3)
        self.right_panel.grid_rowconfigure(5, weight=1)
        self.terminal_heading = tk.Label(self.right_panel, text="DEVICE TERMINAL", font=("TkDefaultFont", 10, "bold"), anchor="w")
        self.terminal_heading.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        self.terminal_output = tk.Text(
            self.right_panel, height=20, wrap="word", state="disabled", borderwidth=0,
            padx=10, pady=10, font=("TkFixedFont", 9), undo=False,
        )
        self.terminal_output.grid(row=1, column=0, sticky="nsew")
        self.terminal_scroll = ttk.Scrollbar(self.right_panel, orient="vertical", command=self.terminal_output.yview)
        self.terminal_scroll.grid(row=1, column=1, sticky="ns")
        self.terminal_output.configure(yscrollcommand=self.terminal_scroll.set)
        self.terminal_output.tag_configure("command", foreground=_PALETTE["accent"])
        self.terminal_output.tag_configure("error", foreground=_PALETTE["error"])
        self.terminal_output.tag_configure("success", foreground=_PALETTE["success"])
        self.prompt_row = tk.Frame(self.right_panel, pady=8)
        self.prompt_row.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.prompt_row.grid_columnconfigure(1, weight=1)
        self.prompt_label = tk.Label(self.prompt_row, text="Router>", font=("TkFixedFont", 9, "bold"), anchor="w")
        self.prompt_label.grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.command_var = tk.StringVar()
        self.command_entry = tk.Entry(self.prompt_row, textvariable=self.command_var, font=("TkFixedFont", 10), borderwidth=0)
        self.command_entry.grid(row=0, column=1, sticky="ew", ipady=5)
        self.command_entry.bind("<Return>", self._submit_command)
        self.command_entry.bind("<Up>", self._history_older)
        self.command_entry.bind("<Down>", self._history_newer)
        self._button(self.prompt_row, "Run", self.execute_command, accent=True).grid(row=0, column=2, padx=(6, 0))

        self.verify_heading = tk.Label(self.right_panel, text="LAB VERIFICATION", font=("TkDefaultFont", 10, "bold"), anchor="w")
        self.verify_heading.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(5, 7))
        self.verify_output = tk.Text(
            self.right_panel, height=8, wrap="word", state="disabled", borderwidth=0,
            padx=10, pady=8, font=("TkFixedFont", 9),
        )
        self.verify_output.grid(row=5, column=0, sticky="nsew")
        self.verify_scroll = ttk.Scrollbar(self.right_panel, orient="vertical", command=self.verify_output.yview)
        self.verify_scroll.grid(row=5, column=1, sticky="ns")
        self.verify_output.configure(yscrollcommand=self.verify_scroll.set)

        self.status_var = tk.StringVar(value="Ready")
        self.status_bar = tk.Label(self.root, textvariable=self.status_var, anchor="w", padx=12, pady=5)
        self.status_bar.grid(row=3, column=0, sticky="ew")

    def _button(
        self,
        parent: tk.Misc,
        label: str,
        command: Callable[[], object],
        *,
        accent: bool = False,
        danger: bool = False,
    ) -> tk.Button:
        bg = _PALETTE["accent"] if accent else (_PALETTE["error"] if danger else _PALETTE["button"])
        fg = "#0b1220" if accent else ("#20070e" if danger else _PALETTE["text"])
        return tk.Button(
            parent,
            text=label,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=_PALETTE["button_hover"],
            activeforeground=_PALETTE["text"],
            relief="flat",
            borderwidth=0,
            padx=9,
            pady=6,
            cursor="hand2",
            font=("TkDefaultFont", 9),
        )

    def _valid_color(self, value: str, fallback: str) -> str:
        try:
            self.root.winfo_rgb(value)
            return value
        except (tk.TclError, TypeError):
            return fallback

    def _apply_theme(self) -> None:
        bg = self._custom_theme["background"]
        text = self._custom_theme["text"]
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "TCombobox", fieldbackground=_PALETTE["panel_alt"],
            background=_PALETTE["button"], foreground=text, arrowcolor=text,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", _PALETTE["panel_alt"])],
            foreground=[("readonly", text)],
        )
        for frame in (self.root, self.header, self.toolbar, self.body, self.sidebar, self.topology_panel, self.right_panel, self.prompt_row, self.device_buttons, self.link_buttons):
            frame.configure(bg=bg if frame in (self.root, self.body) else _PALETTE["panel"])
        for label in (
            self.title_label, self.subtitle_label, self.lab_name_label,
            self.terminal_heading, self.prompt_label, self.status_bar,
            self.device_heading, self.topology_heading, self.verify_heading,
        ):
            label.configure(bg=_PALETTE["panel"], fg=text)
        self.title_label.configure(fg=self._custom_theme["prompt"])
        self.subtitle_label.configure(fg=_PALETTE["muted"])
        self.terminal_output.configure(bg="#0b1120", fg=text, insertbackground=text)
        self.verify_output.configure(bg="#0b1120", fg=text, insertbackground=text)
        self.command_entry.configure(bg="#0b1120", fg=text, insertbackground=text)
        self.prompt_label.configure(fg=self._custom_theme["prompt"])
        self.device_list.configure(bg=_PALETTE["panel_alt"], fg=text, selectbackground=_PALETTE["accent"], selectforeground="#0b1220", highlightbackground=_PALETTE["panel"])
        self.canvas.configure(bg=bg)
        self.status_bar.configure(bg=_PALETTE["panel"])

    def _refresh_all(self) -> None:
        self.lab_name_label.configure(text=self.workspace.name)
        self._refresh_devices()
        self.session.device = self.workspace.active_device
        self.prompt_label.configure(text=self.session.prompt())
        self._draw_topology()

    def _refresh_devices(self) -> None:
        active_id = self.workspace.active_device.device_id if self.workspace.active_device is not None else None
        self._updating_devices = True
        try:
            self.device_list.delete(0, tk.END)
            self._device_ids = []
            selected_index = None
            for device in self.workspace.devices:
                icon = {"ROUTER": "R", "SWITCH": "SW", "HOST": "PC"}.get(device.device_type.name, "?")
                summary = f"{device.hostname} [{icon}] {device.state.name.title()}"
                self.device_list.insert(tk.END, summary)
                self._device_ids.append(device.device_id)
                if device.device_id == active_id:
                    selected_index = len(self._device_ids) - 1
            if selected_index is not None:
                self.device_list.selection_set(selected_index)
                self.device_list.activate(selected_index)
        finally:
            self._updating_devices = False

    def _draw_topology(self) -> None:
        if not hasattr(self, "canvas"):
            return
        self.canvas.delete("all")
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        view = build_topology_view(self.workspace, width, height, margin=78, min_column_gap=200, min_row_gap=150)
        node_centers = {node.device_id: (node.x, node.y) for node in view.nodes}

        if not view.nodes:
            self.canvas.create_text(
                width / 2, height / 2 - 12,
                text="Your lab is empty", fill=_PALETTE["text"],
                font=("TkDefaultFont", 17, "bold"),
            )
            self.canvas.create_text(
                width / 2, height / 2 + 18,
                text="Add a router, switch, or PC to start building a topology.",
                fill=_PALETTE["muted"], font=("TkDefaultFont", 10),
            )
            return

        for index, link in enumerate(view.links):
            key = link.key
            selected = key == self.selected_link_key
            color = _PALETTE["success"] if link.up else _PALETTE["error"]
            line_tag = f"link_{index}"
            self.canvas.create_line(
                link.x1, link.y1, link.x2, link.y2,
                fill=color if link.up else _PALETTE["error"],
                width=4 if selected else 2,
                dash=() if link.up else (7, 5),
                capstyle=tk.ROUND,
                tags=("link", line_tag),
            )
            mid_x = (link.x1 + link.x2) / 2
            mid_y = (link.y1 + link.y2) / 2
            label = "UP" if link.up else "DOWN"
            self.canvas.create_text(
                mid_x, mid_y - 9, text=label,
                fill=color, font=("TkDefaultFont", 8, "bold"), tags=("link", line_tag),
            )
            self.canvas.tag_bind(line_tag, "<Button-1>", lambda event, link_view=link: self._on_link_click(event, link_view))

        for node in view.nodes:
            x, y = node.x, node.y
            selected = self.workspace.active_device is not None and self.workspace.active_device.device_id == node.device_id
            outline = _PALETTE["accent"] if selected else "#9fb0c6"
            outline_width = 3 if selected else 1
            fill = {
                "Router": _PALETTE["router"],
                "Switch": _PALETTE["switch"],
                "Host": _PALETTE["host"],
            }.get(node.device_type, _PALETTE["button"])
            tag = f"node_{node.device_id}"
            if node.device_type == "Router":
                points = [x - 48, y - 23, x - 31, y - 43, x + 31, y - 43, x + 48, y - 23, x + 48, y + 23, x + 31, y + 43, x - 31, y + 43, x - 48, y + 23]
                self.canvas.create_polygon(points, fill=fill, outline=outline, width=outline_width, tags=("node", tag))
                icon_text = "R"
            elif node.device_type == "Switch":
                self.canvas.create_rectangle(x - 49, y - 33, x + 49, y + 33, fill=fill, outline=outline, width=outline_width, tags=("node", tag))
                icon_text = "SW"
            else:
                self.canvas.create_oval(x - 37, y - 33, x + 37, y + 33, fill=fill, outline=outline, width=outline_width, tags=("node", tag))
                icon_text = "PC"
            self.canvas.create_text(x, y, text=icon_text, fill="white", font=("TkDefaultFont", 13, "bold"), tags=("node", tag))
            state_color = _PALETTE["success"] if node.lifecycle_state == "Ready" else _PALETTE["warning"]
            self.canvas.create_text(x, y + 58, text=node.hostname, fill=_PALETTE["text"], font=("TkDefaultFont", 10, "bold"), tags=("node", tag))
            self.canvas.create_text(
                x, y + 76,
                text=f"{node.interfaces_up}/{node.interface_count} interfaces up",
                fill=state_color, font=("TkDefaultFont", 8), tags=("node", tag),
            )
            self.canvas.create_text(x, y + 91, text=node.lifecycle_state, fill=_PALETTE["muted"], font=("TkDefaultFont", 8), tags=("node", tag))
            self.canvas.tag_bind(tag, "<Button-1>", lambda event, device_id=node.device_id: self._on_node_click(event, device_id))
            self.canvas.tag_bind(tag, "<Double-Button-1>", lambda event, device_id=node.device_id: self._on_node_double_click(event, device_id))

    def _on_device_list_select(self, _event: object | None = None) -> None:
        if self._updating_devices:
            return
        selection = self.device_list.curselection()
        if not selection:
            return
        index = int(selection[0])
        if 0 <= index < len(self._device_ids):
            self.select_device(self._device_ids[index])

    def _on_node_click(self, _event: object, device_id: str) -> None:
        self.select_device(device_id)

    def _on_node_double_click(self, _event: object, device_id: str) -> None:
        self.select_device(device_id)
        self.command_entry.focus_set()

    def select_device(self, reference: str) -> None:
        try:
            self.workspace.select_device(reference)
        except (NetsimError, LabError, ValueError) as exc:
            self._set_status(str(exc), error=True)
            return
        self.session.device = self.workspace.active_device
        self.session.mode_stack.reset()
        self._history_cursor = len(self.session.history.all())
        self._refresh_all()
        active = self.workspace.active_device
        if active is not None:
            self._set_status(f"Selected {active.hostname}. Terminal mode reset to user EXEC.")

    def add_device(self, device_type: str) -> None:
        label = {"router": "router", "switch": "switch", "host": "PC/host"}.get(device_type, device_type)
        hostname = simpledialog.askstring("Add device", f"Hostname for new {label}:", parent=self.root)
        if hostname is None:
            return
        try:
            device = self.workspace.create_device(device_type, hostname.strip())
            self.workspace.select_device(device.device_id)
            self.session.device = device
            self.session.mode_stack.reset()
            self.selected_link_key = None
            self._refresh_all()
            self._append_terminal(f"Created {device.device_type.name.lower()} {device.hostname} ({device.device_id}).")
            self._set_status(f"Created {device.hostname}; configure its interfaces in the terminal.")
        except (NetsimError, LabError, ValueError) as exc:
            messagebox.showerror("Could not add device", str(exc), parent=self.root)

    def remove_selected_device(self) -> None:
        active = self.workspace.active_device
        if active is None:
            messagebox.showinfo("Remove device", "Select a device first.", parent=self.root)
            return
        if not messagebox.askyesno("Remove device", f"Remove {active.hostname} and its connected links?", parent=self.root):
            return
        try:
            removed = self.workspace.remove_device(active.device_id)
            self.session.device = self.workspace.active_device
            self.session.mode_stack.reset()
            self.selected_link_key = None
            self._refresh_all()
            self._append_terminal(f"Removed {removed.hostname} and its connected links.")
            self._set_status(f"Removed {removed.hostname}.")
        except (NetsimError, LabError, ValueError) as exc:
            messagebox.showerror("Could not remove device", str(exc), parent=self.root)

    def open_connect_dialog(self) -> None:
        devices = list(self.workspace.devices)
        if len(devices) < 2:
            messagebox.showinfo("Connect interfaces", "Add at least two devices before connecting interfaces.", parent=self.root)
            return
        ConnectDialog(self.root, devices, self._connect_devices)

    def _connect_devices(self, device_a: Device, interface_a: str, device_b: Device, interface_b: str) -> bool:
        try:
            link = self.workspace.connect(device_a.device_id, interface_a, device_b.device_id, interface_b)
            self.selected_link_key = TopologyLinkView(
                device_a.device_id, interface_a, device_b.device_id, interface_b, link.up, 0, 0, 0, 0
            ).key
            self._refresh_all()
            self._append_terminal(f"Connected {device_a.hostname}:{interface_a} <-> {device_b.hostname}:{interface_b} (link up).")
            self._set_status("Link connected. Note: interface administrative state is configured separately.")
            return True
        except (NetsimError, LabError, ValueError) as exc:
            messagebox.showerror("Could not connect interfaces", str(exc), parent=self.root)
            return False

    def _on_link_click(self, _event: object, link_view: TopologyLinkView) -> None:
        self.selected_link_key = link_view.key
        self._draw_topology()
        a = f"{self._hostname_for(link_view.endpoint_a_device_id)}:{link_view.endpoint_a_interface}"
        b = f"{self._hostname_for(link_view.endpoint_b_device_id)}:{link_view.endpoint_b_interface}"
        self._set_status(f"Selected link: {a} ↔ {b} — {'up' if link_view.up else 'down'}.")

    def _hostname_for(self, device_id: str) -> str:
        device = self.workspace.topology.devices().get(device_id)
        return device.hostname if device is not None else device_id[:8]

    def _find_selected_link(self) -> Link | None:
        if self.selected_link_key is None:
            return None
        for link in self.workspace.topology.links():
            candidate = TopologyLinkView(
                link.endpoint_a.device_id, link.endpoint_a.interface_name,
                link.endpoint_b.device_id, link.endpoint_b.interface_name, link.up, 0, 0, 0, 0,
            )
            if candidate.key == self.selected_link_key:
                return link
        return None

    def set_selected_link_state(self, up: bool) -> None:
        link = self._find_selected_link()
        if link is None:
            messagebox.showinfo("Link state", "Click a cable in the topology first.", parent=self.root)
            return
        endpoint = link.endpoint_a
        try:
            self.workspace.set_link_state(endpoint.device_id, endpoint.interface_name, up)
            self._refresh_all()
            state = "up" if up else "down"
            self._append_terminal(f"Link on {self._hostname_for(endpoint.device_id)}:{endpoint.interface_name} set {state}.")
            self._set_status(f"Selected link set {state}.")
        except (NetsimError, LabError, ValueError) as exc:
            messagebox.showerror("Could not change link state", str(exc), parent=self.root)

    def disconnect_selected_link(self) -> None:
        link = self._find_selected_link()
        if link is None:
            messagebox.showinfo("Disconnect link", "Click a cable in the topology first.", parent=self.root)
            return
        endpoint = link.endpoint_a
        try:
            self.workspace.disconnect(endpoint.device_id, endpoint.interface_name)
            self.selected_link_key = None
            self._refresh_all()
            self._append_terminal(f"Disconnected link from {self._hostname_for(endpoint.device_id)}:{endpoint.interface_name}.")
            self._set_status("Link disconnected.")
        except (NetsimError, LabError, ValueError) as exc:
            messagebox.showerror("Could not disconnect link", str(exc), parent=self.root)

    def new_lab(self) -> None:
        if not messagebox.askyesno("New lab", "Start a blank lab? Unsaved changes in the current workspace will be discarded.", parent=self.root):
            return
        self._replace_runtime(build_runtime(topology=Topology(), name="Untitled Lab"))
        self.selected_link_key = None
        self._clear_verification()
        self._refresh_all()
        self._append_terminal("Started a blank lab.", "Add devices or load a scenario to begin.")
        self._set_status("New blank lab ready.")

    def save_lab(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save netsim lab",
            defaultextension=".json",
            filetypes=(("netsim lab (JSON)", "*.json"), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            saved = self.workspace.save(path)
            self._refresh_all()
            self._append_terminal(f"Saved lab to {saved}.")
            self._set_status(f"Saved lab: {saved}")
        except (NetsimError, LabError, OSError, ValueError) as exc:
            messagebox.showerror("Could not save lab", str(exc), parent=self.root)

    def open_lab(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Open netsim lab",
            filetypes=(("netsim lab (JSON)", "*.json"), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            loaded = self.workspace.load(path)
            self.session.device = self.workspace.active_device
            self.session.mode_stack.reset()
            self.selected_link_key = None
            self._clear_verification()
            self._refresh_all()
            self._append_terminal(f"Loaded lab from {loaded}.")
            self._set_status(f"Loaded lab: {loaded}")
        except (NetsimError, LabError, OSError, ValueError) as exc:
            messagebox.showerror("Could not open lab", str(exc), parent=self.root)

    def reset_lab(self) -> None:
        if not messagebox.askyesno("Reset lab", "Discard changes since the last saved/loaded checkpoint?", parent=self.root):
            return
        try:
            self.workspace.reset()
            self.session.device = self.workspace.active_device
            self.session.mode_stack.reset()
            self.selected_link_key = None
            self._clear_verification()
            self._refresh_all()
            self._append_terminal("Lab reset to its last saved/loaded checkpoint.")
            self._set_status("Lab reset.")
        except (NetsimError, LabError, ValueError) as exc:
            messagebox.showerror("Could not reset lab", str(exc), parent=self.root)

    def load_scenario(self) -> None:
        selected = self.scenario_var.get()
        scenario_id = self.scenario_ids.get(selected)
        if not scenario_id:
            return
        try:
            task = self.workspace.load_scenario(scenario_id)
            self.session.device = self.workspace.active_device
            self.session.mode_stack.reset()
            self.selected_link_key = None
            self._clear_verification()
            self._refresh_all()
            self._append_terminal(f"Loaded scenario: {self.workspace.name}.", f"Task: {task}", "Use 'lab verify' when you have finished configuring the lab.")
            self._set_status(f"Scenario loaded: {self.workspace.name}")
        except (NetsimError, LabError, ValueError) as exc:
            messagebox.showerror("Could not load scenario", str(exc), parent=self.root)

    def verify_lab(self) -> None:
        try:
            report = self.workspace.verify()
            lines = [f"{'PASS' if report.passed else 'FAIL'}: {report.passed_count}/{len(report.checks)} checks passed."]
            lines.extend(f"{'PASS' if check.passed else 'FAIL'} {check.name}: {check.detail}" for check in report.checks)
            self._set_text(self.verify_output, lines)
            self._append_terminal(lines[0])
            self._set_status("Lab verification passed." if report.passed else f"Lab verification found {report.failed_count} issue(s).", error=not report.passed)
        except (NetsimError, LabError, ValueError) as exc:
            messagebox.showerror("Verification failed", str(exc), parent=self.root)

    def _submit_command(self, _event: object | None = None) -> str:
        self.execute_command()
        return "break"

    def execute_command(self) -> None:
        line = self.command_var.get()
        self.command_var.set("")
        if not line.strip():
            self.command_entry.focus_set()
            return
        prompt = self.session.prompt()
        self._append_terminal(f"{prompt} {line}", tag="command")
        outcome = self.session.execute_line(line)
        for output_line in outcome.output:
            self._append_terminal(output_line)
        if outcome.error is not None:
            self._append_terminal(outcome.error, tag="error")
        if outcome.exited:

            self.session.mode_stack.reset()
            self._append_terminal("CLI session ended. The lab remains open; enter a command to continue.")
        self.session.device = self.workspace.active_device
        self._history_cursor = len(self.session.history.all())
        self._refresh_all()
        self.command_entry.focus_set()

    def _history_older(self, _event: object | None = None) -> str:
        history = self.session.history.all()
        if not history:
            return "break"
        self._history_cursor = max(0, min(self._history_cursor - 1, len(history) - 1))
        self.command_var.set(history[self._history_cursor])
        self.command_entry.icursor(tk.END)
        return "break"

    def _history_newer(self, _event: object | None = None) -> str:
        history = self.session.history.all()
        if not history:
            return "break"
        self._history_cursor = min(len(history), self._history_cursor + 1)
        self.command_var.set(history[self._history_cursor] if self._history_cursor < len(history) else "")
        self.command_entry.icursor(tk.END)
        return "break"

    def _append_terminal(self, *lines: str, tag: str | None = None) -> None:
        self.terminal_output.configure(state="normal")
        for line in lines:
            if tag:
                self.terminal_output.insert(tk.END, line + "\n", tag)
            else:
                inferred_tag = "error" if line.startswith(("%", "Error", "FAIL")) else None
                if inferred_tag:
                    self.terminal_output.insert(tk.END, line + "\n", inferred_tag)
                else:
                    self.terminal_output.insert(tk.END, line + "\n")
        self.terminal_output.see(tk.END)
        self.terminal_output.configure(state="disabled")
        self.prompt_label.configure(text=self.session.prompt())

    def _set_text(self, widget: tk.Text, lines: list[str]) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, "\n".join(lines) + ("\n" if lines else ""))
        widget.configure(state="disabled")

    def _clear_verification(self) -> None:
        self._set_text(self.verify_output, ["No verification report yet.", "Use 'Verify lab' after building/configuring the topology."])

    def open_appearance(self) -> None:
        options = (
            ("Background", "background"),
            ("Terminal text", "text"),
            ("Prompt", "prompt"),
            ("Error text", "error"),
        )
        for label, key in options:
            selected = colorchooser.askcolor(
                color=self._custom_theme[key], title=f"Choose {label.lower()} color", parent=self.root
            )[1]
            if selected:
                self._custom_theme[key] = selected
        self.settings.theme.name = "custom"
        self.settings.theme.background_color = self._custom_theme["background"]
        self.settings.theme.text_color = self._custom_theme["text"]
        self.settings.theme.prompt_color = self._custom_theme["prompt"]
        self.settings.theme.error_color = self._custom_theme["error"]
        try:
            path = save_settings(self.settings)
            self._apply_theme()
            self._append_terminal(f"Appearance preferences saved to {path}.")
            self._set_status("Appearance updated and saved.")
        except (NetsimError, OSError, ValueError) as exc:
            messagebox.showerror("Could not save appearance", str(exc), parent=self.root)

    def _replace_runtime(self, runtime: NetsimRuntime) -> None:
        self.runtime = runtime
        self.workspace = runtime.workspace
        self.session = runtime.session
        self._history_cursor = 0

    def _set_status(self, text: str, *, error: bool = False) -> None:
        self.status_var.set(text)
        self.status_bar.configure(fg=self._custom_theme["error"] if error else _PALETTE["muted"])

    def _on_close(self) -> None:

        self.root.destroy()


class ConnectDialog:
    """Small non-modal dialog for connecting two device interfaces."""

    def __init__(
        self,
        root: tk.Tk,
        devices: list[Device],
        on_connect: Callable[[Device, str, Device, str], bool],
    ) -> None:
        self.window = tk.Toplevel(root)
        self.window.title("Connect interfaces")
        self.window.transient(root)
        self.window.resizable(False, False)
        self.window.grab_set()
        self.devices = devices
        self.on_connect = on_connect
        self._device_by_label = {
            f"{device.hostname} · {device.device_id[:8]}": device for device in devices
        }
        self._labels = list(self._device_by_label)
        self._interface_vars: list[tk.StringVar] = [tk.StringVar(), tk.StringVar()]
        self._device_vars: list[tk.StringVar] = [tk.StringVar(value=self._labels[0]), tk.StringVar(value=self._labels[1])]
        frame = ttk.Frame(self.window, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        ttk.Label(frame, text="First endpoint").grid(row=0, column=0, sticky="w", pady=(0, 5))
        ttk.Label(frame, text="Second endpoint").grid(row=0, column=1, sticky="w", pady=(0, 5))
        self._device_combos: list[ttk.Combobox] = []
        self._interface_combos: list[ttk.Combobox] = []
        for side in range(2):
            device_combo = ttk.Combobox(frame, textvariable=self._device_vars[side], values=self._labels, state="readonly", width=28)
            device_combo.grid(row=1, column=side, padx=(0 if side == 0 else 12, 0), sticky="ew")
            device_combo.bind("<<ComboboxSelected>>", lambda _event, which=side: self._refresh_interfaces(which))
            self._device_combos.append(device_combo)
            interface_combo = ttk.Combobox(frame, textvariable=self._interface_vars[side], state="readonly", width=28)
            interface_combo.grid(row=2, column=side, padx=(0 if side == 0 else 12, 0), pady=(6, 0), sticky="ew")
            self._interface_combos.append(interface_combo)
            self._refresh_interfaces(side)
        ttk.Label(frame, text="Choose the two endpoints to create a link.").grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 10))
        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="Cancel", command=self.window.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Connect", command=self._submit).pack(side="right")

    def _refresh_interfaces(self, side: int) -> None:
        device = self._device_by_label.get(self._device_vars[side].get())
        names = list(device.interfaces) if device is not None else []
        self._interface_combos[side]["values"] = names
        if names:
            if self._interface_vars[side].get() not in names:
                self._interface_vars[side].set(names[0])
        else:
            self._interface_vars[side].set("")

    def _submit(self) -> None:
        device_a = self._device_by_label.get(self._device_vars[0].get())
        device_b = self._device_by_label.get(self._device_vars[1].get())
        interface_a = self._interface_vars[0].get()
        interface_b = self._interface_vars[1].get()
        if device_a is None or device_b is None or not interface_a or not interface_b:
            messagebox.showerror("Invalid endpoints", "Select both devices and interfaces.", parent=self.window)
            return
        if self.on_connect(device_a, interface_a, device_b, interface_b):
            self.window.destroy()


def _tkinter_install_guidance() -> tuple[str, ...]:
    """Return actionable Tkinter installation guidance for the current platform."""
    if sys.platform.startswith("linux"):
        try:
            distribution = platform.freedesktop_os_release().get("ID", "").lower()
        except (AttributeError, OSError):
            distribution = ""
        if distribution in {"ubuntu", "debian", "linuxmint", "pop", "elementary"}:
            return (
                "On Ubuntu/Debian-based Linux, install Tkinter for the system Python with:",
                "  sudo apt update && sudo apt install python3-tk",
            )
        if distribution == "fedora":
            return (
                "On Fedora, install Tkinter for the system Python with:",
                "  sudo dnf install python3-tkinter",
            )
        if distribution in {"arch", "manjaro", "endeavouros"}:
            return (
                "On Arch-based Linux, install the Tk package with:",
                "  sudo pacman -S tk",
            )
        return (
            "Install the Tkinter package matching the Python interpreter used by NetSim.",
            "Common package names include python3-tk (Ubuntu/Debian) and python3-tkinter (Fedora).",
        )
    if sys.platform == "win32":
        return (
            "On Windows, rerun the Python installer, choose Modify, and enable Tcl/Tk and IDLE.",
            "Then open a new terminal and recreate the virtual environment if Tkinter is still unavailable.",
        )
    if sys.platform == "darwin":
        return (
            "On macOS, use a Python distribution that includes Tk support, such as the official python.org installer.",
            "Check the interpreter with: python -m tkinter",
        )
    return ("Install Tkinter support for the Python interpreter used by NetSim.",)


def main() -> int:
    """Launch the optional Tkinter GUI, with actionable errors on missing Tk/headless systems."""
    if tk is None:
        print("netsim-gui: this Python installation does not include Tkinter.")
        for instruction in _tkinter_install_guidance():
            print(instruction)
        print("Verify Tkinter with: python -m tkinter")
        print("Terminal alternative: netsim (or python -m netsim)")
        return 2
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"netsim-gui: could not open a graphical display: {exc}")
        print("Run the GUI from a desktop session with a graphical display available.")
        print("For SSH, containers, or headless servers, use 'netsim' or 'python -m netsim'.")
        return 2
    NetworkSimulatorApp(root)
    root.mainloop()
    return 0
