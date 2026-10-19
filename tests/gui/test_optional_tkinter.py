"""The CLI package must remain usable when a Python build lacks Tkinter."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import textwrap


def test_gui_launcher_explains_missing_tkinter() -> None:
    source_root = str(Path(__file__).resolve().parents[2] / "src")
    script = textwrap.dedent(
        """
        import builtins
        real_import = builtins.__import__
        def block_tk(name, globals=None, locals=None, fromlist=(), level=0):
            if name == 'tkinter' or name.startswith('tkinter.'):
                raise ImportError('simulated missing Tkinter')
            return real_import(name, globals, locals, fromlist, level)
        builtins.__import__ = block_tk
        from netsim.gui.app import main
        raise SystemExit(main())
        """
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = source_root
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "does not include Tkinter" in result.stdout
    assert "python -m tkinter" in result.stdout
    assert "netsim-gui" in result.stdout
    assert "python -m netsim" in result.stdout
    if sys.platform.startswith("linux"):
        assert "python3-tk" in result.stdout or "python3-tkinter" in result.stdout
