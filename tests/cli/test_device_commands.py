"""Tests for netsim.cli.device_commands.

These are integration tests by design: real CliSession, real
CommandRegistry from build_device_registry(), and real Stage 3 devices
(Router, Switch, Host) - not test doubles. The point of Stage 3 is
proving the CLI actually drives real device state, so faking the
device here would test nothing.
"""

from __future__ import annotations

import unittest

from netsim.cli.device_commands import build_device_registry
from netsim.cli.session import CliSession
from netsim.devices.host import Host
from netsim.devices.router import Router
from netsim.devices.switch import Switch
from netsim.network.engine import NetworkEngine
from netsim.network.topology import Topology


class TestRegistryContents(unittest.TestCase):
    def test_expected_commands_registered(self) -> None:
        registry = build_device_registry()
        names = {c.name for c in registry.all_commands()}
        expected = {
            "enable",
            "disable",
            "configure terminal",
            "interface",
            "router",
            "vlan",
            "hostname",
            "exit",
            "end",
            "show version",
            "show history",
            "description",
            "ip address",
            "shutdown",
            "no shutdown",
            "access-list",
            "ip access-group",
            "no ip access-group",
            "show running-config",
            "show startup-config",
            "show interfaces",
            "show ip interface brief",
            "copy running-config startup-config",
            "reload",
            "show mac address-table",
            "ip route",
        }
        self.assertTrue(expected.issubset(names))


class TestHostnameThroughCli(unittest.TestCase):
    def test_hostname_command_changes_real_router_object(self) -> None:
        router = Router()
        session = CliSession(registry=build_device_registry(), device=router)
        session.execute_line("enable")
        session.execute_line("configure terminal")
        session.execute_line("hostname Tehran-R1")

        self.assertEqual(router.hostname, "Tehran-R1")
        self.assertEqual(session.prompt(), "Tehran-R1(config)#")


class TestInterfaceResolutionThroughCli(unittest.TestCase):
    def setUp(self) -> None:
        self.router = Router(interface_names=["GigabitEthernet0/0", "GigabitEthernet0/1"])
        self.session = CliSession(registry=build_device_registry(), device=self.router)
        self.session.execute_line("enable")
        self.session.execute_line("configure terminal")

    def test_valid_interface_name_enters_interface_config(self) -> None:
        outcome = self.session.execute_line("interface GigabitEthernet0/0")
        self.assertIsNone(outcome.error)
        self.assertEqual(self.session.prompt(), "Router(config-if)#")

    def test_invalid_interface_name_is_rejected_with_real_error(self) -> None:
        outcome = self.session.execute_line("interface GigabitEthernet9/9")
        self.assertIsNotNone(outcome.error)
        assert outcome.error is not None
        self.assertIn("GigabitEthernet9/9", outcome.error)

        self.assertEqual(self.session.prompt(), "Router(config)#")


class TestInterfaceConfigurationThroughCli(unittest.TestCase):
    def setUp(self) -> None:
        self.router = Router(interface_names=["GigabitEthernet0/0"])
        self.session = CliSession(registry=build_device_registry(), device=self.router)
        self.session.execute_line("enable")
        self.session.execute_line("configure terminal")
        self.session.execute_line("interface GigabitEthernet0/0")

    def test_description_sets_real_interface_description(self) -> None:
        self.session.execute_line("description WAN_TO_SHIRAZ")
        iface = self.router.get_interface("GigabitEthernet0/0")
        self.assertEqual(iface.description, "WAN_TO_SHIRAZ")

    def test_ip_address_configures_real_interface(self) -> None:
        outcome = self.session.execute_line("ip address 10.0.0.1 255.255.255.252")
        self.assertIsNone(outcome.error)
        iface = self.router.get_interface("GigabitEthernet0/0")
        self.assertEqual(iface.ipv4_address, "10.0.0.1")
        self.assertEqual(iface.ipv4_prefix_length, 30)

    def test_malformed_ip_address_rejected(self) -> None:
        outcome = self.session.execute_line("ip address 999.1.1.1 255.255.255.0")
        self.assertIsNotNone(outcome.error)
        iface = self.router.get_interface("GigabitEthernet0/0")
        self.assertIsNone(iface.ipv4_address)

    def test_malformed_mask_rejected(self) -> None:
        outcome = self.session.execute_line("ip address 10.0.0.1 not-a-mask")
        self.assertIsNotNone(outcome.error)

    def test_no_shutdown_brings_interface_administratively_up(self) -> None:
        self.assertFalse(self.router.get_interface("GigabitEthernet0/0").admin_up)
        self.session.execute_line("no shutdown")
        self.assertTrue(self.router.get_interface("GigabitEthernet0/0").admin_up)

    def test_shutdown_brings_interface_administratively_down(self) -> None:
        self.session.execute_line("no shutdown")
        self.session.execute_line("shutdown")
        self.assertFalse(self.router.get_interface("GigabitEthernet0/0").admin_up)


class TestDuplicateIpAddressThroughCli(unittest.TestCase):
    def test_second_interface_with_same_ip_is_rejected(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0", "GigabitEthernet0/1"])
        session = CliSession(registry=build_device_registry(), device=router)
        session.execute_line("enable")
        session.execute_line("configure terminal")
        session.execute_line("interface GigabitEthernet0/0")
        session.execute_line("ip address 10.0.0.1 255.255.255.0")
        session.execute_line("exit")
        session.execute_line("interface GigabitEthernet0/1")

        outcome = session.execute_line("ip address 10.0.0.1 255.255.255.252")

        self.assertIsNotNone(outcome.error)
        assert outcome.error is not None
        self.assertIn("10.0.0.1", outcome.error)
        self.assertIsNone(router.get_interface("GigabitEthernet0/1").ipv4_address)


class TestShowCommandsReflectRealState(unittest.TestCase):
    def setUp(self) -> None:
        self.router = Router(hostname="R1", interface_names=["GigabitEthernet0/0", "GigabitEthernet0/1"])
        self.session = CliSession(registry=build_device_registry(), device=self.router)
        self.session.execute_line("enable")
        self.session.execute_line("configure terminal")
        self.session.execute_line("interface GigabitEthernet0/0")
        self.session.execute_line("description uplink")
        self.session.execute_line("ip address 10.0.0.1 255.255.255.0")
        self.session.execute_line("no shutdown")
        self.session.execute_line("end")

    def test_show_running_config_reflects_real_configuration(self) -> None:
        outcome = self.session.execute_line("show running-config")
        text = "\n".join(outcome.output)
        self.assertIn("hostname R1", text)
        self.assertIn("interface GigabitEthernet0/0", text)
        self.assertIn("description uplink", text)
        self.assertIn("ip address 10.0.0.1 255.255.255.0", text)

    def test_show_interfaces_reflects_real_state(self) -> None:
        outcome = self.session.execute_line("show interfaces")
        text = "\n".join(outcome.output)
        self.assertIn("GigabitEthernet0/0 is up", text)
        self.assertIn("uplink", text)
        self.assertIn("10.0.0.1", text)

    def test_show_ip_interface_brief_lists_all_interfaces(self) -> None:
        outcome = self.session.execute_line("show ip interface brief")
        text = "\n".join(outcome.output)
        self.assertIn("10.0.0.1", text)
        self.assertIn("unassigned", text)

    def test_show_startup_config_before_save_is_factory_defaults(self) -> None:
        outcome = self.session.execute_line("show startup-config")
        text = "\n".join(outcome.output)
        self.assertNotIn("10.0.0.1", text)

    def test_copy_running_config_to_startup_then_show_startup_reflects_it(self) -> None:
        self.session.execute_line("copy running-config startup-config")
        outcome = self.session.execute_line("show startup-config")
        text = "\n".join(outcome.output)
        self.assertIn("10.0.0.1", text)


class TestReloadThroughCli(unittest.TestCase):
    def test_reload_restores_last_saved_config(self) -> None:
        router = Router(hostname="R1", interface_names=["GigabitEthernet0/0"])
        session = CliSession(registry=build_device_registry(), device=router)
        session.execute_line("enable")
        session.execute_line("configure terminal")
        session.execute_line("hostname Saved")
        session.execute_line("end")
        session.execute_line("copy running-config startup-config")
        session.execute_line("configure terminal")
        session.execute_line("hostname NotSaved")
        session.execute_line("end")

        session.execute_line("reload")

        self.assertEqual(router.hostname, "Saved")


class TestAccessListCommand(unittest.TestCase):
    def _configure(self, session: CliSession) -> None:
        session.execute_line("enable")
        session.execute_line("configure terminal")

    def test_access_list_permit_with_network_and_mask(self) -> None:
        router = Router()
        session = CliSession(registry=build_device_registry(), device=router)
        self._configure(session)

        outcome = session.execute_line("access-list 1 permit 10.0.0.0 255.0.0.0")

        self.assertIsNone(outcome.error)
        acl = router.access_lists[1]
        self.assertTrue(acl.evaluate("10.0.0.5"))
        self.assertFalse(acl.evaluate("192.168.1.1"))

    def test_access_list_deny_any(self) -> None:
        router = Router()
        session = CliSession(registry=build_device_registry(), device=router)
        self._configure(session)

        outcome = session.execute_line("access-list 1 deny any")

        self.assertIsNone(outcome.error)
        self.assertFalse(router.access_lists[1].evaluate("10.0.0.5"))

    def test_access_list_rejected_on_switch(self) -> None:
        switch = Switch()
        session = CliSession(registry=build_device_registry(), device=switch)
        self._configure(session)

        outcome = session.execute_line("access-list 1 permit any")

        self.assertIsNotNone(outcome.error)

    def test_access_list_invalid_action_rejected(self) -> None:
        router = Router()
        session = CliSession(registry=build_device_registry(), device=router)
        self._configure(session)

        outcome = session.execute_line("access-list 1 allow any")

        self.assertIsNotNone(outcome.error)

    def test_access_list_missing_mask_without_any_rejected(self) -> None:
        router = Router()
        session = CliSession(registry=build_device_registry(), device=router)
        self._configure(session)

        outcome = session.execute_line("access-list 1 permit 10.0.0.0")

        self.assertIsNotNone(outcome.error)

    def test_malformed_access_list_network_returns_cli_error(self) -> None:
        router = Router()
        session = CliSession(registry=build_device_registry(), device=router)
        self._configure(session)

        outcome = session.execute_line("access-list 1 permit 999.1.2.3 255.255.255.0")

        self.assertIsNotNone(outcome.error)
        self.assertIn("valid IPv4 address", outcome.error or "")

    def test_multiple_access_list_statements_accumulate_through_cli(self) -> None:
        router = Router()
        session = CliSession(registry=build_device_registry(), device=router)
        self._configure(session)

        session.execute_line("access-list 1 deny 10.0.0.0 255.0.0.0")
        session.execute_line("access-list 1 permit any")

        acl = router.access_lists[1]
        self.assertEqual(len(acl.rules()), 2)


class TestIpAccessGroupCommand(unittest.TestCase):
    def _enter_interface(self, session: CliSession, name: str) -> None:
        session.execute_line("enable")
        session.execute_line("configure terminal")
        outcome = session.execute_line(f"interface {name}")
        assert outcome.error is None, outcome.error

    def test_applies_acl_inbound_on_real_interface_state(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.get_or_create_access_list(1)
        session = CliSession(registry=build_device_registry(), device=router)
        self._enter_interface(session, "GigabitEthernet0/0")

        outcome = session.execute_line("ip access-group 1 in")

        self.assertIsNone(outcome.error)
        acl = router.get_interface_acl("GigabitEthernet0/0", "in")
        assert acl is not None
        self.assertEqual(acl.number, 1)

    def test_applies_acl_outbound_independent_of_inbound(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.get_or_create_access_list(1)
        router.get_or_create_access_list(2)
        session = CliSession(registry=build_device_registry(), device=router)
        self._enter_interface(session, "GigabitEthernet0/0")

        session.execute_line("ip access-group 1 in")
        session.execute_line("ip access-group 2 out")

        self.assertEqual(router.get_interface_acl("GigabitEthernet0/0", "in").number, 1)
        self.assertEqual(router.get_interface_acl("GigabitEthernet0/0", "out").number, 2)

    def test_invalid_direction_rejected(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        session = CliSession(registry=build_device_registry(), device=router)
        self._enter_interface(session, "GigabitEthernet0/0")

        outcome = session.execute_line("ip access-group 1 sideways")

        self.assertIsNotNone(outcome.error)

    def test_rejected_on_switch(self) -> None:
        switch = Switch(interface_names=["FastEthernet0/1"])
        session = CliSession(registry=build_device_registry(), device=switch)
        self._enter_interface(session, "FastEthernet0/1")

        outcome = session.execute_line("ip access-group 1 in")

        self.assertIsNotNone(outcome.error)

    def test_no_ip_access_group_removes_matching_inbound_binding(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.set_interface_acl("GigabitEthernet0/0", "in", 7)
        session = CliSession(registry=build_device_registry(), device=router)
        self._enter_interface(session, "GigabitEthernet0/0")

        outcome = session.execute_line("no ip access-group 7 in")

        self.assertIsNone(outcome.error)
        self.assertIsNone(router.get_interface_acl("GigabitEthernet0/0", "in"))

    def test_no_ip_access_group_removes_matching_outbound_binding(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.set_interface_acl("GigabitEthernet0/0", "out", 8)
        session = CliSession(registry=build_device_registry(), device=router)
        self._enter_interface(session, "GigabitEthernet0/0")

        outcome = session.execute_line("no ip access-group 8 out")

        self.assertIsNone(outcome.error)
        self.assertIsNone(router.get_interface_acl("GigabitEthernet0/0", "out"))

    def test_no_ip_access_group_does_not_remove_different_acl_number(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.set_interface_acl("GigabitEthernet0/0", "in", 7)
        session = CliSession(registry=build_device_registry(), device=router)
        self._enter_interface(session, "GigabitEthernet0/0")

        outcome = session.execute_line("no ip access-group 9 in")

        self.assertIsNone(outcome.error)
        acl = router.get_interface_acl("GigabitEthernet0/0", "in")
        self.assertIsNotNone(acl)
        self.assertEqual(acl.number, 7)

    def test_no_ip_access_group_validates_direction_and_number(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        session = CliSession(registry=build_device_registry(), device=router)
        self._enter_interface(session, "GigabitEthernet0/0")

        bad_direction = session.execute_line("no ip access-group 1 sideways")
        bad_number = session.execute_line("no ip access-group 100 in")

        self.assertIsNotNone(bad_direction.error)
        self.assertIsNotNone(bad_number.error)

    def test_no_ip_access_group_rejected_on_switch(self) -> None:
        switch = Switch(interface_names=["FastEthernet0/1"])
        session = CliSession(registry=build_device_registry(), device=switch)
        self._enter_interface(session, "FastEthernet0/1")

        outcome = session.execute_line("no ip access-group 1 in")

        self.assertIsNotNone(outcome.error)

    def test_acl_configured_and_applied_actually_changes_ping_behavior(self) -> None:

        from netsim.cli.network_commands import register_network_commands
        from netsim.devices.host import Host
        from netsim.network.engine import NetworkEngine
        from netsim.network.topology import Topology

        topology = Topology()
        pc1 = Host(hostname="PC1")
        router = Router(hostname="R1", interface_names=["GigabitEthernet0/0", "GigabitEthernet0/1"])
        pc2 = Host(hostname="PC2")
        topology.add_device(pc1)
        topology.add_device(router)
        topology.add_device(pc2)
        topology.connect(pc1.device_id, "Ethernet0", router.device_id, "GigabitEthernet0/0")
        topology.connect(router.device_id, "GigabitEthernet0/1", pc2.device_id, "Ethernet0")
        pc1.configure_ipv4("Ethernet0", "10.0.0.10", "255.255.255.0")
        router.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")
        router.configure_ipv4("GigabitEthernet0/1", "192.168.1.1", "255.255.255.0")
        pc2.configure_ipv4("Ethernet0", "192.168.1.10", "255.255.255.0")
        pc1.set_default_gateway("10.0.0.1")
        pc2.set_default_gateway("192.168.1.1")
        for iface in (
            pc1.get_interface("Ethernet0"),
            router.get_interface("GigabitEthernet0/0"),
            router.get_interface("GigabitEthernet0/1"),
            pc2.get_interface("Ethernet0"),
        ):
            iface.set_admin_up(True)
        pc1.boot()
        router.boot()
        pc2.boot()

        registry = build_device_registry()
        register_network_commands(registry)
        engine = NetworkEngine(topology)
        session = CliSession(registry=registry, device=router, network=engine)

        self.assertTrue(engine.ping(pc1.device_id, "192.168.1.10").success)

        session.execute_line("enable")
        session.execute_line("configure terminal")
        session.execute_line("access-list 1 deny 10.0.0.0 255.255.255.0")
        session.execute_line("interface GigabitEthernet0/1")
        session.execute_line("ip access-group 1 out")

        result = engine.ping(pc1.device_id, "192.168.1.10")
        self.assertFalse(result.success)

        removal = session.execute_line("no ip access-group 1 out")
        self.assertIsNone(removal.error)
        self.assertTrue(engine.ping(pc1.device_id, "192.168.1.10").success)


class TestNetworkCommandUnderRouterRip(unittest.TestCase):
    def _enter_router_rip(self, session: CliSession) -> None:
        session.execute_line("enable")
        session.execute_line("configure terminal")
        outcome = session.execute_line("router rip")
        assert outcome.error is None, outcome.error

    def test_network_command_enables_rip_on_real_router_state(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        session = CliSession(registry=build_device_registry(), device=router)
        self._enter_router_rip(session)

        outcome = session.execute_line("network 10.0.0.0 255.0.0.0")

        self.assertIsNone(outcome.error)
        networks = {str(n) for n in router.rip_networks}
        self.assertIn("10.0.0.0/8", networks)

    def test_network_command_rejected_when_protocol_is_not_rip(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        session = CliSession(registry=build_device_registry(), device=router)
        session.execute_line("enable")
        session.execute_line("configure terminal")
        session.execute_line("router ospf")

        outcome = session.execute_line("network 10.0.0.0 255.0.0.0")

        self.assertIsNotNone(outcome.error)
        self.assertEqual(router.rip_networks, frozenset())

    def test_network_command_rejected_on_switch(self) -> None:
        switch = Switch()
        session = CliSession(registry=build_device_registry(), device=switch)
        session.execute_line("enable")
        session.execute_line("configure terminal")
        session.execute_line("router rip")

        outcome = session.execute_line("network 10.0.0.0 255.0.0.0")

        self.assertIsNotNone(outcome.error)

    def test_network_command_rejects_malformed_mask(self) -> None:
        router = Router()
        session = CliSession(registry=build_device_registry(), device=router)
        self._enter_router_rip(session)

        outcome = session.execute_line("network 10.0.0.0 not-a-mask")

        self.assertIsNotNone(outcome.error)

    def test_multiple_network_statements_accumulate(self) -> None:
        router = Router()
        session = CliSession(registry=build_device_registry(), device=router)
        self._enter_router_rip(session)

        session.execute_line("network 10.0.0.0 255.0.0.0")
        session.execute_line("network 192.168.1.0 255.255.255.0")

        networks = {str(n) for n in router.rip_networks}
        self.assertEqual(networks, {"10.0.0.0/8", "192.168.1.0/24"})

    def test_network_statement_persists_after_leaving_config_mode(self) -> None:
        router = Router()
        session = CliSession(registry=build_device_registry(), device=router)
        self._enter_router_rip(session)
        session.execute_line("network 10.0.0.0 255.0.0.0")
        session.execute_line("end")

        networks = {str(n) for n in router.rip_networks}
        self.assertIn("10.0.0.0/8", networks)


class TestIpRouteCommand(unittest.TestCase):
    def test_configures_a_real_static_route_on_router(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        session = CliSession(registry=build_device_registry(), device=router)
        session.execute_line("enable")
        session.execute_line("configure terminal")

        outcome = session.execute_line("ip route 192.168.2.0 255.255.255.0 10.0.0.2")

        self.assertIsNone(outcome.error)
        self.assertIn("192.168.2.0/24", router.static_routes)
        self.assertEqual(str(router.static_routes["192.168.2.0/24"].next_hop), "10.0.0.2")

    def test_rejected_on_switch(self) -> None:
        switch = Switch()
        session = CliSession(registry=build_device_registry(), device=switch)
        session.execute_line("enable")
        session.execute_line("configure terminal")

        outcome = session.execute_line("ip route 192.168.2.0 255.255.255.0 10.0.0.2")

        self.assertIsNotNone(outcome.error)

    def test_rejected_on_host(self) -> None:
        host = Host()
        session = CliSession(registry=build_device_registry(), device=host)
        session.execute_line("enable")
        session.execute_line("configure terminal")

        outcome = session.execute_line("ip route 192.168.2.0 255.255.255.0 10.0.0.2")

        self.assertIsNotNone(outcome.error)

    def test_malformed_next_hop_rejected(self) -> None:
        router = Router()
        session = CliSession(registry=build_device_registry(), device=router)
        session.execute_line("enable")
        session.execute_line("configure terminal")

        outcome = session.execute_line("ip route 192.168.2.0 255.255.255.0 999.1.1.1")

        self.assertIsNotNone(outcome.error)

    def test_configured_route_persists_after_leaving_config_mode(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        session = CliSession(registry=build_device_registry(), device=router)
        session.execute_line("enable")
        session.execute_line("configure terminal")
        session.execute_line("ip route 192.168.2.0 255.255.255.0 10.0.0.2")
        session.execute_line("end")

        self.assertIn("192.168.2.0/24", router.static_routes)


class TestShowMacAddressTableCommand(unittest.TestCase):
    def test_reflects_real_learned_entries_on_switch(self) -> None:
        switch = Switch(interface_names=["FastEthernet0/1"])
        switch.learn_mac("02:00:00:00:00:01", "FastEthernet0/1")
        session = CliSession(registry=build_device_registry(), device=switch)

        outcome = session.execute_line("show mac address-table")

        joined = "\n".join(outcome.output)
        self.assertIn("02:00:00:00:00:01", joined)
        self.assertIn("FastEthernet0/1", joined)

    def test_empty_before_any_learning(self) -> None:
        switch = Switch()
        session = CliSession(registry=build_device_registry(), device=switch)

        outcome = session.execute_line("show mac address-table")

        self.assertIsNone(outcome.error)

    def test_rejected_on_router(self) -> None:
        router = Router()
        session = CliSession(registry=build_device_registry(), device=router)

        outcome = session.execute_line("show mac address-table")

        self.assertIsNotNone(outcome.error)


class TestSwitchportCommandsThroughCli(unittest.TestCase):
    def _enter_interface(self, session: CliSession, name: str) -> None:
        session.execute_line("enable")
        session.execute_line("configure terminal")
        outcome = session.execute_line(f"interface {name}")
        assert outcome.error is None, outcome.error

    def test_switchport_access_vlan_sets_real_interface_state(self) -> None:
        switch = Switch(interface_names=["FastEthernet0/1"])
        session = CliSession(registry=build_device_registry(), device=switch)
        self._enter_interface(session, "FastEthernet0/1")

        outcome = session.execute_line("switchport access vlan 20")

        self.assertIsNone(outcome.error)
        iface = switch.get_interface("FastEthernet0/1")
        self.assertEqual(iface.switchport.mode, "access")
        self.assertEqual(iface.switchport.access_vlan, 20)

    def test_switchport_access_vlan_out_of_range_rejected(self) -> None:
        switch = Switch(interface_names=["FastEthernet0/1"])
        session = CliSession(registry=build_device_registry(), device=switch)
        self._enter_interface(session, "FastEthernet0/1")

        outcome = session.execute_line("switchport access vlan 9999")

        self.assertIsNotNone(outcome.error)

    def test_switchport_access_vlan_rejected_on_router_interface(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        session = CliSession(registry=build_device_registry(), device=router)
        self._enter_interface(session, "GigabitEthernet0/0")

        outcome = session.execute_line("switchport access vlan 10")

        self.assertIsNotNone(outcome.error)

    def test_switchport_mode_trunk_sets_real_interface_state(self) -> None:
        switch = Switch(interface_names=["GigabitEthernet0/1"])
        session = CliSession(registry=build_device_registry(), device=switch)
        self._enter_interface(session, "GigabitEthernet0/1")

        outcome = session.execute_line("switchport mode trunk")

        self.assertIsNone(outcome.error)
        self.assertEqual(switch.get_interface("GigabitEthernet0/1").switchport.mode, "trunk")

    def test_switchport_trunk_allowed_vlan_sets_real_interface_state(self) -> None:
        switch = Switch(interface_names=["GigabitEthernet0/1"])
        session = CliSession(registry=build_device_registry(), device=switch)
        self._enter_interface(session, "GigabitEthernet0/1")
        session.execute_line("switchport mode trunk")

        outcome = session.execute_line("switchport trunk allowed vlan 10,20,30")

        self.assertIsNone(outcome.error)
        self.assertEqual(
            switch.get_interface("GigabitEthernet0/1").switchport.trunk_allowed_vlans, {10, 20, 30}
        )

    def test_reconfiguring_a_port_changes_behavior_immediately(self) -> None:

        switch = Switch(interface_names=["FastEthernet0/1"])
        session = CliSession(registry=build_device_registry(), device=switch)
        self._enter_interface(session, "FastEthernet0/1")
        session.execute_line("switchport access vlan 10")
        self.assertEqual(switch.get_interface("FastEthernet0/1").switchport.access_vlan, 10)

        session.execute_line("switchport access vlan 30")
        self.assertEqual(switch.get_interface("FastEthernet0/1").switchport.access_vlan, 30)


class TestPingDerivesVlanBehaviorFromRealState(unittest.TestCase):
    """The capstone integration requirement: NetworkEngine.ping() must
    derive VLAN separation and same-VLAN connectivity purely from live
    switchport configuration - same subnet, same switch, only the
    VLAN assignment differs, and the outcome must flip correspondingly.
    No Layer 3 router is present in any of these scenarios, so success
    is only possible when Layer 2 genuinely connects the two hosts."""

    def _build(self):
        topology = Topology()
        pc1 = Host(hostname="PC1")
        pc2 = Host(hostname="PC2")
        switch = Switch(interface_names=["FastEthernet0/1", "FastEthernet0/2"])
        for d in (pc1, pc2, switch):
            topology.add_device(d)
        topology.connect(pc1.device_id, "Ethernet0", switch.device_id, "FastEthernet0/1")
        topology.connect(pc2.device_id, "Ethernet0", switch.device_id, "FastEthernet0/2")

        pc1.configure_ipv4("Ethernet0", "192.168.1.10", "255.255.255.0")
        pc2.configure_ipv4("Ethernet0", "192.168.1.20", "255.255.255.0")
        pc1.get_interface("Ethernet0").set_admin_up(True)
        pc2.get_interface("Ethernet0").set_admin_up(True)
        switch.get_interface("FastEthernet0/1").set_admin_up(True)
        switch.get_interface("FastEthernet0/2").set_admin_up(True)
        pc1.boot()
        pc2.boot()
        switch.boot()
        return topology, pc1, pc2, switch

    def test_same_vlan_pings_successfully(self) -> None:
        topology, pc1, pc2, switch = self._build()

        result = NetworkEngine(topology).ping(pc1.device_id, "192.168.1.20")
        self.assertTrue(result.success)

    def test_moving_destination_to_a_different_vlan_breaks_connectivity(self) -> None:
        topology, pc1, pc2, switch = self._build()
        engine = NetworkEngine(topology)
        self.assertTrue(engine.ping(pc1.device_id, "192.168.1.20").success)

        switch.get_interface("FastEthernet0/2").set_switchport_access_vlan(20)

        result = engine.ping(pc1.device_id, "192.168.1.20")
        self.assertFalse(result.success)
        self.assertIn(result.reason.name, ("ARP_UNRESOLVED", "NO_ROUTE"))

    def test_reconfiguring_back_to_the_same_vlan_restores_connectivity(self) -> None:

        topology, pc1, pc2, switch = self._build()
        engine = NetworkEngine(topology)
        switch.get_interface("FastEthernet0/2").set_switchport_access_vlan(20)
        self.assertFalse(engine.ping(pc1.device_id, "192.168.1.20").success)

        switch.get_interface("FastEthernet0/2").set_switchport_access_vlan(1)

        self.assertTrue(engine.ping(pc1.device_id, "192.168.1.20").success)

    def test_configured_live_through_the_cli_produces_the_same_result(self) -> None:

        topology, pc1, pc2, switch = self._build()
        engine = NetworkEngine(topology)
        self.assertTrue(engine.ping(pc1.device_id, "192.168.1.20").success)

        session = CliSession(registry=build_device_registry(), device=switch, network=engine)
        session.execute_line("enable")
        session.execute_line("configure terminal")
        session.execute_line("interface FastEthernet0/2")
        outcome = session.execute_line("switchport access vlan 20")
        self.assertIsNone(outcome.error)

        result = engine.ping(pc1.device_id, "192.168.1.20")
        self.assertFalse(result.success)


class TestVlanCapabilityThroughCli(unittest.TestCase):
    def test_vlan_command_creates_real_vlan_on_switch(self) -> None:
        switch = Switch()
        session = CliSession(registry=build_device_registry(), device=switch)
        session.execute_line("enable")
        session.execute_line("configure terminal")

        outcome = session.execute_line("vlan 100")

        self.assertIsNone(outcome.error)
        self.assertIn(100, switch.vlans)
        self.assertEqual(session.prompt(), "Switch(config-vlan)#")

    def test_vlan_command_rejected_on_router(self) -> None:
        router = Router()
        session = CliSession(registry=build_device_registry(), device=router)
        session.execute_line("enable")
        session.execute_line("configure terminal")

        outcome = session.execute_line("vlan 100")

        self.assertIsNotNone(outcome.error)

        self.assertEqual(session.prompt(), "Router(config)#")

    def test_vlan_command_rejected_on_host(self) -> None:
        host = Host()
        session = CliSession(registry=build_device_registry(), device=host)
        session.execute_line("enable")
        session.execute_line("configure terminal")

        outcome = session.execute_line("vlan 100")

        self.assertIsNotNone(outcome.error)


class TestFullWalkthrough(unittest.TestCase):
    """One end-to-end scenario mirroring the exact transcript from the
    Stage 3 brief."""

    def test_tehran_r1_wan_configuration(self) -> None:
        router = Router(hostname="Router", interface_names=["GigabitEthernet0/0"])
        session = CliSession(registry=build_device_registry(), device=router)

        for line in [
            "enable",
            "configure terminal",
            "hostname Tehran-R1",
            "interface GigabitEthernet0/0",
            "description WAN_TO_SHIRAZ",
            "ip address 10.0.0.1 255.255.255.252",
            "no shutdown",
        ]:
            outcome = session.execute_line(line)
            self.assertIsNone(outcome.error, msg=f"{line!r} -> {outcome.error}")

        iface = router.get_interface("GigabitEthernet0/0")
        self.assertEqual(router.hostname, "Tehran-R1")
        self.assertEqual(iface.description, "WAN_TO_SHIRAZ")
        self.assertEqual(iface.ipv4_address, "10.0.0.1")
        self.assertEqual(iface.ipv4_prefix_length, 30)
        self.assertTrue(iface.admin_up)

if __name__ == "__main__":
    unittest.main()
