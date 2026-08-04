# Feature-freeze hardening initiative

**Status:** Senior context; no active direct execution brief

**Last senior review:** 2026-08-03

**Baseline:** `dev` @ `86e5caf`, `v1.0.0-beta.3`, working tree clean except
an unrelated pre-existing `README.md` edit (out of scope for this
initiative, left untouched), `api/tests` 2153 passed.

**Next batch pointer:** Batches 1-3 (§9 rows 1-3: A1/A2/A4/A6, A3,
B2/B3/B4) are all GREEN and committed; their briefs are retired at
`docs/handoffs/feature-freeze-batch1-pii-hardening.md`,
`docs/handoffs/feature-freeze-batch2-denylist-inversion.md`, and
`docs/handoffs/feature-freeze-batch3-observability.md`. Two real defects
were found and fixed along the way, outside each batch's literal scope but
squarely within the initiative's purpose — see each brief's execution
result for detail:

- Batch 2: the daily-writing MCP tool `get_writing_history` was leaking the
  real Canvas user id embedded in `submission_id` on every call (fixed with
  a one-way hash in `api/dailywriting/projection.py::_safe_submission_ref`).
- Batch 3: none beyond the batch's own scope, but the AST re-sweep found 3
  sites the mechanical B2 pattern should NOT touch (module-import-time
  emit, a circular emit-of-an-emit-failure, and normal two-format control
  flow) — see the Batch 3 brief for exactly which and why.

Next up is §9 row 4: **Batch 4 (D1, D2, D3)** — UI tightening. Read §6 D1,
D2, D3, §7, and §8 for the next brief. This batch is teacher-visible and
requires rendered browser verification for every changed route. No senior
decisions from other batches are outstanding for D1/D2/D3 specifically;
A5, A7, D1.4, D4, C sequencing, and 2.3 remain open per §10 and are not
required to promote this batch — D1.4 in particular is an explicit
"ask before generalizing" question the initiative document raises for a
*future* cycle, not a blocker for D1 itself (rubrics only, this batch).

This document is persistent senior context. It does not authorize implementation directly.

---

## 1. Why this initiative exists

CanvasExpert is feature-frozen as of 2026-08-03. The calendar is the forcing function:
teacher in-service week begins in roughly seven days, students return in sixteen, and the
teacher's own Canvas courses are not yet populated. Nothing in this initiative adds a
teacher-visible capability. Every batch either removes a way the app can be wrong, or
removes a way the app can be wrong *silently*.

The audit that produced this document ran against a green suite and a running instance.
Findings were reproduced, not inferred. Where a claim below is empirical, the reproduction
is given so a later agent can re-run it rather than trust it.

### 1.1 What the audit confirmed is sound

State this explicitly so no batch "fixes" it:

- **One pseudonym space.** `api/dataforge/identity.py` and `api/dailywriting/store/identity.py`
  both delegate to `api.feedback_vault.Vault`. There is no second identity map anywhere in
  the app. Verified by reading both modules.
- **Durable identity key.** The vault is keyed on Canvas user id, not on the pseudonym, so
  a teacher regenerating or hand-setting a pseudonym does not orphan stored records.
- **One outbound path for student data.** `openrouter.ai` is the only non-Canvas,
  non-GitHub destination, and `api/ai_transmission.py::score_openrouter_bundle` is its only
  caller. Every `requests.post`/`requests.get` site in `api/` was checked; the one that
  looks like an exception (`api/operation_ledger/adapters/assignment_whole.py:434`) posts to
  a Canvas-issued upload URL. `api/webui/self_update.py` allowlists both scheme and host.
- **Fail-closed MCP gate with sanitized violations.** `api/mcp_server/pseudonym.py::gate`
  withholds the whole payload on any hard violation and strips the offending id value out of
  the violation string before it can reach a client.
- **Operational log cannot carry PII by construction.** `api/operational_log.py` uses a
  key allowlist, so workflow data is structurally excluded. Batch B expands its *use*; it
  must not weaken this property.
- **Vault durability.** Interprocess lock, atomic write, and OneDrive conflict-copy detection
  are all present and correct in `api/feedback_vault.py`.

---

## 2. Locked decisions from the 2026-08-03 review

These are teacher decisions, not engineering preferences. Do not relitigate them in a batch.

### 2.1 In-text PII beyond names is out of scope

The audit demonstrated that a phone number, a home address, and a district student email
address all pass the outbound gate green. **The teacher ruled these non-issues:** middle-school
students do not write contact information into their assignment responses. No regex detector
for email, phone, or address is to be added. Do not add one as a "cheap win" in a later batch.

Third parties named in student writing (siblings, friends in other sections) are likewise
accepted as out of scope. The vault knows the synced rosters and nothing else, and that is
the intended boundary.

### 2.2 Student self-signatures are handled by the nickname mechanism

The real in-text pattern is a student signing their own work, often with an idiosyncratic
spelling (`- Reneeeee~~~`). The teacher's position: those self-nicknames are stable per
student, and the correct handling is for the teacher to record them as nicknames in the
Students UI, which already feeds `Vault.add_nicknames` / `set_nicknames` and therefore both
`feedback_scrub.build_replacement_map` and `feedback_safety` id/name discovery.

**Consequence for Batch A:** the nickname path is load-bearing, not decorative. Any change to
the scrub or scan must preserve nickname coverage, and the accent-folding work in A1 must
apply to nicknames as well as to `real_name` tokens.

**Noted, not scoped:** exact-match nicknames do not tolerate variable elongation, so
`Reneeeee` recorded as a nickname will not match `Reneeee` in a later essay. A senior may
choose to add elongation-tolerant matching (collapse runs of a repeated character before
comparison) as a follow-on. It is deliberately excluded from Batch A because it changes
matching semantics and the teacher has not asked for it.

### 2.3 OpenRouter's future is undecided and does not gate this work

The teacher is considering removing the OpenRouter connection entirely in favor of the MCP
path. That decision is explicitly deferred. Batch A must therefore harden the shared
primitives (`feedback_scrub`, `feedback_safety`) rather than either send path, so the work
survives whichever way that decision goes.

### 2.4 The feature is called "Routines"

Nav currently reads "Automations"; the page `<title>` reads "Routines". The teacher confirmed
**Routines** is the feature name. This settles the drift in the direction of the title, not
the nav.

### 2.5 There will be no consolidated activity view

The audit proposed a single "what did the app do" surface unifying Receipts, Operation Ledger,
PowerGrader sessions, assessment history, and routine state. **Rejected.** The teacher's
reasoning: that is an operator's mental model, not a teacher's. Teachers verify outcomes in
Canvas, which is where the result actually lands. Do not revive this.

Note the scope boundary carefully: this rejects a *teacher-facing* activity view. It does
**not** reject Batch B, which is developer-facing diagnostics with no new UI surface beyond
relocating an existing button.

### 2.6 The layering critique is accepted in full

The teacher accepted section 2 of the audit without exception, including its framing: the
app "fires up the UI" for work that has nothing to do with the UI. Batch C is authorized in
principle, subject to sequencing.

---

## 3. Batch A: PII barrier, code-side

**Goal:** make the outbound scan as strong as the scrubber it is supposed to verify, and stop
the barrier from depending on a hand-maintained list of field names.

**Files:** `api/feedback_scrub.py`, `api/feedback_safety.py`, `api/mcp_server/pseudonym.py`,
`api/dataforge/eduphoria_parser.py`, `api/webui/templates/assessments.html`.

### A1. Unicode-fold both sides of scrub and scan

**Defect.** The scrub builds `\bJosé\b` from the vault and the scan lowercases without
folding. A student typing the unaccented form is matched by neither.

**Reproduction** (throwaway vault, no real data):

```
vault: "José Flores" -> "Sparky McGee", "Renée Boudreaux" -> "Bingo Watts"

in : "Jose helped me revise my thesis."
out: "Jose helped me revise my thesis."          green, 0 hard, 0 soft  -> SHIPS

in : "My partner Renee Boudreaux said the essay was strong."
out: "My partner Renee Watts said the essay was strong."   green, 0 hard, 0 soft  -> SHIPS
```

The second case is the priority. The surname pseudonymized and the given name did not, so the
artifact reads as a plausible fake name while carrying a real one. A teacher reviewing the
Safe AI Packet has no visual cue that anything is wrong. This defeats the review step that
the whole design leans on.

**Direction.** Normalize with NFKD and strip combining marks on *both* the pattern source and
the scanned text, at every comparison point:

- `feedback_scrub.build_replacement_map` when compiling patterns from `real_name` tokens,
  the full name, and every nickname
- `feedback_scrub.scrub_text` when applying them
- `feedback_safety.scan_payload` when building `lowered_names` and when lowercasing the
  candidate text
- `feedback_scrub.verify_clean` for the same reason

Fold for *matching only*. The replacement text is the pseudonym and is unaffected; the
original text outside a match must be returned byte-identical. A fold applied to the output
would corrupt legitimate student writing, which is a worse failure than the one being fixed.

**Care point.** Folding changes offsets when a combining mark is stripped, so a naive
`re.sub` over folded text and then splicing back into the original will misalign. Either
fold-then-substitute-then-discard-the-original (acceptable: the scrubbed text is what ships),
or match on folded text and map spans back. Pick one and state it in the brief; do not leave
it to the implementer.

### A2. Make the scan token-level

**Defect.** The scrubber matches tokens (given name, surname, each nickname, each id).
The scanner matches only the *full* name string:

```python
for low, original in lowered_names.items():
    if low in t:                 # low == "josé flores"
```

So a single-token scrub miss is invisible to the layer whose entire job is catching scrub
misses. `feedback_scrub.verify_clean` already does per-token matching correctly. The gate
does not call it.

**Direction.** Scan per token with word boundaries, matching the scrubber's own granularity.
Reuse or extract `verify_clean`'s logic rather than writing a third matcher.

**Expected cost.** Soft-flag volume will rise, because single-token matches on common given
names will now fire. That is correct behavior for a *detector*, but see A5 for what soft
flags currently do, and note that this interacts with A5: raising soft volume while soft
flags are silently dropped changes nothing observable. A2 and A5 should land together.

### A3. Invert `_TEXT_FIELDS` from an allowlist to a denylist

**Defect.** `feedback_safety._TEXT_FIELDS` is keyed on field *name*. A payload string under a
key not in the set is not scanned at all. The docstring already admits the hazard
("Any subsystem that adds a new free-text field must add it here too, or the gate silently
stops covering it"). The audit shows the hazard is not theoretical:

- `api/mcp_server/tools.py` constructs payloads using **195 distinct dict keys**. Exactly
  **three** are known to the safety module (`name` forbidden, `ai_context_note` and
  `private_note` in `_TEXT_FIELDS`).
- Unscanned keys that carry free text today include `body_text` (page bodies),
  `description_text` (assignment descriptions), `title`, `label`, `group_name`,
  `section_name`, `course_name`, `message`, `reason`, `summary`, `learning_objective`.
- `_TEXT_FIELDS` contains `assignment_description`, which **no payload anywhere emits**. The
  real key is `description_text`. The single entry someone added for assignment text scans
  nothing. This is the design failing in the exact way it was documented to fail.

Verified unscanned by direct call: `notes`, `summary`, `body`, `excerpt`, `comment`, `title`,
`description_text`.

**Direction.** Scan every string value in the payload. Maintain a small explicit exemption set
for keys whose values are known-structural and high-churn (`id`, `course_id`, `synced_at`,
`state`, `source`, `workflow_state`, `updated_at`, `due_at`, digests, revisions). Everything
else gets scanned by default. The failure mode inverts from "new field silently unprotected"
to "new structural field produces a noisy soft flag until exempted", which is the correct
direction for this app.

**Sequencing note.** A3 must land *after* A1, or the newly-scanned fields will produce a wave
of accent-driven misses that look like regressions in the new code rather than pre-existing
gaps in the old.

### A4. Close the forbidden-key gap the docstring already promises

**Defect.** `api/mcp_server/pseudonym.py`'s module docstring states that
"real Canvas identity (name, sortable_name, short_name, sis_id, canvas user id, section)
never leaves this module." The gate's structural blocklist is:

```
{"name", "real_name", "canvas_id", "sis_id", "sisid", "section",
 "sectionnames", "sectionids", "sectionsisids"}
```

`sortable_name` and `short_name` are named in the promise and absent from the enforcement.
`user_id` is likewise absent, as are `login_id`, `email`, and `student_id`. A Canvas user dict
reaching a payload under `sortable_name` would pass green: the value is a name string, so
Layer 1b's known-id check does not fire, and the key is not in `_TEXT_FIELDS` so Layer 2a
does not scan it.

Nothing emits these today. The exposure is that the guarantee is carried by 45 call sites'
good behavior rather than by the gate. `api/mcp_server/tools.py:404` returns an internal dict
holding `user_id` adjacent to payload-building code, which is exactly the shape that goes
wrong during a later edit.

**Direction.** Add `user_id`, `userid`, `student_id`, `sortable_name`, `short_name`,
`login_id`, `email`, and `section_id` to `_FORBIDDEN_KEYS`. Cheap, and it makes the docstring
true. Confirm no current payload uses any of these names for a non-identity purpose before
landing; `section_id` in particular appears in tools.py and must be checked rather than
assumed.

### A5. Decide what a soft flag means on the MCP path

**Defect.** `gate()` drops soft flags silently and returns the payload:

```
scan_payload soft = [{'where': '.rows[0].text', 'name': 'Aaliyah Johnson'}]
gate() returned   = {"ok": true, "rows": [{"text": "Aaliyah Johnson forgot her chromebook."}]}
```

The exact vault name reaches the MCP client, and nothing anywhere records that it did. On the
PowerGrader path this design is right: soft means "a human decides", and a human is present.
On the MCP path there is no human in the loop at that moment.

**This is a senior decision, not an implementation detail.** Three options:

1. **Attach a non-blocking notice** to the payload so the assistant can tell the teacher.
   Preserves the read, surfaces the risk, costs a schema addition (and therefore a
   `tool_schema_v29.json` bump plus the registry-pinned `docs/mcp-server.md` update).
2. **Emit a counter** to the operational log and stay silent to the client. Zero schema
   change, gives the developer evidence, gives the teacher nothing.
3. **Leave as-is** and document it as intentional.

Recommendation: option 2 for this freeze, option 1 after the OpenRouter decision in 2.3 is
made, because that decision changes how much traffic the MCP path carries. Do not implement
option 1 during a freeze week; it touches the tool schema.

### A6. `assert_no_leaks` is a no-op in the path that has real names

`api/dataforge/eduphoria_parser.py:188`:

```python
if anonymizer is None:
    return text
```

A function named as an assertion performs no assertion whenever the run is un-anonymized,
which is the run that contains real names. The behavior is intentional (un-anonymized output
is *supposed* to carry real names) but the name misleads a reader into believing an
un-anonymized artifact was checked.

**Direction.** Rename to something honest (`scrub_or_passthrough`, or invert to
`assert_no_leaks(text, anonymizer)` raising when `anonymizer is None` and having callers not
call it in that mode). No behavior change. Documentation-grade fix, near-zero risk.

### A7. Default the Assessments pseudonymization checkbox to checked

`api/webui/templates/assessments.html:13`:

```html
<input type="checkbox" name="anonymize" value="true">
```

Unchecked by default.

**This is not a leak.** Verified in `api/dataforge/views.py:436-453`: snapshot saving and
profile publishing are both gated on `anonymize`, so an un-anonymized run writes real-name
reports only into `Student Work/Reports/DataForge`, which is inside the private wall.

**It is a silent feature-disable.** The default run produces no longitudinal snapshot and no
published standards profile, so assessment history and the MCP `get_assessment_context` tool
have nothing to read, and the UI says nothing about why. The teacher discovers this weeks
later when the assistant reports no history.

**Direction.** Default to checked. Additionally, when a run completes with `anonymize` false,
say plainly in the results view that no history was saved and no profile was published, and
why. The second half matters more than the first.

---

## 4. Batch B: observability

**Goal:** when a teacher reports a problem during the first weeks of school, the app should
have written down what happened. Today it has not.

**Files:** `api/operational_log.py` (use, not design), `api/webui/server.py`,
`api/diagnostics.py`, `Open Canvas Expert.bat`, plus the handler sites in section 4.2.

Scope guard: this batch adds **no teacher-facing surface** beyond relocating one existing
button. It does not conflict with the decision in 2.5.

### B1. The operational log is built and unused

`api/operational_log.py` is good work: rotating handler, 1 MiB cap, three backups, key
allowlist, required-field validation. It has **four call sites** in the entire application,
emitting three event names: `canvas.request`, `diagnostics.health`, `ai.transmission`.

No push, no sweep, no mirror refresh, no catalog refresh, no scoring session, no roster sync
writes anything.

**Direction.** Emit on the outcome boundaries that already exist as concepts in the code:
mirror refresh, catalog refresh, push/apply through the operation ledger, sweep, session
start/finish. Use the existing `outcome` vocabulary (`ok`/`blocked`/`failed`/`unconfigured`)
and the existing allowlisted keys. Do not add keys; if a batch needs a new key, that is a
senior decision because it is the property that makes this log safe.

### B2. Forty-three handlers swallow a real failure

An AST pass over `api/` (tests and `__pycache__` excluded) found **70 exception handlers whose
entire body is `pass`**. Categorized by whether the guarded block is best-effort cleanup
(`unlink`, `rmtree`, `close`, `terminate`):

- **27 are legitimate cleanup.** Leave them.
- **43 swallow a real failure.** These produce no log line, no operational event, no UI
  signal, and no return-value difference.

The dangerous cluster is the background mirror, which is the subsystem behind every "my
roster is stale and refresh does not fix it" report:

| Site | Swallows |
|---|---|
| `api/webui/mirror_service.py:297` | `refresh_course_context` |
| `api/webui/mirror_service.py:324` | `discovery.scan_act...` |
| `api/webui/mirror_service.py:347` | token/mirror-enabled precondition |
| `api/webui/mirror_service.py:399` | `run_coordinated_heartbeat_tick` |
| `api/mirror/sync.py:350` | `refresh_catalog_assignments_only` |
| `api/mirror/sync.py:430` | `refresh_catalog_assignments_only` |

Others worth naming: `api/dataforge/views.py:441` drops a longitudinal snapshot silently, so
`snapshots_saved` undercounts with no reason recorded anywhere;
`api/webui/routes/courses.py:261` swallows a group write; `api/webui/routes/course_catalog.py:67`
swallows receipt application.

**Direction.** Do not convert these to raising. Convert them to *recording*: one
`operational_log.emit(..., outcome="failed", error_class=type(exc))` per site. The control
flow stays exactly as it is. This is deliberately the least invasive fix that changes the
diagnostic picture, which is what a freeze week can afford.

### B3. Tracebacks go to a console nobody keeps

`api/webui/server.py:165` prints the formatted traceback to stdout. `Open Canvas Expert.bat`
does not redirect stdout to a file (verified: no redirection in the launcher). The teacher
closes the window and the only copy is gone.

**Direction.** Write tracebacks to a rotating file beside `operations.jsonl` under
`%LOCALAPPDATA%\CanvasExpert\Logs\`. Keep the existing `print` for live debugging.

**Care point.** This file is the one artifact in the app that may contain arbitrary strings
from anywhere in the process, so it is *not* subject to the `operational_log` key allowlist
and must never be treated as safe-by-construction. It must therefore be excluded from any
automatic upload path and included in the support bundle only via the teacher's explicit
action, which B4 already requires.

### B4. The support bundle contains no errors

`api/diagnostics.py::build_support_bundle` produces exactly three members: `health.json`
(configuration booleans), `manifest.json` (versions), `operations.jsonl` (see B1). The
artifact designed for "teacher hits a bug, sends a bundle" contains no traceback and no
record of recent actions.

Its only entry point is `api/webui/templates/connections.html:116`, on the CanvasAgent page
under "Advanced & other clients".

**Direction.** Add the B3 traceback file as a fourth member. Move or duplicate the button to
Settings under "About this app", where someone with a problem will look. Given B3's care
point, the bundle description should say plainly that the log may contain error text from
anywhere in the app and should be reviewed before sending.

---

## 5. Batch C: layering

**Goal:** stop the domain layer from depending on the web layer. Accepted in principle
(2.6); sequencing is the open question.

### C1. `api/webui` is the platform layer

**62 modules outside `api/webui/` import from it.** By target:

| Imported from `api.webui` | Sites |
|---|---|
| `workspace` | 28 |
| `canvas_client` | 11 |
| `config` | 8 |
| everything else combined | ~15 |

Those three modules are the application's foundation: workspace path resolution, Canvas HTTP,
and settings. They live inside the web package, so `api/dataforge`, `api/powergrader`,
`api/mirror`, `api/operation_ledger`, and `api/mcp_server` cannot be imported, tested, or
reasoned about without pulling in the web layer. The MCP server, the surface most in need of
being self-contained, imports the FastAPI application's package to do its job.

**Direction.** Move `workspace`, `config`, and `canvas_client` to `api/` (or a new
`api/platform/`) and leave thin re-export shims at the old paths so the 62 call sites can
migrate incrementally rather than in one commit. `api/runtime_paths.py` already indirects
through `_workspace_module()`, which suggests the seam was anticipated.

**Sequencing.** This is the highest-value item in the initiative and the wrong thing to do in
the seven days before in-service week. It touches import lines in ~62 files, which is exactly
the change that looks safe, passes tests, and breaks a packaged ZIP on a district machine in a
way no test covers. **Recommend deferring C entirely until after the semester starts and the
live-run deferral in the 1.0beta closeout is resolved.**

### C2. Cross-package private imports

Eight sites reach past a module boundary into an underscore-prefixed name. The boundary
declares these private; nothing pins their signatures; no test covers them as contracts.

| Importer | Reaches into |
|---|---|
| `api/gradebook_queries.py:4` | `webui.canvas_client._canvas_get, _canvas_get_all` |
| `api/powergrader/canvas_fetch.py:18` | `webui.canvas_client._canvas_get, _canvas_get_all, _canvas_headers` |
| `api/powergrader/new_quiz_fetch.py:23` | `webui.canvas_client._canvas_headers` |
| `api/powergrader/late_catchup.py:6` | `webui.schooldays._parse_iso_local, _school_days_late_detail` |
| `api/powergrader/student_attachments.py:16` | `webui.source_material_extractors._collapse_ws, _decode_bytes` |
| `api/mirror/sync.py:35` | `course_catalog._error_code` |
| `api/report_local_reads.py:30` | `work_registry.providers.home_attention._PROVEN_STAFF_ROLES, _author_role` |
| `api/feedback_pipeline.py:7` | `feedback_contract._REVIEW_NOTE, _safe` |

(Same-package `_common` / `_io` imports under `api/dailywriting/cli/` and `api/webui/config/`
are correct and excluded.)

**Direction.** Promote each to a public name on the owning module. Mechanical, independently
landable, and it can proceed *without* C1 as a smaller standalone batch if the senior wants
some of C's value during the freeze.

### C3. Fifty-four in-function imports

`grep` finds 54 imports of `api.*` nested inside function bodies. Each is an import cycle that
was worked around rather than broken, and each converts an import-time failure into a
runtime failure, which on a teacher's machine means it surfaces mid-task instead of at
startup. Diagnostic only for now; C1 will resolve a meaningful share of them.

### C4. Module size is wrong in both directions

- `api/mcp_server/tools.py`: 2696 lines, all 45 tools in one namespace. A helper added for one
  tool is in scope for all 45, and the safety gate is applied per-function *by convention*
  rather than enforced by structure. Batch A3 reduces the consequence; it does not fix the
  shape.
- Also large: `api/dataforge/eduphoria_parser.py` 1558, `api/mirror/store.py` 1209,
  `api/panel_themes.py` 1203, `api/webui/school_calendar.py` 1203.
- The opposite failure: `routes/gradebook*.py` is 8 files, `routes/roster*.py` 6,
  `routes/powergrader*.py` 4, `routes/routines*.py` 3. Split by size rather than by seam, so
  one feature change touches several files and no file owns a concept.

No action proposed this cycle. Recorded so a later senior does not rediscover it.

---

## 6. Batch D: UI tightening

Small, teacher-visible, low-risk. The best candidate for freeze week.

### D1. PowerGrader rubrics: synced Library only

**Teacher decision (2.x, confirmed this session):** the rubric picker looks in the synced
`Library/Rubrics` folder and nowhere else.

**Current behavior.** `api/runtime_paths.py:133-134` appends `api_root() / "rubrics"` to the
rubric folder list unconditionally. `api/webui/deps.py:200` dedupes by *absolute path*, so the
workspace copy and the bundled copy both survive; and labels via
`os.path.relpath(path, REPO_ROOT)`, which for an out-of-repo file produces
`..\..\Documents\OneDrive - Pearland ISD\CanvasExpert\Library\Rubrics\ELA_STAAR_ECR_Rubric.txt`.

Observed live: four rubrics rendering as eight entries, on the first screen of the grading
flow.

**Why this is safe to remove.** `api/webui/workspace.py:764-768` seeds `Library/Rubrics` from
`default_docs/Rubrics`, falling back to `api/rubrics` (`_default_rubric_files`). The workspace
copy *is* the seeded copy. The repo folder is a redundant fallback, not a source of anything
unique.

**Direction.**
1. Remove `api_root() / "rubrics"` from `content_folders("rubric")`.
2. Fix the label in `_list_txt_files` to show the file's own name (and, if disambiguation is
   ever needed, its folder), not a path relative to the repo root.
3. **Specify the unconfigured-workspace case explicitly.** With the repo fallback gone,
   `library_folder("Rubrics")` returning `None` yields an empty list. Show an empty picker
   with a pointer to workspace setup. Do **not** silently fall back to repo copies. This app
   already has one bug of exactly that shape on record (the vault CWD fallback that mints
   pseudonyms into `./_System` when no workspace is configured); do not add a second.
4. Decide whether the same treatment applies to `quiz`, `assignment`, and `page`, which also
   mix `api/qf_materials/` examples with the Library. The teacher's instruction named rubrics
   specifically. **Recommend rubrics only this cycle**, and ask before generalizing, because
   the quiz/assignment example files may be doing real work as templates.

### D2. Rename Automations to Routines

Per 2.4. Six user-facing sites plus one authoring doc:

- `api/webui/templates/layouts/_app_header.html:15` (nav)
- `api/webui/templates/dashboard.html:56, :58`
- `api/webui/templates/gradebook.html:22, :386` (tab label and heading)
- `api/webui/templates/routines.html:7` (page header; the `<title>` already says Routines)
- `api/default_docs/AI Authoring/START HERE - CanvasAgent.txt:187`

**Care point.** `_seed_folder_if_missing` skips any file that already exists in the workspace,
so editing the seeded CanvasAgent text does **not** reach an existing teacher's workspace.
`api/webui/ai_ta.py` carries `RETIRED_FILES` and hash machinery for exactly this class of
problem. Check whether the Settings "Rebuild" action regenerates this file before assuming the
edit propagates; if it does not, this rename is cosmetic for existing installs and that should
be stated rather than discovered.

Also check whether `nav_section == 'automate'` is worth renaming. It is internal; recommend
leaving it to keep the diff small.

### D3. Raw internal slugs in the work rail

`api/webui/static/course_expert/work_rail.js:74-76` renders `job.kind` verbatim as an item's
description. Live on Home and Create right now:

```html
<a class="ce-work-rail-item ce-work-rail-attention" href="/routines">Routine attention
  <span class="ce-work-rail-item-desc">routine_state</span></a>
```

Known kinds: `routine_state`, `operation_receipt`, `grade…`, `late…`, `roster…`.

**Direction.** Map kind to a teacher-legible phrase in the provider (server side, where the
kind is authoritative), not in JS. Emit a `description` field and have the rail render that,
falling back to nothing rather than to the slug.

### D4. Start-of-year readiness on Home

The teacher is currently in the app's blind spot: token configured, no courses, no school
calendar. Six of eight nav destinations dead-end on "pick a course". The two surfaces that
work fully without Canvas, **Calendar** and **Create (draft and validate)**, are the two most
useful this week, and nothing points at either.

Gradebook and Calendar each warn correctly *in place* ("No school calendar configured, every
day counts as instructional until one is set up"). Home, the page actually opened first, says
nothing.

**Direction.** One readiness block on Home that names the unmet precondition and links to the
page that fixes it, in the same voice the Gradebook warning already uses. This is the only
item in Batch D that adds anything, and it is a card, not a feature.

**Senior call needed.** This edges against the freeze. Recommend including it: it is the
single highest-value teacher-visible item for the next sixteen days, and it is additive to one
template.

### D5. Deferred cosmetics

Recorded, not scheduled:

- Page-title separators run three ways: 19 pages use an em dash, Home uses `·`, Panels uses
  `-`. The em dashes also contradict the project's own no-em-dash rule.
- Gradebook appears in no nav; it is reachable only from Home and PowerGrader.
- The Writing Timeline is write-only inside the app: `api/webui/routes/dailywriting.py`
  exposes exactly one route, a POST. Reading requires an assistant calling
  `get_writing_history`. This is the intended assistant-first design, but a teacher with no
  assistant connected can feed it all year and never see it. No action proposed; flagged so a
  later senior does not read it as a bug.

---

## 7. Non-goals

Do not do these. Each was considered and rejected this cycle.

1. Regex detection of email, phone, or postal address in student writing (2.1).
2. Any handling of third parties named in student writing (2.1).
3. A consolidated teacher-facing activity or audit view (2.5).
4. Removing the OpenRouter path (2.3, deferred, not rejected).
5. Elongation-tolerant nickname matching (2.2, noted, not scoped).
6. Splitting `api/mcp_server/tools.py` (C4, recorded only).
7. Any MCP tool schema change during freeze week (A5 recommendation).
8. Converting silent exception handlers into raising handlers (B2 records, it does not
   change control flow).

---

## 8. Verification discipline

- `python -m pytest api/tests -q` is the gate. Baseline is 2132 passed. A batch that reduces
  the count without deleting a test is a regression.
- Batch A must add tests that fail against `b8bb5e7`. At minimum: the accented-given-name
  pass-through, the hybrid `Renee Watts` output, a payload string under an unlisted key, and
  a `sortable_name` key reaching the gate. Copy the seeded-vault approach used in the audit;
  it needs no fixtures and no real data.
- `api/tests/conftest.py` isolates tests from real workspace data. Any new test that touches
  the vault must go through it. Do not write a test that reads the teacher's real
  `_System/Identity Vault/vault.json`.
- Batch D changes are rendered-output changes. `api/tests/test_presentation_contracts.py` and
  `api/tests/test_webui_template_contracts.py` are the relevant guards. Note that
  `EXPECTED_PRESENTATION` covers 14 routes and omits `/panels`, `/connections`, and
  `/seating`, so template changes to those three are unguarded; verify them by rendering.
- Rendered verification catches things the suite does not. Both defects fixed in the canonical
  calendar work (`1ab2f89`) were found by looking at the page, not by a test. Look at the
  page.
- The MCP tool count and schema version are pinned by a test against `docs/mcp-server.md`.
  Any tool-surface change must update both.

---

## 9. Recommended sequencing

Constraint: in-service week starts in ~7 days, students in ~16, courses not yet populated,
one developer.

| Order | Batch | Rationale |
|---|---|---|
| 1 | **A1, A2, A4, A6** | Highest risk, smallest diff, all in two pure-stdlib modules with no UI surface. A1 alone retires the hybrid-name failure. |
| 2 | **A3** | Must follow A1. Larger blast radius; expect soft-flag noise before exemptions settle. |
| 3 | **B2, B3, B4** | After this the app can be diagnosed remotely. Everything shipped later becomes cheaper to support. |
| 4 | **D1, D2, D3** | Teacher-visible, hours not days, no architectural risk. |
| 5 | **A7, D4** | Both touch behavior a teacher will meet in week one. |
| 6 | **B1** | Broader emit coverage; valuable but not urgent once B2 lands. |
| last | **C** | Defer past the start of the semester. C2 alone may be promoted early if the senior wants layering progress without the import churn of C1. |

Stop after 5 if the week runs out. Items 1 through 5 are each independently shippable and none
depends on a later one.

## 10. Open decisions for the next senior review

1. **A5**: what a soft flag does on the MCP path. Recommendation is log-only for this freeze;
   revisit after the OpenRouter decision.
2. **D1.4**: whether quiz, assignment, and page pickers get the same synced-library-only
   treatment as rubrics. Teacher named rubrics specifically. Ask before generalizing.
3. **D4**: whether a Home readiness card is inside or outside the freeze. Recommendation is
   inside.
4. **C sequencing**: whether C2 is promoted standalone during the freeze, or the whole of C
   waits for post-semester-start.
5. **2.3**: OpenRouter's future. Not this initiative, but it determines how much A5 and B1
   coverage the MCP path deserves.
