"""Tests for netsim.devices.configuration."""

from __future__ import annotations

import unittest

from netsim.devices.configuration import ConfigSnapshot, render_config_text
from netsim.devices.interface import Interface


class TestConfigSnapshot(unittest.TestCase):
    def test_stores_hostname_and_interfaces(self) -> None:
        iface = Interface(name="GigabitEthernet0/0")
        snapshot = ConfigSnapshot(hostname="R1", interfaces={"GigabitEthernet0/0": iface})
        self.assertEqual(snapshot.hostname, "R1")
        self.assertIn("GigabitEthernet0/0", snapshot.interfaces)

    def test_interfaces_are_deep_copied_not_shared(self) -> None:
        iface = Interface(name="GigabitEthernet0/0")
        snapshot = ConfigSnapshot(hostname="R1", interfaces={"GigabitEthernet0/0": iface})

        iface.set_description("changed after snapshot")

        self.assertEqual(snapshot.interfaces["GigabitEthernet0/0"].description, "")

    def test_capture_produces_independent_snapshot(self) -> None:
        iface = Interface(name="GigabitEthernet0/0")
        original_interfaces = {"GigabitEthernet0/0": iface}

        snapshot = ConfigSnapshot.capture(hostname="R1", interfaces=original_interfaces)
        iface.set_admin_up(True)

        self.assertFalse(snapshot.interfaces["GigabitEthernet0/0"].admin_up)


class TestRenderConfigText(unittest.TestCase):
    def test_includes_hostname_line(self) -> None:
        text = render_config_text(hostname="R1", interfaces={})
        self.assertIn("hostname R1", text)

    def test_includes_interface_stanza(self) -> None:
        iface = Interface(name="GigabitEthernet0/0")
        iface.set_description("uplink")
        iface.set_ipv4_address("10.0.0.1", "255.255.255.0")
        iface.set_admin_up(True)

        text = render_config_text(hostname="R1", interfaces={"GigabitEthernet0/0": iface})

        self.assertIn("interface GigabitEthernet0/0", text)
        self.assertIn("description uplink", text)
        self.assertIn("ip address 10.0.0.1 255.255.255.0", text)
        self.assertNotIn("shutdown\n", text)

    def test_shutdown_interface_shows_shutdown_line(self) -> None:
        iface = Interface(name="GigabitEthernet0/0")
        text = render_config_text(hostname="R1", interfaces={"GigabitEthernet0/0": iface})
        self.assertIn("shutdown", text)

    def test_interfaces_rendered_in_sorted_order(self) -> None:
        interfaces = {
            "GigabitEthernet0/1": Interface(name="GigabitEthernet0/1"),
            "GigabitEthernet0/0": Interface(name="GigabitEthernet0/0"),
        }
        text = render_config_text(hostname="R1", interfaces=interfaces)
        first_index = text.index("GigabitEthernet0/0")
        second_index = text.index("GigabitEthernet0/1")
        self.assertLess(first_index, second_index)

if __name__ == "__main__":
    unittest.main()
