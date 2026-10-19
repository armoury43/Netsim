"""Built-in teaching scenarios for the lab workspace.

Scenario setup is ordinary model-building code: it uses the same Device,
Topology, and NetworkEngine APIs as tests and external front-ends. Checks
are kept separate from the setup so learners can be given an unfinished
network and can run verification after working through the task.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from netsim.core.exceptions import NetsimError
from netsim.devices.host import Host
from netsim.devices.switch import Switch
from netsim.labs.verification import LabCheckResult
from netsim.network.topology import Topology

if TYPE_CHECKING:
    from netsim.labs.workspace import LabWorkspace


@dataclass(frozen=True)
class LabScenario:
    """A built-in topology exercise and its verification rules."""

    scenario_id: str
    title: str
    description: str
    task: str
    start_device_hostname: str
    builder: Callable[[], Topology]
    verifier: Callable[["LabWorkspace"], tuple[LabCheckResult, ...]]


def _build_basic_lan() -> Topology:
    topology = Topology()
    pc1 = Host(hostname="PC1")
    pc2 = Host(hostname="PC2")
    switch = Switch(hostname="SW1")
    topology.add_device(pc1)
    topology.add_device(pc2)
    topology.add_device(switch)
    topology.connect(pc1.device_id, "Ethernet0", switch.device_id, "FastEthernet0/1")
    topology.connect(pc2.device_id, "Ethernet0", switch.device_id, "FastEthernet0/2")

    for device in topology.devices().values():
        device.boot()
    return topology


def _build_vlan_isolation() -> Topology:
    topology = _build_basic_lan()
    switch = next(device for device in topology.devices().values() if isinstance(device, Switch))
    switch.get_or_create_vlan(10, "USERS")
    switch.get_or_create_vlan(20, "GUESTS")
    switch.get_interface("FastEthernet0/1").set_switchport_access_vlan(10)
    switch.get_interface("FastEthernet0/2").set_switchport_access_vlan(20)
    return topology


def _device(workspace: "LabWorkspace", hostname: str):
    return workspace.resolve_device(hostname)


def _check_basic_lan(workspace: "LabWorkspace") -> tuple[LabCheckResult, ...]:
    checks: list[LabCheckResult] = []
    expected = {"PC1": "192.168.10.11", "PC2": "192.168.10.12"}
    for hostname, address in expected.items():
        try:
            host = _device(workspace, hostname)
            iface = host.get_interface("Ethernet0")
            checks.append(
                LabCheckResult(
                    name=f"{hostname} IPv4 address",
                    passed=iface.ipv4_address == address and iface.ipv4_prefix_length == 24,
                    detail=(
                        f"configured {iface.ipv4_address}/{iface.ipv4_prefix_length}"
                        if iface.ipv4_address is not None
                        else "IPv4 address is not configured"
                    ),
                )
            )
            checks.append(
                LabCheckResult(
                    name=f"{hostname} interface enabled",
                    passed=iface.admin_up,
                    detail="interface is up" if iface.admin_up else "interface is administratively down",
                )
            )
        except (NetsimError, KeyError, ValueError, AttributeError) as exc:
            checks.append(LabCheckResult(f"{hostname} configuration", False, str(exc)))

    try:
        switch = _device(workspace, "SW1")
        for interface_name in ("FastEthernet0/1", "FastEthernet0/2"):
            iface = switch.get_interface(interface_name)
            checks.append(
                LabCheckResult(
                    name=f"SW1 {interface_name} enabled",
                    passed=iface.admin_up,
                    detail="switchport is up" if iface.admin_up else "switchport is administratively down",
                )
            )
    except Exception as exc:
        checks.append(LabCheckResult("SW1 switchports", False, str(exc)))

    try:
        result = workspace.ping(_device(workspace, "PC1").device_id, expected["PC2"])
        checks.append(
            LabCheckResult(
                name="PC1 can ping PC2",
                passed=result.success,
                detail="ICMP echo succeeded" if result.success else (result.detail or "ICMP echo failed"),
            )
        )
    except Exception as exc:
        checks.append(LabCheckResult("PC1 can ping PC2", False, str(exc)))
    return tuple(checks)


def _check_vlan_isolation(workspace: "LabWorkspace") -> tuple[LabCheckResult, ...]:
    checks: list[LabCheckResult] = []
    expected = {"PC1": "192.168.10.11", "PC2": "192.168.10.12"}
    for hostname, address in expected.items():
        try:
            host = _device(workspace, hostname)
            iface = host.get_interface("Ethernet0")
            checks.append(
                LabCheckResult(
                    name=f"{hostname} IPv4 address",
                    passed=iface.ipv4_address == address and iface.ipv4_prefix_length == 24,
                    detail=(
                        f"configured {iface.ipv4_address}/{iface.ipv4_prefix_length}"
                        if iface.ipv4_address is not None
                        else "IPv4 address is not configured"
                    ),
                )
            )
            checks.append(
                LabCheckResult(
                    name=f"{hostname} interface enabled",
                    passed=iface.admin_up,
                    detail="interface is up" if iface.admin_up else "interface is administratively down",
                )
            )
        except (NetsimError, KeyError, ValueError, AttributeError) as exc:
            checks.append(LabCheckResult(f"{hostname} configuration", False, str(exc)))

    try:
        switch = _device(workspace, "SW1")
        expected_vlans = {"FastEthernet0/1": 10, "FastEthernet0/2": 20}
        for interface_name, vlan_id in expected_vlans.items():
            iface = switch.get_interface(interface_name)
            actual_vlan = iface.switchport.access_vlan if iface.switchport is not None else None
            checks.append(
                LabCheckResult(
                    name=f"SW1 {interface_name} access VLAN",
                    passed=actual_vlan == vlan_id,
                    detail=f"access VLAN is {actual_vlan}, expected {vlan_id}",
                )
            )
            checks.append(
                LabCheckResult(
                    name=f"SW1 {interface_name} enabled",
                    passed=iface.admin_up,
                    detail="switchport is up" if iface.admin_up else "switchport is administratively down",
                )
            )
    except Exception as exc:
        checks.append(LabCheckResult("SW1 VLAN configuration", False, str(exc)))

    try:
        result = workspace.ping(_device(workspace, "PC1").device_id, expected["PC2"])
        isolated = not result.success
        checks.append(
            LabCheckResult(
                name="VLANs isolate PC1 from PC2",
                passed=isolated,
                detail=(
                    "traffic is blocked across VLANs as expected"
                    if isolated
                    else "PC1 reached PC2; check the switchport VLAN assignments"
                ),
            )
        )
    except Exception as exc:
        checks.append(LabCheckResult("VLANs isolate PC1 from PC2", False, str(exc)))
    return tuple(checks)

_SCENARIOS: dict[str, LabScenario] = {
    "basic-lan": LabScenario(
        scenario_id="basic-lan",
        title="Basic switched LAN",
        description="Connect two hosts through a switch and establish IPv4 connectivity.",
        task=(
            "Configure PC1 as 192.168.10.11/24 and PC2 as 192.168.10.12/24. "
            "Bring both host interfaces and SW1's two connected ports up, then run 'lab verify'."
        ),
        start_device_hostname="PC1",
        builder=_build_basic_lan,
        verifier=_check_basic_lan,
    ),
    "vlan-isolation": LabScenario(
        scenario_id="vlan-isolation",
        title="VLAN isolation",
        description="Configure host addressing while preserving two separate access VLANs.",
        task=(
            "Configure PC1 as 192.168.10.11/24 and PC2 as 192.168.10.12/24. "
            "Bring host and switch interfaces up, keep SW1 Fa0/1 in VLAN 10 and Fa0/2 in VLAN 20, "
            "and verify that the hosts cannot ping across VLANs."
        ),
        start_device_hostname="PC1",
        builder=_build_vlan_isolation,
        verifier=_check_vlan_isolation,
    ),
}


def list_scenarios() -> tuple[LabScenario, ...]:
    """Return available scenarios in stable identifier order."""
    return tuple(_SCENARIOS[key] for key in sorted(_SCENARIOS))


def get_scenario(scenario_id: str) -> LabScenario:
    """Look up a scenario by its stable ID."""
    try:
        return _SCENARIOS[scenario_id.lower()]
    except KeyError:
        available = ", ".join(sorted(_SCENARIOS))
        from netsim.labs.errors import LabOperationError

        raise LabOperationError(
            f"Unknown scenario {scenario_id!r}. Available scenarios: {available}"
        ) from None
