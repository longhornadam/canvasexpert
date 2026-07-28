# Brief — DOCX submissions into the writing record

**Active execution brief. Written 2026-07-28.** One vertical batch.
Supersedes `CanvasExpert-WritingRecord-CanvasIngest-BRIEF.md`, GREEN and closed at `401c7c0`.

**Read `docs/reference/writing-record-module-map.md` first.** It carries this subsystem's
durable state — invariants, delivered batches, open decisions, known defects, and the
verification discipline. This brief assumes it and does not repeat it.

---

## 1. Objective

A teacher points CanvasExpert at a Canvas assignment whose students uploaded Word documents,
and those essays enter the longitudinal writing record — same store, same pseudonyms, same
unscored treatment as the typed responses that already work.

`401c7c0` made typed submissions work end to end. This batch changes only **where the text
comes from**. Everything downstream — `AssignmentContext` construction, derived ids,
pseudonym resolution, roster sync, scrub, segmentation, storage — is already built and must
not be redesigned.

## 2. The one hard problem

**Uploaded files are invisible to the local mirror, by construction.** `api/mirror/store.py`
`_attempt_record` (:583) captures `attachment_names` only — filenames, never bytes, never a
signed URL — and Canvas leaves `body` empty for an `online_upload` submission. There is no
cached copy to read.

So this batch needs the writing record's first live Canvas call. That is permitted, and the
reasoning is settled — do not relitigate it:

`docs/mirror.md` Design law 6 scopes the mirror-only law to the **AI-facing MCP tools**
(`get_roster`, `get_seating_context`, `get_submissions`, `get_gradebook_snapshot`), whose
"whole path to Canvas must stay indirect." The web UI's own gradebook route already falls
back to live Canvas labelled `source: "canvas"`, and `api/portfolio_service.py` and
`api/student_packet.py` already make focused per-submission live calls. Ingest is in that
category.

**The binding constraint: ingest must never be exposed as an MCP tool.** Adding one would
put a live Canvas path under the assistant, which is exactly what the law forbids.

## 3. Locked decisions

1. **Reuse `canvas_ingest`'s existing driver.** DOCX is a text *source*, not a second
   pipeline. Same `AssignmentContext`, same `rep_id_for` / `submission_id_for`, same roster
   sync, same `ingest_unscored`, same refusals. If the shape resists reuse, that is a
   YELLOW, not a licence to fork the driver.
2. **Extraction reuses `api/powergrader/student_attachments.py`.** `_docx_segments` (:49)
   already turns DOCX bytes into plain text with tables and heading order preserved, and
   `python-docx` is a declared dependency (`api/requirements.txt:27`). Do not add a second
   DOCX reader. Note `api/portfolio.py:131` has a simpler one; prefer `_docx_segments`.
3. **The download must be bounded.** `submission_transport.download_binary` (:24-31) today
   has **no size cap, no content-type check, and no signed-URL-expiry handling** — it streams
   to disk unbounded with `allow_redirects=True`. Tolerable for one teacher-watched report;
   not for an unattended pass over a class. The new path must enforce a byte cap and refuse
   an oversized file by name. **Existing callers' behaviour must not change silently** —
   whether that means a new parameter with a preserving default, or a bounded wrapper, is
   yours; justify it.
4. **The class-wide loop must be rate-limit-aware and cancellable.** `api/webui/canvas_client.py`
   is the canonical layer: 429 retry with `Retry-After` (:104-147) and
   `mirror.coordinator.before_physical_get()` for cooperative yield and cancellation.
   `api/submission_transport.py` is purpose-built for focused fetches but builds its own
   session and has neither. Thirty sequential unattended fetches is a different risk profile
   from one report. Choose deliberately and say why; **do not add a third uncoordinated
   Canvas caller.**
5. **Only `.docx` in this batch.** A non-DOCX attachment is skipped and reported, never
   silently ignored. PDF is `LOCAL_ONLY_EXTS` on the `student_attachments` path and is
   extracted only in `api/portfolio.py`; images have no text extraction anywhere; there is
   no OCR in this repository or its dependencies. Handwriting is deferred by the teacher.
6. **Nothing writes to Canvas. No MCP tool. No scoring change.** ECRs remain unscored.

## 4. Scope and insertion points

| Change | File | Note |
|---|---|---|
| Attachment acquisition | `api/dailywriting/canvas_ingest.py` (or a sibling) | The live fetch + bounded download + extraction, behind one seam the driver calls when a submission has no `body`. |
| Bounded download | `api/submission_transport.py` | See §3.3. Smallest change that bounds the new path without altering existing callers. |
| Teacher trigger | `api/webui/routes/dailywriting.py` | The route exists. Extend it; do not add a second. |
| CLI parity | `api/dailywriting/cli/ingest_canvas.py` | Same. |
| Product guide | the `writing_record` topic + its served file | State that uploaded Word documents are included and what is skipped. |

Out of scope: `core/scoring.py`, criteria JSON, `thresholds.py`, the store, the codec,
`projection.py`, `api/mirror/`, and `api/powergrader/` beyond *calling* `_docx_segments`.

## 5. Decisions to make explicitly and record in §12

1. **Body vs attachment precedence.** A submission can carry both. Which wins, or are they
   concatenated? A wrong choice silently truncates a student's work.
2. **Multiple attachments.** One essay split across two files, or an essay plus a rubric the
   student re-uploaded. Concatenate in a stated order, take the largest, or refuse and report?
3. **The byte cap's value**, and what the teacher sees when a file exceeds it.
4. **Fetch failure handling.** `submission_transport.fetch_submission` returns `None` on any
   failure — a missing submission and a network error are indistinguishable. Batch 4 chose
   skip-and-report for an unsynced author; state whether a *transport* failure gets the same
   treatment, and why a silent skip is or is not acceptable when the cause may be transient.
5. **Whether a re-run re-downloads.** Ids are stable, so a re-ingest overwrites — but it will
   also re-fetch every attachment. Acceptable, or is a skip-if-unchanged check warranted?
   Note signed URLs expire, so a cached URL cannot be reused across runs.

## 6. Acceptance criteria

1. For a course whose mirror holds a DOCX-only assignment, one command ingests every
   uploaded essay and `get_writing_history` returns them for the right pseudonyms, in date
   order, with no `Score`.
2. A submission with a `.docx` attachment and one with typed `body` both ingest in the same
   run, and the §5.1 precedence rule is observable in the result.
3. A non-DOCX attachment is skipped **and named** in the run's output. Not silently dropped.
4. A file exceeding the byte cap is refused by name, the run continues, and nothing partial
   is stored for that student.
5. `feedback_safety.scan_payload(result, vault)["green"] is True` **and** `["soft"] == []`
   for a fixture roster whose real names appear inside the extracted DOCX text. The `soft`
   assertion is not optional — a roster name in free text is a soft finding, so `green`
   alone cannot detect a name leak. Include a positive control proving the check can go red;
   `test_dw_canvas_ingest.py`'s scrub-bypass test is the pattern.
6. Running the ingest twice produces the same `get_writing_history` output — no duplicates.
7. A transport failure for one student does not abort the others, and is reported.
8. No live Canvas call happens for a submission whose text is already available from the
   mirror. Assert it: a typed-only assignment must make zero HTTP calls.

## 7. Named verification gate

```bash
python -m pytest api/tests/dailywriting api/tests/test_mcp_server_tools.py -q
```

Plus the full `api/tests` suite. **Re-baseline environmental failures on this machine before
attributing any of them to your work** — see the route card's *Verification discipline*; the
known list is machine-specific and may not transfer.

Required in addition: the **fixture-corpus diff** (`student_word_count` and segment origins
across all of `singles.json`, before and after). Do this even if you believe you touched
nothing shared — that belief has been wrong before in this subsystem.

Manual check: this batch touches a web route. Load it, exercise it once against a fixture
mirror, confirm zero new browser console errors. **Do not point the real machine config at
a scratch workspace** — use the test fixtures and monkeypatch seams the existing tests use.

Mock every Canvas call in tests. No test may touch the network.

## 8. Explicit non-goals

- No OCR, no images, no handwriting. Deferred by the teacher 2026-07-28.
- No PDF. If ECRs start arriving as PDF, that is its own batch (`pypdf` exists in
  `api/portfolio.py` but not on the `student_attachments` path).
- No MCP tool, no Canvas write, no scoring change, no store or codec change.
- No `AssignmentContext` purpose field — see the route card's open decisions.
- Not the paragraph-break span defect, unless you are already in `core/scoring.py`.

## 9. Open decision carried forward

**Which assignments feed the record** — see the route card. Build against option 1 (the
ingest action is the opt-in), which is what `401c7c0` assumes. Do not invent a flag.

## 10. Stop conditions

Return YELLOW rather than guessing if:

- reusing `canvas_ingest`'s driver for an attachment-sourced submission requires reshaping
  the driver rather than adding a source behind a seam;
- bounding the download cannot be done without changing existing callers' behaviour;
- `_docx_segments` output needs post-processing to be usable as submission text (e.g. its
  `[Inline image N]` markers reaching the scrubber or the segmenter).

Return RED if an MCP tool, a Canvas write, or a scoring change appears necessary.

## 11. References (section-routed; do not read wholesale)

- `docs/reference/writing-record-module-map.md` — **read first.**
- `AGENTS.md` — *Non-negotiable guardrails*, *Executor responsibilities*, *Lean engineering defaults*.
- `api/dailywriting/canvas_ingest.py`, `canvas_source.py` — the driver and mapping to extend.
- `api/powergrader/student_attachments.py` — `_docx_segments` :49, `route_bytes` :147.
- `api/submission_transport.py` — `download_binary` :24, `fetch_submission` :34.
- `api/webui/canvas_client.py` — `_physical_get` :104 (429 retry, coordinator yield).
- `api/portfolio_service.py:28-61` — `_assignment_entries`, the existing fetch-and-download precedent.
- `docs/mirror.md` — *Design law 6*, which scopes the mirror-only law to MCP tools.
- `docs/reference/project-state.md` — pre-launch, 0 users, 1 through ~Dec 2026.

## 12. Execution result

_To be completed by the executor: traffic light, commit hash, changed files, commands and
counts, each §5 decision as made with its reason, the fixture-corpus diff result,
deviations, unresolved decisions._
