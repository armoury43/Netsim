# Troubleshooting

This page collects common setup and first-run issues. When reporting a problem, include your OS, Python version, the exact command, and the complete error text. Remove personal paths, tokens, and sensitive data from logs before sharing them.

## `netsim-gui` says Tkinter is missing

This means the Python interpreter that launched NetSim cannot import Tkinter. Tkinter is not installed through pip.

On Ubuntu/Debian-based distributions:

```bash
sudo apt update
sudo apt install python3-tk
```

Then verify using the same activated environment that launches NetSim:

```bash
python -c "import sys; print(sys.executable)"
python -m tkinter
```

If `python -m tkinter` opens a test window, close it and retry `netsim-gui`. If the import still fails, the system package may not match the Python interpreter you are using. See [Installation and First Run](../INSTALLATION.md#4-optional-gui-dependency-tkinter) for Fedora, Arch, Windows, and macOS notes.

## `netsim-gui` says it cannot open a graphical display

Tkinter is present, but the process cannot connect to a graphical desktop. Start NetSim from a local desktop terminal. If you are using SSH, a container, or a headless server, use the CLI instead or configure an appropriate remote/virtual display. The terminal command remains available:

```bash
netsim
```

## `netsim: command not found`

Activate the virtual environment from the repository root:

```bash
source .venv/bin/activate
command -v netsim
```

On Windows PowerShell, use:

```powershell
.\.venv\Scripts\Activate.ps1
Get-Command netsim
```

If the command is still missing, reinstall the checkout into that environment:

```bash
python -m pip install -e ".[dev]"
```

## `No module named venv` or `ensurepip` error

On Ubuntu/Debian, install the venv support package before creating the environment:

```bash
sudo apt update
sudo apt install python3-venv
python3 -m venv .venv
```

On other systems, install or enable venv support for the Python distribution in use.

## `No module named yaml` or another dependency is missing

Make sure the environment is activated, then reinstall the declared dependencies:

```bash
python -m pip install -e ".[dev]"
python -c "import yaml; print(yaml.__version__)"
```

Use `python -m pip` rather than a standalone `pip` command so that pip targets the selected interpreter.

## The GUI opens, but a lab does not pass verification

A newly loaded scenario may be a training task with deliberate configuration steps still unfinished. A `FAIL` from `lab verify` does not automatically mean the application is broken: inspect each check and complete the task described by the scenario before running verification again. For the `basic-lan` walkthrough, see [Lab Management](lab-management.md#configure-a-basic-switched-lan).

## GUI tests are skipped by pytest

The test suite skips tests that require a display when no GUI display can be created. On Linux, install Xvfb and run the GUI-enabled suite:

```bash
xvfb-run -a python -m pytest -q -W error::ResourceWarning
```

A normal test run with GUI skips can still validate CLI, device, network, and workspace behavior; it does not replace testing the visible GUI on a desktop machine.

## Saved lab or settings file fails to load

Save a copy of the file before editing it. NetSim validates saved JSON/YAML configuration and can reject malformed or oversized input rather than partially applying it. Do not share files that contain personal information or private network data. If a valid file fails to load, include the sanitized error message and a minimal reproduction in a bug report.
