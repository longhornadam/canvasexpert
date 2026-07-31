# NoteForge Base Contract

NoteForge authors printable notes from a single filled source. The engine renders that source into
tiered student handouts by blanking key slots, plus a filled teacher key.

## Output Wrapper

Return exactly one JSON object inside these tags:

```text
<NOTEFORGE_JSON>
{
  "version": "1.0-json",
  "type": "guided_notes",
  "title": "Photosynthesis",
  "topic": "How plants make food",
  "mode": "blank",
  "body": []
}
</NOTEFORGE_JSON>
```

## Supported Note Types

This version supports:

- `guided_notes`
- `cornell`
- `frayer`

All note types support `mode: "blank"` and `mode: "exemplar"`.

## Guided-Cloze Notes

Use guided cloze for linear notes with paragraphs and bullets.

- `type`: `guided_notes`
- `mode`: `blank` or `exemplar`
- `body`: ordered note blocks

Supported body blocks:

```json
{ "type": "heading", "text": "What Is Photosynthesis?" }
```

```json
{
  "type": "paragraph",
  "text": "Plants make their own food in the {{chloroplast}}, using energy from {{sunlight}}."
}
```

## Cornell Notes

Use Cornell notes when students need aligned cue questions and note/details, followed by a summary.
Render the whole page from one `cornell` object:

```json
{
  "version": "1.0-json",
  "type": "cornell",
  "mode": "blank",
  "title": "Photosynthesis",
  "topic": "How plants make food",
  "rows": [
    {
      "cue": "What is {{photosynthesis}}?",
      "note": "The process where plants make {{glucose}} using light energy."
    },
    {
      "cue": "Where does it happen?",
      "note": "Inside the {{chloroplast}}, using the green pigment {{chlorophyll}}."
    }
  ],
  "summary": "Plants turn {{sunlight}}, water, and carbon dioxide into food and {{oxygen}}."
}
```

Authoring rules:

- Put cue questions or cue terms in `cue`.
- Put explanations, details, and examples in `note`.
- Use `summary` for a concise synthesis statement.
- Slots in cues, notes, and summary are key learning targets and may be blanked by tier.

## Frayer Model

Use Frayer for vocabulary or concept development. The `term` is given; the four quadrants contain
the key slots.

```json
{
  "version": "1.0-json",
  "type": "frayer",
  "mode": "blank",
  "title": "Vocabulary: Photosynthesis",
  "term": "Photosynthesis",
  "definition": "How plants make {{glucose}} from light, water, and CO2.",
  "characteristics": "Happens in the {{chloroplast}}; needs {{chlorophyll}}; releases {{oxygen}}.",
  "examples": "A fern in sunlight; {{algae}} in a pond.",
  "non_examples": "{{respiration}}; a rock; an animal eating."
}
```

Authoring rules:

- Keep `term` visible; do not wrap it in slot braces in this version.
- Use `definition`, `characteristics`, `examples`, and `non_examples` as concise quadrant text.
- Slots in quadrant text are key learning targets and may be blanked by tier.

```json
{
  "type": "bullets",
  "items": [
    "The green pigment that captures light is {{chlorophyll}}.",
    "The sugar the plant produces is {{glucose}}."
  ]
}
```

## Slot Rules

Write answer slots inline with double braces: `{{answer term}}`.

Every `{{...}}` slot is a key learning target and may be blanked by the tier renderer. Text outside
the braces is fixed scaffold text and remains visible.

Authoring rules:

- Slot one concept, term, phrase, or short answer at a time.
- Prefer vocabulary, causes, effects, steps, names, and relationships.
- Do not slot function words or trivial glue words.
- Keep every sentence readable after the slot is blanked.
- Keep slot answers concise enough for a student write-in line.
- Use fictional or curriculum content only; never include student names or private student data.

## Modes

- `blank`: render Support, Core, Accelerate, and Extend handouts by blanking more key slots at each tier.
- `exemplar`: render a completed study aid with all slots shown; no tier redaction is applied.

## Example

```text
<NOTEFORGE_JSON>
{
  "version": "1.0-json",
  "type": "guided_notes",
  "title": "Photosynthesis",
  "topic": "How plants make food",
  "mode": "blank",
  "body": [
    { "type": "heading", "text": "What Is Photosynthesis?" },
    {
      "type": "paragraph",
      "text": "Plants make their own food in the {{chloroplast}}, using energy from {{sunlight}}, plus water and {{carbon dioxide}}."
    },
    {
      "type": "bullets",
      "items": [
        "The green pigment that captures light is {{chlorophyll}}.",
        "The sugar the plant produces is {{glucose}}.",
        "The gas released is {{oxygen}}."
      ]
    }
  ]
}
</NOTEFORGE_JSON>
```
