# Release checklist

Status: v1.0.0 (all 14 phases complete, 342 tests passing). The portable
ZIP at `releases\LongFormMusicStudio-1.0.0-portable.zip` was built and
frozen-self-check verified on this machine.

## Build tooling (`installer/`)

| File | Purpose |
| --- | --- |
| `entry.py` | Frozen entry point; `--version` and `LFMS_SELF_CHECK=1` run headlessly so builds can be verified automatically (exit code is the assertion) |
| `lfms.spec` | PyInstaller spec: one-dir windowed build, test/tool excludes, scipy workaround, soundfile data collection |
| `rthook_scipy_ellip.py` | Runtime hook stubbing two scipy modules excluded from the bundle (see below) |
| `build_portable.ps1` | One-shot release script: version → tests → ruff → PyInstaller → frozen self-check → ZIP into `releases/` |
| `setup.iss` | Inno Setup 6 script for the setup.exe installer |

## The scipy workaround (documented honestly)

PyInstaller's modulegraph crashes scanning exactly one file on this
machine: `scipy/stats/_stats_py.py`
(`IndexError: tuple index out of range` in `dis`). `scipy.signal`
imports `scipy.stats` eagerly (one `scoreatpercentile` call), and
`scipy.special.__init__` eagerly imports `_ellip_harm_2`, so neither can
simply be dropped. Both are therefore **excluded from the bundle** and
**stubbed at runtime** by the runtime hook:

- `scipy.stats.scoreatpercentile` is reimplemented via
  `numpy.percentile`; every other attribute resolves to a callable that
  raises `NotImplementedError`.
- `scipy.special._ellip_harm_2._ellipsoid/_ellipsoid_norm` raise
  `NotImplementedError`.

LFMS never calls ellipsoidal harmonics or peak-finding statistics; if a
future feature needs them, remove the exclusions after upgrading
PyInstaller past the scan bug.

## Portable build

```
powershell -ExecutionPolicy Bypass -File installer\build_portable.ps1
```

Runs the full gate itself (tests must pass, ruff must be clean) and
produces `releases\LongFormMusicStudio-<version>-portable.zip`
(~85 MB). Verified on this machine at v0.12.0: frozen self-check exits 0.

## Installer (Inno Setup)

The `.iss` script is ready but **compiling it requires Inno Setup 6
(ISCC.exe)**, which is not installed on this machine — do not claim an
installer was built without running ISCC. On a machine with Inno Setup:

1. Run the portable build first (it fills `dist/`).
2. `ISCC.exe installer\setup.iss`
3. Result: `releases\LongFormMusicStudio-<version>-setup.exe`.

## Release checklist (per release)

1. Bump `VERSION` in `lfms/core/version.py` **and** `pyproject.toml`.
2. Update `CHANGELOG.md` with a dated section.
3. `python -m pytest -q` green (with `LFMS_GUI_SMOKE=1`) + ruff clean.
4. Run `installer\build_portable.ps1` — its internal gates re-run tests,
   ruff, then verify the frozen exe headlessly.
5. Manual smoke on the built app: launch once, generate, export.
6. (Machine with Inno Setup) compile `setup.iss`, smoke-test install +
   uninstall.
7. Tag the commit (`v<version>`); artifacts stay in `releases/`
   (git-ignored).

## Screenshots

`python scripts/make_screenshots.py` regenerates all six README captures
headlessly (`QT_QPA_PLATFORM=offscreen` + `QWidget.grab()`), writing
`docs/screenshots/0N-<page>.png`. These are real renders of the running app,
not mockups.

## Publishing the GitHub release (manual — no remote configured here)

This repository was developed locally; no git remote is configured on this
machine, so the actual publish could not be performed here. On a machine with
push access:

```powershell
git remote add origin https://github.com/<org>/LongForm-Music-Studio.git
git push -u origin main
git tag -a v1.0.0 -m "LFMS 1.0.0 — first stable release"
git push origin v1.0.0
```

Then on GitHub → Releases → **Draft a new release**:

1. Choose tag `v1.0.0`; title `LFMS 1.0.0`.
2. Paste the `[1.0.0]` section of [CHANGELOG.md](../CHANGELOG.md) as notes.
3. Attach `releases\LongFormMusicStudio-1.0.0-portable.zip`
   (~85 MB; SHA256 it first: `Get-FileHash <zip> -Algorithm SHA256`).
4. Optionally attach `LongFormMusicStudio-1.0.0-setup.exe` if compiled on a
   machine with Inno Setup.
5. Publish, then verify the download by unzipping on a clean machine and
   running `LongFormMusicStudio.exe --version`.
