# Graphical Workspace

NetSim's optional Tkinter application provides a visual view of the existing simulator backend. It is a second interface to the same workspace and command engine, not a separate network implementation.

## Launch

From an installed environment:

```bash
netsim-gui
```

From a source checkout:

```bash
python -m netsim.gui
```

Tkinter must be available in the Python installation, and a graphical display is required. Some Linux distributions package Tkinter separately. On a headless system, the launcher exits with a clear message; the terminal application remains available through `netsim` or `python -m netsim`.

## Features

- Device inventory and topology canvas for routers, switches, hosts, and links.
- Add or remove devices, select the active device, and connect interfaces through a guided dialog.
- Change a selected link's state or disconnect it. Link state is separate from interface administrative state.
- Execute commands in an embedded terminal that uses the same CLI session, parser, validation, handlers, and command history as the terminal application.
- Load built-in scenarios, run lab verification, create a blank workspace, and save/load/reset JSON labs.
- Customize terminal, background, prompt, and error colors; appearance preferences are stored in the normal settings file.

## Current limits

The topology canvas uses a deterministic automatic layout. Drag-and-drop node placement, animated packet traversal, physical port LEDs, and protocol-timer animation are not implemented. The GUI is designed to make the simulator easier to inspect and use, rather than to replace a full network-design suite.

## GUI tests

Most GUI-related tests exercise the topology projection and application wiring without creating a visible window. Tests that require a display skip when none is available. On Linux with Xvfb installed, run:

```bash
xvfb-run -a python -m pytest -q -W error::ResourceWarning
```
