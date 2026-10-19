# Changelog

Notable user-facing changes are recorded here. This file tracks release baselines rather than every internal development step.

## 0.1.2 — Installation guidance and GUI startup diagnostics

- Added a cross-platform installation guide for source archives, virtual environments, terminal usage, and GUI requirements.
- Added troubleshooting guidance for missing Tkinter, missing graphical displays, venv setup, missing commands/dependencies, and lab-verification failures.
- Improved the GUI launcher's missing-Tkinter output with platform-specific package/setup instructions and an explicit `python -m tkinter` verification step.
- Improved headless-display guidance while keeping the terminal CLI available as a fallback.
- Updated project documentation links and the reported package version.
- Added a visual tour with GUI captures and CLI session examples for the README and documentation.
- Updated `show version` to report the current NetSim product identity instead of an obsolete development-stage label.

## 0.1.1 — Core simulation baseline

- Added an IOS-inspired command-line engine with configuration modes, help, history, abbreviations, and completion.
- Added router, switch, and host models with persistent configuration.
- Implemented in-memory Ethernet forwarding, MAC learning, VLAN-aware switching, ARP, ICMP echo simulation, connected/static routing, and deterministic RIP convergence.
- Added numbered standard IPv4 ACLs with interface direction bindings and ping-path enforcement.
- Added portable lab management, built-in scenarios, workspace verification, and a shared Tkinter GUI.
- Hardened configuration and lab-file input handling and added security regression tests.

## Repository presentation update

- Removed Python comment tokens from source and tests while preserving string literals, CLI prompt characters, executable behavior, and docstrings.
- Reworked project branding, README, usage guides, architecture notes, contributing guidance, and security reporting instructions.
- Added a cross-platform continuous-integration workflow and project issue templates.
