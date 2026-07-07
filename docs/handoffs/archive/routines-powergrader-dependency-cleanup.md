# Handoff: Routines PowerGrader Dependency Cleanup

## Goal

Remove the duplicate-module risk introduced by the `routines.py` split while
preserving the existing PowerGrader scheduled autoscore and late catch-up behavior.

This is a cleanup/refactor task, not a feature task.

## Why This Matters

The app launcher imports the server as `webui.server` from inside `api/`, but
`api/webui/routes/routines_powergrader.py` currently reaches back to:

```python
from api.webui.routes import routines as _r
```

That can load a second copy of the routines module (`api.webui.routes.routines`)
beside the live app copy (`webui.routes.routines`). A probe confirmed the duplicate
module appears after calling a helper such as `_autoscore_receipt_dir`.

The split passes tests today, but duplicate route modules are a fragile dependency
surface for monkeypatches, runtime state, and future scheduler work.

## Guardrails

- Read `AGENTS.md` first.
- Work on `dev`.
- Do not make live Canvas calls.
- Do not commit secrets, tokens, student data, grades, submissions, or private notes.
- Do not broaden scheduled auto-push behavior. It remains teacher-controlled,
  per-job/per-assignment opt-in only.
- Preserve all route paths, routine ids, storage shapes, queue shapes, receipt shapes,
  and status strings.
- Do not touch `LLM_Modules/*_Base.md`.
- Do not revert unrelated dirty worktree changes.

## Files To Change

- `api/webui/routes/routines.py`
- `api/webui/routes/routines_powergrader.py`
- `api/tests/test_powergrader_scheduled_autoscore.py`
- `api/tests/test_powergrader_late_catchup.py`

## Current Shape

`routines.py` imports the dependency objects used by scheduled PowerGrader routines:

- `config`
- `html_to_text`
- `_canvas_send`
- `pg_routes`
- `ai_workflow`
- `autopush_executor`
- `autoscore_queue`
- `canvas_fetch`
- `late_catchup`
- `privacy`
- `session_builder`
- `session_store`

`routines_powergrader.py` accesses those by importing the caller module from
`api.webui.routes`, which is unsafe when the runtime package root is `webui`.

## Preferred Fix

Introduce an explicit dependency bundle in `routines_powergrader.py` and pass it from
`routines.py`.

Suggested shape:

```python
from dataclasses import dataclass
from typing import Any, Callable

@dataclass
class PowerGraderRoutineDeps:
    config: Any
    html_to_text: Callable[[str], str]
    canvas_send: Callable
    pg_routes: Any
    ai_workflow: Any
    autopush_executor: Any
    autoscore_queue: Any
    canvas_fetch: Any
    late_catchup: Any
    privacy: Any
    session_builder: Any
    session_store: Any
```

Then change:

```python
_run_routine_powergrader_scheduled_autoscore(params)
_run_routine_powergrader_late_catchup(params)
```

to internal implementations that accept `deps`, and expose thin factory/wrapper
functions from `routines.py` so `_ROUTINE_RUNNERS` still has callables that accept only
`params`.

Example:

```python
_PG_DEPS = PowerGraderRoutineDeps(...)

def _run_routine_powergrader_scheduled_autoscore(params):
    return routines_powergrader.run_scheduled_autoscore(params, _PG_DEPS)
```

Keep helper functions such as `_autoscore_status_from_summary` importable for tests if
tests already import them.

## Tests To Update

Existing tests monkeypatch `api.webui.routes.routines` attributes. Prefer preserving
that public seam:

- Keep the dependency objects as attributes on `routines.py`.
- Build `_PG_DEPS` at call time or through a tiny helper so monkeypatches are visible.
- Avoid requiring every test to patch `routines_powergrader.py` directly.

Add one regression test that proves no duplicate module is loaded:

```python
def test_powergrader_routines_do_not_import_duplicate_routines_module():
    import sys
    from api.webui.routes import routines_powergrader
    sys.modules.pop("webui.routes.routines", None)  # only if safe in test isolation
    # Better: test through the package style already used by api tests and assert
    # routines_powergrader source no longer imports "api.webui.routes".
```

If direct module-state assertions are too brittle, add a simpler source-level test:

```python
assert "from api.webui.routes import routines" not in Path(...).read_text()
```

## Required Verification

```powershell
py -m py_compile api/webui/routes/routines.py api/webui/routes/routines_powergrader.py
py -m pytest api/tests/test_powergrader_scheduled_autoscore.py api/tests/test_powergrader_late_catchup.py
py -m pytest api/tests/test_route_contract.py
py -m pytest api/tests
```

Also run this probe from repo root and confirm the final line is `False`:

```powershell
@'
import sys
sys.path.insert(0, "api")
import webui.server
from webui.routes import routines_powergrader as pg
pg._autoscore_receipt_dir({"job_id": "probe"})
print("api.webui.routes.routines" in sys.modules)
'@ | py -
```

## Acceptance

- `routines_powergrader.py` has no `from api.webui.routes import routines` import.
- Scheduled autoscore and late catch-up tests still pass.
- Full API tests still pass.
- No route contract changes.
- No Canvas write behavior changes.
