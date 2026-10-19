# NetSim visual tour

This gallery is meant to help a first-time visitor understand what NetSim does before installing it. All examples are from NetSim 0.1.2.

## 1. Graphical workspace

![NetSim GUI with a configured three-device LAN, embedded command-line terminal, and successful verification report](../assets/screenshots/gui-basic-lan-verified.png)

The screenshot shows PC1 and PC2 connected through SW1. Both hosts are addressed, the switch ports are enabled, the embedded CLI reports a successful ping, and the lab verifier reports **10/10 checks passed**. NetSim uses an in-memory network model; this example does not send packets onto a physical network.

The fresh starter workspace is shown separately here:

![NetSim starter GUI with a router and directly connected host](../assets/gui-preview.png)

## 2. Inspect the starter lab

![NetSim CLI transcript showing version, interface state, connected route, and successful ping](../assets/screenshots/cli-quickstart.png)

The transcript comes from actual calls through the CLI session and network engine. It shows version information, interface state, the connected IPv4 route, and an ICMP echo success in the default router/host lab.

## 3. Contextual help and input validation

![NetSim CLI with command abbreviation, contextual help, and an invalid IPv4 address error](../assets/screenshots/cli-help-and-errors.png)

The CLI supports unambiguous command abbreviations and `?` help. Invalid input is reported with the expected syntax instead of exposing a Python traceback.

## 4. A complete switched-LAN verification

![NetSim CLI showing 10 out of 10 checks passing for the basic-lan scenario](../assets/screenshots/cli-lab-verification.png)

The `basic-lan` scenario checks the registered devices, link endpoints, host IPv4 addresses, administrative interface state, switch ports, and PC1-to-PC2 connectivity.

## 5. Standard IPv4 ACL behavior

![NetSim CLI showing an outbound standard ACL denying a ping and successful connectivity after the binding is removed](../assets/screenshots/cli-acl-enforcement.png)

This transcript shows the same simulated ping before and after removing an outbound ACL binding. The first attempt is denied by policy; the second succeeds. NetSim currently models numbered standard IPv4 ACLs that filter on source addresses.

## About these visuals

- The GUI images are captures of the running Tkinter application.
- CLI visuals use actual output obtained by executing commands through the NetSim 0.1.2 runtime, then place that transcript in a consistent terminal-style frame for readability.
- All displayed ping and routing activity is simulated inside NetSim. The application is an educational simulator, not a live packet generator or a full vendor OS implementation.
