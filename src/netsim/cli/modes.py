"""Mode state machine for the CLI.

Network operating systems expose configuration through a hierarchy of
modes (``Router>`` -> ``Router#`` -> ``Router(config)#`` -> ...). This
module owns that hierarchy and nothing else: it has no idea what a
"command" is, only how modes relate to each other and how to render a
prompt suffix for the current mode. :mod:`netsim.cli.session` is the
only thing that decides *when* to push/pop, based on what a command
handler asked for.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from types import MappingProxyType
from typing import Mapping

from netsim.cli.errors import ModeStackError


class CliMode(Enum):
    """The six modes the CLI engine supports."""

    USER_EXEC = auto()
    PRIVILEGED_EXEC = auto()
    GLOBAL_CONFIG = auto()
    INTERFACE_CONFIG = auto()
    ROUTER_CONFIG = auto()
    VLAN_CONFIG = auto()

_PROMPT_SUFFIX: Mapping[CliMode, str] = MappingProxyType(
    {
        CliMode.USER_EXEC: ">",
        CliMode.PRIVILEGED_EXEC: "#",
        CliMode.GLOBAL_CONFIG: "(config)#",
        CliMode.INTERFACE_CONFIG: "(config-if)#",
        CliMode.ROUTER_CONFIG: "(config-router)#",
        CliMode.VLAN_CONFIG: "(config-vlan)#",
    }
)

_ALLOWED_TRANSITIONS: Mapping[CliMode, frozenset[CliMode]] = MappingProxyType(
    {
        CliMode.USER_EXEC: frozenset({CliMode.PRIVILEGED_EXEC}),
        CliMode.PRIVILEGED_EXEC: frozenset({CliMode.GLOBAL_CONFIG}),
        CliMode.GLOBAL_CONFIG: frozenset(
            {CliMode.INTERFACE_CONFIG, CliMode.ROUTER_CONFIG, CliMode.VLAN_CONFIG}
        ),
        CliMode.INTERFACE_CONFIG: frozenset(),
        CliMode.ROUTER_CONFIG: frozenset(),
        CliMode.VLAN_CONFIG: frozenset(),
    }
)


@dataclass(frozen=True)
class ModeContext:
    """A single entry on the mode stack.

    Attributes:
        mode: Which :class:`CliMode` this entry represents.
        params: Mode-specific context, e.g. ``{"interface": "Gi0/0"}``
            for :attr:`CliMode.INTERFACE_CONFIG`. Opaque to the mode
            stack itself; commands and the device layer interpret it.
    """

    mode: CliMode
    params: Mapping[str, str] = field(default_factory=dict)


class ModeStack:
    """Tracks the current mode nesting for one CLI session.

    Always starts in :attr:`CliMode.USER_EXEC` and enforces that modes
    are only entered via a valid parent -> child transition (you can't
    jump straight from ``USER_EXEC`` to ``GLOBAL_CONFIG``, for
    instance) - matching real network OS behavior.
    """

    def __init__(self) -> None:
        self._stack: list[ModeContext] = [ModeContext(mode=CliMode.USER_EXEC)]

    @property
    def current(self) -> ModeContext:
        """The :class:`ModeContext` at the top of the stack."""
        return self._stack[-1]

    def at_base_mode(self) -> bool:
        """True if no mode has been entered beyond the initial USER_EXEC."""
        return len(self._stack) == 1

    def push(self, context: ModeContext) -> None:
        """Enter a new mode as a child of the current one.

        Args:
            context: The mode (and its params) to enter.

        Raises:
            ModeStackError: If ``context.mode`` is not a valid child of
                the current mode.
        """
        allowed = _ALLOWED_TRANSITIONS.get(self.current.mode, frozenset())
        if context.mode not in allowed:
            raise ModeStackError(
                f"Cannot enter {context.mode.name} from {self.current.mode.name}"
            )
        self._stack.append(context)

    def pop(self) -> ModeContext:
        """Leave the current mode, returning to its parent.

        Returns:
            The :class:`ModeContext` that was popped.

        Raises:
            ModeStackError: If already at the base mode (USER_EXEC) -
                there is nothing left to pop to; the caller (session)
                is expected to treat that as "exit the CLI" instead.
        """
        if self.at_base_mode():
            raise ModeStackError("Cannot exit the base mode")
        return self._stack.pop()

    def pop_to_privileged(self) -> None:
        """Collapse any config-mode nesting straight to PRIVILEGED_EXEC.

        Mirrors the real-world ``end`` command / Ctrl-Z.

        Raises:
            ModeStackError: If called from USER_EXEC (there is no
                privileged mode to return to).
        """
        if self.current.mode is CliMode.USER_EXEC:
            raise ModeStackError("Cannot return to privileged EXEC from user EXEC")
        while self.current.mode is not CliMode.PRIVILEGED_EXEC:
            self._stack.pop()

    def reset(self) -> None:
        """Return all the way to USER_EXEC, discarding all nested modes."""
        self._stack = [ModeContext(mode=CliMode.USER_EXEC)]

    def prompt_suffix(self) -> str:
        """The prompt suffix (e.g. ``"(config-if)#"``) for the current mode."""
        return _PROMPT_SUFFIX[self.current.mode]
