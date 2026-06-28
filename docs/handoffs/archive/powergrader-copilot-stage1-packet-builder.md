# PowerGrader Copilot Stage 1: Packet Builder And Batch Splitter

## Goal

Create a pure backend builder that turns an existing SAFE LLM bundle into Copilot batch folders. This stage does not change routes or UI.

The builder must create 3 teacher-upload files per batch and calculate batches locally using token estimates.

## Files To Create

- `api/powergrader/copilot_packet.py`
- `api/tests/test_powergrader_copilot_packet.py`

## Files To Change

- `api/powergrader/__init__.py` only if needed for package exports.

Do not change `api/webui/routes/powergrader.py` in this stage.

## New Module Constants

In `api/powergrader/copilot_packet.py`, define:

```python
DEFAULT_COPILOT_CONTEXT_TOKENS = 128_000
COPILOT_OUTPUT_RESERVE_TOKENS = 24_000
COPILOT_SAFETY_MARGIN_TOKENS = 8_000
MIN_STUDENTWORK_TOKENS = 20_000
PACKET_VERSION = 1
```

Use `webui.source_materials.estimate_text_tokens(text)` for rough token estimates.

## Public Function

Create this function:

```python
def build_copilot_batches(
    *,
    assignment_name: str,
    safe_dir: str,
    llm_bundle: dict,
    rubric_text: str,
    persona: dict,
    effective_context_tokens: int = DEFAULT_COPILOT_CONTEXT_TOKENS,
    output_reserve_tokens: int = COPILOT_OUTPUT_RESERVE_TOKENS,
    safety_margin_tokens: int = COPILOT_SAFETY_MARGIN_TOKENS,
) -> dict:
    ...
```

Return shape:

```python
{
    "version": 1,
    "packet_type": "copilot_batches",
    "mode": "fresh_chat_per_batch",
    "assignment_name": "...",
    "packet_folder": "...",
    "readme_path": "...",
    "budget": {
        "effective_context_tokens": 128000,
        "output_reserve_tokens": 24000,
        "safety_margin_tokens": 8000,
        "fixed_context_tokens": 1234,
        "available_studentwork_tokens": 94766,
    },
    "batch_count": 2,
    "student_count": 34,
    "batches": [
        {
            "batch_id": "batch-01",
            "label": "Batch 1 of 2",
            "folder": "...",
            "files": {
                "assignment_info": "...",
                "rubric_persona": "...",
                "student_work": "..."
            },
            "prompt": "...",
            "student_count": 17,
            "token_estimate": 84200,
            "expected_results": [
                {"pseudonym": "Sparky McGee", "item_id": "42"}
            ],
            "status": "pending",
            "imported_at": None,
            "updated": 0,
            "warnings": []
        }
    ],
    "warnings": []
}
```

All paths should be absolute filesystem paths, matching the existing packet artifact style.

## Folder Layout

Root folder:

```text
<safe_dir>/Safe AI Packet - <AssignmentName>/Copilot Batches/
```

Batch folders:

```text
<safe_dir>/Safe AI Packet - <AssignmentName>/Copilot Batches/Batch 01 of 05/
<safe_dir>/Safe AI Packet - <AssignmentName>/Copilot Batches/Batch 02 of 05/
```

Use `feedback_pipeline._safe(assignment_name, max_len=60)` or the existing safe naming helper from `packet.py` to make filesystem-safe names.

## Upload File Names

Each batch folder must contain exactly these three upload files:

```text
01 - <SafeAssignmentName> - Assignment Information - SAFE.md
02 - <SafeAssignmentName> - Rubric and TA Personality - SAFE.md
03 - <SafeAssignmentName> - StudentWork - SAFE - Batch 01 of 05.md
```

If there are 5 batches, every batch folder gets its own copies of files 01 and 02. This duplication is intentional. Each fresh Copilot chat must be self-contained.

## Assignment Information File

Build this file from `llm_bundle["shared_context"]`.

Required sections:

```markdown
# Assignment Information - SAFE

Assignment: <assignment_name>

This file contains shared assignment/context material for a pseudonymized PowerGrader batch.
It should be uploaded as file 01.

## Assignment Directions

<shared_context.assignment_description or "No assignment directions were included.">

## Source Materials

### <material title>

Source: <material source>

<material text>
```

If there are no materials, include:

```text
No separate source material was included.
```

Do not include real student names.

## Rubric And TA Personality File

Required sections:

```markdown
# Rubric and TA Personality - SAFE

Assignment: <assignment_name>

This file contains scoring instructions for a pseudonymized PowerGrader batch.
It should be uploaded as file 02.

## AI Teaching Assistant Personality

Name: <persona name or "your AI teaching assistant">

<persona personality or "Use a clear, supportive, rubric-based teacher voice.">

## Rubric

<rubric_text or "No rubric text was provided. Use the assignment point value and teacher directions.">

## Required JSON Output

Return only a JSON array. Each element must be exactly:

```json
{
  "pseudonym": "<copy from StudentWork exactly>",
  "item_id": "<copy from StudentWork exactly>",
  "score": 2,
  "feedback": "Brief rubric-based feedback. End with the disclosure sentence exactly once.",
  "disclosure": "Drafted by <TA name> (AI), reviewed by your teacher."
}
```

Rules:

- Score only students in file 03.
- Copy `pseudonym` and `item_id` exactly.
- `score` may be a number or null.
- `feedback` must be non-empty.
- End feedback with the disclosure sentence exactly once.
- Do not identify students.
- Do not mention real names.
```

The disclosure sentence must use the persona name when available.

## StudentWork File

Required sections:

```markdown
# StudentWork - SAFE - Batch 01 of 05

Assignment: <assignment_name>
Batch: 01 of 05
Student count in this file: 17

Score only the students in this file.
Do not score students from another batch.

## Student 01

Pseudonym: Sparky McGee
Item ID: 42
Possible points: 2

### Response

<student response text>
```

If a response has no text, include:

```text
No text response was available in the SAFE packet.
```

## Batch Prompt

Each batch metadata object must include a `prompt` string for the UI to copy.

Prompt template:

```text
Use the three uploaded files in order: 01 Assignment Information, 02 Rubric and TA Personality, and 03 StudentWork for Batch <N> of <TOTAL>.

Score only the students listed in the StudentWork file for Batch <N> of <TOTAL>. Do not score students from any other batch.

Return only valid JSON. Return a JSON array only, with one object per scored student. Copy pseudonym and item_id exactly from StudentWork.
```

## Splitting Algorithm

1. Build the exact text for file 01.
2. Build the exact text for file 02.
3. Build a text block for each student.
4. Estimate fixed context tokens:

   ```python
   fixed_context_tokens = estimate(file_01_text) + estimate(file_02_text) + estimate(batch_prompt_template)
   ```

5. Compute:

   ```python
   available = effective_context_tokens - output_reserve_tokens - safety_margin_tokens - fixed_context_tokens
   ```

6. If `available < MIN_STUDENTWORK_TOKENS`, still build batches, but add a top-level warning:

   ```text
   Assignment information plus rubric/persona is large; Copilot may miss student work. Consider shorter context or API scoring.
   ```

7. Pack students sequentially in SAFE bundle order.
8. Do not split one student across batches.
9. If a single student's block exceeds `available`, put that student alone in a batch and add a batch warning:

   ```text
   This one student's SAFE work is larger than the target Copilot budget. Score this batch carefully or manually.
   ```

10. After final batch count is known, write all batch folders/files with correct `Batch 01 of 05` labels.

## Tests To Add

In `api/tests/test_powergrader_copilot_packet.py`, add tests with fictional names only.

Test 1: creates one small batch.

- Build a fake `llm_bundle` with two students.
- Call `build_copilot_batches(...)`.
- Assert `batch_count == 1`.
- Assert there is one batch folder.
- Assert the batch folder contains exactly 3 `.md` upload files.
- Assert file names start with `01 -`, `02 -`, `03 -`.
- Assert StudentWork contains pseudonyms and item IDs.
- Assert files do not contain any fake real names used outside pseudonyms.

Test 2: forces multiple batches.

- Use a very small `effective_context_tokens`.
- Build five students with long repeated safe text.
- Assert `batch_count > 1`.
- Assert every batch has exactly 3 upload files.
- Assert every expected result appears in exactly one batch.

Test 3: oversized single student.

- Use one very long student response.
- Assert the student gets a single-student batch.
- Assert the batch has a warning.

## Verification

Run:

```powershell
py -m pytest api/tests/test_powergrader_copilot_packet.py
py -m pytest api/tests/test_powergrader_packet.py api/tests/test_route_contract.py
```

All tests must pass.
