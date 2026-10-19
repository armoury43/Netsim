"""Regression tests for malformed local input crossing public API boundaries."""
from __future__ import annotations

import tempfile
import json
import unittest
from pathlib import Path
import tempfile

from netsim.core.exceptions import ConfigurationError
from netsim.labs.errors import LabStorageError
from netsim.labs.workspace import (
    LabWorkspace,
    _MAX_INTERFACES_PER_DEVICE,
    _MAX_LAB_DEVICES,
    _MAX_LAB_LINKS,
    _MAX_TOTAL_ACL_RULES,
    _MAX_TOTAL_INTERFACES,
    _MAX_TOTAL_VLAN_ENTRIES,
)
from netsim.labs.errors import LabFormatError
from netsim.runtime import build_runtime


class TestMalformedPathHandling(unittest.TestCase):
    def test_load_embedded_nul_returns_storage_error(self) -> None:
        workspace = LabWorkspace()
        with self.assertRaises(LabStorageError):
            workspace.load("bad\x00path.json")

    def test_save_embedded_nul_returns_storage_error(self) -> None:
        workspace = LabWorkspace()
        with self.assertRaises(LabStorageError):
            workspace.save("bad\x00path.json")

    def test_cli_load_embedded_nul_does_not_leak_value_error(self) -> None:
        runtime = build_runtime()
        result = runtime.session.execute_line("lab load bad\x00path.json")
        self.assertIsNotNone(result.error)
        self.assertIn("Could not read lab", result.error or "")

    def test_cli_save_embedded_nul_does_not_leak_value_error(self) -> None:
        runtime = build_runtime()
        result = runtime.session.execute_line("lab save bad\x00path.json")
        self.assertIsNotNone(result.error)
        self.assertIn("Could not save lab", result.error or "")

    def test_oversized_lab_is_rejected_with_bounded_read(self) -> None:
        from netsim.labs.workspace import _MAX_LAB_FILE_BYTES

        workspace = LabWorkspace(name="keep-current-lab")
        before_topology = workspace.topology
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "oversized.json"
            path.write_bytes(b"{" + b" " * _MAX_LAB_FILE_BYTES)
            with self.assertRaises(LabStorageError):
                workspace.load(path)
        self.assertIs(workspace.topology, before_topology)
        self.assertEqual(workspace.name, "keep-current-lab")

    def _assert_json_rejected_transactionally(self, document: dict) -> None:
        workspace = LabWorkspace(name="keep-current-lab")
        before_topology = workspace.topology
        before_engine = workspace.engine
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "adversarial.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(LabFormatError):
                workspace.load(path)
        self.assertIs(workspace.topology, before_topology)
        self.assertIs(workspace.engine, before_engine)
        self.assertEqual(workspace.name, "keep-current-lab")

    def _empty_document(self) -> dict:
        return {
            "format_version": 1,
            "name": "malicious oversized lab",
            "active_scenario": None,
            "active_device_id": None,
            "devices": [],
            "links": [],
        }

    def test_device_count_limit_is_checked_before_object_construction(self) -> None:
        document = self._empty_document()
        document["devices"] = [{}] * (_MAX_LAB_DEVICES + 1)
        self._assert_json_rejected_transactionally(document)

    def test_link_count_limit_is_checked_before_topology_construction(self) -> None:
        document = self._empty_document()
        document["links"] = [{}] * (_MAX_LAB_LINKS + 1)
        self._assert_json_rejected_transactionally(document)

    def test_per_device_interface_limit_is_enforced(self) -> None:
        document = self._empty_document()
        document["devices"] = [{"hostname": "R1", "interfaces": [{}] * (_MAX_INTERFACES_PER_DEVICE + 1)}]
        self._assert_json_rejected_transactionally(document)

    def test_total_interface_limit_is_enforced(self) -> None:
        document = self._empty_document()
        count = (_MAX_TOTAL_INTERFACES // _MAX_INTERFACES_PER_DEVICE) + 1
        document["devices"] = [
            {"hostname": f"R{i}", "interfaces": [{}] * _MAX_INTERFACES_PER_DEVICE}
            for i in range(count)
        ]
        self._assert_json_rejected_transactionally(document)

    def test_total_acl_rule_limit_is_enforced(self) -> None:
        document = self._empty_document()
        document["devices"] = [{
            "extra": {"router": {"access_lists": [{"rules": [{}] * (_MAX_TOTAL_ACL_RULES + 1)}]}}
        }]
        self._assert_json_rejected_transactionally(document)

    def test_total_vlan_entry_limit_is_enforced(self) -> None:
        document = self._empty_document()
        document["devices"] = [{
            "extra": {"switch": {"vlans": [{}] * (_MAX_TOTAL_VLAN_ENTRIES + 1)}}
        }]
        self._assert_json_rejected_transactionally(document)

if __name__ == "__main__":
    unittest.main()
