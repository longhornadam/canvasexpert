# Handoff — NoteForge styles: Cornell + Frayer

**Parent spec:** `docs/handoffs/paper-render-layer.md`. **Predecessors:** slices 1–4 on `dev`
(…`9a8927d`, `b3ba037`).
**Lane:** Toyota; contract + layouts fully specified below.
**Status:** ready to implement.

## Why these two

Guided cloze (slice 4) proved tiered **flow** content. Cornell and Frayer prove the spine handles
**structured layouts** too — a 2-column grid and a 2×2 grid — so every remaining style
(boxes-and-bullets, outline, sequence, two-column) becomes a trivial template branch afterward. Both
reuse everything already built: `Slot` + `redact()` (slice 3), the `_slot` macro, `render_html(...,
variant="note")`, and the `note_spike` CLI (per-tier PDF+DOCX + KEY) — **no changes needed to redaction,
the CLI, or the emitters.** Still review-first (dev CLI); live wiring is slice 6.

## Roadmap (renumbered for clarity)
- **Slice 5 (this):** Cornell + Frayer note styles.
- **Slice 6:** Live wiring — NoteForge → webui route + orchestrator → `Finished_Exports` (mirrors slice 2).
- **Slice 7:** Canvas-attach (attach the printable to a Canvas assignment), `api/`.
- Trivial follow-ons (any time): boxes-and-bullets, outline, sequence, two-column templates.

## Design — both styles are a single top-level layout block

A Cornell or Frayer note is **one structured page**, not a flow of paragraphs. Model each as a single
top-level block in `PrintDoc.blocks`; `note.html.j2` dispatches on block type and renders the whole
layout. Cells hold the same inline `runs` (text + `Slot`s) the guided-cloze parser already produces, so
`iter_slots` finds them and `redact`/`filled` work unchanged.

### Contract additions — `LLM_Modules/NoteForge_Base.md`

**Cornell** (`type: "cornell"`): aligned cue|note rows + a summary.
```json
{
  "version": "1.0-json", "type": "cornell", "mode": "blank",
  "title": "Photosynthesis", "topic": "How plants make food",
  "rows": [
    { "cue": "What is {{photosynthesis}}?",
      "note": "The process where plants make {{glucose}} using light energy." },
    { "cue": "Where does it happen?",
      "note": "Inside the {{chloroplast}}, using the green pigment {{chlorophyll}}." }
  ],
  "summary": "Plants turn {{sunlight}}, water, and carbon dioxide into food and {{oxygen}}."
}
```

**Frayer** (`type: "frayer"`): a vocabulary term with four quadrants. The `term` is **given** (the word
being studied); the quadrant text carries the `{{slots}}`.
```json
{
  "version": "1.0-json", "type": "frayer", "mode": "blank",
  "title": "Vocabulary: Photosynthesis", "term": "Photosynthesis",
  "definition": "How plants make {{glucose}} from light, water, and CO2.",
  "characteristics": "Happens in the {{chloroplast}}; needs {{chlorophyll}}; releases {{oxygen}}.",
  "examples": "A fern in sunlight; {{algae}} in a pond.",
  "non_examples": "{{respiration}}; a rock; an animal eating."
}
```
Document both in `NoteForge_Base.md` (canonical). `mode: "exemplar"` works for both (filled study aid).

### `printdoc.py` — layout blocks
```python
@dataclass
class CornellRow:
    cue: list          # runs (str | Slot)
    note: list         # runs (str | Slot)

@dataclass
class CornellLayout:
    rows: list         # list[CornellRow]
    summary: list      # runs (str | Slot)

@dataclass
class FrayerGrid:
    term: str
    definition: list        # runs
    characteristics: list   # runs
    examples: list          # runs
    non_examples: list      # runs
```
Add both to the `Block` union. (Cells are `runs` lists, identical to `Para.runs` — `iter_slots` already
recurses into them.)

### `note_adapter.py` — dispatch on `type`
`to_printdoc(note)` branches: `guided_notes` → existing flow blocks; `cornell` → `[CornellLayout(...)]`;
`frayer` → `[FrayerGrid(...)]`. Reuse `_parse_runs` for every cell, with **stable, unique** slot id
prefixes so redaction stays deterministic, e.g.:
- Cornell: `cue{r}` / `note{r}` per row r → `_parse_runs(text, f"cue{r}")`, `_parse_runs(text, f"note{r}")`, summary `_parse_runs(text, "sum")`.
- Frayer: prefixes `def` / `char` / `ex` / `nonex`.

### `note.html.j2` — add two branches (convergent HTML = tables)
```jinja
{% elif block.__class__.__name__ == "CornellLayout" %}
  <table class="cornell-table"><tbody>
  {% for row in block.rows %}
    <tr>
      <td class="cornell-cue">{% for r in row.cue %}{% if r is string %}{{ r }}{% else %}{{ slot(r) }}{% endif %}{% endfor %}</td>
      <td class="cornell-note">{% for r in row.note %}{% if r is string %}{{ r }}{% else %}{{ slot(r) }}{% endif %}{% endfor %}</td>
    </tr>
  {% endfor %}
  </tbody></table>
  <div class="cornell-summary"><strong>Summary:</strong>
    {% for r in block.summary %}{% if r is string %}{{ r }}{% else %}{{ slot(r) }}{% endif %}{% endfor %}</div>
{% elif block.__class__.__name__ == "FrayerGrid" %}
  <p class="frayer-term"><strong>Term:</strong> {{ block.term }}</p>
  <table class="frayer-table"><tbody>
    <tr><td class="frayer-cell"><div class="frayer-label">Definition</div>{{ _runs(block.definition) }}</td>
        <td class="frayer-cell"><div class="frayer-label">Characteristics</div>{{ _runs(block.characteristics) }}</td></tr>
    <tr><td class="frayer-cell"><div class="frayer-label">Examples</div>{{ _runs(block.examples) }}</td>
        <td class="frayer-cell"><div class="frayer-label">Non-Examples</div>{{ _runs(block.non_examples) }}</td></tr>
  </tbody></table>
```
The repeated `{% for r in runs %}…{% endfor %}` is worth extracting into a small `_runs(runs)` macro in
`_slot.html.j2` (text-or-slot) and reusing it in the guided-cloze branches too — DRY, optional but tidy.

CSS (convergent; tables survive Pandoc→DOCX): `.cornell-table { width:100%; }`,
`.cornell-cue { width:30%; border:1pt solid #999; vertical-align:top; padding:6pt; }`,
`.cornell-note { width:70%; border:1pt solid #999; vertical-align:top; padding:6pt; }`,
`.cornell-summary { border:1pt solid #999; padding:6pt; margin-top:8pt; }`,
`.frayer-table { width:100%; } .frayer-cell { width:50%; height:1.8in; border:1pt solid #999; vertical-align:top; padding:6pt; }`,
`.frayer-label { font-weight:700; font-size:9pt; }`, `.frayer-term { margin-bottom:6pt; }`.

### CLI — unchanged
`note_spike` already loops tiers, calls `redact`/`filled`, renders `variant="note"`, emits PDF+DOCX. It
works for the new types with **no change** (the layout lives in the blocks). Just point it at a Cornell
or Frayer JSON.

## Tests (`test_noteforge_cornell.py`, `test_noteforge_frayer.py`; pure-Python)
Per style:
1. **Adapter:** sample JSON → the layout block with cells parsed to runs; `{{…}}` → `Slot`s with stable
   unique ids across cells; `term` given (Frayer).
2. **Tiering:** `redact("Support")` blanks fewer cell slots than `"Extend"`; rendered Support HTML shows
   more answer text than Extend.
3. **No leak (the gate):** at every tier, a blanked slot's `content_html` is absent from the HTML.
4. **Answer key:** `filled(...)` HTML contains every answer term; Frayer shows the term.
5. **Exemplar mode:** all slots filled, no `.slot-blank`.
Keep full `pytest` green.

## Deferred (NOT this slice)
- Live wiring (slice 6). Boxes-and-bullets / outline / sequence / two-column styles (trivial follow-ons).
- "Extend empties the Cornell cue column" beyond per-slot blanking — a layout nicety, later.
- Frayer "name the term" variant (term as a slot) — keep term given for MVP.

## Guardrails / do NOT touch
- `NoteForge_Base.md` canonical — semantics live there, not in adapter/template code.
- Quiz path + Canvas/QTI path untouched; slices 1–4 tests stay green.
- Renderers keep "trust input, no validation"; pure-Python engine; native emitters stay lazy.
- No PII/FERPA in fixtures; `out/` gitignored.

## Acceptance criteria
- `NoteForge_Base.md` documents `cornell` and `frayer`.
- `note_spike` on a Cornell JSON and a Frayer JSON each writes a Support→Extend set + KEY (PDF+DOCX),
  with the layout intact in both PDF and DOCX and visible tier differences.
- All new tests pass incl. no-leak for both styles; full `pytest` green; quiz output unchanged.
- Hand the `out/` sets back to Adam for visual review (Cornell columns + summary; Frayer 2×2 grid).
