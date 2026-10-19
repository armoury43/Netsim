"""Tests for netsim.devices.base.Device."""

from __future__ import annotations

import unittest

from netsim.devices.base import Device
from netsim.devices.errors import (
    DuplicateInterfaceError,
    DuplicateIPAddressError,
    InterfaceNotFoundError,
    InvalidLifecycleTransitionError,
)
from netsim.devices.state import DeviceState
from netsim.devices.types import DeviceType
from netsim.core.exceptions import ValidationError


class _TestDevice(Device):
    """Minimal concrete Device for exercising base-class behavior only."""

    def __init__(self, hostname: str = "Device1", interface_names: list[str] | None = None) -> None:
        super().__init__(
            hostname=hostname,
            device_type=DeviceType.HOST,
            interface_names=interface_names or ["Ethernet0", "Ethernet1"],
        )


class TestDeviceIdentity(unittest.TestCase):
    def test_has_a_unique_device_id(self) -> None:
        a = _TestDevice()
        b = _TestDevice()
        self.assertNotEqual(a.device_id, b.device_id)

    def test_device_id_is_stable_across_reads(self) -> None:
        device = _TestDevice()
        self.assertEqual(device.device_id, device.device_id)

    def test_device_type_is_set(self) -> None:
        device = _TestDevice()
        self.assertEqual(device.device_type, DeviceType.HOST)


class TestDeviceHostname(unittest.TestCase):
    def test_initial_hostname(self) -> None:
        device = _TestDevice(hostname="R1")
        self.assertEqual(device.hostname, "R1")

    def test_set_hostname_changes_it(self) -> None:
        device = _TestDevice(hostname="R1")
        device.set_hostname("R2")
        self.assertEqual(device.hostname, "R2")

    def test_set_hostname_rejects_empty(self) -> None:
        device = _TestDevice()
        with self.assertRaises(ValidationError):
            device.set_hostname("")

    def test_set_hostname_rejects_whitespace_only(self) -> None:
        device = _TestDevice()
        with self.assertRaises(ValidationError):
            device.set_hostname("   ")


class TestDeviceInterfaceConstruction(unittest.TestCase):
    def test_interfaces_created_from_names(self) -> None:
        device = _TestDevice(interface_names=["Ethernet0", "Ethernet1"])
        self.assertEqual(set(device.interfaces.keys()), {"Ethernet0", "Ethernet1"})

    def test_duplicate_interface_names_rejected_at_construction(self) -> None:
        with self.assertRaises(DuplicateInterfaceError):
            _TestDevice(interface_names=["Ethernet0", "Ethernet0"])

    def test_invalid_interface_name_rejected_at_construction(self) -> None:
        with self.assertRaises(ValidationError):
            _TestDevice(interface_names=["not a valid name"])

    def test_interfaces_property_is_read_only_view(self) -> None:
        device = _TestDevice()
        with self.assertRaises(TypeError):
            device.interfaces["Ethernet0"] = None


class TestDeviceInterfaceLookup(unittest.TestCase):
    def test_get_interface_returns_it(self) -> None:
        device = _TestDevice(interface_names=["Ethernet0"])
        iface = device.get_interface("Ethernet0")
        self.assertEqual(iface.name, "Ethernet0")

    def test_get_interface_raises_for_unknown_name(self) -> None:
        device = _TestDevice(interface_names=["Ethernet0"])
        with self.assertRaises(InterfaceNotFoundError):
            device.get_interface("Ethernet99")


class TestDeviceDuplicateIPDetection(unittest.TestCase):
    def test_same_ip_on_two_interfaces_rejected(self) -> None:
        device = _TestDevice(interface_names=["Ethernet0", "Ethernet1"])
        device.configure_ipv4("Ethernet0", "10.0.0.1", "255.255.255.0")
        with self.assertRaises(DuplicateIPAddressError):
            device.configure_ipv4("Ethernet1", "10.0.0.1", "255.255.255.252")

    def test_reconfiguring_same_interface_with_same_ip_is_allowed(self) -> None:
        device = _TestDevice(interface_names=["Ethernet0"])
        device.configure_ipv4("Ethernet0", "10.0.0.1", "255.255.255.0")
        device.configure_ipv4("Ethernet0", "10.0.0.1", "255.255.255.0")

    def test_different_ips_on_different_interfaces_allowed(self) -> None:
        device = _TestDevice(interface_names=["Ethernet0", "Ethernet1"])
        device.configure_ipv4("Ethernet0", "10.0.0.1", "255.255.255.0")
        device.configure_ipv4("Ethernet1", "10.0.1.1", "255.255.255.0")

    def test_configure_ipv4_on_unknown_interface_raises(self) -> None:
        device = _TestDevice(interface_names=["Ethernet0"])
        with self.assertRaises(InterfaceNotFoundError):
            device.configure_ipv4("Ethernet99", "10.0.0.1", "255.255.255.0")


class TestDeviceLifecycle(unittest.TestCase):
    def test_starts_in_created_state(self) -> None:
        device = _TestDevice()
        self.assertEqual(device.state, DeviceState.CREATED)

    def test_power_on_moves_to_booting(self) -> None:
        device = _TestDevice()
        device.power_on()
        self.assertEqual(device.state, DeviceState.BOOTING)

    def test_complete_boot_moves_to_ready(self) -> None:
        device = _TestDevice()
        device.power_on()
        device.complete_boot()
        self.assertEqual(device.state, DeviceState.READY)

    def test_boot_convenience_reaches_ready_directly(self) -> None:
        device = _TestDevice()
        device.boot()
        self.assertEqual(device.state, DeviceState.READY)

    def test_power_off_from_ready(self) -> None:
        device = _TestDevice()
        device.boot()
        device.power_off()
        self.assertEqual(device.state, DeviceState.POWERED_OFF)

    def test_complete_boot_without_power_on_raises(self) -> None:
        device = _TestDevice()
        with self.assertRaises(InvalidLifecycleTransitionError):
            device.complete_boot()

    def test_power_off_from_created_raises(self) -> None:
        device = _TestDevice()
        with self.assertRaises(InvalidLifecycleTransitionError):
            device.power_off()

    def test_double_power_on_raises(self) -> None:
        device = _TestDevice()
        device.boot()
        with self.assertRaises(InvalidLifecycleTransitionError):
            device.power_on()


class TestDeviceRunningConfig(unittest.TestCase):
    def test_running_config_reflects_live_hostname(self) -> None:
        device = _TestDevice(hostname="R1")
        self.assertIn("hostname R1", device.render_running_config())

    def test_running_config_updates_after_change(self) -> None:
        device = _TestDevice(hostname="R1")
        device.set_hostname("R2")
        self.assertIn("hostname R2", device.render_running_config())
        self.assertNotIn("hostname R1", device.render_running_config())


class TestDeviceStartupConfigAndReload(unittest.TestCase):
    def test_startup_config_before_any_save_reflects_factory_defaults(self) -> None:
        device = _TestDevice(hostname="R1")
        self.assertIn("hostname R1", device.render_startup_config())

    def test_save_config_captures_current_state(self) -> None:
        device = _TestDevice(hostname="R1")
        device.set_hostname("R2")
        device.save_config()
        self.assertIn("hostname R2", device.render_startup_config())

    def test_reload_restores_last_saved_config(self) -> None:
        device = _TestDevice(hostname="R1")
        device.save_config()
        device.set_hostname("Temporary")
        device.reload()
        self.assertEqual(device.hostname, "R1")

    def test_reload_without_any_save_restores_factory_defaults(self) -> None:
        device = _TestDevice(hostname="R1")
        device.set_hostname("Temporary")
        device.reload()
        self.assertEqual(device.hostname, "R1")

    def test_reload_restores_interface_configuration(self) -> None:
        device = _TestDevice(interface_names=["Ethernet0"], hostname="R1")
        device.save_config()
        device.configure_ipv4("Ethernet0", "10.0.0.1", "255.255.255.0")
        device.reload()
        self.assertIsNone(device.get_interface("Ethernet0").ipv4_address)

    def test_unsaved_running_changes_do_not_affect_startup_config(self) -> None:
        device = _TestDevice(hostname="R1")
        device.save_config()
        device.set_hostname("NotSaved")
        self.assertIn("hostname R1", device.render_startup_config())
        self.assertIn("hostname NotSaved", device.render_running_config())

if __name__ == "__main__":
    unittest.main()
