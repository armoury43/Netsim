# Public Release Checklist

Use this checklist when publishing a new NetSim version. Keep the repository private until the review below is complete.

## Before publishing

- [ ] Confirm the intended release version in `pyproject.toml` and `src/netsim/__init__.py` matches.
- [ ] Review `README.md`, `INSTALLATION.md`, `docs/troubleshooting.md`, `CHANGELOG.md`, and `SECURITY.md`.
- [ ] Open the README visual gallery and confirm all relative screenshot paths render and captions accurately describe the included examples.
- [ ] Confirm no local `.venv/`, editor settings, personal lab files, logs, tokens, passwords, or private network data are staged.
- [ ] Run the complete test suite: `python -m pytest -q -W error::ResourceWarning`.
- [ ] On Linux with a desktop or Xvfb, run GUI-dependent tests as well.
- [ ] Build and install a wheel in a clean environment, then smoke-test both `netsim` and `netsim-gui` where Tkinter and a display are available.
- [ ] Inspect the final ZIP/TAR.GZ contents and verify that they include the project root, source, tests, docs, assets, license, and packaging metadata.
- [ ] Do not describe CI, OS, Python-version, or security checks as passing unless those checks were actually run and their results are available.

## Publish on GitHub

1. Create a new repository or open the intended repository in the GitHub web interface.
2. Upload the **contents** of the `netsim/` project directory so `README.md` and `pyproject.toml` are visible at the repository root. Avoid uploading a ZIP containing a second nested project directory as the live repository structure.
3. Review the rendered README and confirm that the relative links, banner, GUI preview, installation instructions, license, and security reporting guidance render correctly.
4. Wait for the configured GitHub Actions workflows to finish. Fix failures before claiming cross-platform CI support.
5. For a GitHub Release, use a tag matching the version (for example, `v0.1.2`), copy the matching entry from `CHANGELOG.md` into release notes, and label it **pre-release** while the project is still marked Alpha.
6. Attach a source ZIP/TAR.GZ only if you want to provide a named release archive in addition to GitHub's automatically generated source archives. If you publish a wheel, build it from the exact tag and test-install that wheel.

## Release integrity

- Keep the source archive and installed wheel for a release generated from the same commit/tag.
- Generate SHA-256 hashes after the final files are created; regenerate the checksum file any time an archive changes.
- Treat the Alpha status as meaningful: document supported behavior and limitations, and do not advertise the simulator as a production router or a live penetration-testing tool.
