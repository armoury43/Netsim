"""Display-independent topology projection used by the graphical front-end.

The GUI consumes immutable view objects rather than reaching into Tk widgets
from network code. This keeps topology layout and state summaries testable in
headless environments.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from netsim.labs.workspace import LabWorkspace


@dataclass(frozen=True)
class TopologyNodeView:
    device_id: str
    hostname: str
    device_type: str
    lifecycle_state: str
    interface_count: int
    interfaces_up: int
    x: float
    y: float


@dataclass(frozen=True)
class TopologyLinkView:
    endpoint_a_device_id: str
    endpoint_a_interface: str
    endpoint_b_device_id: str
    endpoint_b_interface: str
    up: bool
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def key(self) -> tuple[str, str, str, str]:
        """Orientation-independent identity suitable for selection."""
        a = (self.endpoint_a_device_id, self.endpoint_a_interface)
        b = (self.endpoint_b_device_id, self.endpoint_b_interface)
        left, right = sorted((a, b))
        return left[0], left[1], right[0], right[1]


@dataclass(frozen=True)
class TopologyView:
    width: int
    height: int
    nodes: tuple[TopologyNodeView, ...]
    links: tuple[TopologyLinkView, ...]


def build_topology_view(
    workspace: LabWorkspace,
    width: int,
    height: int,
    *,
    margin: int = 72,
    min_column_gap: int = 190,
    min_row_gap: int = 140,
) -> TopologyView:
    """Project the current workspace into a deterministic grid layout.

    Nodes are arranged in a responsive grid in workspace order. Links resolve
    to node centers; the drawing layer is free to add icons or label offsets.
    Empty workspaces produce an empty view without special cases in the GUI.
    """
    safe_width = max(1, int(width))
    safe_height = max(1, int(height))
    devices = list(workspace.devices)
    if not devices:
        return TopologyView(safe_width, safe_height, (), ())

    usable_width = max(1, safe_width - 2 * margin)
    columns = max(1, min(len(devices), (usable_width + min_column_gap) // min_column_gap))
    rows = math.ceil(len(devices) / columns)
    usable_height = max(1, safe_height - 2 * margin)
    col_gap = usable_width / max(1, columns - 1) if columns > 1 else 0
    row_gap = usable_height / max(1, rows - 1) if rows > 1 else 0

    positions: dict[str, tuple[float, float]] = {}
    node_views: list[TopologyNodeView] = []
    for index, device in enumerate(devices):
        row, col = divmod(index, columns)

        row_count = min(columns, len(devices) - row * columns)
        row_offset = (columns - row_count) * col_gap / 2 if columns > 1 else 0
        x = margin + col * col_gap + row_offset
        y = margin + row * row_gap
        positions[device.device_id] = (x, y)
        interfaces = list(device.interfaces.values())
        node_views.append(
            TopologyNodeView(
                device_id=device.device_id,
                hostname=device.hostname,
                device_type=device.device_type.name.title(),
                lifecycle_state=device.state.name.replace("_", " ").title(),
                interface_count=len(interfaces),
                interfaces_up=sum(1 for interface in interfaces if interface.admin_up),
                x=x,
                y=y,
            )
        )

    link_views: list[TopologyLinkView] = []
    for link in workspace.topology.links():
        pos_a = positions.get(link.endpoint_a.device_id)
        pos_b = positions.get(link.endpoint_b.device_id)
        if pos_a is None or pos_b is None:

            continue
        link_views.append(
            TopologyLinkView(
                endpoint_a_device_id=link.endpoint_a.device_id,
                endpoint_a_interface=link.endpoint_a.interface_name,
                endpoint_b_device_id=link.endpoint_b.device_id,
                endpoint_b_interface=link.endpoint_b.interface_name,
                up=link.up,
                x1=pos_a[0],
                y1=pos_a[1],
                x2=pos_b[0],
                y2=pos_b[1],
            )
        )

    return TopologyView(safe_width, safe_height, tuple(node_views), tuple(link_views))
