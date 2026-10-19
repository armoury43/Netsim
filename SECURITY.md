# Security Policy

NetSim is an educational, in-process network simulator. It does not send real network traffic or perform penetration tests against external systems.

## Supported baseline

Security and robustness fixes are currently focused on the latest project baseline. No formal support or backport policy has been established yet.

## Reporting a vulnerability

Please do not publish details of an exploitable issue in a public issue before maintainers have had a chance to assess it. If the repository host provides private vulnerability reporting, use that channel. Otherwise, contact the project maintainer privately through the contact method listed on the repository profile.

Include, where practical:

- affected version or commit;
- operating system and Python version;
- minimal reproduction steps or a proof-of-concept using only a local test environment;
- observed impact and expected behavior;
- relevant traceback or logs with secrets and personal data removed.

Do not include real credentials, private network data, or data belonging to others. Please allow time for triage and a fix before public disclosure.

## Scope

Reports involving command parsing, malformed or oversized lab/configuration files, unintended file access, code execution, state corruption, denial of service, and dependency vulnerabilities are relevant. The fact that the simulator models ACLs or routing is not itself a security guarantee for any real network.
