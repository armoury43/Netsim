"""Tests for the Stage 7 ACL additions to netsim.devices.router.Router.

test_router.py/test_router_stage4.py/test_router_stage6.py are all
untouched. Covers: ACL storage, per-interface/direction application,
and save/reload persistence (same pattern as static routes/RIP config).
"""

from __future__ import annotations

import unittest

from netsim.core.exceptions import ValidationError
from netsim.devices.errors import InterfaceNotFoundError
from netsim.devices.router import Router


class TestAccessListStorage(unittest.TestCase):
    def test_get_or_create_access_list_creates_a_new_one(self) -> None:
        router = Router()
        acl = router.get_or_create_access_list(1)
        self.assertEqual(acl.number, 1)
        self.assertIn(1, router.access_lists)

    def test_get_or_create_access_list_returns_existing_one(self) -> None:
        router = Router()
        first = router.get_or_create_access_list(1)
        second = router.get_or_create_access_list(1)
        self.assertIs(first, second)

    def test_access_lists_property_is_read_only(self) -> None:
        router = Router()
        with self.assertRaises(TypeError):
            router.access_lists[1] = None


class TestInterfaceAclApplication(unittest.TestCase):
    def test_no_acl_applied_by_default(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        self.assertIsNone(router.get_interface_acl("GigabitEthernet0/0", "in"))
        self.assertIsNone(router.get_interface_acl("GigabitEthernet0/0", "out"))

    def test_set_interface_acl_inbound(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.get_or_create_access_list(1)
        router.set_interface_acl("GigabitEthernet0/0", "in", 1)

        acl = router.get_interface_acl("GigabitEthernet0/0", "in")
        assert acl is not None
        self.assertEqual(acl.number, 1)

    def test_set_interface_acl_outbound_independent_of_inbound(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.get_or_create_access_list(1)
        router.get_or_create_access_list(2)
        router.set_interface_acl("GigabitEthernet0/0", "in", 1)
        router.set_interface_acl("GigabitEthernet0/0", "out", 2)

        self.assertEqual(router.get_interface_acl("GigabitEthernet0/0", "in").number, 1)
        self.assertEqual(router.get_interface_acl("GigabitEthernet0/0", "out").number, 2)

    def test_set_interface_acl_on_unknown_interface_raises(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.get_or_create_access_list(1)
        with self.assertRaises(InterfaceNotFoundError):
            router.set_interface_acl("GigabitEthernet9/9", "in", 1)

    def test_remove_interface_acl(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.get_or_create_access_list(1)
        router.set_interface_acl("GigabitEthernet0/0", "in", 1)
        router.remove_interface_acl("GigabitEthernet0/0", "in")
        self.assertIsNone(router.get_interface_acl("GigabitEthernet0/0", "in"))


class TestAclSurvivesSaveAndReload(unittest.TestCase):
    def test_saved_acl_and_application_survive_reload(self) -> None:
        import ipaddress

        from netsim.devices.acl import AclRule

        router = Router(interface_names=["GigabitEthernet0/0"])
        acl = router.get_or_create_access_list(1)
        acl.add_rule(AclRule(action="deny", source_network=ipaddress.ip_network("10.0.0.0/24")))
        router.set_interface_acl("GigabitEthernet0/0", "in", 1)
        router.save_config()

        router.remove_interface_acl("GigabitEthernet0/0", "in")
        router.reload()

        restored_acl = router.get_interface_acl("GigabitEthernet0/0", "in")
        assert restored_acl is not None
        self.assertEqual(restored_acl.number, 1)
        self.assertFalse(restored_acl.evaluate("10.0.0.5"))

    def test_unsaved_acl_is_discarded_on_reload(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.save_config()
        router.get_or_create_access_list(1)
        router.set_interface_acl("GigabitEthernet0/0", "in", 1)

        router.reload()

        self.assertEqual(dict(router.access_lists), {})
        self.assertIsNone(router.get_interface_acl("GigabitEthernet0/0", "in"))

    def test_unsaved_rule_added_to_existing_acl_is_discarded_on_reload(self) -> None:
        import ipaddress

        from netsim.devices.acl import AclRule

        router = Router(interface_names=["GigabitEthernet0/0"])
        acl = router.get_or_create_access_list(1)
        acl.add_rule(AclRule(action="deny", source_network=ipaddress.ip_network("10.0.0.0/24")))
        router.set_interface_acl("GigabitEthernet0/0", "in", 1)
        router.save_config()

        router.add_access_list_rule(1, "permit", "any")
        self.assertTrue(acl.evaluate("192.168.1.1"))

        router.reload()

        restored = router.access_lists[1]
        self.assertEqual(len(restored.rules()), 1)
        self.assertFalse(restored.evaluate("192.168.1.1"))

    def test_edits_after_reload_do_not_mutate_startup_acl_snapshot(self) -> None:
        import ipaddress

        from netsim.devices.acl import AclRule

        router = Router(interface_names=["GigabitEthernet0/0"])
        acl = router.get_or_create_access_list(1)
        acl.add_rule(AclRule(action="deny", source_network=ipaddress.ip_network("10.0.0.0/24")))
        router.save_config()
        router.reload()

        router.add_access_list_rule(1, "permit", "any")
        router.reload()

        self.assertEqual(len(router.access_lists[1].rules()), 1)
        self.assertFalse(router.access_lists[1].evaluate("192.168.1.1"))

    def test_acl_coexists_with_static_routes_and_rip_across_reload(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.add_static_route("192.168.9.0", "255.255.255.0", "10.0.0.9")
        router.enable_rip("10.0.0.0", "255.0.0.0")
        router.get_or_create_access_list(1)
        router.set_interface_acl("GigabitEthernet0/0", "in", 1)
        router.save_config()

        router.reload()

        self.assertIn("192.168.9.0/24", router.static_routes)
        self.assertIn("10.0.0.0/8", {str(n) for n in router.rip_networks})
        self.assertIsNotNone(router.get_interface_acl("GigabitEthernet0/0", "in"))


class TestAddAccessListRule(unittest.TestCase):
    """Router.add_access_list_rule is the CLI-facing convenience
    method (primitive string args, real validation) - the same
    pattern as add_static_route/enable_rip."""

    def test_permit_rule_with_network_and_mask(self) -> None:
        router = Router()
        router.add_access_list_rule(1, "permit", "10.0.0.0", "255.0.0.0")

        acl = router.access_lists[1]
        self.assertTrue(acl.evaluate("10.0.0.5"))
        self.assertFalse(acl.evaluate("192.168.1.1"))

    def test_deny_rule_with_network_and_mask(self) -> None:
        router = Router()
        router.add_access_list_rule(1, "deny", "10.0.0.0", "255.0.0.0")
        router.add_access_list_rule(1, "permit", "0.0.0.0", "0.0.0.0")

        acl = router.access_lists[1]
        self.assertFalse(acl.evaluate("10.0.0.5"))
        self.assertTrue(acl.evaluate("192.168.1.1"))

    def test_any_keyword_matches_everything(self) -> None:
        router = Router()
        router.add_access_list_rule(1, "permit", "any")

        acl = router.access_lists[1]
        self.assertTrue(acl.evaluate("10.0.0.5"))
        self.assertTrue(acl.evaluate("192.168.1.1"))

    def test_invalid_action_rejected(self) -> None:
        router = Router()
        with self.assertRaises(ValidationError):
            router.add_access_list_rule(1, "allow", "any")

    def test_missing_mask_without_any_keyword_rejected(self) -> None:
        router = Router()
        with self.assertRaises(ValidationError):
            router.add_access_list_rule(1, "permit", "10.0.0.0")

    def test_malformed_mask_rejected(self) -> None:
        router = Router()
        with self.assertRaises(ValidationError):
            router.add_access_list_rule(1, "permit", "10.0.0.0", "not-a-mask")

    def test_malformed_ipv4_network_rejected_as_validation_error(self) -> None:
        router = Router()
        with self.assertRaises(ValidationError):
            router.add_access_list_rule(1, "permit", "999.1.2.3", "255.255.255.0")

    def test_ipv6_network_rejected_as_validation_error(self) -> None:
        router = Router()
        with self.assertRaises(ValidationError):
            router.add_access_list_rule(1, "permit", "2001:db8::1", "64")

    def test_any_does_not_accept_an_extra_mask(self) -> None:
        router = Router()
        with self.assertRaises(ValidationError):
            router.add_access_list_rule(1, "permit", "any", "255.255.255.0")

    def test_multiple_rules_accumulate_in_order(self) -> None:
        router = Router()
        router.add_access_list_rule(1, "deny", "10.0.0.0", "255.0.0.0")
        router.add_access_list_rule(1, "permit", "any")

        acl = router.access_lists[1]
        self.assertEqual(len(acl.rules()), 2)
        self.assertEqual(acl.rules()[0].action, "deny")
        self.assertEqual(acl.rules()[1].action, "permit")


class TestInterfaceAclDirectionValidation(unittest.TestCase):
    def test_set_interface_acl_rejects_invalid_direction(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.get_or_create_access_list(1)
        with self.assertRaises(ValidationError):
            router.set_interface_acl("GigabitEthernet0/0", "sideways", 1)

    def test_valid_directions_still_work(self) -> None:
        router = Router(interface_names=["GigabitEthernet0/0"])
        router.get_or_create_access_list(1)
        router.set_interface_acl("GigabitEthernet0/0", "in", 1)
        router.set_interface_acl("GigabitEthernet0/0", "out", 1)

if __name__ == "__main__":
    unittest.main()


class TestAclNumberValidation(unittest.TestCase):
    def test_access_list_number_range_is_enforced(self) -> None:
        router = Router()
        with self.assertRaises(ValidationError):
            router.get_or_create_access_list(100)
        with self.assertRaises(ValidationError):
            router.set_interface_acl("GigabitEthernet0/0", "in", 0)
