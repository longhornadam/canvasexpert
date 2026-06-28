# PowerGrader Copilot Stage 2: Integrate Batch Generation Into Packet Mode

## Goal

When a teacher starts PowerGrader in `Use My AI Chat` mode (`mode == "packet"`), generate Copilot batch folders in addition to the existing Safe AI Packet ZIP.

Do not remove the legacy packet ZIP yet.

## Files To Change

- `api/powergrader/ai_workflow.py`
- `api/powergrader/session_builder.py`
- `api/webui/routes/powergrader.py` only if needed to pass new response fields through
- `api/tests/test_powergrader_packet.py` or new focused tests if needed

## Behavior

For `mode == "packet"`:

- Continue existing privacy pipeline.
- Continue writing SAFE and PRIVATE artifacts.
- Continue writing the existing packet ZIP.
- Also create Copilot batch folders using `copilot_packet.build_copilot_batches(...)`.
- Store batch metadata in the saved session.

For `mode == "assisted"`:

- Do not generate Copilot batches.
- Keep OpenRouter behavior unchanged.

For `mode == "fast"`:

- Do not generate Copilot batches.

## Import

In `api/powergrader/ai_workflow.py`, import:

```python
from powergrader import copilot_packet
```

## Where To Generate

In `run_ai_workflow(...)`, after:

```python
packet_info = packet.build_safe_ai_packet(...)
privacy_artifacts.update(packet_info)
```

add Copilot generation only when `mode == "packet"` and `safe_students > 0`.

Use:

```python
copilot_info = copilot_packet.build_copilot_batches(
    assignment_name=assignment_name,
    safe_dir=safe_dir,
    llm_bundle=llm_bundle,
    rubric_text=rubric_text,
    persona=persona,
)
```

Then add:

```python
privacy_artifacts["copilot_packet_folder"] = copilot_info.get("packet_folder")
privacy_artifacts["copilot_readme"] = copilot_info.get("readme_path")
privacy_artifacts["copilot_batch_count"] = copilot_info.get("batch_count", 0)
privacy_artifacts["copilot_student_count"] = copilot_info.get("student_count", 0)
```

Also include the full `copilot_info` in the AI workflow return dict:

```python
"copilot_packet": copilot_info
```

If no Copilot packet was generated, return:

```python
"copilot_packet": None
```

## Privacy Step

When Copilot batches are created, append:

```python
privacy.privacy_step(
    "copilot_batches",
    "Created Copilot batch folders",
    "ok",
    f"{copilot_info['batch_count']} batch folder(s), each with 3 numbered upload files.",
    path=copilot_info.get("packet_folder"),
    action_label="Open Copilot batch folder",
)
```

If `copilot_info["warnings"]` is non-empty, use status `"warn"` and append the first warning to the detail.

## Session Schema

Add a new top-level session key:

```json
"copilot_packet": {
  "version": 1,
  "packet_type": "copilot_batches",
  "mode": "fresh_chat_per_batch",
  "assignment_name": "Essay",
  "packet_folder": "...",
  "readme_path": "...",
  "budget": {...},
  "batch_count": 5,
  "student_count": 117,
  "batches": [...]
}
```

Only packet mode sessions should have a non-null `copilot_packet`.

Update `session_builder.build_session(...)` signature to accept:

```python
copilot_packet: dict | None = None
```

Then include:

```python
"copilot_packet": copilot_packet,
```

in the returned session dict.

Update the call in `routes/powergrader.py` to pass:

```python
copilot_packet=ai_result.get("copilot_packet")
```

## Start Response

Update `pg_start()` success response to include:

```python
"copilot_batch_count": (ai_result.get("copilot_packet") or {}).get("batch_count", 0),
"copilot_packet_folder": (ai_result.get("copilot_packet") or {}).get("packet_folder"),
```

Do not remove existing fields.

## README File

The Stage 1 builder should write a parent README. If it does not yet, add it now.

File:

```text
README - Copilot Steps.md
```

Content must explicitly say:

```markdown
# Copilot Steps

This is one PowerGrader session. Do not start a new PowerGrader session for each batch.

For each batch:

1. Start a new Copilot chat.
2. Upload files 01, 02, and 03 from that batch folder.
3. Paste the batch prompt from PowerGrader.
4. Copy Copilot's JSON response.
5. Return to the same PowerGrader session.
6. Paste results into the matching batch import box.
7. Continue with the next batch.
```

Do not place this README inside each batch folder as a fourth upload file.

## Do Not Do

- Do not remove legacy `packet_zip`.
- Do not change OpenRouter scoring.
- Do not change existing `privacy_artifacts.safe_bundle`.
- Do not change `feedback_pipeline.write_safe_and_private(...)`.
- Do not change result schema.

## Verification

Run:

```powershell
py -m pytest api/tests/test_powergrader_copilot_packet.py
py -m pytest api/tests/test_powergrader_packet.py api/tests/test_route_contract.py
```

If you add response fields without adding routes, route contract should remain unchanged.

## Acceptance Criteria

- Packet mode sessions save `copilot_packet` metadata.
- Copilot batch folders are generated with exactly 3 upload files per batch.
- Existing Safe AI Packet ZIP still exists.
- Assisted/API mode behavior is unchanged.
- Focused tests pass.
