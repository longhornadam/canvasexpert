# PowerGrader Refactor Stage 2: Extract Pure Backend Helpers

## Goal

Extract storage, privacy, and Safe AI Packet helpers from `api/webui/routes/powergrader.py` into a dedicated `api/powergrader/` package.

This stage should not change behavior. It should keep compatibility wrappers in the route module so existing tests continue to pass.

## Files To Change

- `api/webui/routes/powergrader.py`
- `api/tests/test_powergrader_packet.py` only if absolutely necessary, but prefer not to touch it.

## Files To Create

- `api/powergrader/__init__.py`
- `api/powergrader/session_store.py`
- `api/powergrader/privacy.py`
- `api/powergrader/packet.py`

## Move To `session_store.py`

Move these functions from `api/webui/routes/powergrader.py`:

- `_pg_dir`
- `_session_path`
- `_safe_session_id`
- `_mode_label`
- `_load_session`
- `_save_session`

Also create a new function:

```python
def list_session_summaries() -> list[dict]:
    ...
```

`list_session_summaries()` must contain the session-listing logic currently inside the `list_sessions()` route.

Important dependencies:

```python
import json
import os
from webui import workspace
```

Keep the same path behavior:

- Use `workspace.workspace_root()`.
- Store sessions under `<workspace>/PowerGrader/`.
- Sanitize session IDs the same way as before.

## Move To `privacy.py`

Move these functions:

- `_privacy_step`
- `_feedback_artifact_dirs`
- `_write_privacy_audit_file`
- `_write_openrouter_debug_file`

Important dependencies:

```python
import json
import os
import traceback
from datetime import datetime

import feedback_pipeline as fp
import openrouter_client as orc
from webui import workspace
```

Do not change JSON fields written by `_write_privacy_audit_file()` or `_write_openrouter_debug_file()`.

## Move To `packet.py`

Move these functions:

- `_safe_ai_packet_name`
- `_packet_paths`
- `_shared_context_text`
- `_readable_responses_text`
- `_paste_format_text`
- `_build_safe_ai_packet`

Important dependencies:

```python
import json
import os
import zipfile

import feedback_pipeline as fp
```

Do not change packet filenames:

- `START HERE - Instructions for your AI.txt`
- `Student Responses.json`
- `Student Responses - readable.txt`
- `Source Materials.txt`
- `Paste Results Back Here - Format.txt`

Do not change ZIP contents.

## Update `routes/powergrader.py`

1. Import the new modules:

   ```python
   from powergrader import packet, privacy, session_store
   ```

2. Add compatibility aliases near the imports or helper section:

   ```python
   _pg_dir = session_store.pg_dir
   _session_path = session_store.session_path
   _safe_session_id = session_store.safe_session_id
   _mode_label = session_store.mode_label
   _load_session = session_store.load_session
   _save_session = session_store.save_session

   _privacy_step = privacy.privacy_step
   _feedback_artifact_dirs = privacy.feedback_artifact_dirs
   _write_privacy_audit_file = privacy.write_privacy_audit_file
   _write_openrouter_debug_file = privacy.write_openrouter_debug_file

   _build_safe_ai_packet = packet.build_safe_ai_packet
   ```

3. Prefer public names in the new modules without leading underscores, for example `packet.build_safe_ai_packet`.
4. Keep the aliases above so existing tests that import `api.webui.routes.powergrader._build_safe_ai_packet` continue to pass.
5. Replace the body of the `list_sessions()` route with:

   ```python
   return JSONResponse({"sessions": session_store.list_session_summaries()})
   ```

6. Remove the moved function definitions from the route file.
7. Remove imports from `routes/powergrader.py` that are no longer used after the move.

## Do Not Do

- Do not change endpoint paths.
- Do not change route function names.
- Do not change session JSON.
- Do not change Safe AI Packet file names or contents.
- Do not change tests unless imports become impossible. Compatibility aliases should avoid test changes.

## Verification

Run:

```powershell
py -m pytest api/tests/test_powergrader_packet.py api/tests/test_route_contract.py
```

Both tests must pass.

## Acceptance Criteria

- New `api/powergrader/` package exists.
- Storage, privacy, and packet helper code no longer lives directly in `routes/powergrader.py`.
- Existing tests pass without route contract changes.
- Existing tests can still access `powergrader._build_safe_ai_packet`, `powergrader._write_openrouter_debug_file`, `_load_session`, `_save_session`, and `_vault` as needed.
