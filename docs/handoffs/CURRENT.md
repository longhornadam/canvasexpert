# Make report comment provenance honest and its sidecar atomic

> **DEEPSEEK EXECUTION AUTHORITY.** Read `AGENTS.md`, this file, and only the references
> routed below. Do not read `NEXT_BATCH.md`, `HANDOFF_TEMPLATE.md`, or `archive/`.

Status: **READY**

Risk: **medium** - private Student Reports/portfolio metadata and fallback selection only; no
Canvas write or rendered DOCX contract changes.

Depends on: commit `f482042` (accepted 02 Home comment-aware reads)

## Teacher-visible result

Reports use local comments only inside the same bounded freshness policy as Home. Their private
source manifest reports the oldest required scope timestamp and cannot be torn by interruption.

## Acceptance criteria

- [ ] The shared report join requires current typed assignments plus current
      `PRIVATE_SUBMISSION_COMMENTS` at the configured serve-age bound; otherwise it preserves the
      existing live Canvas fallback.
- [ ] `_source_manifest.json` reports `source=mirror` only for that local path and uses the
      minimum assignment/comment-inclusive timestamp; fallback remains `source=canvas` with no
      claimed sync timestamp.
- [ ] Missing/corrupt/aged comment state cannot be labeled mirror-current.
- [ ] `write_source_manifest` writes a same-directory temporary file, flushes and fsyncs it,
      then `os.replace`s the destination; failure leaves the prior destination readable and
      cleans the temporary file best-effort.
- [ ] DOCX content, evidence fetches, `_manifest.json` dedupe behavior, report roots, and private
      manifest allowlist remain unchanged.
- [ ] The named acceptance gate passes.

## Explicit non-goals

- New manifest fields/schema, rendering provenance into DOCX, comment write invalidation,
portfolio/report UI changes, or changes to signed-URL/evidence ownership.

## Locked decisions

- Reuse the dedicated comment scope's existing normalized rows; do not join a third duplicate
  submission read. Apply `mirror_queries._serve_max_age_hours()` consistently to assignment and
  comment scopes.
- Keep manifest entry keys exactly `course_name, source, synced_at, generated_at`.
- Implement atomic replacement locally in `report_local_reads.py`; do not introduce a generic
  persistence abstraction. Temp files contain private data and must stay in `dest_dir`.
- Update test mirror fixtures by recording comment state current; do not weaken prior assertions.

## Scope

- `api/report_local_reads.py`
- `api/tests/test_report_local_reads.py`
- `api/tests/test_student_packet.py`
- `api/tests/test_portfolio_service.py`
- `api/student_packet.py` or `api/portfolio_service.py` only if an unchanged call signature
  requires a mechanical adjustment; otherwise do not edit them

## Read only these references

- `AGENTS.md`; this promoted brief
- `docs/reference/canvasmirror-1.0beta-information-spine.md`: §11.7 only
- `api/mirror/read_service.py`: assignment and comment scope readers
- the exact files under Scope

Do not read archived handoffs, unrelated report routes, or the whole vision document.

## Preflight - stop if these facts are false

```powershell
rg -n "def _joined_course_records|def local_course_freshness|def write_source_manifest" api/report_local_reads.py
rg -n "_source_manifest|local_course_freshness" api/tests/test_report_local_reads.py api/tests/test_student_packet.py api/tests/test_portfolio_service.py
rg -n "PRIVATE_SUBMISSION_COMMENTS" api/mirror/read_service.py
```

- Both report generators still share `report_local_reads` and the manifest schema is unchanged.
- The writer still uses a direct destination `open(..., "w")`, making this repair necessary.

## Named acceptance gate

```powershell
py -m pytest api/tests/test_report_local_reads.py api/tests/test_student_packet.py api/tests/test_portfolio_service.py -q
```

- Add aged/missing comment fallback, minimum timestamp, successful replace, and injected
  pre-replace failure-preserves-old-file tests. No broad suite.

## Stop conditions

- **RED:** honest comment freshness requires a DOCX or public response-shape change.
- **YELLOW:** Windows prevents replacing an existing closed manifest in the focused test; report
  the exact exception and keep the old file intact.

## Execution result

Record traffic light, changed files, focused command/count, deviations, unresolved decisions,
and commit hash if created.
