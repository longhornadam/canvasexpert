# File-based AI assist trace: PowerGrader and Create with a chat that has no MCP

**Status:** Batches 1, 2, 3, and 5 executed and committed 2026-08-05. Batch 6 remains. **Batch 4
(packaging) is closed as of 2026-08-06: rejected**, not implemented — see the correction below and
section 4.5. One new finding (section 4.8) and one open decision (section 8.4) that execution
turned up are unaffected. See section 0 for the pick-up point.

**Correction, 2026-08-06.** Section 4.5 concluded ZIP read/write was safe to lean on, based on a
vendor self-report. That self-report was wrong. Confirmed via Microsoft's own
file-formats-supported-by-Copilot support page: M365 Copilot can produce a ZIP as output but
cannot read one as an attachment. Every conclusion in this document that depended on ZIP being
readable input is reversed: Batch 4's "one ZIP per batch" and "ZIP return lane" plan (§4.3, §7) is
rejected, not merely gated, and the flat packet's existing "Download packet ZIP" button and its
backend route have been removed from the product rather than given a return lane. See §4.3, §4.5,
and §7 for the specifics, left in place with strikethrough-style notes rather than rewritten, so the
reasoning that led here stays legible.

---

## 0. Execution state, for whoever picks this up

Four commits on `dev`, each verified green in an isolated worktree at 1 failed / 2210, 2210, 2218,
2226 passed. That single failure is
`api/tests/test_presentation_contracts.py::test_migrated_feature_css_consumes_shared_visual_tokens`
(a `calendar.css` token check). It fails at baseline `1847615` too, so it predates all of this work
and is nobody's regression here.

| Commit | Batch | What landed |
| --- | --- | --- |
| `28ef33c` | 1 | Zero-result imports fail closed; parser widened; `parsed_count` reported |
| `3e55deb` | 5 + 4a | Vendor-neutral naming across the packet flow; batch cards take a file |
| `833c283` | 2a | AI helper downloads carry their real filenames |
| `a0b481e` | 3 + 2b | Scoring skills retired with both surfaces; binary-upload guard; file lane named first |

**Not committed, and deliberately so:** the working tree still carries about 40 unrelated
in-flight files (an "assistant staged scores" feature spanning `routes/powergrader.py`,
`session_actions.py`, `feedback_contract.py`, and the MCP tools, plus Panels, Calendar, and
school-calendar work). None of it is mine. Two files needed hunk-level staging to keep it out of
these commits: `queue_import.js` (8 of 11 hunks are mine) and `test_route_contract.py` (one deleted
line is mine). If you commit those files wholesale you will sweep in someone else's feature.

**What remains, in order:**

1. **Section 4.8, new.** The batch path drops writing-timeline data entirely. Decide section 8.4
   first; this is not a mechanical fix.
2. **Batch 4, packaging half (section 4.3, 4.5).** One ZIP per batch, and a return lane for the
   whole-class ZIP. Still gated on a real attach test in the app, which has not been done.
3. **Batch 6 (section 4.7).** Consolidate the four hand-maintained copies of the output contract.
   The verified drift is that `build_contract_text` documents `writing_process_observations` and
   `rubric_persona_text` does not, which is section 4.8's other half.

**Correction to this document from execution:** section 4.2 said fourteen teacher-facing vendor
strings. The real count was nineteen. Five more sat in `ai_workflow.py`, `import_results.py`, and
`late_catchup.py`, files the original trace did not open. All nineteen are now handled. One
two-vendor mention survives in a `reports.py` docstring, which is developer-facing and reads as an
example list.

---

**Status of the analysis below:** diagnostic trace. Findings are unchanged from the original pass
except where marked.

**Baseline:** `dev` @ `1847615`, working tree (carries uncommitted changes across PowerGrader,
Panels, Calendar, WebUI, and the MCP tools). Sibling of
[three-scenario-teacher-trace.md](three-scenario-teacher-trace.md), which stays the record for
the assistant-driven paths.

**Trigger:** an in-tenant chat app with a high-capability model behind it, free to the teacher, is
about to become what most of this building actually uses. It takes files in and gives files out, and
it has **no MCP**. So every CanvasExpert path that assumes a tool-calling assistant is unavailable,
and the paths that survive are the file and clipboard ones. Those paths were built as the fallback
behind the MCP lane. They are now the main line.

**Framing:** the goal is that CanvasExpert works well with whatever chat a teacher brings, not that
it targets one. Vendor neutrality is settled policy (§8.1). One vendor is named throughout this
document only because the code already names it in fourteen teacher-facing places, which §4.2 treats
as debt to pay down rather than a direction to lean into.

**Method:** walked the two named surfaces in the running UI (local server on 8766) and read the
code behind each hop. Where a finding was cheap to prove, it was proven by execution rather than
by reading: parser behavior in §4.1 and the docx crash in §6.2 were reproduced directly, and the
download headers in §5.1 were read off a live response.

---

## 1. Confidence tags

- **[V]** Verified by execution or by reading every hop directly.
- **[T]** Traced from a file:line read, no execution pass. A lead, not a fact.
- **[X]** Depends on a chat app's own behavior, which is outside this repo and untested here.

---

## 2. What the teacher is actually holding

Two things, and it is worth being precise about which is which, because the product currently
blurs them.

**A chat that takes files.** The teacher can attach files to the conversation and can ask
for a file back. That makes the natural shape: CanvasExpert writes files, the teacher attaches
them, the chat returns something, the teacher brings it back.

**A chat with no hands.** It cannot read the workspace, cannot call `get_scoring_packet`, cannot
call `stage_scores`. Everything the MCP lane does automatically becomes a manual step the teacher
has to get right, in order, without a confirmation that the step landed.

So the question for this trace is not "does the file path exist." It does. The question is whether
a teacher who never reads documentation can get through it and know whether it worked.

---

## 3. The three paths that exist today, and the fact that there are three

There is not one file-based AI-assist scoring path. There are three, and they are separately
discoverable, carry three different output contracts, and only one of them can get results back
into the review queue.

| Path | Where the teacher finds it | Output contract | Can results return to PowerGrader? |
| --- | --- | --- | --- |
| Copilot batch folders | PowerGrader queue, after starting a "Score with AI chat" session | `{pseudonym, item_id, score, feedback}` per batch | Yes, per batch |
| Flat Safe AI Packet ZIP | Same strip, as "Download packet ZIP" | Same contract, whole class in one file | No, see §4.3 |
| "Score with ..." scoring skills | `/ai-expert`, listed beside the authoring skills | Whatever the rubric's own `output_template` says | No, see §5.2. **Retired**, §8.2 |

The third one is the most discoverable and the least safe, which is why it is now retired. Note that
retiring it does not by itself reduce the count to two: the same prompt has a second surface on the
Create page (§6.3), and whether that goes too is the last open question in §8.2.

---

## 4. PowerGrader: "Score with AI chat"

The mode is real and reasonably deep. `api/powergrader/copilot_packet.py` is literally a Copilot
batch builder: it splits students into context-sized batches, writes three numbered upload files
per batch, generates a per-batch prompt, and the queue page renders a card per batch with its own
paste box that validates against that batch's expected roster. Late catch-up generates additional
late batches. That is a well-shaped design. The problems are at the edges where a teacher's actual
keystrokes land.

### 4.1 The blocking one: five plausible model replies import nothing and report success [V]

`api/feedback_results.py:95` unwraps exactly one wrapper key:

```python
if isinstance(data, dict):
    data = data.get("results", [])
return data if isinstance(data, list) else []
```

Anything else that is not a bare array becomes `[]`. And `validate_results([])` returns `ok: True`,
because its `errors` list is empty and unscored students are only warnings
([api/feedback_results.py:184](../../api/feedback_results.py:184)). So
`import_results_into_session` reaches step 6 with nothing to merge, sets `updated = 0`, and returns
`{"ok": True, "updated": 0}`.

The UI then reports that as a success. [queue_import.js:299](../../api/webui/static/powergrader/queue_import.js:299)
prints `"<label> imported: 0 AI suggestion(s)."` and line 300 raises the toast
`"<label> imported for review."` with `false` in the error position.

Reproduced directly against the real functions, with a two-student bundle:

| Model reply shape | Parsed rows | `validate.ok` |
| --- | --- | --- |
| bare array (the contract) | 1 | True |
| fenced array with prose around it | 1 | True |
| `{"results": [...]}` | 1 | True |
| `{"scores": [...]}` | **0** | **True** |
| `{"students": [...]}` | **0** | **True** |
| a single bare object, not wrapped in an array | **0** | **True** |
| one fenced object per student | **0** | **True** |
| a short JSON preamble object, then the real array | **0** | **True** |

The last row is its own failure: `_first_json_block` walks to the *first* decodable `[` or `{` and
stops, so a leading `{"note": "I scored 5 students"}` shadows the array that follows.

The single-object row is the one most likely to bite. `_split_batches`
([copilot_packet.py:68](../../api/powergrader/copilot_packet.py:68)) deliberately emits a
one-student batch whenever a student's work exceeds the budget, and a one-student batch is exactly
the case where a model answers with a lone object instead of an array of one.

No test covers any of this. `grep parse_results api/tests` returns nothing.

Consequence in the room: the teacher works a batch, pastes, sees "imported", moves to the next
batch, and finds an empty review queue at the end with no idea which batch dropped.

Fix shape, in order of value:
1. Treat `updated == 0` against a non-empty `expected_results` as a failure, not a success. This
   alone converts every row above into a visible error.
2. Unwrap any single list-valued key, not just `results`.
3. Accept a bare object that carries `pseudonym` as a one-element list.
4. Prefer the largest or last decodable JSON block over the first.
5. Tell the teacher what was found: "read 0 results from 1,400 characters" beats "imported: 0".

### 4.2 The packet flow names one vendor in teacher-facing copy, which breaks the stance [V]

Vendor neutrality is settled policy (§8.1). Measured against it, the packet flow is the one place in
the product that violates it, and it does so in fourteen teacher-facing places.

The mode card itself is fine: *"Makes a file you can paste into Claude or ChatGPT yourself."*
([powergrader_setup.html:107](../../api/webui/templates/powergrader_setup.html:107)). So is
`about.html:50` ("MagicSchool, Copilot, Claude, ChatGPT") and `settings.html:354`, because naming
several vendors as examples is neutral by enumeration.

What is not neutral is everything past the Start button. Nine strings in the queue:

| Where | String |
| --- | --- |
| `queue_import.js:61` | "Open Copilot batch folder" |
| `queue_import.js:88` | "start a new Copilot chat ... then paste Copilot's JSON back here" |
| `queue_import.js:89` | "before you send them to Copilot" |
| `queue_import.js:110` | "Start a new Copilot chat for this batch" |
| `queue_import.js:114` | "Copy Copilot prompt" |
| `queue_import.js:279` | "Paste Copilot JSON first." |
| `queue_late_catchup.js:57` | "Generate Late Copilot Batch" |
| `queue_late_catchup.js:67` | "Copilot batches generated: N" |
| `queue_late_catchup.js:153` | "Generating late Copilot batch..." |

Plus two warnings that surface in the privacy strip
([copilot_packet.py:21,25](../../api/powergrader/copilot_packet.py:21)): "Copilot may miss student
work" and "larger than the target Copilot budget".

Plus three artifacts the teacher sees in Explorer, which outlive any UI change:

- the folder is literally named `Copilot Batches` ([copilot_packet.py:147](../../api/powergrader/copilot_packet.py:147))
- the file is `README - Copilot Steps.md` ([:166](../../api/powergrader/copilot_packet.py:166))
- its body reads "# Copilot Steps", "1. Start a new Copilot chat.", "4. Copy Copilot's JSON response."

A teacher on MagicSchool or Claude who opens that folder is told to use a product they do not have.
The renames are mechanical ("AI Chat Batches", "README - Steps for your AI chat", "Start a new chat
in your AI assistant"), but the folder rename is a path change, so it needs the same
`RETIRED_FILES` care that seeded-file renames take (see the CanvasAgent instruction-set precedent).

Internal module and key names (`copilot_packet.py`, `copilot_packet`, `batch_id`) are not
teacher-facing and are not worth churning.

### 4.3 The most prominent artifact is the one with no way back [V]

When a packet session has batches, the strip offers three artifacts
([queue_import.js:57-63](../../api/webui/static/powergrader/queue_import.js:57)): "Open packet
folder", "Open Copilot batch folder", and "Download packet ZIP". The ZIP is the only one that
looks like a thing you can hand to a chat app, and it is the one that cannot come back:

- Line 66 hides `legacyImportBox` whenever batches exist. That box holds the only whole-class
  textarea and the only file picker.
- The per-batch boxes validate every row against that batch's `expected_results`
  ([import_results.py:58-78](../../api/powergrader/import_results.py:58)). A whole-class result
  pasted into Batch 1 fails with "belongs to another batch or was not in this batch".

So the packet ZIP in packet mode was a dead end, and it was the most clickable thing in the strip.
Its `START HERE` file still instructed the model to score every student and return one array, which
was advice the session could no longer accept.

**Resolved 2026-08-06, reversing this section's original conclusion.** §4.5 at the time argued for
giving the ZIP a return lane instead of removing it. That argument rested on ZIP being readable
input, which is now confirmed false (see the correction at the top of this document). The actual
fix taken: the "Download packet ZIP" button and its backend route were removed from the product.
No return lane was built, because the artifact it would have served was never safe to promise in
the first place.

### 4.4 The batch return channel is paste-only [V]

A batch card renders a bare `<textarea>`
([queue_import.js:118](../../api/webui/static/powergrader/queue_import.js:118)) with no file input
and no placeholder. The `.json` file picker exists only on the legacy box
([powergrader_queue.html:68](../../api/webui/templates/powergrader_queue.html:68)), which §4.3 just
established is hidden in this mode.

A chat whose selling point is that it hands you files has no file lane home. The teacher opens the
download, selects all, copies, and pastes. Each of those steps is a place to lose a batch, and §4.1
means losing one is silent.

The fix is small and already has a working precedent in this same file: the hidden legacy box's file
input reads the file locally with `FileReader` and drops the text into the textarea
([queue_import.js:230-240](../../api/webui/static/powergrader/queue_import.js:230)). Lifting that
same six lines onto the batch cards is most of the work.

### 4.5 The format worry was wrong, and that reopens the packaging question [WRONG, corrected 2026-08-06]

This was tagged [X] on the assumption that `.md` and `.json` might not be attachable. Per the
vendor's own account, `.md`, `.json`, and `.zip` are all readable, ZIP contents are enumerable and
extractable, and it can emit files including ZIPs. Treat that as a vendor self-report rather than a
test result, but it is plausible and it points the same way as the rest of this section.

**That vendor self-report was wrong.** Confirmed 2026-08-06 against Microsoft's own
file-formats-supported-by-Copilot support page: M365 Copilot can emit a ZIP but cannot read one as
an attachment. `.md` and `.json` as loose files remain fine; ZIP as an input artifact is not. The
two consequences drawn below are only half right as a result.

Two consequences, as originally written:

- **Drop the `.docx` / `.txt` variant idea.** The packet's existing `.md` and `.json` are fine. That
  removes a whole speculative work item. **This part holds.**
- ~~The packaging assumption is now the interesting question, not the format. The batch layout
  ships three loose `.md` files per batch because that was the safe shape for a chat that might only
  take plain text one file at a time. If ZIP reading holds, one ZIP per batch is a strictly better
  artifact: one attachment, no chance of the teacher attaching 01 and 03 but forgetting 02, and the
  README travels with it.~~ **This part does not hold.** ZIP reading does not hold, so the batch
  layout's three loose files were never a stopgap waiting on a better packaging idea; they were
  already the right answer, arrived at for the wrong stated reason. Batches keep shipping as loose
  files.

What does **not** change is §4.6. Batching exists because of the context window, not because of
attachment limits, so a large class still needs splitting no matter how few files it arrives in. And
the failure mode of a chat that reads a ZIP but silently attends to only part of it is the same
silent under-scoring §4.6 describes, landing on the same silent import in §4.1. Moot for batches now
that ZIP packaging is rejected, but the same reasoning is why the flat packet's ZIP button was
removed rather than kept as an unverified convenience: a silent-partial-read failure is exactly the
failure class §4.1 exists to close, and there is no way to verify "attended to" from this side of
the attachment.

### 4.6 Batch sizing is pinned to 128k with no way to change it [V]

`DEFAULT_COPILOT_CONTEXT_TOKENS = 128_000`
([copilot_packet.py:14](../../api/powergrader/copilot_packet.py:14)). No production caller ever
passes `effective_context_tokens`; there is no setting and no UI control. Batch sizes are identical
regardless of which chat the teacher uses, and if the in-tenant model's usable window is smaller in
practice, the failure is a truncated batch that scores some students and quietly omits the rest.
That failure lands on §4.1's silent path.

Also in this call site: `ai_workflow.py:258` and `:270` invoke both `build_safe_ai_packet` and
`build_copilot_batches` without `assignment_id`, so the compact layout falls back to a hash of the
assignment name instead of the stable Canvas id it was designed to use.

### 4.8 The batch path silently drops writing-timeline data [V, found during execution]

Not in the original trace. Found while scoping the section 4.7 consolidation, and it is the reason
that batch is still open.

The SAFE bundle carries writing-timeline data per response:
`feedback_artifacts.py:305-307` runs `writing_timeline.safe_projection(...)` and sets
`response["writing_timeline"]`. The flat packet dumps the whole bundle into
`Student Responses.json` ([packet.py:184](../../api/powergrader/packet.py:184)), so it travels, and
the flat packet's `START HERE` documents `writing_process_observations` as an optional teacher-only
field with explicit guardrails ([feedback_contract.py:91](../../api/feedback_contract.py:91)).

The batch path does neither. `_student_blocks`
([copilot_packet.py:40-65](../../api/powergrader/copilot_packet.py:40)) builds `03-work.md` from
only `pseudonym`, `item_id`, `possible`, and the response text. It never reads `writing_timeline`.
And file 02's contract (`rubric_persona_text`) never mentions `writing_process_observations`.

So in the primary non-MCP path, the AI is never given the timeline data and never asked for
`writing_process_observations`. Both halves are missing consistently, the data and the instruction,
which reads more like an unstated decision than a bug, but nothing records it and the flat packet in
the very same session behaves differently.

**Corrected 2026-08-05.** An earlier version of this section said the queue's "Tracked DOCX, Writing
Timeline" badge promises something packet mode cannot deliver, and section 8.4 leaned toward hiding
the badge in packet mode. That was wrong and the instinct was acted on and then withdrawn before any
code changed. The timeline strip renders from **local session data**
([queue_writing_timeline.js:56](../../api/webui/static/powergrader/queue_writing_timeline.js:56)
reads `students[].attachments[].writing_timeline`), not from the AI. Packet mode therefore gives the
teacher the full working timeline view: signals, sparkline, and navigation. The badge is accurate,
and hiding it would remove a feature that works.

The scope of the real gap is narrower than first written: what is absent in packet mode is only the
AI's teacher-only observation note. Nothing in the UI promises that note, so nothing is currently
lying to anyone.

Left unfixed on purpose. See section 8.4.

### 4.7 The same contract is written four times [V]

`build_contract_text` (START HERE), `paste_format_text` (flat packet),
`rubric_persona_text` ("Required JSON Output" inside file 02), and `batch_prompt` (the copy button
and the README) each state the output contract in their own words. They already disagree:
`build_contract_text` documents `writing_process_observations`, `rubric_persona_text` does not
mention it. Four hand-maintained copies of one contract will keep drifting, and the model reads
whichever one the teacher happened to attach.

---

## 5. `/ai-expert`, the page a teacher will actually find first

Nav does not link `/ai-expert` directly; the teacher reaches it from Create's "See them all" or
from Settings. Once there it is the densest AI page in the product, and both of its problems point
at the file-based workflow.

### 5.1 Every Download button produces a file named `file` [V]

Every download link on the page carries a bare `download` attribute with no value: five template
sites in `ai_expert.html` (lines 28, 53, 79, 108, 110) covering the start-here file, the authoring
skills, the scoring skills, and both MagicSchool Toolkit files, plus the four on Create
([course_expert.html:62](../../api/webui/templates/course_expert.html:62)). Neither backing route,
`/api/ai-ta/file` nor `/api/ai-ta/toolkit-file`, sets `Content-Disposition`
([library.py:100-126](../../api/webui/routes/library.py:100)). Read off the live server:

```
content-type: text/plain; charset=utf-8
content-disposition: null
href: /api/ai-ta/file?name=Author%20a%20Quiz%20%28QuizForge%29.txt
download: ""
```

With no filename in the attribute and none in a header, the browser derives the name from the URL
path, whose last segment is `file`. The query string is not part of the name. A teacher who
downloads all four authoring skills gets `file.txt`, `file (1).txt`, `file (2).txt`,
`file (3).txt`. The toolkit links land as `toolkit-file`, same defect, different word.

The tooltip on that button reads: *"Download as .txt so you can drop it into your assistant's
project files."* That is precisely the file-based on-ramp, and it is the one that breaks. Attaching a
file is better than pasting 23,602 characters into a chat box, which is what the Copy button hands
over for Quiz (measured live).

This is the cheapest high-value fix in this document: put the real name in the `download`
attribute, or set `Content-Disposition` in the route.

### 5.2 The page advertises a raw, unpseudonymized scoring path that cannot come home [V]

Under "Scoring skills", one file per rubric, the page says: *"Paste a skill file, then paste student
essays one at a time."* The generated file ends with
*"I will paste one student response at a time. Wait for it."*
([rf.scoring_prompt](../../api/webui/rf.py)).

Three things are true about that path at once:

- **No vault.** Nothing pseudonymizes anything. The instruction is to paste real student writing
  into the chat. The packet flow's entire privacy design, the vault, the safety gate, the
  acknowledgement checkbox on the setup page, is simply absent here.
- **No route back.** The output shape comes from each rubric's own `output_template` and carries
  no `pseudonym` and no `item_id`. It cannot satisfy `validate_results`, so it can never be
  imported into a session. Whatever the teacher gets, they retype.
- **It outranks the safe path.** It sits beside the authoring skills the teacher came for, one hop
  from Create, and it is the only thing on any page that answers "how do I score with my AI chat"
  without first starting a PowerGrader session.

A teacher told "use the district chat for everything" who lands on this page will find this before the
packet flow.

**Decided: retire them** (§8.2). Two things make that more than deleting a template block, and both
are in §8.2: the existing retirement machinery cannot reach these files, and the same prompt has a
second home on the Create page (§6.3).

---

## 6. Create: the Forge round trip

The shape here is better. "Start in your assistant" is three honest steps: copy or download the
instruction file, ask your assistant, bring the result back to Paste JSON or Upload. Both a paste
box and a file picker exist on every tab, which is more than the batch cards get. Two problems.

### 6.1 The envelope is mandatory with no fallback [V code-side, T on chat rendering]

`pf.ENVELOPE_RE` and its siblings require the literal tags and nothing else
([pf.py:11](../../api/webui/pf.py:11)):

```python
ENVELOPE_RE = re.compile(r"<PAGEFORGE_JSON>\s*(\{.*\})\s*</PAGEFORGE_JSON>", re.S)
```

No match means `["no <PAGEFORGE_JSON> … </PAGEFORGE_JSON> envelope found"]`. There is no bare-JSON
fallback, so a model that returns a perfect payload in a plain code fence fails.

Note the product now holds two opposite stances on the same problem. PowerGrader's parser is
tolerant and fails silently (§4.1). Create's parser is strict and fails loudly. Loud is the better
half of that pair, and this section is a smaller worry than §4.1 for exactly that reason.

The remaining worry is the clipboard, not the model: `<PAGEFORGE_JSON>` is shaped like an HTML tag,
and chat renderers can swallow unknown angle-bracket tags so they never reach the text the teacher
copies, even when the model emitted them correctly. That risk is specific to the paste lane.

Since file output is confirmed (§4.5), there is a mitigation that needs no parser change and no
testing: tell the teacher to ask for the payload **as a `.md` or `.json` file** and use Upload, where
the envelope survives whatever the chat window does to it. Right now the instruction files say
nothing about which lane to prefer, and step 3 of "Start in your assistant" lists paste first
([course_expert.html:72](../../api/webui/templates/course_expert.html:72)). Reversing that order is a
copy change.

### 6.2 A `.docx` upload crashes with an unhandled decode error [V]

`/api/temp-upload` writes any uploaded file's raw bytes into a `temp_*.json` path with no format
detection ([push_validation.py:19-36](../../api/webui/routes/push_validation.py:19)). The parsers
then open that path as UTF-8 text and catch only `OSError`
([pf.py:19-23](../../api/webui/pf.py:19)).

Reproduced by handing a real ZIP-structured file to `pf.parse_file`:

```
RAISED UnicodeDecodeError : 'utf-8' codec can't decode byte 0x9c in position 11: invalid start byte
```

That is a 500, not a message. And `.docx` is the single most likely thing a teacher gets back when
they ask a current chat app for "a file". The `accept=".json,.txt"` filter makes it less likely
but does not prevent it, and that filter also excludes `.md`, which is the other format these apps
reach for. A sniff-and-explain guard ("that looks like a Word file; paste the JSON instead, or
ask for a .txt") costs very little.

### 6.3 The retired scoring prompt has a second home on this page [V]

Found while scoping §8.2, and it is the reason that decision is not a one-line delete.

`rf.scoring_prompt` has two consumers, not one:

1. `ai_ta.py:155`, which generates the `/ai-expert` "Score with ..." files. Retired.
2. `/api/rf/scoring-prompt` ([push_validation.py:171-175](../../api/webui/routes/push_validation.py:171)),
   which backs a **"Copy scoring prompt"** button on Create's Assignment tab
   ([course_expert.html:351](../../api/webui/templates/course_expert.html:351),
   [push/assignment.js:102-112](../../api/webui/static/push/assignment.js:102)).

The second copies the identical text, ending in the identical *"I will paste one student response at a
time. Wait for it."*, and reports success as *"Copied, paste into MagicSchool or Copilot"*. Same
absence of the vault, same absence of a route back into the queue. It also carries the §4.2 vendor
naming, making it the fifteenth teacher-facing instance.

So retiring the files alone moves the hazard rather than removing it, and leaves it on a **more**
trafficked page than the one it came from. Whether that button goes too is the one part of §8.2 left
open.

---

## 7. Recommended batch sequence

Ordered by whether a teacher loses work, not by size. The format question that used to gate this
sequence is closed (§4.5), so it can start immediately.

**Batch 1: stop the silent zero-import.** §4.1. Fail the import when a batch expecting results gets
none; widen the unwrap; report what was actually read. Add the eight-shape table above as tests,
since none exist. This is the only finding here that loses a teacher's work without telling them,
and it is also the precondition for trusting the larger payloads Batch 4 would enable.

**Batch 2: three small honesty fixes.** §5.1, the `download` filename, which is the cheapest
high-value fix in the document. §6.2, the docx guard. §6.1, reverse the paste-first ordering so the
file lane is the recommended one.

**Batch 3: retire the `/ai-expert` scoring skills.** §5.2, decided in §8.2. Delist first (removing
the template section is the safe move and works regardless of what is on disk), then stop generating,
then decide the folder sweep. Take the Create-page "Copy scoring prompt" button with it (§6.3) or the
retirement is cosmetic.

**Batch 4: give the file lanes a home.** §4.4, lift the existing `FileReader` handler onto the batch
cards so a returned file can be picked rather than retyped. ~~Reconsider packaging: decide the ZIP's
fate now that ZIP reading is plausible.~~ **Closed 2026-08-06, rejected**: ZIP reading is not
plausible, it is confirmed absent. No ZIP return lane, no one-ZIP-per-batch. The flat packet's
"Download packet ZIP" button and backend route were removed instead of given a return lane.

**Batch 5: genericize the teacher-facing vendor naming.** §4.2. Nine UI strings, two warnings, and
three on-disk artifact names. The folder rename is a path change, so it needs `RETIRED_FILES`
handling; that is the only non-trivial part.

**Batch 6: consolidate the contract text.** §4.7. One source, rendered into the four places. This
gets cheaper if Batch 4 changes the packaging, so it goes last on purpose.

---

## 8. Open decisions

### 8.1 Decided: stay vendor-neutral, and treat the existing naming as debt

Settled 2026-08-05. The product does not name a preferred AI chat. Naming several as examples
("MagicSchool, Copilot, Claude, ChatGPT") stays fine; singling one out does not. The goal is that
CanvasExpert works well with whatever chat the teacher brings.

This closes the question and converts §4.2 from a decision into Batch 5 work: nine UI strings, two
privacy-strip warnings, and three on-disk artifact names currently single out one vendor, all of them
past the Start button where a teacher has already committed to the mode.

It also settles what §4.5 is allowed to conclude. The format finding is useful because it tells us
`.md`, `.json`, and `.zip` are all safe to lean on, not because it makes one chat the target. Any
packaging change from Batch 4 should be justified as "one attachment beats three", which is true for
every chat, rather than as "this is what one vendor likes".

### 8.2 Decided: retire the `/ai-expert` scoring skills

Settled 2026-08-05. The "Score with ..." files come out. The packet flow covers the use case and
does it with the vault; these predate it and contradict it (§5.2).

Scoping this turned up two things that make it more than deleting a template block.

**The existing retirement machinery cannot reach these files.** `RETIRED_FILES`
([ai_ta.py:52](../../api/webui/ai_ta.py:52)) is keyed by exact filename against a frozenset of
shipped-content hashes, and `_retire_superseded` deletes only copies whose hash matches, so a
teacher's edits survive. Neither half works here: the names are generated from each teacher's own
rubric titles (`Score with - District ECR Rubric (0-10).txt`), and the contents are generated from
their rubrics, so there is no shippable name list and no shippable hash. That is the right design
for seeded files and simply does not apply to generated ones.

So retirement needs three moves, and the third needs a call:

1. **Stop generating.** Drop the per-rubric loop in `build_library`
   ([ai_ta.py:166-180](../../api/webui/ai_ta.py:166)).
2. **Delist.** The page finds them by prefix scan, `f.label.startswith("Score with")`
   ([ai_expert.html:70](../../api/webui/templates/ai_expert.html:70)), over whatever is on disk.
   Stopping generation therefore does **not** delist anything: every teacher who has run a rebuild
   keeps seeing them forever. Removing the template section is what delists, and it delists
   regardless of what is on disk, which makes it the safe first move.
3. **Sweep the folder, or don't.** Files already written stay in the teacher's AI Authoring folder
   after delisting. A `Score with - *.txt` prefix sweep is the only way to clear them, and it cannot
   tell an untouched generated file from one a teacher edited. Options: sweep unconditionally,
   sweep only files whose content still matches a freshly regenerated prompt from the current rubric
   (a hash check that actually works, because the rubric is on hand), or leave them and let them go
   stale. The middle one preserves the `RETIRED_FILES` principle without needing shipped hashes.

**The prompt has a second home.** §6.3. The same text is one click away on Create's Assignment tab
via `/api/rf/scoring-prompt`, which is a busier page than `/ai-expert`. Retiring only the files
relocates the hazard upward. `rf.scoring_prompt` itself cannot be deleted while that route stands.

That leaves one question, and it is narrower than the original one: **does the "Copy scoring prompt"
button on the Assignment tab go too?** If yes, `rf.scoring_prompt` and its route go with it and the
raw-essay path is gone from the product. If no, the retirement is cosmetic and the honest move is to
say on that button what §5.2 says about the files. Recommend yes, on the grounds that keeping it is
the whole thing this decision was meant to end.

Also adjacent, not in scope unless you say so: the MagicSchool Toolkit's **Essay Scorer** recipe on
the same page describes building a MagicSchool tool with a rubric as Knowledge and feeding it student
essays. Same underlying exposure, different artifact, and it is a vendor-specific recipe rather than a
CE-generated file. Left alone.

Test and doc references to clean up: `api/tests/webui/test_ai_ta.py`,
`api/tests/test_beta075_runtime.py`, `api/tests/powergrader/test_packet.py`, and
`api/webui/README.md`.

### 8.4 Decided: carry an aggregate-only writing-timeline summary into the batch path

**Settled 2026-08-05: option three, aggregate only.** Counts, totals, tracking-presence booleans, and
the already-categorized author fields travel into `03-work.md`, and file 02's contract gains
`writing_process_observations` with the guardrails `build_contract_text` already states.
`largest_insertions` stays out: it carries no student text, but it is a list of individual edit events
with timestamps, and per-edit timing is what most invites the integrity inference
`sanitize_process_observation` exists to block. The counts already carry the volume signal.

Implementation is specified field by field in
[docs/handoffs/codex-file-based-ai-assist-remainder.md](../codex-file-based-ai-assist-remainder.md)
item 5.1, which also folds in section 4.7's consolidation, since the contract text becomes
load-bearing once it has to state these guardrails.

The options as they stood before the decision, kept for the reasoning:

Section 4.8, and the reason it was not just fixed. This is a privacy question wearing a bug's
clothing, which is exactly the kind of thing not to settle inside an implementation pass.

Writing-timeline data describes authorship and revision behavior: who touched a document, in what
order, with what gaps. `safe_projection` exists to strip it down before it leaves the machine, and
`sanitize_process_observation` exists to stop the model turning it into an integrity accusation on
the way back. Both of those guards were built for a payload that goes out over the API lane. Putting
the same data into a `.md` file that a teacher hands to a chat app by hand is a different exposure,
and the teacher is the one choosing the destination.

Three options:

- **Leave it out, and write it down.** Treat writing-process observations as an API-lane and MCP-lane
  capability. Change no behavior, and document the difference so it stops being rediscovered.
  Smallest, and honest. Note this option no longer includes hiding the badge: see the correction in
  section 4.8 for why that would remove working local functionality.
- **Include it, gated.** Carry the safe projection into `03-work.md` and add
  `writing_process_observations` to file 02's contract, behind the same acknowledgement the packet
  mode already requires. Most capable, most exposure, and it makes section 4.7's consolidation
  load-bearing rather than cosmetic.
- **Include only the aggregate.** Author count and revision-span summary, never per-document
  detail. Middle path, and probably enough for the coaching use the feature was built for.

No recommendation from me here. The third is likelier to be what you actually want; the first costs
nothing and is defensible on its own.

### 8.3 Whether batch sizing becomes visible

§4.6. A hardcoded 128k that no caller can override was fine when the packet flow was aimed at
whatever chat the teacher happened to have. If one chat is about to become the house default, the
number either becomes a setting or becomes a documented assumption with a visible warning when a
batch approaches it.

---

## 9. Still unverified

- **Closed 2026-08-06.** `.md` and `.json` read/write hold. ZIP does not: confirmed against
  Microsoft's file-formats-supported-by-Copilot page that M365 Copilot cannot read a ZIP as an
  attachment. The follow-on questions this used to leave open, whether a chat that opens a ZIP
  attends to every file inside rather than the first few, and what a given chat's usable context is
  versus the hardcoded 128k in §4.6, are moot for ZIP specifically now that it is off the table. The
  128k question survives independently; see §8.3.
- Whether angle-bracket envelope tags survive a chat's rendering into the clipboard (§6.1). The
  recommended fix routes around this rather than depending on the answer, so it is no longer
  blocking.
- The live packet round trip end to end. This trace read the code and the rendered pages, but no
  real session was created, because that needs Canvas submissions and this workspace has no
  synthetic Canvas by standing decision. §4.1's parser behavior was proven against the real
  functions rather than through a live session, so the parse and validate hops are solid; the
  claim that a teacher sees "imported: 0" rests on reading `queue_import.js:299`, not on watching
  it happen.
- Whether `pg-ai-check`, the acknowledgement checkbox, actually gates the packet build server-side
  or only in the browser. Not traced.
- The New Quizzes CSV lane under "Advanced feedback and imports". Out of scope here, and it has
  its own contract.
