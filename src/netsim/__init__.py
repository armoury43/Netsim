"""netsim: an open-source virtual network training and simulation platform.

See the project README for the full vision and development roadmap.
This top-level package intentionally stays empty of logic — it only
exposes the version number. Import from the relevant subpackage
(``netsim.core``, ``netsim.cli``, ``netsim.devices``, ``netsim.network``,
``netsim.labs``, ``netsim.gui``) instead of relying on re-exports here.
"""

__version__ = "0.1.2"

__all__ = ["__version__"]
