# Architecture Overview

NetSim is organized around a shared simulation backend with separate terminal and graphical front ends. The design aims to keep protocol behavior testable without requiring a terminal emulator, GUI, or physical network hardware.

## Package boundaries

| Package | Responsibility |
|---|---|
| `netsim.core` | Application settings, logging, events, and shared exceptions |
| `netsim.cli` | Command grammar, mode stack, validation, help, completion, history, and terminal execution |
| `netsim.devices` | Router, switch, and host configuration models, interfaces, VLAN settings, routes, and ACLs |
| `netsim.network` | Topology, links, Ethernet forwarding, ARP, IPv4 reachability, ICMP, route selection, and RIP convergence |
| `netsim.labs` | Workspace orchestration, device/link lifecycle, JSON import/export, built-in scenarios, and verification |
| `netsim.gui` | Tkinter presentation layer over the shared workspace and CLI APIs |

## Main data flow

A user command enters the CLI parser and command registry, is checked against the active mode, and is dispatched to a handler. The handler delegates configuration to the relevant device or workspace API. Network commands query or update the network engine; they do not implement a second packet-forwarding path inside the CLI.

The GUI uses the same workspace, command session, and device models. It presents their current state and forwards terminal input through the established CLI pipeline. This avoids maintaining separate CLI and GUI copies of networking logic.

## Persistent and runtime state

Persistent state includes device identity and configuration, interface settings, routing configuration, ACL rules and bindings, VLAN configuration, host gateway settings, and link state stored in a lab document.

Runtime state includes learned ARP entries, switch MAC-learning tables, and dynamically learned RIP routes. These values are recreated when a lab is loaded or reset rather than being treated as configuration. Topology changes invalidate the relevant runtime state so connectivity is derived from the current graph.

## Simulation boundaries

NetSim models selected networking behavior in memory. It does not attach to host interfaces, emit Ethernet frames onto a physical network, capture real traffic, or perform discovery against external addresses. A simulated ping is an application-level exercise through the modeled route, ARP, link, switching, ACL, and echo-reply path, not an operating-system ICMP packet.

RIP convergence is deterministic and explicit rather than driven by real protocol timers. The simulator does not currently model OSPF, STP/RSTP, NAT, DHCP, TCP/UDP applications, extended ACL matching, or timing-accurate packet animation.

## Lab import safety

Lab loading validates the input and constructs a candidate workspace before replacing the active state. File-size and structural limits constrain imported JSON documents. Runtime caches are not imported as trusted state. Application settings use safe YAML loading and validate expected field types. These controls reduce common malformed-input risks but do not constitute a formal security certification.

## Testing approach

The test suite is divided into unit, integration, acceptance, security-regression, and GUI workflow tests. The standard headless test command skips GUI-dependent cases if no display is available. Xvfb can be used in a Linux environment to exercise the GUI tests without a physical display.
