"""Tests for the Stage 6 Device save/reload extensibility hooks.

Device itself has no device-specific config beyond hostname/interfaces,
so this exercises the hook mechanism through a minimal test subclass -
Router and Switch's real overrides are tested in their own files
(test_router_stage6.py, test_switch_stage6.py).
"""

from __future__ import annotations

import unittest

from netsim.devices.base import Device
from netsim.devices.types import DeviceType


class _DeviceWithExtraConfig(Device):
    """Minimal Device subclass with one extra piece of config-layer
    state, to prove the hook mechanism itself works before relying on
    it from Router/Switch."""

    def __init__(self) -> None:
        super().__init__(hostname="Test1", device_type=DeviceType.HOST, interface_names=["Ethernet0"])
        self.favorite_number = 0

    def _capture_extra_config(self) -> dict[str, object]:
        return {"favorite_number": self.favorite_number}

    def _restore_extra_config(self, extra: dict[str, object]) -> None:
        self.favorite_number = extra.get("favorite_number", 0)


class TestExtraConfigDefaultsToNothing(unittest.TestCase):
    """A plain Device (no override) must behave exactly as before -
    this is the backward-compatibility guarantee for Host, which never
    overrides these hooks."""

    def test_base_device_capture_extra_config_is_empty(self) -> None:
        from netsim.devices.host import Host

        host = Host()
        self.assertEqual(host._capture_extra_config(), {})

    def test_base_device_restore_extra_config_is_a_no_op(self) -> None:
        from netsim.devices.host import Host

        host = Host()
        host._restore_extra_config({"anything": "ignored"})


class TestExtraConfigSurvivesSaveAndReload(unittest.TestCase):
    def test_saved_extra_config_is_restored_on_reload(self) -> None:
        device = _DeviceWithExtraConfig()
        device.favorite_number = 42
        device.save_config()
        device.favorite_number = 999

        device.reload()

        self.assertEqual(device.favorite_number, 42)

    def test_unsaved_extra_config_is_discarded_on_reload(self) -> None:

        device = _DeviceWithExtraConfig()
        device.save_config()
        device.favorite_number = 999

        device.reload()

        self.assertEqual(device.favorite_number, 0)

    def test_reload_without_any_save_restores_factory_default_extra_config(self) -> None:
        device = _DeviceWithExtraConfig()
        device.favorite_number = 999

        device.reload()

        self.assertEqual(device.favorite_number, 0)

    def test_hostname_and_interfaces_still_work_normally_alongside_extra_config(self) -> None:

        device = _DeviceWithExtraConfig()
        device.set_hostname("Saved")
        device.favorite_number = 7
        device.save_config()
        device.set_hostname("NotSaved")
        device.favorite_number = 0

        device.reload()

        self.assertEqual(device.hostname, "Saved")
        self.assertEqual(device.favorite_number, 7)

if __name__ == "__main__":
    unittest.main()
