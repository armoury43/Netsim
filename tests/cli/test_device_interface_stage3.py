"""Tests for the Stage 3 additions to netsim.cli.device_interface.

These are pure structural-typing checks against real Stage 3 devices
(Router/Switch) - no test doubles needed here, since the whole point is
proving the real device classes satisfy the CLI's protocols without
either package importing the other.
"""

from __future__ import annotations

import unittest

from netsim.cli.device_interface import FullDeviceContext, InterfaceContext, VlanCapableDeviceContext
from netsim.devices.host import Host
from netsim.devices.router import Router
from netsim.devices.switch import Switch


class TestInterfaceContextProtocol(unittest.TestCase):
    def test_real_interface_satisfies_protocol(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        iface = router.get_interface("GigabitEthernet0/0")
        self.assertIsInstance(iface, InterfaceContext)


class TestFullDeviceContextProtocol(unittest.TestCase):
    def test_router_satisfies_full_device_context(self) -> None:
        self.assertIsInstance(Router(), FullDeviceContext)

    def test_switch_satisfies_full_device_context(self) -> None:
        self.assertIsInstance(Switch(), FullDeviceContext)

    def test_host_satisfies_full_device_context(self) -> None:
        self.assertIsInstance(Host(), FullDeviceContext)


class TestVlanCapableDeviceContextProtocol(unittest.TestCase):
    def test_switch_satisfies_vlan_capable_protocol(self) -> None:
        self.assertIsInstance(Switch(), VlanCapableDeviceContext)

    def test_router_does_not_satisfy_vlan_capable_protocol(self) -> None:
        self.assertNotIsInstance(Router(), VlanCapableDeviceContext)

    def test_host_does_not_satisfy_vlan_capable_protocol(self) -> None:
        self.assertNotIsInstance(Host(), VlanCapableDeviceContext)

if __name__ == "__main__":
    unittest.main()
