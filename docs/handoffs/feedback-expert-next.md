# Handoff: FeedbackExpert — next tasks (still Phase B)

**Lane:** Ferrari plan → can hand mechanical parts to Toyota. **Do not start until read.**
This records the direction set at end of the prior session. We are **still heavily in Phase B**;
**Phase C (Canvas write-back) stays in the magazine** — not yet, but it's the end state.

## Where we are (already built, on `dev`)

FeedbackExpert exists with: pseudonym vault (`api/feedback_vault.py`), pseudonymize/re-identify +
drop-folder pipeline (`api/feedback_pipeline.py`), outbound PII safety gate
(`api/feedback_safety.py`), OpenRouter client (`api/openrouter_client.py`), routes
(`api/webui/routes/feedback.py`), and a two-lane page (`feedback_expert.html`: "own LLM tool" vs
"OpenRouter"). All offline-tested. The current entry point is **CSV-drop-folder first** and
**pseudonymize-first** — that's what the reframe below changes.

## The reframe (why this handoff exists)

We've been **over-anchored on New Quizzes ambiguity**. But **Assignments WORK via the API today**
(PAT in active courses — proven; submissions readable even in past course `109045`). So the
**headline flow should be assignment-driven and guided**, not CSV/drop-folder-driven. And
**pseudonymization should move to an internal pipeline stage** — the user shouldn't start there.

### Target UX (the thing to build)

A single guided panel:

> **Select Course → Select Assignment → Select AI-TA → Select Rubric → Select Feedback Pattern → GO**

Then a **progress bar** running the pipeline end to end:

1. Download the assignment's submissions (text entries) from Canvas
2. Pseudonymize (internal — still hard-gated by `feedback_safety` before anything leaves)
3. OpenRouter scores + drafts feedback (cost-confirmed)
4. Re-identify

…ending with **a link to open the feedback/scoring for review** + a **"Push to Canvas" button**
(the Push is Phase C — wire the button now but the actual write-back stays deferred; until then it
can be disabled/"coming soon" or just produce the ToEnter CSV).

The existing **CSV drop-folder lane stays** as the path for **New Quizzes** (which still can't be
API-fetched) and for **"my own LLM tool"** users. The new guided flow is the automated,
Assignments-first headline.

## Tasks (ordered)

1. **Assignment-driven guided flow + progress bar.** New UI: course picker → assignment picker
   (reuse `GET /api/assignments-full` from `routes/reports.py`) → AI-TA → Rubric → Feedback Pattern
   → GO. Because there's no file upload (selections only), use **SSE** for the progress bar —
   clean GET stream, none of the upload+SSE friction we hit before. New route e.g.
   `GET /api/feedback/run/stream?course_id=&assignment_id=&ai_ta=&rubric=&pattern=`.
   Orchestrate existing pieces:
   - Fetch submissions: mirror `api/portfolio_service.py::build_merged_portfolios` /
     `student_packet.build_packet` (the `/students/submissions?include[]=assignment` call).
   - Pseudonymize submissions into the **same bundle shape** as
     `feedback_pipeline.pseudonymize` (write a sibling `pseudonymize_submissions` keyed by the
     vault on `canvas_id`; item = assignment, prompt = `assignment.description`,
     response = `submission.body`, possible = `points_possible`).
   - Gate: `feedback_safety.scan_payload` MUST pass green before the OpenRouter call (even though
     pseudonymization is now "internal", the hard block stays).
   - Score: `openrouter_client.score`; re-identify: `feedback_pipeline.reidentify`; write ToEnter +
     `_audit`.

2. **Pre-built AI-TA persona library + dropdown + custom.** Today persona is a single synced
   `{name, personality}` (`config.get/set_ai_ta_persona`). Make it a **library**: ship a handful of
   ready-made personas (name + personality), present a **dropdown** + a "create your own" option;
   selected persona drives the contract/disclosure. Storage: synced (travels with the teacher).

3. **Define + build "Feedback Pattern".** New concept the teacher named, distinct from the rubric.
   A Feedback Pattern = the **pedagogical shape of the narrative feedback** (e.g. Glow/Grow,
   Two-Stars-and-a-Wish, WWW/EBI, Praise-Question-Polish, "one concrete next step", tone/length).
   Decide: data shape, a prebuilt set, custom creation, where stored (synced), and how it's injected
   into the scoring contract (`feedback_pipeline.build_contract_text` /
   `openrouter_client.build_request`). Selectable in the guided flow.

4. **Stop leading with New Quizzes.** Make course/assignment selection the prominent first action;
   demote the CSV/NQ drop-folder to the clearly-labeled secondary (NQ + own-tool) path.

5. **Pseudonymization as an internal stage.** Reposition it out of the user's step 1 in the guided
   flow (it runs inside the pipeline). Keep it user-visible only in the manual/own-tool lane.

## Reuse (don't rebuild)

- Submissions fetch: `api/portfolio_service.py`, `api/student_packet.py`, `routes/reports.py`
  (`/api/assignments-full`, `_canvas_get_all`).
- Pipeline: `feedback_pipeline.{pseudonymize,reidentify,reidentified_csv}`,
  `feedback_safety.scan_payload`, `openrouter_client.{build_request,score,estimate_tokens}`,
  `feedback_vault.Vault`.
- SSE pattern: `deps._sse` + `StreamingResponse` (see `routes/reports.py` packet stream).
- Rubrics: `deps.list_rubric_files()`. Persona/config: `webui/config.py`.

## Open questions / decisions for next session

- **Feedback Pattern**: exact schema + the prebuilt set (needs a quick teacher gut-check).
- **"Push to Canvas" now or stub?** Recommend stub/disabled this round (Phase C), flow ends at
  review + ToEnter. Confirm with the teacher.
- **Progress granularity**: per-student SSE lines vs a coarse bar. Per-student is cheap and matches
  the existing packet stream.
- **Multiple attempts / ungraded** handling on assignment submissions.

## Guardrails (unchanged, non-negotiable)

Only pseudonymized payloads leave the machine; the safety gate hard-blocks non-green even when
pseudonymization is "internal". Vault + OpenRouter key stay synced-private / keyring, never the
repo. Disclosure on by default. Cost-confirm before paid calls. See `CLAUDE.md` + the
`feedbackexpert` memory.

## Verification (mostly testable now — the win of going Assignments-first)

- Offline: `pseudonymize_submissions` round-trip + safety-green on a synthetic submissions fixture;
  OpenRouter call mocked.
- Live: run the guided flow against a real course assignment (e.g. past course `109045`) → confirm
  download → pseudonymize → (with a key) OpenRouter → re-identified review output. Only the final
  **Push to Canvas** is Phase-C / deferred.
