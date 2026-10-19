"""Headless tests for the GUI's display-independent topology projection."""

from __future__ import annotations

from netsim.devices.host import Host
from netsim.devices.router import Router
from netsim.devices.switch import Switch
from netsim.gui.model import TopologyLinkView, build_topology_view
from netsim.network.topology import Topology
from netsim.runtime import build_runtime


def test_empty_workspace_has_an_empty_topology_view() -> None:
    runtime = build_runtime(topology=Topology(), name="Empty")

    view = build_topology_view(runtime.workspace, width=800, height=500)

    assert view.width == 800
    assert view.height == 500
    assert view.nodes == ()
    assert view.links == ()


def test_default_runtime_view_projects_nodes_and_existing_link() -> None:
    runtime = build_runtime()

    view = build_topology_view(runtime.workspace, width=1000, height=600)

    assert [node.hostname for node in view.nodes] == ["Router", "PC1"]
    assert {node.device_type for node in view.nodes} == {"Router", "Host"}
    assert all(0 <= node.x <= 1000 and 0 <= node.y <= 600 for node in view.nodes)
    assert len(view.links) == 1
    link = view.links[0]
    assert link.up is True
    assert link.endpoint_a_device_id != link.endpoint_b_device_id
    assert (link.x1, link.y1) != (link.x2, link.y2)


def test_view_reflects_device_interface_state_and_new_links() -> None:
    runtime = build_runtime(topology=Topology(), name="Test")
    router = runtime.workspace.create_device("router", "R1")
    switch = runtime.workspace.create_device("switch", "SW1")
    host = runtime.workspace.create_device("host", "PC1")
    router.get_interface("GigabitEthernet0/0").set_admin_up(True)
    runtime.workspace.connect(router.device_id, "GigabitEthernet0/0", switch.device_id, "FastEthernet0/1")
    runtime.workspace.connect(switch.device_id, "FastEthernet0/2", host.device_id, "Ethernet0")
    runtime.workspace.set_link_state(switch.device_id, "FastEthernet0/2", False)

    view = build_topology_view(runtime.workspace, width=900, height=650)

    assert len(view.nodes) == 3
    router_view = next(node for node in view.nodes if node.hostname == "R1")
    assert router_view.interfaces_up == 1
    assert router_view.interface_count == 2
    assert len(view.links) == 2
    assert sum(link.up for link in view.links) == 1
    assert sum(not link.up for link in view.links) == 1


def test_link_view_key_is_independent_of_endpoint_order() -> None:
    forward = TopologyLinkView("a", "Ethernet0", "b", "GigabitEthernet0/0", True, 0, 0, 1, 1)
    reverse = TopologyLinkView("b", "GigabitEthernet0/0", "a", "Ethernet0", True, 1, 1, 0, 0)

    assert forward.key == reverse.key
