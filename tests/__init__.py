"""Test suite for netsim.

Tests are written as ``unittest.TestCase`` classes so the suite runs
with only the standard library (``python -m unittest discover``) in
environments without network access to install pytest. pytest, once
available, discovers and runs these natively without any changes.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
