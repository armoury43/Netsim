# Security and Robustness Review

**Reviewed baseline:** NetSim 0.1.1  
**Review date:** 2026-10-17  
**Environment:** Linux, Python 3.13.5, PyYAML 6.0.3; GUI tests under Xvfb

This is a historical record of the 0.1.1 review, not a certification of later releases. Version 0.1.2 updates platform-specific GUI startup guidance and installation documentation; the current automated test results should be reviewed separately before release.

## Summary

The review focused on local application robustness: command input, IPv4 parsing, application settings, imported lab files, CLI execution, and packaging smoke checks. It was a targeted project-level review, not a third-party penetration test or a formal security certification.

Three issues were found and corrected in the reviewed baseline:

1. Some malformed application configuration values could escape parsing as raw `TypeError` exceptions. Configuration loading now validates expected path/theme field types, normalizes errors to `ConfigurationError`, uses PyYAML's safe loader, and enforces a 1 MiB configuration-file limit.
2. An embedded NUL in a user-supplied lab path could raise `ValueError` outside the storage error boundary. Invalid paths now produce a controlled `LabStorageError`, with API and CLI regression tests.
3. A small but structurally dense imported lab could expand into a much larger Python object graph. Lab import now enforces a 10 MiB bounded read and structural limits before constructing devices and links.

Current lab-import caps include 1,024 devices, 2,048 links, 128 interfaces per device, 16,384 total interfaces, 8,192 ACL rules, and 16,384 VLAN entries.

## Validation recorded for this baseline

- Full unit, integration, acceptance, security-regression, and GUI workflow suite with `ResourceWarning` treated as an error.
- 20,000 generated and command-shaped CLI inputs, including Unicode, control characters, newlines, and embedded NULs.
- 5,000 generated application-configuration inputs.
- 3,000 invalid or randomized IPv4 destinations sent through the public ping/workspace API.
- 15,000 schema-mutation cases against generated lab JSON; rejected imports were checked for workspace-state preservation.
- 100,000 randomized ACL decisions compared with a reference first-match interpreter.
- 25,000 randomized route lookups compared with an independent longest-prefix/administrative-distance selector.
- Regression tests for untrusted Python YAML tags.
- Source scans for selected dangerous primitives and unsafe YAML loading patterns.
- Built and installed the `netsim-0.1.1-py3-none-any.whl` package in a separate target and smoke-tested the installed CLI and GUI.

See the release test output for exact counts applicable to a given checkout. These historical counts should not be treated as a guarantee for future code changes.

## Security boundary

NetSim is an in-process simulator. It does not send real network traffic, probe external hosts, capture physical traffic, or replace an authorized penetration-testing toolkit. Its security controls protect application input and lab/configuration handling; they do not prove that all code is bug-free.

## Limitations

Bandit, Ruff, Mypy, and pip-audit were not available in the review environment, so no successful run of those tools is claimed. The reviewed source was not separately tested on every supported operating system or Python version. A source-pattern scan is not a substitute for dynamic analysis, dependency auditing, or an independent security review.

For reporting a newly discovered security problem, follow [SECURITY.md](../SECURITY.md).
