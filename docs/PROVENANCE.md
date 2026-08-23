# Provenance Center

Status: Phase 9 implemented and tested (272 tests passing overall).

## Package layout (`lfms.provenance`)

| Module | Contents |
| --- | --- |
| `certificate.py` | `ProvenanceRecord`, `build_record`/`record_from_item`, TXT/JSON writers |
| `verify.py` | `verify_parameters` / `verify_item` — fingerprint re-verification |

## Certificates

A certificate records the full lineage of one generated item:

- App + generator versions, creation timestamp, schema version.
- Library identity (id/title/kind), fingerprint, duration.
- Composition facts: BPM, key, repetition score.
- Full generation parameters (JSON dict).
- Optional measured loudness block and QC status.
- License note (default: locally generated, no third-party samples,
  royalty-free to the creator under their LFMS license).

`record.to_text()` renders a printable certificate; `to_json()` produces
machine-readable output; `write_certificate(record, dir, fmt)` writes
`LFMS-cert-<title>-<fingerprint>.txt|json`.

## Verification

Generation is deterministic per parameter set, so lineage is provable:
`verify_item(item)` parses the stored `params_json`, recomposes with
`Composer`, and compares the fingerprint. Results are honest data
(`VerifyResult.ok/message/recomputed_fingerprint`) — mismatch means the
audio does not match its certificate. Items without fingerprint or usable
parameters report why they cannot be verified instead of pretending.

## UI (`Export & Provenance` page)

- Combo of all library items that carry generation parameters.
- Live provenance summary (fingerprint/BPM/key/params/license).
- **Verify fingerprint** button — recomposes and reports VERIFIED/FAILED.
- Save certificate as TXT or JSON (folder dialog; tests/scripts use
  `save_certificate_to_dir(dir, fmt)` directly).

## Honest limitations

- The Export page does not render WAV/MP3 yet: there is no offline
  renderer that turns a symbolic `Composition` into audio (the Phase 6
  MixBus renders stems/sources, not compositions). Rendering + mastering
  hand-off remains the biggest open item before v1.0.0's export promise.
- PDF export was declared optional and is not implemented.
- Licensing is provenance-only: LFMS asserts what it generated and how;
  it does not perform third-party content detection.
