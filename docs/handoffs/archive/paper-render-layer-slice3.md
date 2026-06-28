# Handoff — Paper render layer, Slice 3: tier-redaction engine

**Parent spec:** `docs/handoffs/paper-render-layer.md`. **Predecessors:** slices 1–2 (committed on
`dev`: `270c385`, `6da8621`, `19445d4`).
**Lane:** Toyota (self-contained engine + unit tests).
**Status:** ready to implement.

## ⚠️ Read first — dependency / no visible output yet

Tier redaction blanks a fraction of **"key" slots**. Slots are a **NoteForge** construct (guided
notes, Cornell cells, etc.) that **does not exist yet** — the quiz model has no slots. So **this slice
ships the redaction *engine* + unit tests in isolation**, exercised with synthetic slot content. Its
first *visible* use is NoteForge (slices 4–5), where a single filled note JSON renders as
Support/Core/Accelerate/Extend by blanking more or fewer slots.

> Sequencing note for Adam: there is **no teacher-visible artifact** from slice 3 alone. If you'd
> rather see tiers on paper sooner, we can fold a thin NoteForge "guided cloze" template into this
> work so redaction has something to render. Otherwise this is pure plumbing that NoteForge plugs into.

This is the *mechanism* behind the product-standard 4 tiers ([[differentiation-model]]) — "same content,
scaffold up." For quizzes/assignments the 4 tiers stay an authoring **convention** (four authored
variants); for **notes**, redaction mechanizes the same principle from one source.

## Goal

A pure function `redact(printdoc, tier) -> PrintDoc` that returns a copy of the document with a
deterministic, tier-appropriate fraction of its **key** slots switched from "given" (show content) to
"blank" (show a write-in space). Properties: **deterministic** (same doc+tier ⇒ same result),
**monotonic** (Support ⊆ Core ⊆ Accelerate ⊆ Extend in which slots are blanked), **pure** (input
unmutated), and **key-consistent** (the fully-given document is always the answer key).

## Files to add / change

```
engine/rendering/physical/
  tiers.py        # NEW — tier constants + blank fractions
  redact.py       # NEW — redact(printdoc, tier) + slot walking
  printdoc.py     # ADD a Slot primitive (+ include in Block/QPayload unions)
  templates/_slot.html.j2   # NEW — small partial/macro NoteForge templates will reuse
  styles/print.css          # ADD .slot-blank + .slot-given
engine/tests/unit/test_tier_redaction.py   # NEW
```

### `tiers.py`
```python
TIERS = ("Support", "Core", "Accelerate", "Extend")

# Fraction of KEY slots blanked (write-in) at each tier. Support gives the most
# scaffolding (fewest blanks); Extend gives the least (all key slots blanked).
TIER_BLANK_FRACTION = {
    "Support": 0.25,
    "Core": 0.50,
    "Accelerate": 0.90,
    "Extend": 1.00,
}
```

### `printdoc.py` — add the Slot primitive
```python
@dataclass
class Slot:
    id: str                 # stable id — drives deterministic blanking order
    content_html: str       # the filled content (the "answer")
    key: bool = True        # learning target? only key slots are eligible to blank
    given: bool = True      # render state: True = show content, False = show a blank
```
A Slot may appear as a block, or nested inside future NoteForge layout blocks (Cornell columns,
Frayer quadrants, boxes). `redact` must find slots wherever they live (see below). Add `Slot` to the
`Block` union now; NoteForge will add the layout blocks that *contain* slots in slice 5.

### `redact.py`
```python
import copy, hashlib, math
from engine.rendering.physical.printdoc import PrintDoc, Slot
from engine.rendering.physical.tiers import TIER_BLANK_FRACTION

def redact(printdoc: PrintDoc, tier: str) -> PrintDoc:
    if tier not in TIER_BLANK_FRACTION:
        raise ValueError(f"unknown tier: {tier!r}")
    doc = copy.deepcopy(printdoc)               # purity: never mutate the input
    key_slots = [s for s in _iter_slots(doc) if s.key]
    # deterministic, stable order by hashed id — fixed "blanking priority"
    key_slots.sort(key=lambda s: hashlib.sha256(s.id.encode()).digest())
    n_blank = math.ceil(TIER_BLANK_FRACTION[tier] * len(key_slots))
    for i, slot in enumerate(key_slots):
        slot.given = i >= n_blank               # blank the first n_blank in priority order
    return doc

def _iter_slots(doc) -> "Iterator[Slot]":
    """Yield every Slot in the document, however nested (block-level today;
    inside NoteForge layout blocks later). Implement a small recursive walk over
    dataclass fields / lists so it keeps working as block types are added."""
    ...
```
- **Monotonic by construction:** the sort order is fixed, so the first `ceil(0.25 N)` ⊆ first
  `ceil(0.5 N)` ⊆ … ⊆ all. A slot blanked at Support is blanked at every harder tier.
- **Answer key:** there is no separate "redacted key." The **fully-given** document (no `redact`, or a
  helper `filled(doc)` that forces every `given=True`) is the teacher key — always matches the blanks.
- **Small-N caveat:** with very few key slots, `ceil` makes Support blank aggressively (1 slot ⇒
  Support blanks it). Realistic notes have many slots; document this and don't over-engineer.

### Template partial `_slot.html.j2` + CSS
A reusable snippet NoteForge templates include per slot:
```jinja
{% macro slot(s) %}
  {% if s.given %}<span class="slot-given">{{ s.content_html | safe }}</span>
  {% else %}<span class="slot-blank">&nbsp;</span>{% endif %}
{% endmacro %}
```
`.slot-blank { display:inline-block; min-width:1.5in; border-bottom:1pt solid #333; }` (a write-in
line). `.slot-given { }` (normal). Keep it **convergent HTML** (inline-block + border-bottom survive
Pandoc→DOCX) per the slice-1 fidelity rule.

## Tests (`test_tier_redaction.py`, pure-Python, no native libs)
Build a synthetic `PrintDoc` with ~10 key slots (+ a couple `key=False` scaffold slots), then assert:
1. **Determinism:** `redact(doc, t)` twice ⇒ identical `given` vectors.
2. **Purity:** original `doc` slots unchanged after `redact`.
3. **Counts:** blanked count == `ceil(fraction * n_key)` for each tier.
4. **Monotonicity:** `{blanked at Support} ⊆ {Core} ⊆ {Accelerate} ⊆ {Extend}` (compare slot id sets).
5. **Key-only:** `key=False` slots are never blanked at any tier.
6. **Extend:** all key slots blanked.
7. **Answer key:** `filled(doc)` (or the untouched doc) has every slot `given=True`.

## Deferred to NoteForge (slices 4–5), explicitly NOT in slice 3
- Emitting four tiered files per note (the packager/CLI looping tiers + calling `redact` then
  `render_html`). Add a `tier` param to the render/packaging path then, when there's note content.
- "Extend drops non-key scaffolds" (e.g., removing the Cornell cue column) — a NoteForge *template*
  decision, not core redaction.
- Any quiz-side use of slots (e.g., FITB word-bank as Support scaffold) — separate, later.

## Guardrails / do NOT touch
- Don't wire `redact` into the live quiz path — quizzes have no slots; leave `generate_physical_outputs`
  alone.
- Contracts canonical; Canvas/QTI path and validation untouched.
- Pure-Python engine; no native-lib dependency in redaction or its tests.
- No PII/FERPA in fixtures; `out/` stays gitignored.

## Acceptance criteria
- `redact(printdoc, tier)` exists with the four tiers; all 7 test groups pass; full `pytest` green.
- `Slot` added to `printdoc.py`; `_slot.html.j2` + `.slot-blank`/`.slot-given` present and render a
  write-in line vs. content (verifiable by rendering a synthetic slot doc, even if no NoteForge yet).
- No change to quiz output (slices 1–2 behavior identical; their tests still green).
