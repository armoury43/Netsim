# Installation and First Run

This guide covers the source ZIP, a local development installation, the terminal CLI, and the optional graphical workspace. Start here if you are new to Python environments or if `netsim-gui` reports that Tkinter is missing.

## 1. Requirements

- Python **3.10 or newer**.
- Internet access for the initial `pip` installation, unless the required packages are already available locally.
- PyYAML, installed automatically when NetSim is installed with pip.
- **GUI only:** Tkinter support in the same Python installation used to run NetSim, plus a working desktop display. Tkinter is a Python standard-library interface, but some operating-system packages distribute its underlying Tcl/Tk components separately. Installing the NetSim package with pip does not install system Tkinter.

The terminal CLI does not require Tkinter.

## 2. Extract the source archive

Extract the downloaded ZIP, then open a terminal **inside the directory that contains `pyproject.toml`**. The repository root should contain at least:

```text
README.md
INSTALLATION.md
pyproject.toml
src/
tests/
```

For example, if the archive was extracted to `~/Downloads/netsim`, run:

```bash
cd ~/Downloads/netsim-0.1.2
ls pyproject.toml README.md src tests
```

If `pyproject.toml` is not found, you are probably in the parent directory. Use your file manager to enter the inner project directory, then retry.

## 3. Install in a virtual environment

A virtual environment keeps NetSim's Python packages separate from the packages managed by your operating system.

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

If `python3 -m venv .venv` reports that `venv` or `ensurepip` is missing on Ubuntu/Debian, install the venv support package and retry:

```bash
sudo apt update
sudo apt install python3-venv
python3 -m venv .venv
```

### Windows PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

If PowerShell blocks activation due to the current execution policy, open a terminal where activation is permitted or use Command Prompt instead:

```bat
.venv\Scripts\activate.bat
python -m pip install -e ".[dev]"
```

The `.[dev]` extra includes the project plus pytest, pytest-cov, and mypy. If you only want to run NetSim and do not need its development/test tools, use `python -m pip install -e .` instead.

## 4. Optional GUI dependency: Tkinter

The CLI and GUI are separate entry points. **Do not try to install Tkinter with `pip install tkinter`; that is not the supported installation method.** Install Tk/Tkinter support for the Python interpreter your virtual environment uses.

### Ubuntu / Debian / Linux Mint / Pop!_OS

```bash
sudo apt update
sudo apt install python3-tk
```

Then, with the NetSim virtual environment activated, verify the interpreter can open Tk's test window:

```bash
python -m tkinter
```

If a small Tk test window appears, close it and continue. If the import still fails, compare the Python versions:

```bash
python --version
python -c "import sys; print(sys.executable)"
python -c "import tkinter; print(tkinter.TkVersion)"
```

Install the operating-system package matching that Python installation. For Ubuntu/Debian, the `python3-tk` package is normally intended for the distribution's system Python. If NetSim is running under a separately installed Python, use a Python distribution that includes compatible Tcl/Tk support or consult that interpreter's installation instructions.

### Fedora

```bash
sudo dnf install python3-tkinter
```

### Arch Linux / Manjaro

```bash
sudo pacman -S tk
```

Package names can vary by distribution and Python build. The important point is that Tkinter must be available to the **same interpreter** that runs `netsim-gui`.

### Windows

Tkinter is generally included with the official Windows Python installer. If it is unavailable, rerun that installer, choose **Modify**, and make sure **Tcl/Tk and IDLE** is selected. Open a new terminal, reactivate `.venv`, and verify with:

```powershell
python -m tkinter
```

### macOS

Use a Python distribution with Tcl/Tk support (the official installer from python.org is a common option). Verify the selected interpreter with:

```bash
python -m tkinter
```

## 5. Launch NetSim

Keep the virtual environment activated when using the commands below.

### Terminal CLI

```bash
netsim
```

Equivalent source/module entry point:

```bash
python -m netsim
```

The terminal CLI works without Tkinter. It is also the recommended fallback on SSH sessions, containers, and headless servers.

### Graphical workspace

```bash
netsim-gui
```

Equivalent module entry point:

```bash
python -m netsim.gui
```

A desktop display is required. If the GUI command reports missing Tkinter, follow [the Tkinter instructions above](#4-optional-gui-dependency-tkinter). If it reports that it cannot open a graphical display, run it from your desktop session. On a headless machine, use the CLI or configure a suitable remote/virtual display.

## 6. Verify the installation

From the activated virtual environment, run:

```bash
python -c "import netsim, yaml; print('NetSim', netsim.__version__); print('PyYAML', yaml.__version__)"
python -m pytest -q -W error::ResourceWarning
```

Some GUI tests skip when Tkinter or a graphical display is unavailable. To run display-dependent GUI workflow tests on Linux, install Xvfb and run:

```bash
xvfb-run -a python -m pytest -q -W error::ResourceWarning
```

A successful test suite is useful evidence, but is not a guarantee that every feature is defect-free. See [Troubleshooting](docs/troubleshooting.md) for common problems and [Lab Management](docs/lab-management.md) for a complete first scenario.

## 7. Remove the local development installation

From the repository root, with the environment activated:

```bash
python -m pip uninstall netsim
```

Then leave the environment and remove its directory when you no longer need it:

```bash
deactivate
rm -rf .venv
```

The final command deletes the local virtual environment directory only. It does not delete your source checkout or per-user NetSim settings/lab files.
