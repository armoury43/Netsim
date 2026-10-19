"""Initialize and run the interactive NetSim command-line application.

This module is the composition root that builds the runtime, default lab,
network engine, and CLI session. The rest of the CLI, device, and network
packages communicate through explicit interfaces and do not rely on this
entry point for their internal logic.
"""

from __future__ import annotations

import logging
import sys

from netsim import __version__
from netsim.core.config import ConfigurationError, get_config_dir, load_settings
from netsim.core.logging_config import configure_logging, get_logger
from netsim.cli.terminal import run
from netsim.network.topology import Topology
from netsim.devices.router import Router
from netsim.runtime import build_default_topology, build_runtime


def _build_default_topology() -> tuple[Topology, Router]:
    """Backward-compatible private alias used by integration tests."""
    return build_default_topology()


def main() -> int:
    """Initialize core services and run the interactive CLI.

    Returns:
        Process exit code (0 on success, 1 on configuration failure).
    """
    try:
        settings = load_settings()
    except ConfigurationError as exc:

        print(f"netsim: configuration error: {exc}", file=sys.stderr)
        return 1

    configure_logging(level=getattr(logging, settings.log_level))
    logger = get_logger(__name__)

    logger.info("netsim v%s starting", __version__)
    logger.info("Config directory: %s", get_config_dir())

    runtime = build_runtime()
    run(runtime.session)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
