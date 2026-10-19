"""Standard access control lists.

Deliberately "standard" ACL semantics only - source-IP-based filtering,
matching numbered ACLs 1-99 in real IOS. Extended ACLs (destination
IP, protocol, port filtering) are a natural extension once this
project models TCP/UDP - filtering on protocol/port before those exist
would just be unused surface area.

Evaluation semantics: rules are checked in the order they were added,
and the first matching rule decides the outcome. To avoid accidentally
blocking all traffic when an ACL is applied before rules are configured,
an empty ACL permits traffic; once at least one rule exists, any source
not matched by a rule is denied by the implicit deny at the end.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Literal

ANY_NETWORK = ipaddress.ip_network("0.0.0.0/0")


@dataclass(frozen=True)
class AclRule:
    """A single ACL rule.

    Attributes:
        action: ``"permit"`` or ``"deny"``.
        source_network: The source network this rule matches. Use
            :data:`ANY_NETWORK` for the ``any`` keyword.
    """

    action: Literal["permit", "deny"]
    source_network: ipaddress.IPv4Network

    def matches(self, source_ip: str) -> bool:
        """Whether this rule's network covers ``source_ip``."""
        return ipaddress.ip_address(source_ip) in self.source_network


class AccessList:
    """An ordered, numbered list of :class:`AclRule` entries.

    Args:
        number: The ACL's number (1-99 for standard ACLs, matching
            real IOS numbering, though not enforced here - a later
            stage introducing named/extended ACLs can widen this
            without changing evaluation semantics).
    """

    def __init__(self, number: int) -> None:
        self.number = number
        self._rules: list[AclRule] = []

    def add_rule(self, rule: AclRule) -> None:
        """Append a rule to the end of the list (rules are evaluated in order)."""
        self._rules.append(rule)

    def rules(self) -> list[AclRule]:
        """Every rule currently in the list, in evaluation order."""
        return list(self._rules)

    def evaluate(self, source_ip: str) -> bool:
        """Whether ``source_ip`` is permitted by this access list.

        Matches real IOS precisely, including an easy-to-miss nuance:
        an access list with *zero* rules ever added to it (e.g.
        referenced by ``ip access-group`` before any ``access-list``
        statement was configured for that number) applies no
        filtering at all - everything is permitted. The implicit deny
        only activates once at least one real rule exists; it is the
        fallback for "nothing matched", not the default for "nothing
        was ever configured".

        Args:
            source_ip: The source address being checked.

        Returns:
            ``True`` if permitted, ``False`` if denied.
        """
        if not self._rules:
            return True
        for rule in self._rules:
            if rule.matches(source_ip):
                return rule.action == "permit"
        return False
