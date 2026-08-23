# Troubleshooting

Status: growing list; entries below are real issues encountered during
development, not hypotheticals.

## Python venv creation fails (exit status 101 / "Unable to create process")

**Symptom**

```
python -m venv .venv
Error: Command '[...python.exe, '-Im', 'ensurepip', '--upgrade', '--default-pip']'
returned non-zero exit status 101
```

and running `.venv\Scripts\python.exe` prints
`Unable to create process using '<base python> ...'`.

**Cause observed**: on some machines (Python 3.10.0 here) antivirus or process
policy blocks spawning child interpreters, breaking `ensurepip` and the venv
launcher. Happens on both C: and external drives.

**Workaround used for this repo's development**

```powershell
python -m pip install --user -e ".[dev]"
python -m pytest          # run from the repository root
```

The global interpreter runs fine directly; only spawned children fail.
Consider upgrading Python (3.10.0 → latest 3.x) which also resolves this in
most reported cases.

## G: drive notes

The repository lives at `G:\LongForm-Music-Studio` (external/fixed data drive).
No absolute paths are stored in code — runtime data locations resolve via
`LFMS_DATA_DIR`, `portable.flag`, or `%APPDATA%` (see ARCHITECTURE.md §F paths).

## Audio device unavailable (upcoming Phase 2)

Planned guidance: check Windows sound settings, select another output device in
Settings → Audio, and verify exclusive-mode apps aren't holding the device.
