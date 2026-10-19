"""Shared application wiring for the terminal and graphical front-ends.

This module is the composition root: it connects the device, topology,
network, CLI, and lab packages without making those lower-level packages
depend on an application entry point.
"""

from __future__ import annotations

from dataclasses import dataclass

from netsim.cli.device_commands import build_device_registry
from netsim.cli.lab_commands import register_lab_commands
from netsim.cli.network_commands import register_network_commands
from netsim.cli.registry import CommandRegistry
from netsim.cli.session import CliSession
from netsim.devices.base import Device
from netsim.devices.host import Host
from netsim.devices.router import Router
from netsim.labs.workspace import LabWorkspace
from netsim.network.topology import Topology


@dataclass
class NetsimRuntime:
    """A fully wired application runtime shared by front-ends."""

    workspace: LabWorkspace
    session: CliSession
    registry: CommandRegistry


def build_default_topology() -> tuple[Topology, Router]:
    """Build a useful starter network: one router and one directly connected host."""
    topology = Topology()
    router = Router(interface_names=["GigabitEthernet0/0", "GigabitEthernet0/1"])
    host = Host(hostname="PC1")
    topology.add_device(router)
    topology.add_device(host)
    topology.connect(router.device_id, "GigabitEthernet0/0", host.device_id, "Ethernet0")
    router.configure_ipv4("GigabitEthernet0/0", "10.0.0.1", "255.255.255.0")
    host.configure_ipv4("Ethernet0", "10.0.0.2", "255.255.255.0")
    router.get_interface("GigabitEthernet0/0").set_admin_up(True)
    host.get_interface("Ethernet0").set_admin_up(True)
    router.boot()
    host.boot()
    return topology, router


def build_runtime(
    *,
    topology: Topology | None = None,
    active_device: Device | None = None,
    name: str = "Starter Lab",
) -> NetsimRuntime:
    """Wire a workspace, command registry, and CLI session.

    If no topology is provided, the default router-to-host example is built.
    GUI users and terminal users therefore start with the exact same backend.
    """
    if topology is None:
        topology, default_device = build_default_topology()
        if active_device is None:
            active_device = default_device
    workspace = LabWorkspace(topology=topology, active_device=active_device, name=name)
    registry = build_device_registry()
    register_network_commands(registry)
    register_lab_commands(registry)
    session = CliSession(
        registry=registry,
        device=workspace.active_device,
        network=workspace,
        workspace=workspace,
    )
    return NetsimRuntime(workspace=workspace, session=session, registry=registry)
