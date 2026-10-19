"""pytest configuration.

Ensures ``src/`` is importable even if the package hasn't been
``pip install -e``'d (pytest's own ``pythonpath`` setting in
pyproject.toml already does this too; this is a defensive fallback so
the test suite also works when invoked in unusual ways).
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
