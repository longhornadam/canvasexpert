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

## Guided-Cloze Notes

Slice 1 supports only:

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
