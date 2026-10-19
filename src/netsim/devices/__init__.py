"""Virtual device models: Router, Switch, Host.

Layering: :mod:`~netsim.devices.types` (DeviceType) and
:mod:`~netsim.devices.state` (DeviceState) are the shared vocabulary.
:mod:`~netsim.devices.addressing` wraps stdlib :mod:`ipaddress` for
IPv4 validation. :mod:`~netsim.devices.interface` (Interface,
SwitchportConfig) and :mod:`~netsim.devices.configuration`
(ConfigSnapshot, render_config_text) are used by
:mod:`~netsim.devices.base` (the ``Device`` base class), which
:mod:`~netsim.devices.router`, :mod:`~netsim.devices.switch`, and
:mod:`~netsim.devices.host` subclass. :mod:`~netsim.devices.errors`
holds the exception hierarchy, all under
:class:`netsim.core.exceptions.DeviceError`.

Nothing in this package imports from :mod:`netsim.cli` - devices are
usable completely headlessly. The only place the two packages meet is
:mod:`netsim.cli.device_interface`'s structural protocols, satisfied
here without any import in either direction.
"""

from netsim.devices.addressing import parse_ipv4_address, parse_ipv4_mask
from netsim.devices.base import Device
from netsim.devices.configuration import ConfigSnapshot, render_config_text
from netsim.devices.errors import (
    DuplicateInterfaceError,
    DuplicateIPAddressError,
    InterfaceNotFoundError,
    InvalidLifecycleTransitionError,
    UnsupportedCapabilityError,
)
from netsim.devices.host import Host
from netsim.devices.interface import Interface, SwitchportConfig
from netsim.devices.router import Router
from netsim.devices.state import DeviceState
from netsim.devices.switch import Switch, Vlan
from netsim.devices.types import DeviceType

__all__ = [
    "parse_ipv4_address",
    "parse_ipv4_mask",
    "Device",
    "ConfigSnapshot",
    "render_config_text",
    "DuplicateInterfaceError",
    "DuplicateIPAddressError",
    "InterfaceNotFoundError",
    "InvalidLifecycleTransitionError",
    "UnsupportedCapabilityError",
    "Host",
    "Interface",
    "SwitchportConfig",
    "Router",
    "DeviceState",
    "Switch",
    "Vlan",
    "DeviceType",
]
