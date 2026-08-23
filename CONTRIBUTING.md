# Contributing to LFMS

Thanks for helping build a professional, trustworthy tool for creators.

## Ground rules

1. **No fake features** — every control must work, be marked experimental, or
   be disabled with an explanation. Never fabricate test results.
2. **Copyright safety first** — never add samples/assets without a verified
   license and an entry in `THIRD_PARTY_LICENSES.md`.
3. **Offline core stays offline** — network features belong behind optional,
   explicit adapters.

## Workflow

1. Fork/branch from `main` (`feat/<topic>`, `fix/<topic>`).
2. Set up: `.\scripts\dev_setup.ps1`.
3. Code style:
   - Type hints on all public functions.
   - Modular design; no huge single files; no hardcoded paths or API keys.
   - Docstrings where behavior isn't obvious.
4. Run before pushing:
   ```powershell
   .\.venv\Scripts\python.exe -m ruff check .
   .\.venv\Scripts\python.exe -m pytest
   ```
5. PRs must include tests for changed behavior; CI must pass.

## Reporting bugs

Open a GitHub issue with: Windows version, LFMS version, steps to reproduce,
expected vs actual result, and the relevant snippet from `Logs/` (redact any
personal paths you don't want to share).

## Security issues

See SECURITY.md — please use private security advisories, not public issues.
