"""Core engine primitives: configuration, logging, events, exceptions.

Nothing in ``netsim.core`` may import from ``netsim.cli``,
``netsim.devices``, ``netsim.network``, ``netsim.labs``, or
``netsim.gui`` — this package sits at the bottom of the dependency
graph and everything else depends on it, never the other way around.
"""

from netsim.core.config import Settings, ThemeSettings, load_settings, save_settings
from netsim.core.events import Event, EventBus
from netsim.core.exceptions import (
    CommandError,
    ConfigDirectoryError,
    ConfigurationError,
    DeviceError,
    LabError,
    NetsimError,
    NetworkSimulationError,
    ValidationError,
)
from netsim.core.logging_config import configure_logging, get_logger

__all__ = [
    "Settings",
    "ThemeSettings",
    "load_settings",
    "save_settings",
    "Event",
    "EventBus",
    "NetsimError",
    "ConfigurationError",
    "ConfigDirectoryError",
    "ValidationError",
    "CommandError",
    "DeviceError",
    "NetworkSimulationError",
    "LabError",
    "configure_logging",
    "get_logger",
]
