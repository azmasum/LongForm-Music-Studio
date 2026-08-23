# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | development — best effort |

## Reporting a vulnerability

Use GitHub **private security advisories** for this repository. Do not open
public issues for security problems.

## Security design rules enforced in code review

- No execution of arbitrary files from project/preset data; `.lfms` and preset
  JSON are validated on load.
- API keys are never hardcoded; they are read from environment variables or
  OS-protected storage, and never written to logs or crash reports.
- User audio and projects stay local; any network feature requires explicit
  opt-in (privacy.local_only_mode defaults to ON).
- SQL access uses parameterized queries exclusively; sort/filter expressions
  are whitelisted.
