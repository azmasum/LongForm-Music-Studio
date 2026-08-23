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

## Export pipeline (`lfms.exporter`)

`export_item(service, item_id, output_dir, preset=…)` completes the MVP loop:

1. Recompose from the item's stored parameters (`Composer`).
2. Offline-render the raw mix (`CompositionRenderer`, ~10x realtime).
3. Auto-master to the chosen preset (YOUTUBE/PODCAST/EBU_R128/
   BACKGROUND_BED).
4. Write the delivery file (WAV or FLAC), delete the raw temp file.
5. Run QC gates on the mastered audio.
6. Register the export in the library (measurement fields + `export`,
   `target:*`, `fp-source:*` tags).
7. Write a provenance certificate next to the delivered file.

The Export page drives this end-to-end with a preset picker and output
folder; progress reports through the status bar.

## Honest limitations

- Single exports on the Export page run synchronously on the GUI
  thread; the Batch page (Phase 11) runs the same pipeline off-thread.
- PDF certificates optional → not implemented.
- Licensing is provenance-only: LFMS asserts what it generated and how;
  it does not perform third-party content detection.
