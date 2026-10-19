# Contributing

Thanks for considering a contribution to NetSim. Improvements to correctness, reproducibility, usability, and documentation are especially valuable.

## Before opening a change

1. Check the existing issue tracker or discussion area, if available, to avoid duplicating work.
2. Keep changes focused and explain the user-visible behavior they affect.
3. Add regression tests for bug fixes and tests for new behavior.
4. Update documentation when commands, file formats, supported behavior, or limitations change.

## Local development

NetSim supports Python 3.10 and newer.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest -q -W error::ResourceWarning
```

On Windows PowerShell, activate the environment with:

```powershell
.\.venv\Scripts\Activate.ps1
```

GUI-dependent tests skip when no display is available. On Linux with Xvfb installed, exercise the full GUI workflow suite with:

```bash
xvfb-run -a python -m pytest -q -W error::ResourceWarning
```

## Engineering expectations

- Preserve the boundary between device configuration, network behavior, workspace orchestration, and front-end presentation.
- Avoid duplicating network logic in command handlers or GUI callbacks.
- Prefer explicit, typed interfaces and domain-specific errors over broad exception handling.
- Validate untrusted imported data before mutating active state.
- Keep simulation behavior deterministic unless a feature explicitly requires modeled time or randomness.
- Do not introduce live network probing or traffic capture as an implicit side effect.
- Keep code, user-facing messages, tests, and documentation in English so the project can be maintained by an international contributor base.

## Pull requests

Describe the problem, summarize the design, list tests run, and state any limitations that remain. Do not claim a test, platform, or security scanner was run unless it actually was.
