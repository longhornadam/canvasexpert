# PowerGrader Refactor Stage 3: Extract Context, Estimates, And Canvas Fetch

## Goal

Extract Canvas submission fetching, source/rubric context, and token/cost estimate helpers from `api/webui/routes/powergrader.py`.

This stage should preserve current behavior exactly.

## Files To Change

- `api/webui/routes/powergrader.py`

## Files To Create

- `api/powergrader/canvas_fetch.py`
- `api/powergrader/context.py`
- `api/powergrader/estimates.py`

## Move To `canvas_fetch.py`

Move:

- `_CODE_EXTS`
- `_MAX_CODE_BYTES`
- `_fetch_submissions`
- `_enrich_with_code_files`

Use public names in the new module:

- `fetch_submissions`
- `enrich_with_code_files`

Important dependencies:

```python
import os

import requests
from webui.canvas_client import _canvas_get, _canvas_get_all, _canvas_headers
```

Do not change:

- Canvas endpoint paths.
- Included Canvas fields.
- File extension list.
- Max file byte limit.
- Timeout.
- Error swallowing behavior for failed attachment downloads.

## Move To `context.py`

Move:

- `_vault`
- `_load_rubric_text`
- `_folder_file_names`
- `_uploads_list`
- `_build_source_context`
- `_apply_shared_context`

Use public names:

- `vault`
- `load_rubric_text`
- `folder_file_names`
- `uploads_list`
- `build_source_context`
- `apply_shared_context`

Important dependencies:

```python
import os

import feedback_vault
from webui import source_materials, workspace
from webui.deps import list_rubric_files
```

Do not change:

- Rubric matching behavior.
- Source material parsing behavior.
- Shared context JSON shape.
- Prompt-clearing behavior when prompt equals assignment description.
- Vault path behavior.

## Move To `estimates.py`

Move:

- `_assignment_student_count`
- `_estimate_bundle`
- `_cost_label`

Use public names:

- `assignment_student_count`
- `estimate_bundle`
- `cost_label`

Important dependencies:

```python
import feedback_pipeline as fp
from webui import source_materials
from powergrader.context import apply_shared_context
```

Do not change:

- Default estimate count of `30`.
- Count basis labels.
- Synthetic student response behavior.
- Cost label formatting.

## Update `routes/powergrader.py`

1. Import:

   ```python
   from powergrader import canvas_fetch, context, estimates
   ```

2. Replace helper calls:

   - `_fetch_submissions(...)` -> `canvas_fetch.fetch_submissions(...)`
   - `_enrich_with_code_files(...)` -> `canvas_fetch.enrich_with_code_files(...)`
   - `_vault()` -> `context.vault()`
   - `_load_rubric_text(...)` -> `context.load_rubric_text(...)`
   - `_build_source_context(...)` -> `context.build_source_context(...)`
   - `_apply_shared_context(...)` -> `context.apply_shared_context(...)`
   - `_assignment_student_count(...)` -> `estimates.assignment_student_count(...)`
   - `_estimate_bundle(...)` -> `estimates.estimate_bundle(...)`
   - `_cost_label(...)` -> `estimates.cost_label(...)`

3. Keep this compatibility alias in `routes/powergrader.py` because an existing test monkeypatches `_vault`:

   ```python
   _vault = context.vault
   ```

4. If any other existing test imports a moved underscore helper from `routes/powergrader.py`, add a compatibility alias rather than changing the test.
5. Remove moved function definitions from the route file.
6. Remove imports that become unused.

## Do Not Do

- Do not change `pg_estimate()` response JSON.
- Do not change `pg_start()` response JSON.
- Do not change Canvas fetch behavior.
- Do not change source material warnings.
- Do not change token estimate math or labels.

## Verification

Run:

```powershell
py -m pytest api/tests/test_powergrader_packet.py api/tests/test_route_contract.py
```

Both tests must pass.

## Acceptance Criteria

- Canvas fetch logic lives in `api/powergrader/canvas_fetch.py`.
- Source/rubric/vault context logic lives in `api/powergrader/context.py`.
- Estimate helpers live in `api/powergrader/estimates.py`.
- Route contract unchanged.
- Focused tests pass.
