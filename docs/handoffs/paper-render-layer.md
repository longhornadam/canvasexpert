# Handoff — Paper render layer (cross-forge physical output: tiered DOCX + locked PDF)

**Lane:** Ferrari (architecture + cross-cutting; spawns scoped Toyota slices below).
**Status:** design spec — **PDF-engine decision settled: Option C** (single HTML substrate), 2026-06-25.
Ready to scope Toyota slices; one remaining sub-decision (html→docx engine) noted below.
**Author context:** 2026-06-25 direction conversation. Driver: going *heavy on-paper* next school
year (anti-screen movement in education; paper is a valid mode). Principle: **more options, not
fewer** — produce a printable *and* (optionally) a Canvas assignment that links/attaches it.

---

## Goal

Turn the existing quiz-only physical renderer into a **content-type-agnostic paper render layer**
that any forge's JSON can feed, with two cross-cutting capabilities:

1. **Two physical targets from one content model:**
   - **DOCX** = the *teacher-editable* master (keep/extend the current python-docx path).
   - **PDF** = the *student-final, locked* deliverable ("so they can't screw it up after
     downloading it" — Adam, 2026-06-25). PDF is **new**; it does not exist today.
2. **Tier as scaffold-density (redaction), not four authored versions.** One JSON holds the
   *fully-filled* content; the renderer blanks a fraction of the learning-target slots per tier
   (`Support` ≈ half-filled, `Core` ≈ cue-level, `Accelerate` ≈ near-empty, `Extend` = empty +
   scaffolds stripped). This is [[differentiation-model]] expressed as a *render* concern.

Non-goal (this spec): the Canvas-push side of "attach the PDF to an assignment." That reuses the
existing `api/` assignment-push path and is a follow-on once the render layer emits a PDF artifact.

---

## Why this shape

- The seam already half-exists: `engine/rendering/physical/` + `engine/packagers/physical_handler.py`
  already emit student-DOCX + answer-key + rationale, and `engine/rendering/{canvas,correction_doc,
  physical}` already models "one content → multiple render targets." We are **generalizing what
  QuizForge proved**, not inventing a pattern.
- Authoring contracts stay canonical (`LLM_Modules/*_Base.md`). Print becomes a *render target*, so a
  new forge (NoteForge, DeckForge) inherits paper + PDF + tiers for free by defining only its JSON.
- "Forges aren't destinations" was about *navigation*, not output — a rendered printable is a
  legitimate terminal deliverable. (See [[forge-concept]] nuance, [[paper-output-direction]].)

---

## Current state (verified 2026-06-25, CE `engine/`)

```
engine/core/{quiz,questions,answers}.py        # quiz-specific domain model
engine/rendering/
  canvas/                                       # → Canvas QTI / New Quizzes
  correction_doc/                               # → marked-up correction doc
  physical/
    styles/default_styles.py                    # DOCX font/margin/table constants
    README.md
engine/packagers/
  packager.py
  canvas_handler.py
  physical_handler.py                           # Quiz → student DOCX + key + rationale (DOCX only)
```

**Constraints to respect:** `physical_handler.py` "performs NO validation — trusts input is perfect"
(validation happens upstream). It parses inline HTML bold/italic into python-docx runs via
`_FormattedHTMLParser`. Keep that contract: the render layer renders; it does not validate.

---

## Target architecture

```
forge JSON ─parse/validate (unchanged, upstream)─► PrintDoc ─redact(tier)─► paged HTML+print-CSS
                                                                                  │  (single substrate)
                                                                  ┌───────────────┴───────────────┐
                                                          WeasyPrint → PDF              html→docx → DOCX
                                                       (student-locked final)        (teacher-editable master)
```

**Chosen (Option C):** every template is authored *once* as HTML + print-CSS. Two emitters consume
that one substrate — WeasyPrint for the locked student PDF, an html→docx converter for the editable
teacher master. PDF and DOCX therefore always match, and a new note style is one HTML/CSS template,
not two renderers.

### 1. `PrintDoc` — the content-type-agnostic model
A small intermediate representation the renderers consume, so renderers stop importing `Quiz`
directly. A `PrintDoc` is an ordered list of **blocks**; each block is one of a closed set of
primitives the paper layer knows how to lay out:

- `Heading`, `Prose` (may carry inline-HTML bold/italic, reusing the existing parser)
- `RuledLines(n)` — blank writing lines
- `Slot{ id, content, key: bool, given_when: tier-threshold }` — a fillable unit (see redaction)
- `Box{ label, body[] }`, `Columns(left[], right[])`, `Grid(rows, cols, cells[])` — layout
  containers that the note styles compose from
- `AnswerKeyRef` / `PageBreak`

Each forge ships a **small adapter** `to_printdoc(parsed) -> PrintDoc`. Quiz's adapter wraps the
current behavior; NoteForge/DeckForge add their own. Renderers depend only on `PrintDoc`.

### 2. Tier redaction (the core new idea)
- Every fillable unit is a `Slot`. Author marks `key: true` on the units that are *learning targets*
  (the words/ideas worth making a student produce) vs. scaffolding that should usually stay given.
- A pure function `redact(printdoc, tier) -> printdoc` blanks a fraction of `key` slots:
  - `Support` → blank ~25% of key slots (half-filled feel), keep all non-key scaffolds.
  - `Core` → blank ~50%, keep cue scaffolds.
  - `Accelerate` → blank ~90%.
  - `Extend` → blank 100% **and** drop non-key scaffolds (e.g. Cornell cue column emptied/removed).
- Redaction is **deterministic** (seed by slot `id`) so the same JSON+tier always yields the same
  sheet, and so the answer key always matches. The teacher master (DOCX) can render at any tier or
  "all tiers as a packet."
- This is a **render concern only** — no contract/engine schema change to the differentiation model;
  it stays "convention, not engine change" ([[differentiation-model]]).

### 3. One substrate, two emitters (Option C)
- **Substrate** — `PrintDoc` (post-redaction) → **paged HTML + print-CSS** via a single template set
  (`engine/rendering/physical/templates/`, `.../styles/*.css`). All layout lives here.
- **PDF emitter** — WeasyPrint(HTML) → PDF. The locked student artifact.
- **DOCX emitter** — html→docx converter (see sub-decision) → editable teacher master.
- The current python-docx `physical_handler.py` is **retired/replaced** by this path. Its style
  constants in `physical/styles/default_styles.py` become the source values for the print-CSS.

---

## DECISION — PDF/DOCX engine: **Option C** (settled 2026-06-25)

> **Engine update (2026-06-25, post-slice-1):** the HTML→PDF backend is **headless Chromium
> (Playwright)**, not WeasyPrint — WeasyPrint needed a Windows GTK/Pango install; Chromium is
> self-contained and higher fidelity. HTML→DOCX is **`pypandoc-binary`** (bundled Pandoc, no PATH).
> Wherever this doc says "WeasyPrint," read "Chromium."

Author every template once as HTML + print-CSS; emit PDF (Chromium, locked, student) and DOCX
(html→docx via Pandoc, editable, teacher) from that one substrate. Chosen over A (python-docx DOCX + separate
HTML/PDF) and B (Word-COM DOCX→PDF) because: one template set per note style, PDF/DOCX always match,
print-CSS is the natural medium for Cornell columns / Frayer quadrants / ruled lines / page-locked
scaffolds, and there's no MS-Word automation dependency.

**Cost we are accepting:** the existing, working python-docx quiz DOCX renderer is replaced by the
html→docx path. The current quiz DOCX output is the regression baseline (see slice #1 guard).

### Sub-decision (resolve during slice #1) — which html→docx converter?
- **Pandoc** (external binary, HTML→DOCX) — best fidelity, clean editable DOCX, well-maintained;
  cost = a non-pip system dependency to install/bundle on the teacher's machine.
- **`htmldocx` / pure-Python** — pip-only, no system dep; cost = weaker fidelity on tables/columns,
  the exact constructs the note styles lean on.
- *Lean:* **Pandoc**, unless the bundling friction on locked-down district machines is unacceptable
  — in which case fall back to pure-Python and constrain template HTML to what it converts cleanly.
  Decide by spiking the quiz template both ways against the slice #1 baseline.

---

## NoteForge — first new forge on this layer

NoteForge produces note-taking scaffolds. Two modes (carry a `mode` in the contract):
- `blank` — an empty/partial template the student fills (the common case; tier = how much is pre-filled).
- `exemplar` — fully-completed notes as a study aid / model.

### Junior-high (6–8) note styles — catalog + how each tiers
Adam asked for popular styles beyond Cornell. Ranked by redaction-friendliness (how cleanly the
single-JSON → tiered-sheet model works). All compose from the `PrintDoc` primitives above.

1. **Guided / cloze notes** *(the workhorse)* — prose with key terms as `Slot{key:true}`. Tiering is
   literally "how many blanks." Best fit; build first.
2. **Cornell** — `Columns(cue, notes)` + `summary`. Support pre-fills cue questions + partial notes +
   a summary sentence-starter; Extend empties the cue column.
3. **Two-column / T-notes** — `term | definition`, `cause | effect`, `Q | A`. Redact either column.
4. **Outline notes** — hierarchical (I / A / 1). Support gives the full heading skeleton; Accelerate
   gives only top-level headings; student supplies the rest.
5. **Boxes-and-bullets** — main-idea `Box` + supporting bullet `Slot`s. Support pre-fills the boxes
   (student adds bullets); Accelerate blanks both. Great for reading/main-idea work.
6. **Frayer model** *(vocabulary)* — 2×2 `Grid`: definition / characteristics / examples /
   non-examples. Redact per quadrant. Excellent for ELA/science vocab.
7. **Sequence / flow / timeline** — ordered `Slot`s. Support fills some steps, leaves gaps; good for
   processes, plot, historical order.
8. **Concept map / web** — central term + connected nodes. Tierable but **spatial** — Support
   pre-labels some bubbles/connectors. Higher build cost (layout); defer past the linear styles.
9. **KWL** (Know / Want / Learned) and **sketchnotes** — least redaction-friendly (student-generated
   by design). Support as `blank`/`exemplar` templates, but don't force the tier-redaction model on
   them. Lowest priority.

**Build order:** Guided cloze → Cornell → Two-column → Frayer → Boxes-and-bullets → Outline →
Sequence → (Concept map) → (KWL/sketchnotes).

---

## Toyota-able slices (in order; each becomes its own self-contained handoff)

1. **Option-C fidelity spike (NON-DESTRUCTIVE).** Stand up the whole substrate on the *quiz*, beside
   the existing renderer, and stop for Adam's fidelity verdict. `PrintDoc` model + `to_printdoc(Quiz)`
   + Jinja2 HTML/print-CSS + Pandoc html→docx + WeasyPrint html→pdf, driven by a standalone dev CLI
   that writes `*_NEW.docx` + `*_NEW.pdf` next to the current files. **Touches nothing in the live
   path.** Full handoff: `docs/handoffs/paper-render-layer-slice1.md`. *Gate:* Adam judges fidelity
   before slice 2.
2. **Adopt or adjust (pending verdict).** If fidelity passes: wire the new path into `packager.py`,
   retire the python-docx `physical_handler`, keep the current quiz DOCX as a content/structure
   regression baseline (visual parity, not byte parity), `py -m pytest engine/tests` green. If it
   falls short: capture exactly where (which constructs) and iterate the templates/converter choice.
3. **Tier redaction.** `redact(printdoc, tier)` + deterministic seeding + answer-key consistency.
   *Acceptance:* same JSON+tier stable; key always matches blanks; tier monotonicity
   (Support ⊆ Core ⊆ Accelerate blanked sets).
4. **NoteForge contract** — `LLM_Modules/NoteForge_Base.md` (Guided + Cornell first), `mode`,
   `key`-slot marking, tier semantics. *Canonical; never fork in backend code.*
5. **NoteForge adapter + templates** for the build-order styles.
6. **(Follow-on, `api/`)** "attach printable to a Canvas assignment" — reuse assignment push.

---

## Guardrails that apply
- **Contracts are canonical** — NoteForge behavior lives in `LLM_Modules/NoteForge_Base.md`; do not
  encode note semantics by editing renderer code instead of the contract.
- **No validation in renderers** — keep `physical_handler`'s "trusts input is perfect" contract;
  validation stays upstream.
- **FERPA** — student names never baked into templates/tests; the paper layer renders content, not
  roster data. Filled exemplars/test fixtures use fictional content only.
- **engine/ is offline** — no network, no token in the render path.

## What NOT to touch
- The `api/` push logic and `LLM_Modules/*_Base.md` *existing* contracts (Quiz/Assignment/Page/Rubric).
- The Canvas/QTI render path (`engine/rendering/canvas/`).
- Validation layers.
