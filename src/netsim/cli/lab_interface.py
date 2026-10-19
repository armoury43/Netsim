"""Structural boundary between CLI handlers and the lab/workspace layer."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Protocol, runtime_checkable

from netsim.cli.device_interface import DeviceContext
from netsim.cli.network_interface import NetworkContext


@runtime_checkable
class LabCheckContext(Protocol):
    """Fields displayed by ``lab verify`` for a single check."""

    @property
    def name(self) -> str: ...

    @property
    def passed(self) -> bool: ...

    @property
    def detail(self) -> str: ...


@runtime_checkable
class LabReportContext(Protocol):
    """Fields displayed by the CLI from a verification report."""

    @property
    def passed(self) -> bool: ...

    @property
    def passed_count(self) -> int: ...

    @property
    def checks(self) -> tuple[LabCheckContext, ...]: ...


@runtime_checkable
class LabContext(NetworkContext, Protocol):
    """Minimum workspace API used by lab-management CLI commands.

    Device and network implementation details stay outside the CLI. A GUI,
    scripted frontend, or test fake can implement this protocol without
    inheriting from the concrete LabWorkspace class.
    """

    @property
    def active_device(self) -> DeviceContext | None: ...

    @property
    def name(self) -> str: ...

    def resolve_device(self, reference: str) -> DeviceContext: ...

    def select_device(self, reference: str) -> DeviceContext: ...

    def create_device(
        self, device_type: str, hostname: str, interface_names: Iterable[str] | None = None
    ) -> DeviceContext: ...

    def remove_device(self, reference: str) -> DeviceContext: ...

    def connect(
        self, device_a: str, interface_a: str, device_b: str, interface_b: str
    ) -> object: ...

    def disconnect(self, device_reference: str, interface_name: str) -> bool: ...

    def set_link_state(self, device_reference: str, interface_name: str, up: bool) -> None: ...

    def devices_summary(self) -> list[str]: ...

    def topology_summary(self) -> list[str]: ...

    def save(self, path: str | Path) -> Path: ...

    def load(self, path: str | Path) -> Path: ...

    def reset(self) -> None: ...

    def load_scenario(self, scenario_id: str) -> str: ...

    def verify(self) -> LabReportContext: ...
