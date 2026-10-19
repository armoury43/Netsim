# Lab Management Guide

The lab workspace provides a shared API for building, configuring, saving, restoring, and verifying network topologies. The terminal CLI and Tkinter GUI use the same workspace.

## Start a built-in scenario

Launch NetSim with `netsim` or `python -m netsim`, then run:

```text
Router> lab list-scenarios
Router> lab scenario basic-lan
Router> show topology
Router> lab verify
```

The `basic-lan` scenario demonstrates basic IPv4 connectivity on a switched LAN. The `vlan-isolation` scenario demonstrates that hosts assigned to separate access VLANs cannot communicate directly at Layer 2 without an appropriate Layer 3 path.

## Configure a basic switched LAN

The built-in scenario provides a convenient starting point. You can also configure a lab explicitly:

```text
Router> lab scenario basic-lan
PC1> enable
PC1# configure terminal
PC1(config)# interface Ethernet0
PC1(config-if)# ip address 192.168.10.11 255.255.255.0
PC1(config-if)# no shutdown
PC1(config-if)# end
PC1# device select PC2
PC2# configure terminal
PC2(config)# interface Ethernet0
PC2(config-if)# ip address 192.168.10.12 255.255.255.0
PC2(config-if)# no shutdown
PC2(config-if)# end
PC2# device select SW1
SW1# configure terminal
SW1(config)# interface FastEthernet0/1
SW1(config-if)# no shutdown
SW1(config-if)# exit
SW1(config)# interface FastEthernet0/2
SW1(config-if)# no shutdown
SW1(config-if)# end
SW1# lab verify
```

Interface names must match the interfaces present on the selected virtual device. Newly created devices are ready for configuration, but interfaces start administratively down until enabled.

## Manage devices and links

```text
Router> show devices
Router> show topology
Router> device add router R2 GigabitEthernet0/0,GigabitEthernet0/1
Router> connect R1 GigabitEthernet0/1 R2 GigabitEthernet0/0
Router> link down R1 GigabitEthernet0/1
Router> link up R1 GigabitEthernet0/1
Router> disconnect R1 GigabitEthernet0/1
Router> device remove R2
```

A link's operational state is distinct from an interface's administrative state. Disconnecting a link removes the connection; taking a link down preserves the connection but makes it unavailable to the simulated forwarding path.

## Save, load, and reset

```text
Router> lab save practice-lab.json
Router> lab load practice-lab.json
Router> lab reset
```

Lab files are versioned JSON documents. They record the lab name, selected scenario/device, device types and identifiers, interface configuration, router static routes and RIP statements, standard ACLs and bindings, switch VLAN databases, host gateway settings, and links with their up/down state.

Loading validates and builds a candidate topology before replacing the current workspace. Saving writes a temporary file and then atomically replaces the destination. Invalid or over-limit lab files should be rejected without partially replacing the active workspace.

`lab reset` restores the most recently saved or loaded lab checkpoint. It is a workspace operation, not the same as reloading one selected device.

## Runtime state policy

Learned ARP entries, switch MAC tables, and RIP-learned routes are not persisted. A lab load/reset creates a fresh network engine and re-derives runtime state from the current topology and configuration. Topology changes also invalidate affected runtime state.

## Python API

```python
from netsim.labs import LabWorkspace

workspace = LabWorkspace()
router = workspace.create_device("router", "R1")
host = workspace.create_device("host", "PC1")
workspace.connect("R1", "GigabitEthernet0/0", "PC1", "Ethernet0")
workspace.save("practice-lab.json")
report = workspace.verify()
print(report.passed, report.passed_count, report.failed_count)
```

`LabWorkspace` orchestrates device and topology lifecycle. Route selection and packet forwarding remain the responsibility of `NetworkEngine`, and each device owns its configuration model.
