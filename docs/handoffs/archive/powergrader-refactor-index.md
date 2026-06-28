# PowerGrader Modularity Refactor Handoff Index

## Purpose

PowerGrader is working, but the implementation is too concentrated:

- `api/webui/routes/powergrader.py` is 1,308 lines.
- `api/webui/templates/powergrader_setup.html` is 814 lines.
- `api/webui/templates/powergrader_queue.html` is 847 lines.

The goal is not a product redesign. The goal is smaller files with discrete jobs while preserving current functionality.

## Baseline Verification

Before starting any stage, run:

```powershell
py -m pytest api/tests/test_powergrader_packet.py api/tests/test_route_contract.py
```

At inspection time, both tests passed.

## Stage Order

Complete these handoffs in order:

1. `docs/handoffs/powergrader-refactor-stage0-bugfix.md`
2. `docs/handoffs/powergrader-refactor-stage1-static-assets.md`
3. `docs/handoffs/powergrader-refactor-stage2-pure-backend-helpers.md`
4. `docs/handoffs/powergrader-refactor-stage3-context-estimates-canvas.md`
5. `docs/handoffs/powergrader-refactor-stage4-session-mutations.md`
6. `docs/handoffs/powergrader-refactor-stage5-start-workflow.md`

Do not skip stages. Do not combine stages unless explicitly asked by the user.

## Global Guardrails

- Do not change route paths.
- Do not change API response shapes.
- Do not change the session JSON schema unless a handoff explicitly says to.
- Do not change Canvas API behavior.
- Do not change privacy behavior.
- Do not touch `LLM_Modules/`.
- Do not touch `api/feedback_pipeline.py`, `api/feedback_safety.py`, `api/feedback_vault.py`, or `api/openrouter_client.py`.
- Do not introduce real student names, course data, tokens, district data, or submission content into repo files or tests.
- Session files must keep writing to the user workspace under `PowerGrader/`, never into the repo.

## Import Rule

The app is commonly run from the `api/` directory via:

```powershell
cd api
py qf_ui.py
```

Therefore new PowerGrader backend modules should be imported as top-level package modules from route files:

```python
from powergrader import packet, privacy, session_store
```

Do not use `from api.powergrader ...` inside `api/webui/routes/powergrader.py`.

## Completion Target

After all stages:

- `api/webui/routes/powergrader.py` should be under 500 lines.
- No new backend PowerGrader module should be over 500 lines.
- Existing focused tests must pass.
- Route contract must remain unchanged.
- PowerGrader setup and queue UI must behave the same.
