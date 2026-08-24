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

Inno Setup 6.7.3 is installed on this machine and the installer was
compiled successfully for v1.0.0:

```
ISCC.exe installer\setup.iss
-> releases\LongFormMusicStudio-<version>-setup.exe (~54 MB)
```

The frozen exe carries a proper Windows version resource (embedded by
`installer/lfms.spec` from `lfms.core.version`, single source of truth);
setup.iss reads the version from it via `GetVersionNumbersString`.

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

## Publishing to GitHub (done for v1.0.0)

Published on 2026-08-23:

- Repo: <https://github.com/azmasum/LongForm-Music-Studio>
- Release: <https://github.com/azmasum/LongForm-Music-Studio/releases/tag/v1.0.0>
  (attaches `LongFormMusicStudio-1.0.0-portable.zip`, ~85 MB)
- CI: GitHub Actions runs the full suite on every push/PR —
  windows-latest + ubuntu-latest × Python 3.10/3.12, GUI tests included
  via Qt offscreen (Linux runners get `libegl1 libgl1 libxkbcommon0
  libdbus-1-3 libfontconfig1`; see `.github/workflows/ci.yml`)

Steps actually used (via `gh` CLI):

```powershell
gh repo create LongForm-Music-Studio --public --source . --remote origin --push
git tag -a v1.0.0 -m "LFMS 1.0.0 - first stable release"
git push origin v1.0.0
gh release create v1.0.0 releases\LongFormMusicStudio-1.0.0-portable.zip `
    --title "LFMS 1.0.0 - first stable release" --notes-file release-notes.md
```

For future releases repeat only: bump version → changelog → tests/ruff →
`installer\build_portable.ps1` → tag → `gh release create`.

## v1.1.0 (published 2026-08-24)

- Changes: MP3/OGG export, generated audio saved to a user-chosen folder
  (default Downloads) and loaded into the transport player, interactive
  timeline clips (select/drag/delete), Mix & Timeline usage hints,
  player deadlock fix. 352 tests green.
- Release: <https://github.com/azmasum/LongForm-Music-Studio/releases/tag/v1.1.0>
- `LongFormMusicStudio-1.1.0-portable.zip` — 85.8 MB —
  SHA256 `44C15D9CCAF91A499644DAC7B3036872E439C288F6EEB6BC40CE60B1C861F8D1`
- `LongFormMusicStudio-1.1.0-setup.exe` — 54.0 MB —
  SHA256 `BA7894713693F8D94B7B626E9403CABE536EE31DDA587EC4300988E080372D46`
- Frozen self-checks passed (`--version` → 1.1.0, `LFMS_SELF_CHECK=1`).
