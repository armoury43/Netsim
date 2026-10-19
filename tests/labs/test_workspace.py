"""Stage 8 workspace, persistence, scenario, and verification tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from netsim.core.exceptions import ValidationError
from netsim.devices.host import Host
from netsim.devices.router import Router
from netsim.devices.state import DeviceState
from netsim.devices.switch import Switch
from netsim.labs.errors import LabFormatError, LabOperationError, LabStorageError
from netsim.labs.workspace import LabWorkspace
from netsim.network.errors import DeviceNotInTopologyError, InterfaceAlreadyConnectedError


class TestWorkspaceDeviceManagement(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = LabWorkspace()

    def test_create_select_remove_devices(self) -> None:
        router = self.workspace.create_device("router", "R1")
        switch = self.workspace.create_device("switch", "SW1")
        host = self.workspace.create_device("host", "PC1")
        self.assertIsInstance(router, Router)
        self.assertIsInstance(switch, Switch)
        self.assertIsInstance(host, Host)
        self.assertEqual(router.state, DeviceState.READY)
        self.assertEqual(self.workspace.active_device, router)
        self.assertEqual(self.workspace.select_device("pc1"), host)
        self.assertEqual(self.workspace.active_device, host)

        removed = self.workspace.remove_device("PC1")
        self.assertEqual(removed.hostname, "PC1")
        self.assertEqual(self.workspace.active_device, router)
        with self.assertRaises(DeviceNotInTopologyError):
            self.workspace.topology.get_device(host.device_id)

    def test_rejects_duplicate_or_invalid_hostnames_and_device_types(self) -> None:
        self.workspace.create_device("host", "PC1")
        with self.assertRaises(LabOperationError):
            self.workspace.create_device("router", "pc1")
        with self.assertRaises(ValidationError):
            self.workspace.create_device("firewall", "FW1")
        with self.assertRaises(ValidationError):
            self.workspace.create_device("host", "not a hostname")

    def test_host_can_only_have_one_interface(self) -> None:
        with self.assertRaises(ValidationError):
            self.workspace.create_device("host", "PC1", ["Ethernet0", "Ethernet1"])

    def test_connect_disconnect_and_link_state(self) -> None:
        pc1 = self.workspace.create_device("host", "PC1")
        pc2 = self.workspace.create_device("host", "PC2")
        link = self.workspace.connect("PC1", "Ethernet0", "PC2", "Ethernet0")
        self.assertTrue(link.up)
        self.workspace.set_link_state("PC1", "Ethernet0", False)
        self.assertFalse(link.up)
        self.assertTrue(self.workspace.disconnect("PC2", "Ethernet0"))
        self.assertIsNone(self.workspace.topology.get_link(pc1.device_id, "Ethernet0"))
        self.assertFalse(self.workspace.disconnect("PC2", "Ethernet0"))

    def test_connect_rejects_already_connected_interfaces(self) -> None:
        self.workspace.create_device("host", "PC1")
        self.workspace.create_device("host", "PC2")
        self.workspace.create_device("host", "PC3")
        self.workspace.connect("PC1", "Ethernet0", "PC2", "Ethernet0")
        with self.assertRaises(InterfaceAlreadyConnectedError):
            self.workspace.connect("PC1", "Ethernet0", "PC3", "Ethernet0")

    def test_removing_device_also_removes_its_links(self) -> None:
        self.workspace.create_device("host", "PC1")
        self.workspace.create_device("switch", "SW1")
        self.workspace.connect("PC1", "Ethernet0", "SW1", "FastEthernet0/1")
        self.workspace.remove_device("PC1")
        self.assertEqual(self.workspace.topology.links(), [])


class TestWorkspacePersistence(unittest.TestCase):
    def _configured_workspace(self) -> LabWorkspace:
        workspace = LabWorkspace(name="Full Config Lab")
        router = workspace.create_device("router", "R1", ["GigabitEthernet0/0", "GigabitEthernet0/1"])
        switch = workspace.create_device("switch", "SW1")
        host = workspace.create_device("host", "PC1")
        workspace.connect("R1", "GigabitEthernet0/0", "SW1", "FastEthernet0/1")
        workspace.connect("SW1", "FastEthernet0/2", "PC1", "Ethernet0")

        router.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")
        router.configure_ipv4("GigabitEthernet0/1", "10.0.1.1", "255.255.255.0")
        router.get_interface("GigabitEthernet0/0").set_admin_up(True)
        router.get_interface("GigabitEthernet0/1").set_admin_up(False)
        router.get_interface("GigabitEthernet0/1").set_description("unused link")
        router.add_static_route("192.168.5.0", "255.255.255.0", "10.0.0.254")
        router.enable_rip("10.0.0.0", "255.255.255.0")
        router.add_access_list_rule(10, "deny", "10.10.0.0", "255.255.0.0")
        router.add_access_list_rule(10, "permit", "any")
        router.set_interface_acl("GigabitEthernet0/0", "in", 10)
        router.get_interface("GigabitEthernet0/0").set_mac_address("02:00:00:00:00:11")

        switch.get_or_create_vlan(10, "USERS")
        switch.get_interface("FastEthernet0/1").set_switchport_access_vlan(10)
        switch.get_interface("FastEthernet0/2").set_switchport_trunk({10, 20})
        switch.get_interface("FastEthernet0/1").set_admin_up(True)
        switch.learn_mac("02:00:00:00:00:AB", "FastEthernet0/1")

        host.configure_ipv4("Ethernet0", "10.0.0.10", "255.255.255.0")
        host.set_default_gateway("10.0.0.1")
        host.get_interface("Ethernet0").set_admin_up(True)
        workspace.select_device("R1")
        workspace.engine.arp_cache_for(router.device_id).learn("10.0.0.20", "02:00:00:00:00:20")
        return workspace

    def test_round_trip_preserves_device_interface_router_and_vlan_config(self) -> None:
        workspace = self._configured_workspace()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "full-lab.json"
            workspace.save(path)

            restored = LabWorkspace()
            restored.load(path)
            router = restored.resolve_device("R1")
            switch = restored.resolve_device("SW1")
            host = restored.resolve_device("PC1")
            self.assertIsInstance(router, Router)
            self.assertIsInstance(switch, Switch)
            self.assertIsInstance(host, Host)

            self.assertEqual(router.get_interface("GigabitEthernet0/0").ipv4_address, "10.0.0.1")
            self.assertTrue(router.get_interface("GigabitEthernet0/0").admin_up)
            self.assertFalse(router.get_interface("GigabitEthernet0/1").admin_up)
            self.assertEqual(router.get_interface("GigabitEthernet0/1").description, "unused link")
            self.assertEqual(router.get_interface("GigabitEthernet0/0").mac_address, "02:00:00:00:00:11")
            self.assertIn("192.168.5.0/24", router.static_routes)
            self.assertEqual(len(router.rip_networks), 1)
            self.assertEqual(router.access_lists[10].rules()[0].action, "deny")
            self.assertEqual(router.interface_acl_in["GigabitEthernet0/0"], 10)
            self.assertEqual(switch.vlans[10].name, "USERS")
            self.assertEqual(switch.get_interface("FastEthernet0/1").switchport.access_vlan, 10)
            self.assertEqual(switch.get_interface("FastEthernet0/2").switchport.trunk_allowed_vlans, {10, 20})
            self.assertEqual(host.default_gateway, "10.0.0.1")
            self.assertEqual(len(restored.topology.links()), 2)
            self.assertEqual(restored.active_device.hostname, "R1")

            self.assertEqual(dict(restored.engine.arp_table(router.device_id)), {})
            self.assertEqual(dict(workspace.resolve_device("SW1").mac_table), {"02:00:00:00:00:AB": "FastEthernet0/1"})
            self.assertEqual(dict(switch.mac_table), {})

    def test_save_is_checkpoint_for_reset(self) -> None:
        workspace = self._configured_workspace()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "checkpoint.json"
            workspace.save(path)
            workspace.create_device("host", "TEMP")
            workspace.disconnect("SW1", "FastEthernet0/1")
            workspace.reset()
            self.assertNotIn("TEMP", [device.hostname for device in workspace.devices])
            self.assertEqual(len(workspace.topology.links()), 2)
            self.assertEqual(workspace.active_device.hostname, "R1")

    def test_link_operational_state_persists_across_save_and_load(self) -> None:
        workspace = LabWorkspace()
        workspace.create_device("host", "PC1")
        workspace.create_device("host", "PC2")
        workspace.connect("PC1", "Ethernet0", "PC2", "Ethernet0")
        workspace.set_link_state("PC1", "Ethernet0", False)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "link-state.json"
            workspace.save(path)
            restored = LabWorkspace()
            restored.load(path)
            self.assertFalse(restored.topology.links()[0].up)

    def test_topology_changes_invalidate_arp_and_switch_mac_runtime_state(self) -> None:
        workspace = LabWorkspace()
        pc1 = workspace.create_device("host", "PC1")
        pc2 = workspace.create_device("host", "PC2")
        switch = workspace.create_device("switch", "SW1")
        workspace.connect("PC1", "Ethernet0", "SW1", "FastEthernet0/1")
        workspace.connect("PC2", "Ethernet0", "SW1", "FastEthernet0/2")
        pc1.configure_ipv4("Ethernet0", "192.0.2.1", "24")
        pc2.configure_ipv4("Ethernet0", "192.0.2.2", "24")
        for device, interface_name in (
            (pc1, "Ethernet0"), (pc2, "Ethernet0"),
            (switch, "FastEthernet0/1"), (switch, "FastEthernet0/2"),
        ):
            device.get_interface(interface_name).set_admin_up(True)
        self.assertTrue(workspace.ping(pc1.device_id, "192.0.2.2").success)
        self.assertTrue(workspace.engine.arp_table(pc1.device_id))
        self.assertTrue(switch.mac_table)
        workspace.set_link_state("PC1", "Ethernet0", False)
        self.assertEqual(dict(workspace.engine.arp_table(pc1.device_id)), {})
        self.assertEqual(dict(switch.mac_table), {})

    def test_bad_json_load_is_transactional(self) -> None:
        workspace = self._configured_workspace()
        before_devices = tuple((device.hostname, device.device_id) for device in workspace.devices)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bad.json"
            path.write_text("{ not json", encoding="utf-8")
            with self.assertRaises(LabFormatError):
                workspace.load(path)
        after_devices = tuple((device.hostname, device.device_id) for device in workspace.devices)
        self.assertEqual(after_devices, before_devices)

    def test_invalid_link_reference_is_rejected_without_replacing_live_topology(self) -> None:
        workspace = self._configured_workspace()
        before_ids = {device.device_id for device in workspace.devices}
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "broken.json"
            doc = workspace._export_document()
            doc["links"][0]["endpoint_a"]["device_id"] = "missing-device"
            path.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(LabFormatError):
                workspace.load(path)
        self.assertEqual({device.device_id for device in workspace.devices}, before_ids)

    def test_duplicate_ip_configuration_can_be_saved_and_verified_after_load(self) -> None:
        workspace = LabWorkspace()
        pc1 = workspace.create_device("host", "PC1")
        pc2 = workspace.create_device("host", "PC2")
        pc1.configure_ipv4("Ethernet0", "192.0.2.5", "24")
        pc2.configure_ipv4("Ethernet0", "192.0.2.5", "24")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "broken-but-useful.json"
            workspace.save(path)
            restored = LabWorkspace()
            restored.load(path)
            self.assertEqual(restored.resolve_device("PC1").get_interface("Ethernet0").ipv4_address, "192.0.2.5")
            self.assertTrue(any("Unique IPv4 address" in check.name and not check.passed for check in restored.verify().checks))

    def test_load_missing_file_reports_storage_error(self) -> None:
        workspace = LabWorkspace()
        with self.assertRaises(LabStorageError):
            workspace.load("no-such-lab-file.json")

    def test_empty_lab_can_be_saved_and_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "empty.json"
            empty = LabWorkspace()
            empty.save(path)
            restored = LabWorkspace()
            restored.load(path)
            self.assertEqual(restored.devices, ())
            self.assertIsNone(restored.active_device)


class TestScenariosAndVerification(unittest.TestCase):
    def test_initial_basic_lan_fails_verification_and_can_be_completed(self) -> None:
        workspace = LabWorkspace()
        task = workspace.load_scenario("basic-lan")
        self.assertIn("192.168.10.11/24", task)
        self.assertFalse(workspace.verify().passed)

        pc1 = workspace.resolve_device("PC1")
        pc2 = workspace.resolve_device("PC2")
        switch = workspace.resolve_device("SW1")
        pc1.configure_ipv4("Ethernet0", "192.168.10.11", "24")
        pc2.configure_ipv4("Ethernet0", "192.168.10.12", "24")
        for device, iface_name in (
            (pc1, "Ethernet0"), (pc2, "Ethernet0"),
            (switch, "FastEthernet0/1"), (switch, "FastEthernet0/2"),
        ):
            device.get_interface(iface_name).set_admin_up(True)
        report = workspace.verify()
        self.assertTrue(report.passed, "\n".join(f"{c.name}: {c.detail}" for c in report.checks))

    def test_vlan_isolation_scenario_verifies_blocked_traffic(self) -> None:
        workspace = LabWorkspace()
        workspace.load_scenario("vlan-isolation")
        pc1, pc2, switch = (
            workspace.resolve_device("PC1"),
            workspace.resolve_device("PC2"),
            workspace.resolve_device("SW1"),
        )
        pc1.configure_ipv4("Ethernet0", "192.168.10.11", "24")
        pc2.configure_ipv4("Ethernet0", "192.168.10.12", "24")
        for device, iface_name in (
            (pc1, "Ethernet0"), (pc2, "Ethernet0"),
            (switch, "FastEthernet0/1"), (switch, "FastEthernet0/2"),
        ):
            device.get_interface(iface_name).set_admin_up(True)
        report = workspace.verify()
        self.assertTrue(report.passed, "\n".join(f"{c.name}: {c.detail}" for c in report.checks))

    def test_unknown_scenario_has_actionable_error(self) -> None:
        workspace = LabWorkspace()
        with self.assertRaises(LabOperationError):
            workspace.load_scenario("not-real")

if __name__ == "__main__":
    unittest.main()


class TestWorkspaceMalformedInputRobustness(unittest.TestCase):
    """Adversarial lab-file inputs must fail cleanly and transactionally."""

    def setUp(self) -> None:
        self.workspace = LabWorkspace(name="Keep this lab")
        self.host = self.workspace.create_device("host", "PC1")
        self.before_topology = self.workspace.topology
        self.before_engine = self.workspace.engine
        self.before_active_device = self.workspace.active_device
        self.before_device_ids = tuple(device.device_id for device in self.workspace.devices)

    def assert_failed_import_is_transactional(self, path: Path) -> None:
        with self.assertRaises(LabFormatError):
            self.workspace.load(path)
        self.assertEqual(self.workspace.name, "Keep this lab")
        self.assertIs(self.workspace.topology, self.before_topology)
        self.assertIs(self.workspace.engine, self.before_engine)
        self.assertIs(self.workspace.active_device, self.before_active_device)
        self.assertEqual(tuple(device.device_id for device in self.workspace.devices), self.before_device_ids)

    def test_invalid_utf8_is_reported_as_lab_format_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "not-utf8.json"
            path.write_bytes(b"\xff\xfe\xfa")
            self.assert_failed_import_is_transactional(path)

    def test_extremely_deep_json_is_reported_without_raw_recursion_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "deep.json"
            path.write_text("[" * 10_000 + "0" + "]" * 10_000, encoding="utf-8")
            self.assert_failed_import_is_transactional(path)

    def test_excessively_long_json_integer_is_reported_as_lab_format_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "huge-integer.json"
            digits = "9" * 5_000
            path.write_text(
                '{"format_version":' + digits + ',"devices":[],"links":[]}',
                encoding="utf-8",
            )
            self.assert_failed_import_is_transactional(path)
