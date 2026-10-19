"""Cross-stage acceptance checks for the complete Stage 9 distribution.

These tests deliberately combine existing layers rather than retesting every
small method in isolation. They cover the default runtime, routed traffic,
ACL enforcement, RIP convergence, and the full lifecycle of built-in labs.
"""

from __future__ import annotations

from netsim.devices.host import Host
from netsim.devices.router import Router
from netsim.labs.workspace import LabWorkspace
from netsim.network.engine import NetworkEngine
from netsim.network.icmp import PingFailureReason
from netsim.network.topology import Topology
from netsim.runtime import build_runtime


def _bring_up(*interfaces) -> None:
    for interface in interfaces:
        interface.set_admin_up(True)


def _routed_lab(*, rip: bool = False) -> tuple[Topology, Host, Router, Router, Host, NetworkEngine]:
    """Build a real PC—R1—R2—PC topology with two IPv4 subnets."""
    topology = Topology()
    pc1 = Host(hostname="PC1")
    r1 = Router(
        hostname="R1",
        interface_names=["GigabitEthernet0/0", "GigabitEthernet0/1"],
    )
    r2 = Router(
        hostname="R2",
        interface_names=["GigabitEthernet0/0", "GigabitEthernet0/1"],
    )
    pc2 = Host(hostname="PC2")
    for device in (pc1, r1, r2, pc2):
        topology.add_device(device)

    topology.connect(pc1.device_id, "Ethernet0", r1.device_id, "GigabitEthernet0/0")
    topology.connect(r1.device_id, "GigabitEthernet0/1", r2.device_id, "GigabitEthernet0/0")
    topology.connect(r2.device_id, "GigabitEthernet0/1", pc2.device_id, "Ethernet0")

    pc1.configure_ipv4("Ethernet0", "10.0.1.2", "255.255.255.0")
    pc1.set_default_gateway("10.0.1.1")
    r1.configure_ipv4("GigabitEthernet0/0", "10.0.1.1", "255.255.255.0")
    r1.configure_ipv4("GigabitEthernet0/1", "10.0.12.1", "255.255.255.252")
    r2.configure_ipv4("GigabitEthernet0/0", "10.0.12.2", "255.255.255.252")
    r2.configure_ipv4("GigabitEthernet0/1", "10.0.2.1", "255.255.255.0")
    pc2.configure_ipv4("Ethernet0", "10.0.2.2", "255.255.255.0")
    pc2.set_default_gateway("10.0.2.1")

    _bring_up(
        pc1.get_interface("Ethernet0"),
        r1.get_interface("GigabitEthernet0/0"),
        r1.get_interface("GigabitEthernet0/1"),
        r2.get_interface("GigabitEthernet0/0"),
        r2.get_interface("GigabitEthernet0/1"),
        pc2.get_interface("Ethernet0"),
    )
    for device in (pc1, r1, r2, pc2):
        device.boot()

    if rip:
        r1.enable_rip("10.0.1.0", "255.255.255.0")
        r1.enable_rip("10.0.12.0", "255.255.255.252")
        r2.enable_rip("10.0.2.0", "255.255.255.0")
        r2.enable_rip("10.0.12.0", "255.255.255.252")
    else:
        r1.add_static_route("10.0.2.0", "255.255.255.0", "10.0.12.2")
        r2.add_static_route("10.0.1.0", "255.255.255.0", "10.0.12.1")

    return topology, pc1, r1, r2, pc2, NetworkEngine(topology)


def test_installed_runtime_cli_and_default_ping_work_together() -> None:
    runtime = build_runtime()
    router = runtime.workspace.resolve_device("Router")

    result = runtime.workspace.ping(router.device_id, "10.0.0.2")
    assert result.success
    assert runtime.workspace.engine.arp_table(router.device_id)

    for command in ("show devices", "show topology", "ping 10.0.0.2", "show arp"):
        outcome = runtime.session.execute_line(command)
        assert outcome.error is None, f"{command}: {outcome.error}"


def test_multihop_static_routing_acl_deny_and_removal_regression() -> None:
    _, pc1, r1, _r2, _pc2, engine = _routed_lab()
    assert engine.ping(pc1.device_id, "10.0.2.2").success

    r1.add_access_list_rule(10, "deny", "10.0.1.2", "255.255.255.255")
    r1.add_access_list_rule(10, "permit", "any")
    r1.set_interface_acl("GigabitEthernet0/0", "in", 10)
    denied = engine.ping(pc1.device_id, "10.0.2.2")
    assert not denied.success
    assert denied.reason is PingFailureReason.ACL_DENIED

    r1.remove_interface_acl("GigabitEthernet0/0", "in")
    assert engine.ping(pc1.device_id, "10.0.2.2").success


def test_multihop_ping_fails_when_request_reaches_destination_but_return_route_is_missing() -> None:
    _, pc1, _r1, r2, _pc2, engine = _routed_lab()
    r2.remove_static_route("10.0.1.0", "255.255.255.0")

    result = engine.ping(pc1.device_id, "10.0.2.2")

    assert not result.success
    assert result.reason is PingFailureReason.NO_ROUTE
    assert "10.0.1.2" in result.detail


def test_multihop_rip_requires_convergence_then_forwards() -> None:
    _, pc1, _r1, _r2, _pc2, engine = _routed_lab(rip=True)
    before = engine.ping(pc1.device_id, "10.0.2.2")
    assert not before.success
    assert before.reason is PingFailureReason.NO_ROUTE

    rounds = engine.converge_rip()
    assert rounds > 0
    assert engine.ping(pc1.device_id, "10.0.2.2").success
    assert engine.converge_rip() == 0


def test_switched_lan_link_failure_and_recovery() -> None:
    workspace = LabWorkspace()
    pc1 = workspace.create_device("host", "PC1")
    pc2 = workspace.create_device("host", "PC2")
    switch = workspace.create_device("switch", "SW1")
    workspace.connect("PC1", "Ethernet0", "SW1", "FastEthernet0/1")
    workspace.connect("PC2", "Ethernet0", "SW1", "FastEthernet0/2")
    pc1.configure_ipv4("Ethernet0", "192.0.2.1", "24")
    pc2.configure_ipv4("Ethernet0", "192.0.2.2", "24")
    _bring_up(
        pc1.get_interface("Ethernet0"),
        pc2.get_interface("Ethernet0"),
        switch.get_interface("FastEthernet0/1"),
        switch.get_interface("FastEthernet0/2"),
    )

    assert workspace.ping(pc1.device_id, "192.0.2.2").success
    workspace.set_link_state("PC1", "Ethernet0", False)
    assert not workspace.ping(pc1.device_id, "192.0.2.2").success
    workspace.set_link_state("PC1", "Ethernet0", True)
    assert workspace.ping(pc1.device_id, "192.0.2.2").success


def test_builtin_lab_scenarios_have_reachable_passing_states() -> None:
    for scenario_id in ("basic-lan", "vlan-isolation"):
        workspace = LabWorkspace()
        task = workspace.load_scenario(scenario_id)
        assert task
        assert not workspace.verify().passed

        pc1 = workspace.resolve_device("PC1")
        pc2 = workspace.resolve_device("PC2")
        switch = workspace.resolve_device("SW1")
        pc1.configure_ipv4("Ethernet0", "192.168.10.11", "255.255.255.0")
        pc2.configure_ipv4("Ethernet0", "192.168.10.12", "255.255.255.0")
        _bring_up(
            pc1.get_interface("Ethernet0"),
            pc2.get_interface("Ethernet0"),
            switch.get_interface("FastEthernet0/1"),
            switch.get_interface("FastEthernet0/2"),
        )

        report = workspace.verify()
        assert report.passed, f"{scenario_id}: {[c for c in report.checks if not c.passed]}"


def test_lab_import_rejects_broken_link_without_mutating_live_workspace(tmp_path) -> None:
    workspace = LabWorkspace(name="Keep Me")
    workspace.create_device("host", "PC1")
    workspace.create_device("host", "PC2")
    workspace.connect("PC1", "Ethernet0", "PC2", "Ethernet0")
    saved = tmp_path / "valid-lab.json"
    workspace.save(saved)

    import json
    from netsim.labs.errors import LabFormatError

    document = json.loads(saved.read_text(encoding="utf-8"))
    document["links"][0]["endpoint_a"]["device_id"] = "not-a-device"
    broken = tmp_path / "broken-lab.json"
    broken.write_text(json.dumps(document), encoding="utf-8")
    before = (workspace.name, tuple((d.device_id, d.hostname) for d in workspace.devices), len(workspace.topology.links()))

    try:
        workspace.load(broken)
    except LabFormatError:
        pass
    else:
        raise AssertionError("malformed topology was accepted")

    after = (workspace.name, tuple((d.device_id, d.hostname) for d in workspace.devices), len(workspace.topology.links()))
    assert after == before
