# PowerGrader Copilot Batch Packet Handoff Index

Status: Completed and archived after Stages 1-5 were implemented.

## Purpose

PowerGrader's `Use My AI Chat` flow needs to be friendly for Microsoft Copilot in an education tenant.

Assumptions:

- Many users will use Microsoft Copilot.
- Copilot may allow only 3 uploaded files at a time.
- Copilot may not accept ZIP files.
- Copilot context behavior is opaque, even when the underlying model is strong.

The new flow must create one PowerGrader session for the Canvas assignment, then split the SAFE student work into Copilot-sized batches. Teachers import each Copilot response back into the same PowerGrader session.

## Teacher Mental Model

Use this exact product model:

1. Start one PowerGrader session for one Canvas assignment.
2. Choose `Use My AI Chat`.
3. PowerGrader creates one or more Copilot batches.
4. For each batch, the teacher starts a fresh Copilot chat.
5. The teacher uploads exactly 3 numbered files from that batch folder.
6. The teacher pastes the batch prompt.
7. The teacher copies Copilot's JSON response.
8. The teacher pastes it into that batch inside the same PowerGrader session.
9. PowerGrader fills AI suggestions cumulatively.
10. The teacher reviews, edits, approves, and pushes to Canvas from the same session.

Do not tell teachers to start a new PowerGrader session for each batch.

## Stage Order

Complete these handoffs in order:

1. `docs/handoffs/powergrader-copilot-stage1-packet-builder.md`
2. `docs/handoffs/powergrader-copilot-stage2-integrate-generation.md`
3. `docs/handoffs/powergrader-copilot-stage3-batch-import.md`
4. `docs/handoffs/powergrader-copilot-stage4-queue-ui.md`
5. `docs/handoffs/powergrader-copilot-stage5-tests-and-polish.md`

Do not combine stages unless explicitly asked.

## Global Guardrails

- Do not change Fast mode behavior.
- Do not change Auto-Score With API behavior except where shared session display code must tolerate new fields.
- Do not remove the existing Safe AI Packet ZIP yet. Keep it for backward compatibility.
- Do not write real student data, tokens, district data, or submission content into repo files or tests.
- Do not touch `LLM_Modules/`.
- Do not touch `api/feedback_pipeline.py`, `api/feedback_safety.py`, `api/feedback_vault.py`, or `api/openrouter_client.py` unless a handoff explicitly says so. These handoffs do not require edits there.
- Preserve route paths unless a handoff explicitly adds a route. Prefer extending existing endpoints with optional form fields.
- Keep `api/webui/routes/powergrader.py` under 500 lines.
- Keep new backend PowerGrader modules under 500 lines.

## Context Budget Policy

Default effective Copilot context budget:

```python
DEFAULT_COPILOT_CONTEXT_TOKENS = 128_000
COPILOT_OUTPUT_RESERVE_TOKENS = 24_000
COPILOT_SAFETY_MARGIN_TOKENS = 8_000
```

Usable student-work budget:

```python
available_studentwork_tokens = (
    effective_context_tokens
    - output_reserve_tokens
    - safety_margin_tokens
    - fixed_context_tokens
)
```

Do not assume 400k. Design for 128k by default because Copilot attachment handling is opaque.

## Three Uploaded Files Per Batch

Each Copilot batch folder must contain exactly these 3 upload files:

```text
01 - <AssignmentName> - Assignment Information - SAFE.md
02 - <AssignmentName> - Rubric and TA Personality - SAFE.md
03 - <AssignmentName> - StudentWork - SAFE - Batch 01 of 05.md
```

For one-batch assignments, still use:

```text
03 - <AssignmentName> - StudentWork - SAFE - Batch 01 of 01.md
```

Additional helper files may exist in the parent packet folder, but the batch folder itself should make the three upload files obvious.

## Verification Baseline

Run after each implementation stage:

```powershell
py -m pytest api/tests/test_powergrader_packet.py api/tests/test_route_contract.py
```

Run full API tests before final handoff:

```powershell
py -m pytest api/tests
```
