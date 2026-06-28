# Handoff — NoteForge, vertical slice 1: guided-cloze notes with tiers

**Parent spec:** `docs/handoffs/paper-render-layer.md`. **Predecessors:** slices 1–3 on `dev`
(`270c385`, `6da8621`, `19445d4`, `9a8927d`).
**Lane:** Toyota for the code; the **contract shape below is fully specified** so no design round-trip.
**Status:** ready to implement.

## Why this slice

This is the first thing that makes tier differentiation **visible on paper**. One filled note JSON →
the *same* notes printed at Support / Core / Accelerate / Extend (more blanks as you go up) + a filled
answer key. It exercises the whole stack end-to-end: a new **NoteForge** contract → adapter →
`PrintDoc` (with `Slot`s) → `redact()` (slice 3) → HTML substrate → Chromium PDF + Pandoc DOCX.

Scope is deliberately ONE note style: **guided cloze** (fill-in-the-blank prose). It's the workhorse
and the simplest. Cornell / Frayer / boxes-and-bullets are cheap follow-ons on the same spine (a later
slice). Like slice 1, this ships as a **dev CLI (`note_spike`), non-destructive** — Adam reviews the
tiered output, *then* a follow-on wires NoteForge into the live webui/orchestrator (mirrors slice 2).

## The contract — `LLM_Modules/NoteForge_Base.md` (canonical; authored once, engine consumes it)

Define `<NOTEFORGE_JSON>` for guided notes. Slots are authored **inline** with `{{double braces}}`
(LLM-friendly — far easier than nested run arrays). Everything outside braces is fixed scaffold text.

```
<NOTEFORGE_JSON>
{
  "version": "1.0-json",
  "type": "guided_notes",
  "title": "Photosynthesis",
  "topic": "How plants make food",
  "mode": "blank",
  "body": [
    { "type": "heading", "text": "What Is Photosynthesis?" },
    { "type": "paragraph",
      "text": "Plants make their own food in the {{chloroplast}}, using energy from {{sunlight}}, plus water and {{carbon dioxide}}." },
    { "type": "bullets", "items": [
        "The green pigment that captures light is {{chlorophyll}}.",
        "The sugar the plant produces is {{glucose}}.",
        "The gas released is {{oxygen}}."
    ] }
  ]
}
</NOTEFORGE_JSON>
```

- `type`: `guided_notes` (only style this slice). `mode`: `blank` (student fill-in; tiers redact) or
  `exemplar` (all slots shown — a completed study aid; no redaction).
- `body` blocks: `heading` (`text`), `paragraph` (`text` with `{{slots}}`), `bullets` (`items[]`, each
  a string with `{{slots}}`).
- Every `{{…}}` is a **key** slot (eligible to blank). The brace contents are the **answer**.
- The `NoteForge_Base.md` doc states the rules an authoring LLM follows (one concept per slot, slot the
  vocabulary/target terms not function words, keep scaffold sentences readable when blanked, etc.).
  **Do not encode note semantics in engine code — they live in the contract.**

## Engine changes

### 1. `printdoc.py` — note block types (inline runs can hold `Slot`s)
```python
@dataclass
class Heading:
    text: str

@dataclass
class Para:
    runs: list            # list[str | Slot]  — literal text and inline slots, in order

@dataclass
class BulletList:
    items: list           # list[list[str | Slot]]  — each bullet is its own run list
```
Add these to the `Block` union. `iter_slots` (slice 3) already walks dataclass fields + lists, so it
finds `Slot`s inside `Para.runs` / `BulletList.items` with no change.

### 2. `note_adapter.py` — NoteForge JSON → `PrintDoc`
```python
def to_printdoc(note: dict) -> PrintDoc:   # note = parsed JSON
    blocks = []
    for bi, block in enumerate(note.get("body", [])):
        t = block.get("type")
        if t == "heading":
            blocks.append(Heading(text=block.get("text", "")))
        elif t == "paragraph":
            blocks.append(Para(runs=_parse_runs(block.get("text", ""), bi)))
        elif t == "bullets":
            blocks.append(BulletList(items=[
                _parse_runs(item, f"{bi}-{ii}") for ii, item in enumerate(block.get("items", []))
            ]))
    return PrintDoc(title=note.get("title", "Untitled Notes"),
                    instructions=note.get("topic", ""), blocks=blocks, answer_key=None)

def _parse_runs(text: str, prefix) -> list:
    # split on {{...}}; even segments = literal text, odd = slot answers
    parts = re.split(r"\{\{(.+?)\}\}", text)
    runs, si = [], 0
    for i, seg in enumerate(parts):
        if i % 2 == 0:
            if seg:
                runs.append(seg)
        else:
            runs.append(Slot(id=f"b{prefix}s{si}", content_html=seg.strip(), key=True))
            si += 1
    return runs
```
- **Slot ids are positional and stable** (`b{block}s{slot}`) — required for deterministic redaction.
- No validation (trust input), consistent with the quiz path.
- Parsing the tag envelope: extract the JSON between `<NOTEFORGE_JSON>`…`</NOTEFORGE_JSON>` (reuse the
  existing tagged-payload helper if convenient, else a simple strip), then `json.loads`.

### 3. `note.html.j2` — note template (uses the `_slot.html.j2` macro from slice 3)
```jinja
{% extends "base.html.j2" %}
{% from "_slot.html.j2" import slot %}
{% block content %}
<p class="name-line">Name: ________________________________________________</p>
<h1>{{ printdoc.title }}{% if tier %} — {{ tier }}{% endif %}</h1>
{% if printdoc.instructions %}<p class="note-topic">{{ printdoc.instructions }}</p>{% endif %}
{% for block in printdoc.blocks %}
  {% if block.__class__.__name__ == "Heading" %}
    <h2 class="note-heading">{{ block.text }}</h2>
  {% elif block.__class__.__name__ == "Para" %}
    <p class="note-para">{% for run in block.runs %}{% if run is string %}{{ run }}{% else %}{{ slot(run) }}{% endif %}{% endfor %}</p>
  {% elif block.__class__.__name__ == "BulletList" %}
    <ul class="note-bullets">{% for item in block.items %}<li>{% for run in item %}{% if run is string %}{{ run }}{% else %}{{ slot(run) }}{% endif %}{% endfor %}</li>{% endfor %}</ul>
  {% endif %}
{% endfor %}
{% endblock %}
```
Add light CSS for `.note-heading`, `.note-para`, `.note-bullets`, `.note-topic` (convergent HTML; the
`.slot-blank` write-in line already exists).

### 4. `html_renderer.render_html` — add the note variant
Accept `variant="note"` → `note.html.j2`, and pass an optional `tier` label into the context (for the
"— Support" header). Keep `quiz`/`key` behavior unchanged.

### 5. Per-tier emission + `note_spike.py` (dev CLI)
```
py -m engine.rendering.physical.note_spike --input <note.json> --output <dir> [--tiers Support,Core,Accelerate,Extend]
```
Flow:
```python
note = _load_noteforge_json(input_path)
printdoc = to_printdoc(note)
base = sanitize_filename(printdoc.title) or "Untitled_Notes"
if note.get("mode") == "exemplar":
    docs = {"Exemplar": filled(printdoc)}
else:
    docs = {tier: redact(printdoc, tier) for tier in selected_tiers}
docs["KEY"] = filled(printdoc)                      # teacher answer key = all slots shown
for label, doc in docs.items():
    html = render_html(doc, variant="note", tier=(label if label not in ("KEY","Exemplar") else None))
    # student-locked PDF + editable DOCX per artifact (mirror the quiz path)
    html_to_pdf(html, css, out/f"{base}_{label}.pdf")
    with TemporaryDirectory() as tmp:
        ref = build_reference_docx(...)
        html_to_docx(html, ref, out/f"{base}_{label}.docx")
```
Default output set: `{base}_{Support,Core,Accelerate,Extend}.pdf` + `.docx`, plus `{base}_KEY.pdf` +
`.docx`. (File count is the one knob — fine to dial back to "PDF per tier + KEY both formats" if it
feels heavy; note it in the CLI `--help`.)

## Tests (`engine/tests/unit/test_noteforge_guided_cloze.py`, pure-Python, no native libs)
1. **Adapter:** a sample note JSON → `PrintDoc` with the right block types; `{{…}}` becomes `Slot`s with
   stable ids and `key=True`; literal text preserved between slots.
2. **Tiering integration:** for the sample, `redact(printdoc, "Support")` blanks fewer slots than
   `"Extend"`; rendered Support HTML contains *more* answer text than Extend; **no blanked answer leaks**
   into the student HTML at any tier (assert a known Extend-blanked term is absent).
3. **Answer key:** `filled(printdoc)` HTML contains every answer term.
4. **Exemplar mode:** renders all slots filled, no redaction.
5. **Render smoke (skip-guarded):** if Chromium+Pandoc present, `note_spike` writes non-empty PDFs/DOCX
   for each tier + KEY.
Keep full `pytest` green.

## Deferred (NOT this slice)
- **Live wiring** (webui route + orchestrator for notes) — follow-on, mirrors slice 2. This slice is the
  reviewable dev CLI only.
- **Other note styles** (Cornell, Frayer, boxes-and-bullets, outline, sequence) — follow-on templates on
  this spine; each adds a `type` + a template branch.
- **"Extend drops scaffolds"** beyond blanking (e.g. removing cue columns) — Cornell-specific, later.
- **Slot variants** (always-given emphasis, multi-answer) — keep MVP to plain key slots.

## Guardrails / do NOT touch
- `NoteForge_Base.md` is **canonical** — note semantics live there, not in adapter/template code.
- Quiz path (`generate_physical_outputs`, `quiz_adapter`, `quiz.html.j2`) and the Canvas/QTI path
  untouched; slices 1–3 tests stay green.
- Renderers keep "trust input, no validation."
- Pure-Python engine; native emitters stay lazy-imported. No PII/FERPA in fixtures; `out/` gitignored.

## Acceptance criteria
- `LLM_Modules/NoteForge_Base.md` exists and documents the guided-cloze contract above.
- `note_spike` on a sample guided-cloze JSON writes, into `out/`, a Support→Extend set of PDFs/DOCX +
  a KEY — where Support is visibly mostly-filled and Extend mostly-blank, and the KEY is fully filled.
- All unit tests pass incl. the **no-answer-leak** assertion; full `pytest` green.
- No change to quiz output.
- Hand the `out/` tiered set back to Adam for visual review before any live-wiring follow-on.
