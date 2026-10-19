"""Command-line interface primitives and public integration protocols.

The package separates command definitions, mode state, parsing, registry
resolution, validation, history, completion, and terminal I/O. Device,
network, and lab behavior is accessed through structural protocols so the
CLI remains a front end rather than a second implementation of the backend.
"""

from netsim.cli.command import Argument, Command, CommandContext, CommandResult
from netsim.cli.device_interface import (
    DeviceContext,
    FullDeviceContext,
    InterfaceContext,
    MacTableCapableDeviceContext,
    StaticRoutingCapableDeviceContext,
    VlanCapableDeviceContext,
)
from netsim.cli.history import CommandHistory
from netsim.cli.modes import CliMode, ModeContext, ModeStack
from netsim.cli.network_interface import NetworkContext, PingResultContext
from netsim.cli.registry import CommandRegistry
from netsim.cli.session import CliSession, ExecutionOutcome

__all__ = [
    "Argument",
    "Command",
    "CommandContext",
    "CommandResult",
    "DeviceContext",
    "FullDeviceContext",
    "InterfaceContext",
    "MacTableCapableDeviceContext",
    "StaticRoutingCapableDeviceContext",
    "VlanCapableDeviceContext",
    "NetworkContext",
    "PingResultContext",
    "CommandHistory",
    "CliMode",
    "ModeContext",
    "ModeStack",
    "CommandRegistry",
    "CliSession",
    "ExecutionOutcome",
]
