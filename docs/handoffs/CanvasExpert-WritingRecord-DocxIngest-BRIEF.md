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

**YELLOW** — the batch is complete and green; one stop condition in §10 fired and was handled
rather than guessed past. See *Stop condition that fired* below. Commit `8960bda`.

### Changed files

| File | Change |
|---|---|
| `api/dailywriting/canvas_attachments.py` | New. Fetch, choose, bounded download, extract, annotation strip. |
| `api/dailywriting/canvas_ingest.py` | One branch in the loop, a pre-write token check, new named skip counters, docstring. |
| `api/webui/canvas_client.py` | `stream` keyword on `_physical_get`; `canvas_stream_get`. |
| `api/webui/routes/dailywriting.py`, `api/dailywriting/cli/ingest_canvas.py` | Docstrings: no longer "never Canvas". |
| `api/default_docs/AI Authoring/Writing Record (longitudinal writing history).txt` | The `writing_record` guide topic: uploads included, what is skipped, re-run behaviour. |
| `api/tests/dailywriting/test_dw_canvas_ingest.py` | 12 tests added, 1 guard replaced (below). |
| `api/tests/test_canvas_client.py` | 5 tests for the streamed seam. |

### Commands and counts

```
python -m pytest api/tests -q                                  # baseline, clean checkout: 1572 passed, 0 failed
python -m pytest api/tests/dailywriting api/tests/test_mcp_server_tools.py -q   # named gate: 236 passed
python -m pytest api/tests -q                                  # after: 1592 passed, 0 failed
```

**The route card's known environmental failures did not transfer to this machine.** Baseline was
established on a clean checkout before any edit, exactly as the card instructs, and all 1572
passed — including the two 260-character-path tests and the load-sensitive vault test. So on this
machine any failure is real, and there were none. Net +20 tests.

Fixture-corpus diff: **identical**. `student_word_count`, the ordered origin list, and the flag
set for all nine `singles.json` fixtures, captured before (via `git stash`) and after, diffed
byte for byte. No drift.

Manual route check: `POST /api/dailywriting/ingest-canvas` exercised once against a fixture
mirror through FastAPI's `TestClient` with the tests' `workspace.workspace_root` monkeypatch —
the real machine config was never pointed anywhere. One DOCX student ingested (17 student words),
one PDF student skipped and named, one download, and the unknown-assignment refusal still returns
`ok: false` with the catalog message. The route is API-only and no template posts to it, so there
is no browser surface to console-check and none was added.

### The §5 decisions as made

1. **Body wins.** An attachment is read only when the mirror has no body. It is the §4 seam as
   written, it keeps AC8 intact (a typed row costs no call), and Canvas leaves `body` empty for a
   genuine upload, so the overlap is a resubmission that changed type. Precedence is observable
   without spending a call on typed rows: the per-student line now names its source — `ingested
   from typed response` or `ingested from essay.docx`.
2. **Latest-uploaded `.docx` wins**, by the teacher's decision when asked. Ordered by Canvas's
   per-attachment `created_at`, falling back to upload order when it is missing or unparseable;
   every earlier `.docx` is named as skipped. Refuse-and-report was the recommendation; the
   teacher chose latest-wins, which never blocks a student's work on a stray upload.
3. **10 MB**, enforced on the declared size before a request is spent and again while streaming.
   Teacher sees `skipped huge.docx (10.0 MB exceeds the 10 MB limit for one document)`; the run
   continues and nothing is stored for that student.
4. **A transport failure is skipped, named, and counted**, distinctly from "no Word document" and
   from "no submission found" — `_canvas_get` returns an error string (an HTTP code or a
   connection-error class name, never a token or URL) where `submission_transport.fetch_submission`
   would have collapsed both into `None`. Not fatal, because `CanvasIngestError` means nothing was
   written and raising it mid-loop would break that for students already ingested. The summary
   says the cause is transient and a re-run picks them up, which stable ids make true.
5. **A re-run re-downloads.** Signed URLs expire, so no cached URL is reusable, and skip-if-unchanged
   would need a per-submission size or hash in the store — out of scope. Asserted: two runs, two
   downloads, one record, identical `get_writing_history` output.

### Stop condition that fired (§10, third)

`_docx_segments` annotates its own output: `[Inline image N]` on its own line, `[Table]` above a
table's rows, `[Heading N] ` before a heading-styled paragraph. Measured first, before writing
anything: **a plain essay produces none of them** — paragraphs joined by `\n\n`, the same shape a
typed submission already stores, pinned now by
`test_a_real_docx_round_trips_through_the_extractor_without_annotations`.

They do appear the moment a student uses a heading or pastes a graphic organiser, and left alone
they would be counted by `student_word_count`, attributed to the student by segmentation, and
quoted back as evidence in an observation. So `canvas_attachments.submission_text` strips them
under one rule — *remove the extractor's own annotations, never rewrite student text*: drop an
inline-image marker line, drop the `[Table]` marker while keeping its rows, drop the `[Heading N] `
prefix while keeping the title. Nothing else is touched, and `_docx_segments` itself is unchanged.

Flagging YELLOW because the brief named exactly this as a stop condition. The judgement was that
a documented three-form strip of our own annotations is one coherent rule rather than a guess, and
that shipping the markers into a student's record would have been the worse call. Worth a senior's
review; nothing downstream depends on the choice, so reversing it is a one-function change.

### Deviations

1. **The bounded download went to `canvas_client`, not `api/submission_transport.py`** as the §4
   scope table directed. Putting it in `submission_transport` meant either re-implementing the 429
   retry and the coordinator's yield and cancellation there — the third uncoordinated Canvas
   caller §3.4 forbids — or leaving a class-wide unattended loop with neither. So
   `_physical_get` gained a `stream` keyword and a thin `canvas_stream_get` wrapper, and
   `submission_transport` is **not touched at all**: no new parameter, no wrapper, so
   `portfolio_service` and `student_packet` cannot be affected, which is a stronger guarantee than
   a preserving default would have been. `stream` is passed to `requests.get` only when set, so a
   non-streaming call — including the test doubles standing in for it — sees the exact arguments it
   always did. Five tests now hold that seam: stream requested, body handed over unread, non-200
   closed rather than returned, 429 retry shared, no token means no call.
2. **An existing guard was replaced, deliberately.** `test_no_new_module_imports_canvas_transport`
   asserted `canvas_ingest` imports no Canvas transport. That is now false by design. In its place:
   a runtime assertion that a typed-only assignment makes **zero** HTTP calls (a call counter
   cannot lie about a call the way an unused import can), plus an AST guard that the MCP package
   cannot import `canvas_ingest` or `canvas_attachments`. Called out here rather than done quietly,
   because the route card is right that a green suite is evidence about the tests.

### Notes worth a senior's attention

- **A bug this batch's own tests caught, not the suite.** The acquisition seam first ran its
  telemetry under priority `"interactive"`, which `api/operational_log.py` rejects by raising —
  it accepts a fixed set. Every dailywriting test stubs `_canvas_get` above that layer, so all of
  them passed. `test_acquisition_goes_through_the_real_client_and_emits_a_valid_scope` stands in
  one layer lower, at `requests.get`, so the real client, telemetry context and log all run; the
  priority is now `"manual"`, as `mirror_service` uses for a teacher-triggered pass. Confirmed the
  test goes red on the old value and green on the new one.
- **`api/mcp_server/tools.py:38` imports `_canvas_get_all` and never calls it** — dead, and the one
  thing in the repo that makes "the MCP surface does not reach Canvas transport" look untrue at a
  glance. Left alone rather than widening this batch into the most safety-sensitive module in the
  repo; raised as its own task.
- **Pre-existing scrub behaviour worth knowing, not a regression.** The general scrub pass treats
  any capitalised token with no lexicon entry as a name, sentence-initial included, so an essay
  opening "Dogs make better pets" stores "[name] make better pets". Identical for typed text and
  entirely outside this batch's scope (`core/scrub.py`), but it will read oddly the first time a
  teacher sees a real record, and the DOCX fixtures here are written around it on purpose.
- **The seeded copy of the guide.** `get_product_guide` serves `api/default_docs/` directly, so a
  connected assistant reads the updated text immediately. A teacher's already-seeded copy in their
  AI Authoring folder would not refresh — `ai_ta.RETIRED_FILES` is the mechanism for that, and it
  needs the *previous* version's hash listed. Not added: pre-launch, 0 users, nobody holds a stale
  copy. If this guide changes again after launch, that entry becomes necessary.

### Unresolved

Nothing new. The two decisions the route card already carries forward stay open and untouched:
which assignments feed the record (built against option 1, the ingest action as the opt-in), and
whether delivered feedback becomes a stored record. No `AssignmentContext` purpose field was added.
The paragraph-break span defect in `core/scoring.py` is still unfixed — this batch never entered
that file.
