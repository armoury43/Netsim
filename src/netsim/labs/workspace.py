"""Manage a live network topology as a portable, testable lab workspace.

The workspace is the orchestration boundary shared by CLI commands and the
optional graphical GUI. Device configuration remains in device models, forwarding remains
in NetworkEngine, and this layer owns lifecycle operations (create, connect,
save, load, reset, scenario selection, and verification).
"""

from __future__ import annotations

import copy
import ipaddress
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable

from netsim.core.exceptions import NetsimError, ValidationError
from netsim.devices.acl import AclRule
from netsim.devices.base import Device
from netsim.devices.host import Host
from netsim.devices.router import Router
from netsim.devices.state import DeviceState
from netsim.devices.switch import Switch, Vlan
from netsim.labs.errors import LabFormatError, LabOperationError, LabStorageError
from netsim.labs.verification import LabCheckResult, LabVerificationReport
from netsim.network.engine import NetworkEngine
from netsim.network.icmp import PingResult
from netsim.network.errors import LinkNotFoundError
from netsim.network.link import Link
from netsim.network.topology import Topology

_FORMAT_VERSION = 1
_MAX_LAB_FILE_BYTES = 10 * 1024 * 1024

_MAX_LAB_DEVICES = 1024
_MAX_LAB_LINKS = 2048
_MAX_INTERFACES_PER_DEVICE = 128
_MAX_TOTAL_INTERFACES = 16384
_MAX_TOTAL_ACL_RULES = 8192
_MAX_TOTAL_VLAN_ENTRIES = 16384
_VALID_HOSTNAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")


class LabWorkspace:
    """Mutable workspace for network devices, topology, and training labs.

    A workspace always keeps a single facade identity while its internal
    NetworkEngine can be recreated after topology changes. This makes it safe
    for front-ends to hold the workspace as their network-context object.

    Args:
        topology: Existing topology to manage. If omitted, an empty one is made.
        active_device: Device initially selected in the interactive CLI.
        name: Human-readable lab name.
    """

    def __init__(
        self,
        topology: Topology | None = None,
        active_device: Device | None = None,
        name: str = "Untitled Lab",
    ) -> None:
        self.topology = topology if topology is not None else Topology()
        self.name = name
        self.active_scenario: str | None = None
        self._engine = NetworkEngine(self.topology)
        self._active_device_id = active_device.device_id if active_device is not None else None
        if self._active_device_id not in self.topology.devices():
            self._active_device_id = self._choose_device_id()
        self._reset_snapshot: dict[str, Any] = self._export_document()

    @property
    def engine(self) -> NetworkEngine:
        """Current underlying engine, for advanced integrations and tests."""
        return self._engine

    @property
    def active_device(self) -> Device | None:
        """Device currently selected in the interactive CLI, if any."""
        if self._active_device_id is None:
            return None
        return self.topology.devices().get(self._active_device_id)

    @property
    def devices(self) -> tuple[Device, ...]:
        """Current devices in insertion order."""
        return tuple(self.topology.devices().values())

    def _choose_device_id(self) -> str | None:
        devices = list(self.topology.devices().values())
        for device in devices:
            if isinstance(device, Router):
                return device.device_id
        return devices[0].device_id if devices else None

    def _refresh_engine(self) -> None:
        """Discard runtime caches after a topology mutation."""
        self._engine = NetworkEngine(self.topology)
        for device in self.topology.devices().values():
            if isinstance(device, Switch):
                device.clear_mac_table()

    def ping(self, source_device_id: str, destination_ip: str) -> PingResult:
        """Delegate ping to the current engine."""
        return self._engine.ping(source_device_id, destination_ip)

    def format_arp_table(self, device_id: str) -> list[str]:
        """Delegate the formatted ARP table to the current engine."""
        return self._engine.format_arp_table(device_id)

    def format_routing_table(self, device_id: str) -> list[str]:
        """Delegate the formatted routing table to the current engine."""
        return self._engine.format_routing_table(device_id)

    def forget_rip_routes(self, device_id: str) -> None:
        """Delegate removal of dynamic RIP routes."""
        self._engine.forget_rip_routes(device_id)

    def converge_rip(self, max_rounds: int = 16) -> int:
        """Run the current engine's deterministic RIP convergence routine."""
        return self._engine.converge_rip(max_rounds=max_rounds)

    def resolve_device(self, reference: str) -> Device:
        """Resolve a device by exact ID or case-insensitive hostname."""
        direct = self.topology.devices().get(reference)
        if direct is not None:
            return direct
        matches = [
            device
            for device in self.topology.devices().values()
            if device.hostname.casefold() == reference.casefold()
        ]
        if not matches:
            raise LabOperationError(f"No device named or identified by {reference!r} exists in this lab")
        if len(matches) > 1:
            raise LabOperationError(f"Device reference {reference!r} is ambiguous; use a device ID")
        return matches[0]

    def select_device(self, reference: str) -> Device:
        """Select a device for the current CLI session."""
        device = self.resolve_device(reference)
        self._active_device_id = device.device_id
        return device

    def create_device(
        self,
        device_type: str,
        hostname: str,
        interface_names: Iterable[str] | None = None,
    ) -> Device:
        """Create and register a Router, Switch, or Host device.

        ``interface_names`` defaults to the device model's standard
        interface set. Hosts support exactly one interface.
        """
        if not isinstance(hostname, str) or not _VALID_HOSTNAME.fullmatch(hostname):
            raise ValidationError(
                "Hostname must start with a letter and contain only letters, digits, '_' or '-' (max 32 chars)",
                field="hostname",
                value=hostname,
            )
        if any(device.hostname.casefold() == hostname.casefold() for device in self.devices):
            raise LabOperationError(f"A device named {hostname!r} already exists")

        if not isinstance(device_type, str):
            raise ValidationError("Device type must be a string", field="device_type", value=device_type)
        kind = device_type.casefold()
        names = list(interface_names) if interface_names is not None else None
        if names is not None and (not names or any(not isinstance(name, str) or not name.strip() for name in names)):
            raise ValidationError("At least one non-empty interface name is required", field="interfaces")
        if kind == "router":
            device: Device = Router(hostname=hostname, interface_names=names)
        elif kind == "switch":
            device = Switch(hostname=hostname, interface_names=names)
        elif kind in {"host", "pc", "computer"}:
            if names is not None and len(names) != 1:
                raise ValidationError("A host supports exactly one interface", field="interfaces", value=names)
            device = Host(hostname=hostname, interface_name=names[0] if names else "Ethernet0")
        else:
            raise ValidationError(
                "Device type must be 'router', 'switch', or 'host'", field="device_type", value=device_type
            )

        device.boot()
        self.topology.add_device(device)
        if self._active_device_id is None:
            self._active_device_id = device.device_id
        self._refresh_engine()
        return device

    def remove_device(self, reference: str) -> Device:
        """Remove a device and all connected links."""
        device = self.resolve_device(reference)
        was_active = device.device_id == self._active_device_id
        removed = self.topology.remove_device(device.device_id)
        if was_active:
            self._active_device_id = self._choose_device_id()
        self._refresh_engine()
        return removed

    def connect(
        self,
        device_a: str,
        interface_a: str,
        device_b: str,
        interface_b: str,
    ) -> Link:
        """Connect two named devices' interfaces."""
        left = self.resolve_device(device_a)
        right = self.resolve_device(device_b)
        link = self.topology.connect(left.device_id, interface_a, right.device_id, interface_b)
        self._refresh_engine()
        return link

    def disconnect(self, device_reference: str, interface_name: str) -> bool:
        """Disconnect one interface; return False if it was already unconnected."""
        device = self.resolve_device(device_reference)
        device.get_interface(interface_name)
        existing = self.topology.get_link(device.device_id, interface_name)
        if existing is None:
            return False
        self.topology.disconnect(device.device_id, interface_name)
        self._refresh_engine()
        return True

    def set_link_state(self, device_reference: str, interface_name: str, up: bool) -> None:
        """Set the operational state of a link attached to an interface."""
        device = self.resolve_device(device_reference)
        device.get_interface(interface_name)
        link = self.topology.get_link(device.device_id, interface_name)
        if link is None:
            raise LinkNotFoundError(device.device_id, interface_name)
        link.set_up(up)
        self._refresh_engine()

    def devices_summary(self) -> list[str]:
        """Return user-readable device inventory lines."""
        devices = sorted(self.devices, key=lambda d: (d.hostname.casefold(), d.device_id))
        if not devices:
            return ["No devices in the current lab."]
        return [
            f"{device.hostname:<16} {device.device_type.name.lower():<8} "
            f"{device.state.name.lower():<12} {device.device_id}"
            for device in devices
        ]

    def topology_summary(self) -> list[str]:
        """Return a human-readable topology inventory."""
        lines = ["Devices:"] + [f"  {line}" for line in self.devices_summary()]
        lines.append("Links:")
        links = self.topology.links()
        if not links:
            lines.append("  (none)")
        for link in links:
            a = self.topology.get_device(link.endpoint_a.device_id)
            b = self.topology.get_device(link.endpoint_b.device_id)
            state = "up" if link.up else "down"
            lines.append(
                f"  {a.hostname}:{link.endpoint_a.interface_name} <-> "
                f"{b.hostname}:{link.endpoint_b.interface_name} [{state}]"
            )
        return lines

    def save(self, path: str | os.PathLike[str]) -> Path:
        """Atomically save the current lab as a portable JSON document.

        The file includes device/interface configuration and physical link
        state. It intentionally excludes learned ARP/MAC/RIP runtime state.
        """
        target = Path(path).expanduser()
        document = self._export_document()
        payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
        temporary_path: Path | None = None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary_path = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, target)
        except (OSError, ValueError) as exc:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise LabStorageError(f"Could not save lab to {str(target)!r}: {exc}") from exc

        self.name = str(document["name"])
        self._reset_snapshot = copy.deepcopy(document)
        return target

    def load(self, path: str | os.PathLike[str]) -> Path:
        """Load a lab transactionally; malformed input leaves the live lab untouched."""
        source = Path(path).expanduser()
        try:

            with source.open("rb") as stream:
                raw_bytes = stream.read(_MAX_LAB_FILE_BYTES + 1)
            if len(raw_bytes) > _MAX_LAB_FILE_BYTES:
                raise LabStorageError(
                    f"Lab file is too large (maximum {_MAX_LAB_FILE_BYTES} bytes)"
                )
            text = raw_bytes.decode("utf-8")
        except LabStorageError:
            raise
        except UnicodeDecodeError as exc:

            raise LabFormatError(f"Lab file {str(source)!r} is not valid UTF-8") from exc
        except (OSError, ValueError) as exc:

            raise LabStorageError(f"Could not read lab from {str(source)!r}: {exc}") from exc

        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LabFormatError(f"Invalid JSON in lab file {str(source)!r}: {exc.msg}") from exc
        except (RecursionError, ValueError) as exc:

            raise LabFormatError(
                f"Invalid JSON in lab file {str(source)!r}: {type(exc).__name__}"
            ) from exc
        if not isinstance(raw, dict):
            raise LabFormatError("Lab document must be a JSON object")
        candidate_topology, id_map = _build_topology(raw)
        metadata = _validate_metadata(raw, id_map)

        self.topology = candidate_topology
        self.name = metadata["name"]
        self.active_scenario = metadata["active_scenario"]
        old_active = metadata["active_device_id"]
        self._active_device_id = id_map.get(old_active) if old_active is not None else None
        if self._active_device_id is None:
            self._active_device_id = self._choose_device_id()
        self._engine = NetworkEngine(self.topology)
        self._reset_snapshot = self._export_document()
        return source

    def reset(self) -> None:
        """Restore the most recently loaded or saved checkpoint of this lab."""
        snapshot = copy.deepcopy(self._reset_snapshot)
        topology, id_map = _build_topology(snapshot)
        metadata = _validate_metadata(snapshot, id_map)
        self.topology = topology
        self.name = metadata["name"]
        self.active_scenario = metadata["active_scenario"]
        old_active = metadata["active_device_id"]
        self._active_device_id = id_map.get(old_active) if old_active is not None else None
        if self._active_device_id is None:
            self._active_device_id = self._choose_device_id()
        self._engine = NetworkEngine(self.topology)

    def load_scenario(self, scenario_id: str) -> str:
        """Load a clean instance of a built-in teaching scenario."""
        from netsim.labs.scenarios import get_scenario

        scenario = get_scenario(scenario_id)
        topology = scenario.builder()
        start = next(
            (device for device in topology.devices().values()
             if device.hostname.casefold() == scenario.start_device_hostname.casefold()),
            None,
        )
        self.topology = topology
        self.name = scenario.title
        self.active_scenario = scenario.scenario_id
        self._active_device_id = start.device_id if start is not None else self._choose_device_id()
        self._engine = NetworkEngine(self.topology)
        self._reset_snapshot = self._export_document()
        return scenario.task

    def verify(self) -> LabVerificationReport:
        """Verify topology integrity and, when selected, the active scenario."""
        checks = list(_verify_topology(self.topology))
        if self.active_scenario is not None:
            from netsim.labs.scenarios import get_scenario

            scenario = get_scenario(self.active_scenario)
            checks.extend(scenario.verifier(self))
        if not checks:
            checks.append(LabCheckResult("Lab contains devices", False, "The lab is empty"))
        return LabVerificationReport(tuple(checks))

    def _export_document(self) -> dict[str, Any]:
        devices = [_device_to_dict(device) for device in self.topology.devices().values()]
        links = [
            {
                "endpoint_a": {
                    "device_id": link.endpoint_a.device_id,
                    "interface_name": link.endpoint_a.interface_name,
                },
                "endpoint_b": {
                    "device_id": link.endpoint_b.device_id,
                    "interface_name": link.endpoint_b.interface_name,
                },
                "up": link.up,
            }
            for link in self.topology.links()
        ]
        return {
            "format_version": _FORMAT_VERSION,
            "name": self.name,
            "active_scenario": self.active_scenario,
            "active_device_id": self._active_device_id,
            "devices": devices,
            "links": links,
        }


def _device_to_dict(device: Device) -> dict[str, Any]:
    if isinstance(device, Router):
        kind = "router"
        static_routes = [
            {"network": str(route.network), "next_hop": str(route.next_hop)}
            for route in device.static_routes.values()
        ]
        acls: dict[int, Any] = {}
        for number, access_list in device.access_lists.items():
            acls[number] = access_list
        for number in (*device.interface_acl_in.values(), *device.interface_acl_out.values()):
            acls.setdefault(number, None)
        router_extra: dict[str, Any] = {
            "static_routes": static_routes,
            "rip_networks": sorted(str(network) for network in device.rip_networks),
            "access_lists": [
                {
                    "number": number,
                    "rules": [
                        {"action": rule.action, "source_network": str(rule.source_network)}
                        for rule in access_list.rules()
                    ] if access_list is not None else [],
                }
                for number, access_list in sorted(acls.items())
            ],
            "interface_acl_in": dict(device.interface_acl_in),
            "interface_acl_out": dict(device.interface_acl_out),
        }
        extra: dict[str, Any] = {"router": router_extra}
    elif isinstance(device, Switch):
        kind = "switch"
        extra = {
            "switch": {
                "vlans": [
                    {"vlan_id": vlan.vlan_id, "name": vlan.name}
                    for _, vlan in sorted(device.vlans.items())
                ]
            }
        }
    elif isinstance(device, Host):
        kind = "host"
        extra = {"host": {"default_gateway": device.default_gateway}}
    else:
        raise LabFormatError(f"Unsupported device model {type(device).__name__!r}")

    interfaces: list[dict[str, Any]] = []
    for iface in device.interfaces.values():
        switchport: dict[str, Any] | None = None
        if iface.switchport is not None:
            switchport = {
                "mode": iface.switchport.mode,
                "access_vlan": iface.switchport.access_vlan,
                "trunk_allowed_vlans": sorted(iface.switchport.trunk_allowed_vlans),
            }
        interfaces.append(
            {
                "name": iface.name,
                "description": iface.description,
                "admin_up": iface.admin_up,
                "ipv4_address": iface.ipv4_address,
                "ipv4_prefix_length": iface.ipv4_prefix_length,
                "mac_address": iface.mac_address,
                "switchport": switchport,
            }
        )

    return {
        "id": device.device_id,
        "type": kind,
        "hostname": device.hostname,
        "state": device.state.name,
        "interfaces": interfaces,
        "extra": extra,
    }


def _build_topology(raw: dict[str, Any]) -> tuple[Topology, dict[str, str]]:
    version = raw.get("format_version")
    if not isinstance(version, int) or isinstance(version, bool) or version != _FORMAT_VERSION:
        raise LabFormatError(
            f"Unsupported lab format version {version!r}; supported version is {_FORMAT_VERSION}"
        )
    device_specs = raw.get("devices")
    link_specs = raw.get("links")
    if not isinstance(device_specs, list) or not isinstance(link_specs, list):
        raise LabFormatError("Lab document must contain 'devices' and 'links' arrays")
    _preflight_collection_limits(device_specs, link_specs)

    topology = Topology()
    id_map: dict[str, str] = {}
    for spec in device_specs:
        if not isinstance(spec, dict):
            raise LabFormatError("Each device entry must be a JSON object")
        old_id = _nonempty_string(spec.get("id"), "device.id")
        if old_id in id_map:
            raise LabFormatError(f"Duplicate device ID {old_id!r} in lab document")
        hostname = _nonempty_string(spec.get("hostname"), "device.hostname")
        interfaces_spec = spec.get("interfaces")
        if not isinstance(interfaces_spec, list) or not interfaces_spec:
            raise LabFormatError(f"Device {hostname!r} must define at least one interface")
        if len(interfaces_spec) > _MAX_INTERFACES_PER_DEVICE:
            raise LabFormatError(
                f"Device {hostname!r} exceeds the {_MAX_INTERFACES_PER_DEVICE}-interface limit"
            )
        interface_names = [_nonempty_string(i.get("name"), "interface.name") for i in _object_list(interfaces_spec, "interfaces")]
        try:
            device = _make_device(spec.get("type"), hostname, interface_names)
            topology.add_device(device)
            id_map[old_id] = device.device_id
            _restore_device_config(device, spec)
            _restore_device_state(device, spec.get("state"))

            device.save_config()
        except LabFormatError:
            raise
        except (NetsimError, ValueError, TypeError, KeyError) as exc:
            raise LabFormatError(f"Invalid configuration for device {hostname!r}: {exc}") from exc

    for spec in link_specs:
        if not isinstance(spec, dict):
            raise LabFormatError("Each link entry must be a JSON object")
        left = _parse_endpoint(spec.get("endpoint_a"), "link.endpoint_a")
        right = _parse_endpoint(spec.get("endpoint_b"), "link.endpoint_b")
        if left[0] not in id_map or right[0] not in id_map:
            raise LabFormatError("Link references a device ID that is not present in the lab")
        try:
            link = topology.connect(id_map[left[0]], left[1], id_map[right[0]], right[1])
            up = spec.get("up", True)
            if not isinstance(up, bool):
                raise LabFormatError("Link field 'up' must be a boolean")
            link.set_up(up)
        except LabFormatError:
            raise
        except (NetsimError, ValueError, TypeError) as exc:
            raise LabFormatError(f"Invalid link {left[1]!r} <-> {right[1]!r}: {exc}") from exc

    _verify_serialized_topology(topology)
    return topology, id_map


def _preflight_collection_limits(device_specs: list[Any], link_specs: list[Any]) -> None:
    """Reject structurally oversized labs before constructing device objects."""
    if len(device_specs) > _MAX_LAB_DEVICES:
        raise LabFormatError(f"Lab exceeds the {_MAX_LAB_DEVICES}-device limit")
    if len(link_specs) > _MAX_LAB_LINKS:
        raise LabFormatError(f"Lab exceeds the {_MAX_LAB_LINKS}-link limit")

    total_interfaces = 0
    total_acl_rules = 0
    total_vlan_entries = 0
    for spec in device_specs:
        if not isinstance(spec, dict):
            continue
        interfaces = spec.get("interfaces")
        if isinstance(interfaces, list):
            if len(interfaces) > _MAX_INTERFACES_PER_DEVICE:
                hostname = spec.get("hostname", "<unknown>")
                raise LabFormatError(
                    f"Device {hostname!r} exceeds the {_MAX_INTERFACES_PER_DEVICE}-interface limit"
                )
            total_interfaces += len(interfaces)
            if total_interfaces > _MAX_TOTAL_INTERFACES:
                raise LabFormatError(
                    f"Lab exceeds the {_MAX_TOTAL_INTERFACES}-interface total limit"
                )

        extra = spec.get("extra")
        if not isinstance(extra, dict):
            continue
        router_extra = extra.get("router")
        if isinstance(router_extra, dict):
            acls = router_extra.get("access_lists")
            if isinstance(acls, list):
                for acl in acls:
                    if isinstance(acl, dict):
                        rules = acl.get("rules")
                        if isinstance(rules, list):
                            total_acl_rules += len(rules)
                            if total_acl_rules > _MAX_TOTAL_ACL_RULES:
                                raise LabFormatError(
                                    f"Lab exceeds the {_MAX_TOTAL_ACL_RULES}-ACL-rule total limit"
                                )
        switch_extra = extra.get("switch")
        if isinstance(switch_extra, dict):
            vlans = switch_extra.get("vlans")
            if isinstance(vlans, list):
                total_vlan_entries += len(vlans)
                if total_vlan_entries > _MAX_TOTAL_VLAN_ENTRIES:
                    raise LabFormatError(
                        f"Lab exceeds the {_MAX_TOTAL_VLAN_ENTRIES}-VLAN-entry total limit"
                    )


def _make_device(kind: object, hostname: str, interface_names: list[str]) -> Device:
    if kind == "router":
        return Router(hostname=hostname, interface_names=interface_names)
    if kind == "switch":
        return Switch(hostname=hostname, interface_names=interface_names)
    if kind == "host":
        if len(interface_names) != 1:
            raise LabFormatError(f"Host {hostname!r} must have exactly one interface")
        return Host(hostname=hostname, interface_name=interface_names[0])
    raise LabFormatError(f"Unsupported device type {kind!r}")


def _restore_device_config(device: Device, spec: dict[str, Any]) -> None:
    interfaces_spec = _object_list(spec.get("interfaces"), "interfaces")
    known_names = set(device.interfaces)
    serialized_names = {item.get("name") for item in interfaces_spec}
    if serialized_names != known_names:
        raise LabFormatError(f"Device {device.hostname!r} interface list is inconsistent")

    for item in interfaces_spec:
        name = _nonempty_string(item.get("name"), "interface.name")
        iface = device.get_interface(name)
        description = item.get("description", "")
        if not isinstance(description, str):
            raise LabFormatError(f"Interface {name!r} description must be a string")
        iface.set_description(description)
        admin_up = item.get("admin_up", False)
        if not isinstance(admin_up, bool):
            raise LabFormatError(f"Interface {name!r} field 'admin_up' must be a boolean")
        iface.set_admin_up(admin_up)
        address = item.get("ipv4_address")
        prefix = item.get("ipv4_prefix_length")
        if address is None:
            if prefix is not None:
                raise LabFormatError(f"Interface {name!r} has a prefix length but no IPv4 address")
        else:
            if not isinstance(prefix, int) or isinstance(prefix, bool) or not (0 <= prefix <= 32):
                raise LabFormatError(f"Interface {name!r} has an invalid IPv4 prefix length")
            device.configure_ipv4(name, str(address), str(prefix))
        mac = item.get("mac_address")
        if mac is not None:
            iface.set_mac_address(str(mac))
        switchport_data = item.get("switchport")
        if iface.switchport is None:
            if switchport_data is not None:
                raise LabFormatError(f"Routed interface {name!r} cannot contain switchport settings")
        else:
            if not isinstance(switchport_data, dict):
                raise LabFormatError(f"Switchport interface {name!r} must contain switchport settings")
            mode = switchport_data.get("mode")
            if mode == "access":
                vlan_id = switchport_data.get("access_vlan", 1)
                if not isinstance(vlan_id, int) or isinstance(vlan_id, bool):
                    raise LabFormatError(f"Interface {name!r} has an invalid access VLAN")
                iface.set_switchport_access_vlan(vlan_id)
            elif mode == "trunk":
                allowed = switchport_data.get("trunk_allowed_vlans", [])
                if not isinstance(allowed, list) or any(
                    not isinstance(v, int) or isinstance(v, bool) for v in allowed
                ):
                    raise LabFormatError(f"Interface {name!r} has an invalid trunk VLAN list")
                iface.set_switchport_trunk(set(allowed))
            else:
                raise LabFormatError(f"Interface {name!r} has invalid switchport mode {mode!r}")

    extra = spec.get("extra", {})
    if not isinstance(extra, dict):
        raise LabFormatError(f"Device {device.hostname!r} field 'extra' must be an object")
    if isinstance(device, Host):
        host_extra = extra.get("host", {})
        if not isinstance(host_extra, dict):
            raise LabFormatError(f"Host {device.hostname!r} extra configuration must be an object")
        gateway = host_extra.get("default_gateway")
        if gateway is not None:
            device.set_default_gateway(_nonempty_string(gateway, "host.default_gateway"))
    elif isinstance(device, Switch):
        switch_extra = extra.get("switch", {})
        if not isinstance(switch_extra, dict):
            raise LabFormatError(f"Switch {device.hostname!r} extra configuration must be an object")
        vlan_specs = _object_list(switch_extra.get("vlans", []), "switch.vlans")
        restored_vlans: list[Vlan] = []
        for vlan in vlan_specs:
            vlan_id = vlan.get("vlan_id")
            vlan_name = vlan.get("name")
            if not isinstance(vlan_id, int) or isinstance(vlan_id, bool):
                raise LabFormatError("VLAN ID must be an integer")
            if not isinstance(vlan_name, str) or not vlan_name.strip():
                raise LabFormatError("VLAN name must be a non-empty string")
            restored_vlans.append(Vlan(vlan_id=vlan_id, name=vlan_name))
        device.replace_vlan_database(restored_vlans)
    elif isinstance(device, Router):
        router_extra = extra.get("router", {})
        if not isinstance(router_extra, dict):
            raise LabFormatError(f"Router {device.hostname!r} extra configuration must be an object")
        for route in _object_list(router_extra.get("static_routes", []), "router.static_routes"):
            network = ipaddress.ip_network(_nonempty_string(route.get("network"), "static_route.network"), strict=True)
            if not isinstance(network, ipaddress.IPv4Network):
                raise LabFormatError("Only IPv4 static routes are supported")
            device.add_static_route(str(network.network_address), str(network.netmask), _nonempty_string(route.get("next_hop"), "static_route.next_hop"))
        for network_text in _string_list(router_extra.get("rip_networks", []), "router.rip_networks"):
            network = ipaddress.ip_network(network_text, strict=True)
            if not isinstance(network, ipaddress.IPv4Network):
                raise LabFormatError("Only IPv4 RIP networks are supported")
            device.enable_rip(str(network.network_address), str(network.netmask))
        seen_acl_numbers: set[int] = set()
        for access_list_spec in _object_list(router_extra.get("access_lists", []), "router.access_lists"):
            number = access_list_spec.get("number")
            if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= 99:
                raise LabFormatError("Standard ACL number must be between 1 and 99")
            if number in seen_acl_numbers:
                raise LabFormatError(f"Duplicate access-list definition {number}")
            seen_acl_numbers.add(number)
            device.get_or_create_access_list(number)
            for rule in _object_list(access_list_spec.get("rules", []), f"ACL {number}.rules"):
                action = rule.get("action")
                source_text = _nonempty_string(rule.get("source_network"), "acl.source_network")
                if action not in ("permit", "deny"):
                    raise LabFormatError(f"Invalid action {action!r} in ACL {number}")
                network = ipaddress.ip_network(source_text, strict=True)
                if not isinstance(network, ipaddress.IPv4Network):
                    raise LabFormatError("ACL source network must be IPv4")
                device.get_or_create_access_list(number).add_rule(AclRule(action=action, source_network=network))
        for direction, key in (("in", "interface_acl_in"), ("out", "interface_acl_out")):
            bindings = router_extra.get(key, {})
            if not isinstance(bindings, dict):
                raise LabFormatError(f"Router {device.hostname!r} {key} must be an object")
            for interface_name, number in bindings.items():
                if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= 99:
                    raise LabFormatError("Interface ACL number must be between 1 and 99")
                device.set_interface_acl(str(interface_name), direction, number)


def _restore_device_state(device: Device, state_text: object) -> None:
    if not isinstance(state_text, str):
        raise LabFormatError(f"Device {device.hostname!r} state must be a string")
    try:
        target = DeviceState[state_text]
    except KeyError:
        raise LabFormatError(f"Device {device.hostname!r} has invalid state {state_text!r}") from None
    if target is DeviceState.CREATED:
        return
    device.power_on()
    if target is DeviceState.BOOTING:
        return
    device.complete_boot()
    if target is DeviceState.POWERED_OFF:
        device.power_off()


def _validate_metadata(raw: dict[str, Any], id_map: dict[str, str]) -> dict[str, Any]:
    name = raw.get("name", "Imported Lab")
    if not isinstance(name, str) or not name.strip():
        raise LabFormatError("Lab field 'name' must be a non-empty string")
    scenario = raw.get("active_scenario")
    if scenario is not None and not isinstance(scenario, str):
        raise LabFormatError("Lab field 'active_scenario' must be a string or null")
    active = raw.get("active_device_id")
    if active is not None and not isinstance(active, str):
        raise LabFormatError("Lab field 'active_device_id' must be a string or null")
    if scenario is not None:
        from netsim.labs.scenarios import get_scenario

        try:
            get_scenario(scenario)
        except LabOperationError as exc:
            raise LabFormatError(str(exc)) from exc
    if active is not None and active not in id_map:
        raise LabFormatError("Lab active_device_id refers to a device that is not present")
    return {"name": name, "active_scenario": scenario, "active_device_id": active}


def _verify_serialized_topology(topology: Topology) -> None:
    report = _verify_topology(topology)

    failures = [check for check in report if not check.passed and check.name.startswith("Link ")]
    if failures:
        summary = "; ".join(f"{check.name}: {check.detail}" for check in failures)
        raise LabFormatError(f"Lab topology failed integrity checks: {summary}")


def _verify_topology(topology: Topology) -> tuple[LabCheckResult, ...]:
    devices = list(topology.devices().values())
    checks: list[LabCheckResult] = []
    checks.append(LabCheckResult("Lab has devices", bool(devices), f"{len(devices)} device(s) registered"))

    hostnames: dict[str, str] = {}
    addresses: dict[str, str] = {}
    for device in devices:
        folded = device.hostname.casefold()
        if folded in hostnames:
            checks.append(
                LabCheckResult(
                    f"Unique hostname {device.hostname}", False,
                    f"conflicts with device {hostnames[folded]!r}",
                )
            )
        else:
            hostnames[folded] = device.hostname
        for iface in device.interfaces.values():
            if iface.ipv4_address is not None:
                previous = addresses.get(iface.ipv4_address)
                if previous is not None:
                    checks.append(
                        LabCheckResult(
                            f"Unique IPv4 address {iface.ipv4_address}", False,
                            f"assigned to both {previous} and {device.hostname}:{iface.name}",
                        )
                    )
                else:
                    addresses[iface.ipv4_address] = f"{device.hostname}:{iface.name}"

    attached: dict[tuple[str, str], Link] = {}
    for index, link in enumerate(topology.links(), start=1):
        valid = True
        details: list[str] = []
        for endpoint in (link.endpoint_a, link.endpoint_b):
            device = topology.devices().get(endpoint.device_id)
            if device is None:
                valid = False
                details.append(f"missing device {endpoint.device_id}")
                continue
            if endpoint.interface_name not in device.interfaces:
                valid = False
                details.append(f"missing interface {device.hostname}:{endpoint.interface_name}")
                continue
            key = (endpoint.device_id, endpoint.interface_name)
            if key in attached:
                valid = False
                details.append(f"interface {device.hostname}:{endpoint.interface_name} has multiple links")
            attached[key] = link
        checks.append(
            LabCheckResult(
                f"Link {index} endpoints",
                valid,
                ", ".join(details) if details else ("both endpoints are valid" if valid else "invalid endpoint"),
            )
        )
    return tuple(checks)


def _parse_endpoint(raw: object, field: str) -> tuple[str, str]:
    if not isinstance(raw, dict):
        raise LabFormatError(f"{field} must be an object")
    return (
        _nonempty_string(raw.get("device_id"), f"{field}.device_id"),
        _nonempty_string(raw.get("interface_name"), f"{field}.interface_name"),
    )


def _nonempty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LabFormatError(f"{field} must be a non-empty string")
    return value


def _object_list(value: object, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise LabFormatError(f"{field} must be an array of objects")
    return value


def _string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise LabFormatError(f"{field} must be an array of strings")
    return value
