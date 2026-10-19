"""The command abstraction.

A :class:`Command` is pure data plus a handler function - registering
one never requires touching :mod:`netsim.cli.registry`,
:mod:`netsim.cli.parser`, or :mod:`netsim.cli.session`. That is what
makes the command set extensible: new commands are new ``Command``
instances registered from anywhere (see
:mod:`netsim.cli.builtin_commands` for the pattern), never new branches
in the engine itself.

Handlers receive a :class:`CommandContext` and return a
:class:`CommandResult`. Handlers never touch the mode stack or history
directly - they *describe* what should happen (push this mode, print
this output, ...) and :class:`netsim.cli.session.CliSession` is the
only thing that actually applies it. This keeps handlers trivially
testable in isolation, with no session/terminal required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from netsim.cli.device_interface import DeviceContext
from netsim.cli.modes import CliMode, ModeContext
from netsim.cli.network_interface import NetworkContext
from netsim.cli.lab_interface import LabContext


@dataclass(frozen=True)
class Argument:
    """Declares one positional argument a command accepts.

    Args:
        name: Argument name, used in usage strings (e.g. ``<name>``)
            and as the key in :attr:`CommandContext.args`.
        validator: Optional callable that converts+validates the raw
            token, raising :class:`netsim.core.exceptions.ValidationError`
            on failure. Defaults to the identity function (any string
            is accepted as-is).
        required: Whether the argument must be supplied.
        help_text: Shown by the help system.
    """

    name: str
    validator: Callable[[str], Any] | None = None
    required: bool = True
    help_text: str = ""

    def validate(self, raw: str) -> Any:
        """Convert and validate a single raw token.

        Args:
            raw: The token as typed by the user.

        Returns:
            The validated (and possibly type-converted) value.

        Raises:
            netsim.core.exceptions.ValidationError: If ``raw`` is invalid.
        """
        if self.validator is None:
            return raw
        return self.validator(raw)


@dataclass(frozen=True)
class CommandResult:
    """What a command handler wants to happen next.

    Handlers build one of these and return it; they never mutate mode
    state or history themselves - only :class:`CliSession` interprets
    these fields and applies the effect. This keeps a handler a pure
    function of its :class:`CommandContext`, trivially unit-testable.

    Attributes:
        output: Lines of text to display to the user.
        mode_push: If set, the session should enter this mode next.
        mode_pop: If true, the session should leave the current mode
            (equivalent to a real ``exit``). If already at the base
            mode, the session interprets this as ending the CLI
            session rather than as an error.
        mode_pop_to_privileged: If true, collapse any config-mode
            nesting straight to PRIVILEGED_EXEC (equivalent to ``end``).
        should_exit_cli: If true, the session should terminate
            regardless of mode.
    """

    output: list[str] = field(default_factory=list)
    mode_push: ModeContext | None = None
    mode_pop: bool = False
    mode_pop_to_privileged: bool = False
    should_exit_cli: bool = False


@dataclass(frozen=True)
class CommandContext:
    """Everything a handler needs to do its job.

    Attributes:
        device: The current :class:`DeviceContext`, or ``None`` if no
            device is attached to this session. Handlers must never
            reach for anything about a device except through this
            object.
        args: Validated argument values, keyed by :class:`Argument` name.
        raw_tokens: The full, unmodified token sequence the user typed.
        history: A read-only snapshot of prior command-line entries,
            most-recent-last, for commands like ``show history``.
        mode_params: The current mode's params (see
            :class:`netsim.cli.modes.ModeContext`), e.g.
            ``{"interface": "GigabitEthernet0/0"}`` while in
            INTERFACE_CONFIG. Opaque to the engine itself - only
            handlers that know what a given mode's params mean (e.g.
            an interface-config command) interpret them.
        network: The current :class:`~netsim.cli.network_interface.NetworkContext`,
            or ``None`` if no network engine is attached to this
            session. Handlers must never reach for topology/ARP/
            routing state except through this object.
    """

    device: DeviceContext | None
    args: dict[str, Any]
    raw_tokens: tuple[str, ...]
    history: tuple[str, ...] = ()
    mode_params: Mapping[str, str] = field(default_factory=dict)
    network: NetworkContext | None = None
    workspace: LabContext | None = None

CommandHandler = Callable[[CommandContext], CommandResult]


@dataclass(frozen=True)
class Command:
    """A single CLI command definition.

    Attributes:
        name: Canonical, space-separated command name, e.g.
            ``"configure terminal"``. Words are matched independently
            for IOS-style abbreviation (see :mod:`netsim.cli.registry`).
        handler: Called with a populated :class:`CommandContext` when
            this command is resolved and its arguments validated.
        allowed_modes: The set of :class:`CliMode` values this command
            may be run from.
        aliases: Alternate, fully-distinct names for this command
            (e.g. ``"quit"`` for ``"exit"``). Not needed for simple
            abbreviations - those are handled automatically - only for
            genuinely different wording.
        arguments: Positional arguments this command accepts, in order.
        help_text: One-line description shown by ``?`` / ``help``.
        hidden: If true, excluded from help listings (still resolvable
            if typed in full - useful for diagnostic/internal commands).
    """

    name: str
    handler: CommandHandler
    allowed_modes: frozenset[CliMode]
    aliases: tuple[str, ...] = ()
    arguments: tuple[Argument, ...] = ()
    help_text: str = ""
    hidden: bool = False

    @property
    def name_tokens(self) -> tuple[str, ...]:
        """The canonical name split into words."""
        return tuple(self.name.split())

    def all_name_variants(self) -> tuple[str, ...]:
        """Canonical name followed by all aliases."""
        return (self.name, *self.aliases)

    def usage(self) -> str:
        """Render a usage string, e.g. ``"ip address <ip> <mask> [secondary]"``."""
        parts = [self.name]
        for argument in self.arguments:
            if argument.required:
                parts.append(f"<{argument.name}>")
            else:
                parts.append(f"[{argument.name}]")
        return " ".join(parts)
