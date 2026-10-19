"""Tests for netsim.devices.acl.

Standard ACL semantics only (source-IP based filtering) - matches the
project's current ICMP-only protocol support. Extended ACLs
(protocol/port filtering) are a natural extension once TCP/UDP exist.
"""

from __future__ import annotations

import unittest

from netsim.devices.acl import ANY_NETWORK, AccessList, AclRule


class TestAclRule(unittest.TestCase):
    def test_permit_rule_matches_covered_address(self) -> None:
        rule = AclRule(action="permit", source_network=ANY_NETWORK)
        self.assertTrue(rule.matches("10.0.0.1"))

    def test_rule_does_not_match_address_outside_its_network(self) -> None:
        import ipaddress

        rule = AclRule(action="permit", source_network=ipaddress.ip_network("10.0.0.0/24"))
        self.assertFalse(rule.matches("192.168.1.1"))


class TestAccessListEvaluation(unittest.TestCase):
    def test_empty_access_list_permits_everything_no_filtering_configured(self) -> None:

        acl = AccessList(number=1)
        self.assertTrue(acl.evaluate("10.0.0.1"))

    def test_single_permit_rule_allows_matching_source(self) -> None:
        acl = AccessList(number=1)
        acl.add_rule(AclRule(action="permit", source_network=ANY_NETWORK))
        self.assertTrue(acl.evaluate("10.0.0.1"))

    def test_single_deny_rule_blocks_matching_source(self) -> None:
        import ipaddress

        acl = AccessList(number=1)
        acl.add_rule(AclRule(action="deny", source_network=ipaddress.ip_network("10.0.0.0/24")))
        self.assertFalse(acl.evaluate("10.0.0.5"))

    def test_first_match_wins(self) -> None:
        import ipaddress

        acl = AccessList(number=1)
        acl.add_rule(AclRule(action="deny", source_network=ipaddress.ip_network("10.0.0.0/24")))
        acl.add_rule(AclRule(action="permit", source_network=ANY_NETWORK))

        self.assertFalse(acl.evaluate("10.0.0.5"))

        self.assertTrue(acl.evaluate("192.168.1.1"))

    def test_implicit_deny_at_end_when_nothing_matches(self) -> None:
        import ipaddress

        acl = AccessList(number=1)
        acl.add_rule(AclRule(action="permit", source_network=ipaddress.ip_network("10.0.0.0/24")))
        self.assertFalse(acl.evaluate("192.168.1.1"))

    def test_rules_property_reflects_insertion_order(self) -> None:
        import ipaddress

        acl = AccessList(number=1)
        rule_a = AclRule(action="deny", source_network=ipaddress.ip_network("10.0.0.0/24"))
        rule_b = AclRule(action="permit", source_network=ANY_NETWORK)
        acl.add_rule(rule_a)
        acl.add_rule(rule_b)
        self.assertEqual(acl.rules(), [rule_a, rule_b])

if __name__ == "__main__":
    unittest.main()
