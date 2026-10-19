"""End-to-end CLI integration tests for Stage 8 lab commands."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from netsim.cli.device_commands import build_device_registry
from netsim.cli.lab_commands import register_lab_commands
from netsim.cli.network_commands import register_network_commands
from netsim.cli.session import CliSession
from netsim.labs.workspace import LabWorkspace


def _session(workspace: LabWorkspace) -> CliSession:
    registry = build_device_registry()
    register_network_commands(registry)
    register_lab_commands(registry)
    return CliSession(
        registry=registry,
        device=workspace.active_device,
        network=workspace,
        workspace=workspace,
    )


class TestLabCliCommands(unittest.TestCase):
    def test_scenario_device_switching_configuration_and_verification(self) -> None:
        workspace = LabWorkspace()
        session = _session(workspace)
        outcome = session.execute_line("lab scenario basic-lan")
        self.assertIsNone(outcome.error)
        self.assertEqual(session.prompt(), "PC1>")

        for command in (
            "enable", "configure terminal", "interface Ethernet0",
            "ip address 192.168.10.11 255.255.255.0", "no shutdown", "end",
            "device select PC2", "configure terminal", "interface Ethernet0",
            "ip address 192.168.10.12 255.255.255.0", "no shutdown", "end",
            "device select SW1", "configure terminal", "interface FastEthernet0/1",
            "no shutdown", "exit", "interface FastEthernet0/2", "no shutdown", "end",
        ):
            outcome = session.execute_line(command)
            self.assertIsNone(outcome.error, f"{command!r}: {outcome.error}")

        outcome = session.execute_line("lab verify")
        self.assertIsNone(outcome.error)
        self.assertIn("PASS:", "\n".join(outcome.output))
        self.assertIn("10/10 checks passed", "\n".join(outcome.output))

    def test_create_connect_link_down_up_and_remove_commands(self) -> None:
        workspace = LabWorkspace()
        session = _session(workspace)
        for command in (
            "device add host PC1",
            "device add host PC2",
            "connect PC1 Ethernet0 PC2 Ethernet0",
            "link down PC1 Ethernet0",
        ):
            outcome = session.execute_line(command)
            self.assertIsNone(outcome.error, f"{command!r}: {outcome.error}")
        self.assertFalse(workspace.topology.links()[0].up)
        self.assertIsNone(session.execute_line("link up PC1 Ethernet0").error)
        self.assertTrue(workspace.topology.links()[0].up)
        self.assertIsNone(session.execute_line("device remove PC2").error)
        self.assertEqual(workspace.topology.links(), [])

    def test_save_load_and_reset_through_cli(self) -> None:
        workspace = LabWorkspace()
        workspace.load_scenario("basic-lan")
        session = _session(workspace)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "saved-lab.json"
            self.assertIsNone(session.execute_line(f"lab save {path}").error)
            workspace.create_device("host", "TEMP")
            self.assertIsNone(session.execute_line("lab reset").error)
            self.assertNotIn("TEMP", [device.hostname for device in workspace.devices])
            self.assertIsNone(session.execute_line(f"lab load {path}").error)
            self.assertEqual(session.prompt(), "PC1>")
            self.assertEqual(len(workspace.topology.links()), 2)

    def test_list_commands_do_not_require_privileged_mode(self) -> None:
        workspace = LabWorkspace()
        workspace.load_scenario("basic-lan")
        session = _session(workspace)
        self.assertIsNone(session.execute_line("show devices").error)
        self.assertIsNone(session.execute_line("show topology").error)
        self.assertIsNone(session.execute_line("lab list-scenarios").error)

if __name__ == "__main__":
    unittest.main()
