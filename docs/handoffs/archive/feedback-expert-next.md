# Handoff: FeedbackExpert — Phase B done, Phase C is next

> **SUPERSEDED (2026-06-21):** the active V1 is now **`feedbackexpert-name-manager-v1.md`**
> (SAFE/PRIVATE folders, aggressive scrub, fake-name pseudonyms, a Name Manager screen).
> **Automated re-identification / Phase C push is parked** in favor of a PowerGrader-manual
> model (teacher takes SAFE files to any LLM, enters grades by hand using a who-is-who
> decoder). The Phase C section below + the Feedback Scoring Contract remain as *dormant*
> code/notes; do not extend them. Read the V1 handoff for current direction.

**Lane:** Ferrari plan → can hand mechanical parts to Toyota. **Do not start until read.**

> **STATUS (2026-06-15): Phase B is BUILT and on `dev`** — assignment-driven guided flow,
> persona library (Sage/Pip/Coach Vale + custom), basic Glows & Grows pattern, two-step
> cost-gated run (`/run/prepare` → confirm → `/run/stream`). Tasks 1–5 below are **done**;
> they're kept for context. **Phase C (Canvas write-back) is now the active target** — and it
> is no longer vague: it's defined by the **Feedback Scoring Contract**
> (`docs/contracts/feedback-scoring-contract.md`), with a validator
> (`feedback_pipeline.validate_results`) and self-tests already in place. See "Phase C" at the
> bottom of this file.
>
> **Decision (2026-06-15): we are NOT attaching an OpenRouter key.** Scoring is done by *any*
> LLM/tool that emits the contract; the teacher drops the result file in `3_FromLLM/`. The
> OpenRouter lane stays in the code but is not the path we're developing. The contract is the
> seam that makes the LLM choice irrelevant.

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
   clean GET stream, none of the upload+SSE friction we hit before. **Built as two steps** so the
   paid call is cost-gated (an SSE stream can't pause mid-flight for a client OK):
   `GET /api/feedback/run/prepare?course_id=&assignment_id=&rubric_name=` (fetch → pseudonymize →
   HARD safety gate → write bundle → return token estimate; nothing paid) then, after the teacher
   confirms cost, `GET /api/feedback/run/stream?bundle_name=&persona_id=&rubric_name=&pattern_id=`
   (re-scan → score → re-identify → ToEnter).
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
   `{name, personality}` (`config.get/set_ai_ta_persona`). Make it a **library**: ship the
   ready-made personas below (name + personality), present a **dropdown** + a "create your own"
   option; selected persona drives the contract/disclosure. Storage: synced (travels with the
   teacher). **Ship these 3 starter personas (DECIDED):**
   - **Sage** — a calm, thoughtful mentor. Warm and patient; names what's working before what to
     fix; precise without being cold. Default.
   - **Pip** — upbeat and energetic; plain language, short punchy sentences. Built for reluctant
     readers — high warmth, low jargon.
   - **Coach Vale** — direct and action-oriented; frames feedback as "your next rep." Concrete,
     motivating, no fluff.

3. **Build "Feedback Pattern" — keep it BASIC for now (DECIDED).** A Feedback Pattern = the
   pedagogical shape of the narrative feedback, distinct from the rubric. The teacher's reasoning:
   *kids don't read a ton of feedback*, so keep it short and skimmable. The one shipped pattern:
   - **LLM score** derived from the selected **rubric**
   - **2–3 glows**, **1–2 grows**
   - a **2–3 sentence** overall improvement strategy
   - signed with the **AI-TA persona's name** (disclosure)

   Proposed data shape (synced storage; injected into `feedback_pipeline.build_contract_text` /
   `openrouter_client.build_request`):
   ```json
   {
     "id": "basic",
     "name": "Glows & Grows (Basic)",
     "score_from_rubric": true,
     "glows": { "min": 2, "max": 3 },
     "grows": { "min": 1, "max": 2 },
     "strategy_sentences": { "min": 2, "max": 3 },
     "sign_with_persona": true
   }
   ```
   Build the selector + injection now; the library can grow later. Selectable in the guided flow.

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

## Decisions (LOCKED by teacher — do not re-litigate)

- **Feedback Pattern**: basic only — score from rubric, 2–3 glows / 1–2 grows, 2–3 sentence
  strategy, signed by persona. Schema in Task 3 above. (Rationale: kids don't read much feedback.)
- **AI-TA personas**: ship the 3 starters in Task 2 (Sage / Pip / Coach Vale) + "create your own."
- **"Push to Canvas"**: button shipped as a disabled stub in Phase B. **Phase C now builds it for
  real** against the Feedback Scoring Contract (see Phase C section below).
- **Progress granularity**: **per-student** SSE lines (matches the existing packet stream).
- **Multiple attempts**: treat the **latest submission at the time of scoring** as the canonical
  event. (No attempt-picking UI.)
- **Late / ungraded**: **timestamp** the submission, then route through the **existing late-work
  process** (enter # of days late) rather than inventing new handling here.
- **OpenRouter model slug**: teacher will specify/verify later — not a blocker for this build
  (mock the call in offline tests; default slug may be stale).

## Guardrails (unchanged, non-negotiable)

Only pseudonymized payloads leave the machine; the safety gate hard-blocks non-green even when
pseudonymization is "internal". Vault + OpenRouter key stay synced-private / keyring, never the
repo. Disclosure on by default. Cost-confirm before paid calls. See `AGENTS.md` + the
`feedbackexpert` memory.

## Verification (Phase B — done)

- Offline: `pseudonymize_submissions` round-trip + safety-green on a synthetic submissions fixture
  (`api/tests/test_feedback_pipeline.py`); contract self-test (`validate_results` + re-identify).
- Live (optional, not our path): guided flow against a real assignment → download → pseudonymize →
  any contract-emitting LLM → re-identified review output.

---

# Phase C — Push to Canvas (ACTIVE)

**Foundation already in place (on `dev`):** the **Feedback Scoring Contract**
(`docs/contracts/feedback-scoring-contract.md`) + `feedback_pipeline.validate_results()` +
self-tests. Read the contract doc first — it defines the exact input Phase C consumes and was
proven by having an LLM (Claude) author conforming output against it.

**The flow to build** — a new `/feedback/push` path, SSE, per-student:

1. **Pick a results file** from `FeedbackExpert/3_FromLLM/` (any LLM/tool produced it in the
   contract shape). No OpenRouter involved.
2. **Validate**: `fp.validate_results(results, bundle, vault)`. Hard errors block; warnings
   (out-of-range scores, unscored students) are shown but don't block.
3. **Re-identify**: `fp.reidentify(results, vault)` → rows with `canvas_id`, `real_name`, `score`,
   `feedback`.
4. **Review preview** in-browser (real names + scores + comments). Teacher deselects any row.
   This is the human gate — nothing posts unseen.
5. **Push, on explicit confirm**, per selected row (reuse `_canvas_send`):
   ```
   PUT /api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/{canvas_id}
       submission[posted_grade] = <score>     # omit when score is null (comment-only)
       comment[text_comment]    = <feedback>  # already ends with the AI disclosure
   ```
6. **Late / ungraded** → route through the existing late-work flow (# days late), not blind-post.
7. **Audit** a pseudonymous line per push into `_audit/`.

**Constraints / decisions:**
- **Assignments only.** New Quizzes write-back stays parked (PAT/403 limit, see
  `newquizzes-pat-status` memory).
- **Explicit confirmation required** — this changes real grades and notifies students. Show a
  count ("post N grades + comments to <course>?") before any PUT.
- **Idempotency-aware** — re-running must not silently double-post; decide skip-already-graded vs
  overwrite (recommend: show current grade in the preview, let teacher choose).
- **v1 = single `score`** as `posted_grade`. Per-criterion rubric assessment is a future extension.

**Tests to write:** validator already covered; add `_canvas_send`-mocked tests for the push
(payload shape, score-null → comment-only, late routing, dry-run/preview counts).
