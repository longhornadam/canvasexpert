# Update Canvas Expert from inside the app

**Status:** CURRENT direct execution brief
**Executor:** one Claude Sonnet 5 implementation agent, running the whole slice in a new session
**Branch:** `dev`
**Base:** current `origin/dev` after the executor's preflight fetch
**Risk:** medium-high. This slice replaces program files on disk and adds the app's
first outbound call to a host other than Canvas or OpenRouter. Treat the download,
verification, and file-swap rules below as guardrails, not suggestions.

This brief is the only execution authority for this work, and the only brief in
`docs/handoffs/`.

## Teacher-visible objective

A teacher on version N sees, in Settings, that version N+1 exists. They click
**Download update**, then **Restart and update**. The console window closes and
reopens, and the app comes back on N+1 with every setting, course, and workspace
file intact. They never download a ZIP, never unzip anything, and never delete a
folder.

If GitHub is unreachable, blocked, or the download is corrupt, they see a plain
message and nothing on disk changes. The manual "download the ZIP and replace the
folder" path keeps working for those teachers.

## The one obstacle, and the shape it forces

A running Python process cannot reliably replace the folder it is running from, and
`cmd.exe` cannot overwrite a `.bat` file it is currently reading. So the swap happens
at the only moment when nothing in the app folder is running: between the app exiting
and the launcher restarting it, executed by a helper script copied to `%TEMP%`.

The sequence is fixed:

1. App downloads and verifies the new build, extracts it to `%LOCALAPPDATA%\CanvasExpert\update\staged`. The app folder is untouched.
2. App exits with code 7.
3. `Open Canvas Expert.bat` sees code 7, copies the applier to `%TEMP%`, starts it, and exits so it holds no file open.
4. The applier backs up the current folder, mirrors `staged` over it, clears staging, and relaunches the launcher.
5. The launcher's existing `requirements.txt` hash guard installs any new dependencies, then starts the app.

Do not invent a different sequence. In-process replacement, folder renames from
inside the folder, and self-overwriting batch files all fail on Windows in ways that
leave a teacher with a broken install and no rollback.

## Required context

Read only:

1. `AGENTS.md`.
2. This brief.
3. `docs/reference/settings-module-map.md`: the sections describing Settings page
   routes, card structure, and JS ownership.
4. `docs/reference/webui-presentation-system.md`: `Template API` and `Page conventions`.
5. The exact files named in "Allowed scope" below.

Do not read the CanvasMirror information spine, other module maps, or retired
handoffs. Do not run a repository-wide index to widen this list.

## Preflight, stop before writing if any assumption is false

1. Fetch `origin`, confirm the branch is `dev`, and preserve unrelated worktree changes.
2. Confirm these seams still exist:
   - [`api/qf_ui.py`](../../api/qf_ui.py) `main()` calls `uvicorn.run(app, ...)` directly and imports `api.__version__`.
   - [`api/__init__.py:3`](../../api/__init__.py) defines `__version__`.
   - [`Open Canvas Expert.bat`](../../Open Canvas Expert.bat) ends with `py qf_ui.py` followed by `pause`, after the `%LOCALAPPDATA%\CanvasExpert\reqs.hash` guard.
   - [`api/webui/config/_io.py:123`](../../api/webui/config/_io.py) defines `CONFIG_PATH` inside the app folder, and [`api/webui/workspace.py:27`](../../api/webui/workspace.py) defines a second `CONFIG_PATH` pointing at the same file.
   - `requests` is already in [`api/requirements.txt`](../../api/requirements.txt).
   - [`api/tests/test_route_contract.py`](../../api/tests/test_route_contract.py) holds an `EXPECTED` route snapshot.
3. Confirm `git remote get-url origin` is `https://github.com/longhornadam/canvasexpert.git`.
4. Add no new dependency. Everything here is `requests`, `zipfile`, `hashlib`, `shutil`, and stdlib.
5. The repository is public as of 2026-07-25, verified anonymously: an unauthenticated
   `GET https://api.github.com/repos/longhornadam/canvasexpert` returns 200 with
   `"private": false`. Release assets therefore download without a token, and the
   downloader must never send one.

## Locked decisions

### D1. Machine-local state leaves the app folder (prerequisite, same commit series)

The applier mirrors the new build over the app folder, so anything of the teacher's
living inside it is at risk. Move it out first, in this slice, before the applier exists.

- Add `runtime_paths.local_app_dir()` returning `%LOCALAPPDATA%\CanvasExpert`, falling
  back to `~/AppData/Local/CanvasExpert` when the variable is unset. Model it on
  [`api/operation_ledger/paths.py`](../../api/operation_ledger/paths.py) `private_root()`, which already does exactly this.
- `config/_io.py::CONFIG_PATH` and `workspace.py::CONFIG_PATH` both become
  `local_app_dir() / "config.json"`. They must resolve to the same file; the MCP
  server relies on `workspace.py` reading the pinned workspace root without the
  OneDrive environment present.
- `profiles.py::PROFILES_PATH` becomes `local_app_dir() / "profiles.json"`.
- One-time migration on first read: if the new path is missing and the legacy
  in-folder file exists, copy it across. **Leave the legacy file in place.** Deleting
  it breaks an older copy of the app on the same machine and gains nothing, and the
  preserve list in D4 keeps it alive across updates anyway.
- `gradebook_service.CURVE_EVENTS_PATH` is already only a migration source for
  `operation_ledger.paths.curve_events_file()`. Leave that code alone; just make sure
  the file name is in the preserve list.
- Ten test references to `CONFIG_PATH` exist across `api/tests/test_beta075_storage.py`
  and `api/tests/test_workspace.py`. Update them to point at the new location rather
  than weakening them.

### D2. Exit code 7 means "apply the staged update"

In `qf_ui.py`, build the server explicitly so a route can stop it:

```python
config = uvicorn.Config(app, host=HOST, port=port, log_level="info")
server = uvicorn.Server(config)

def request_restart(exit_code: int) -> None:
    app.state.restart_exit_code = exit_code
    server.should_exit = True

app.state.request_restart = request_restart
server.run()
raise SystemExit(getattr(app.state, "restart_exit_code", 0))
```

The app is also constructed without the launcher (tests, and the MCP server path). A
route that finds no `request_restart` on `app.state` returns HTTP 409 with a message
telling the teacher to close the app and reopen it with `Open Canvas Expert.bat`. It
must never raise.

Code 7 is the only non-zero code this slice introduces. In the batch file test with
`if errorlevel 7 if not errorlevel 8`, because `errorlevel` comparison is "greater than
or equal".

### D3. The launcher hands off to a helper in `%TEMP%`

`Open Canvas Expert.bat` gains, in place of the bare `py qf_ui.py`:

```bat
py qf_ui.py
if errorlevel 7 if not errorlevel 8 (
  copy /y "%~dp0api\scripts\apply_update.cmd" "%TEMP%\ce_apply_update.cmd" >nul
  start "" "%TEMP%\ce_apply_update.cmd" "%~dp0"
  exit /b
)
pause
```

The applier lives at `api/scripts/apply_update.cmd`, not in `tools/`. `tools/` is
dropped when `main` is rebuilt as the public snapshot, and an applier missing from the
release is an update that bricks the folder.

The parent launcher must `exit /b` immediately, without `pause` and without `/wait`, so
it releases its own file handle. The applier opens with a short `ping -n 3 127.0.0.1 >nul`
delay for the same reason. Do not use `timeout`, which needs an interactive console.

### D4. What the applier does, in order

Argument 1 is the app root, passed with a trailing backslash from `%~dp0`.

1. Verify `%LOCALAPPDATA%\CanvasExpert\update\staged\Open Canvas Expert.bat` exists.
   If not, relaunch the app unchanged and exit. A missing payload is never a wipe.
2. Mirror the current app root to `%LOCALAPPDATA%\CanvasExpert\backup\previous` (one
   generation, overwritten each time).
3. Mirror `staged` over the app root with `robocopy /MIR`, excluding the preserve list.
4. Treat `robocopy` exit codes below 8 as success and 8 or above as failure. On
   failure, restore from the backup, write the reason to
   `%LOCALAPPDATA%\CanvasExpert\update\last_apply.json`, and relaunch.
5. Delete `staged`, move `pending.json` to `last_apply.json`.
6. `start "" "<app root>\Open Canvas Expert.bat"` and exit.

The preserve list, excluded from both the backup and the mirror, is exactly:

```
/XF config.json config.json.lock profiles.json curve_events.json teks_outcomes.json .env
/XD temp out .git __pycache__
```

Define that list once as a variable in the applier with a comment saying it mirrors
`.gitignore`'s runtime section, and add a test asserting the two stay in step
(read `.gitignore`, assert every runtime path it names appears in the applier text).
That test is the only thing standing between a future gitignored state file and a
teacher losing it during an update.

### D5. Download and verification rules

New module `api/webui/self_update.py`. These are non-negotiable:

- **Pinned source.** Only `https://api.github.com/repos/longhornadam/canvasexpert/releases/latest`.
  The repository slug is a module constant, not configuration, and not derived from
  anything a teacher can edit.
- **HTTPS only.** Reject any URL whose scheme is not `https`.
- **Host allowlist, checked every hop.** Follow redirects manually with
  `allow_redirects=False`, validating each `Location` host against
  `{"api.github.com", "github.com", "objects.githubusercontent.com"}`. Cap at 5 hops.
  Checking only the final URL is not sufficient.
- **Size cap.** Stream in 64 KB chunks, abort past 200 MB. Connect and read timeouts
  of 30 seconds.
- **Hash check.** The release must carry a `SHA256SUMS.txt` asset. The ZIP's SHA256
  must appear in it against the exact asset filename. A missing sums file, a missing
  filename, or a mismatch aborts and stages nothing. State honestly in the code
  comment what this does and does not buy: it catches corruption and a swapped asset,
  not a compromised release. Signing is a possible follow-up, not part of this slice.
- **Extraction safety.** Walk entries by hand. Reject any entry with an absolute path,
  a drive letter, a `..` component after normalization, or a symlink bit in
  `external_attr`. Reject the whole archive on the first bad entry.
- **Atomic staging.** Extract to a sibling temp directory, then rename to `staged`. A
  partial extract must never be visible as `staged`.
- **Teacher-initiated only.** No check on launch, no background polling, no automatic
  download, no automatic apply. Every step is a click.
- **No telemetry.** The version check is a bare GET with no query parameters and no
  identifying headers beyond a plain user agent. Say so in the module docstring.

For local testing, honor `CANVAS_EXPERT_UPDATE_FEED` **only when it points at a
loopback host** (`127.0.0.1` or `localhost`). Every other rule still applies to it,
including the hash check. Any non-loopback value is ignored, not honored with a
warning.

### D6. Routes and payloads

New router `api/webui/routes/updates.py`, registered like its siblings.

| Route | Method | Returns |
|---|---|---|
| `/api/update/status` | GET | `{ok, current, latest, available, published_at, notes_url, staged, error}` |
| `/api/update/download` | POST | `{ok, version, bytes}` or `{ok: false, error}` |
| `/api/update/apply` | POST | `{ok: true, restarting: true}`, then shuts down |
| `/api/update/cancel` | POST | `{ok: true}`, clears staging |

`status` never raises: unreachable host, timeout, rate limit, and malformed JSON all
come back as `{ok: false, error: "<plain sentence>"}`. `staged` is `null` or
`{version, bytes}`.

`apply` must return its response before the server stops. Send it, then trigger the
shutdown from a `threading.Timer(0.5, ...)`. Refuse with 409 when nothing is staged, or
when `app.state.request_restart` is absent.

Add all four routes to `EXPECTED` in `api/tests/test_route_contract.py` in the same
commit.

### D7. Version comparison

Parse `MAJOR.MINOR.PATCH` with an optional `-beta.N` or `-rc.N`, tolerating a leading
`v` on the tag. Rank a final release above any prerelease of the same number:
`(major, minor, patch, 1, 0)` for final, `(major, minor, patch, 0, n)` for prerelease.
An unparseable version on either side yields `available: false` and an error string.
Never offer a downgrade. Current is `api.__version__`, today `0.75.0-beta.0`.

### D8. What the teacher sees

- A Settings card `id="update-card"`, placed last in the "About this app" group, with a
  rail link labeled **Updates**. Follow the existing `.ce-panel.ce-settings-panel`
  pattern in [`api/webui/templates/settings.html`](../../api/webui/templates/settings.html) and the JS-per-card convention in
  `api/webui/static/settings/`. New file: `static/settings/updates.js`.
- Resting state: "You are on 0.75.0-beta.0." plus a **Check for updates** button.
- Update found: the new version, its date, a link to the release notes, and
  **Download update**.
- Downloaded: "Version 1.0 is ready to install." plus **Restart and update** and a
  quieter **Cancel**. Say plainly that the app will close and reopen by itself.
- Errors are one calm sentence and a retry. No stack traces, no error codes, no
  security theater about hashes or hosts. The verification is quiet by design.
- The About page gains the version number in its footer area, since a teacher asked
  for help needs to be able to read it out.

Copy stays relaxed and teacher-facing: no capitals for emphasis, no compliance banner,
no em-dashes anywhere in code, comments, or copy.

### D9. Release build

New `.github/workflows/release.yml`, triggered on tags matching `v*`:

1. Check out the tagged commit.
2. Produce `CanvasExpert.zip` containing a single top-level `CanvasExpert/` directory,
   excluding `.git`, `.github`, and `__pycache__`.
3. Produce `SHA256SUMS.txt` covering that asset.
4. Attach both to a GitHub release for the tag.

The applier resolves the payload root by locating `Open Canvas Expert.bat` at depth 0
or 1 inside the extracted tree, so a wrapper folder is fine either way.

Because `main` is rebuilt as a clean orphan snapshot for releases, `.github/` must
survive into it. Note that in the execution result so the next person rebuilding `main`
keeps it.

## Allowed scope

Create:

- `api/webui/self_update.py`
- `api/webui/routes/updates.py`
- `api/webui/static/settings/updates.js`
- `api/scripts/apply_update.cmd`
- `api/tests/test_self_update.py`
- `.github/workflows/release.yml`

Modify:

- `api/qf_ui.py`, `Open Canvas Expert.bat`, `Repair.bat` (add restore-from-backup)
- `api/runtime_paths.py`, `api/webui/config/_io.py`, `api/webui/config/__init__.py`,
  `api/webui/workspace.py`, `api/webui/profiles.py`
- `api/webui/templates/settings.html`, `api/webui/templates/about.html`,
  `api/webui/static/pages/settings.css`, `api/webui/routes/pages.py` (settings context),
  `api/webui/server.py` (router registration)
- `api/tests/test_route_contract.py`, `api/tests/test_beta075_storage.py`,
  `api/tests/test_workspace.py`
- `docs/reference/settings-module-map.md` if it enumerates cards or routes
- This brief's `Execution result`

Nothing else. In particular, do not touch the seeded-document machinery in
`api/webui/ai_ta.py`, the mirror, PowerGrader, or any Canvas write path.

## Acceptance criteria

1. With a loopback feed serving a build whose version is higher, Settings shows the
   update, downloads it, and reports it ready. `%LOCALAPPDATA%\CanvasExpert\update\staged`
   contains the payload; the app folder is byte-identical to before.
2. Clicking **Restart and update** closes the app and reopens it on the new version,
   with the Canvas base URL, saved courses, download root, and workspace pin unchanged.
3. A ZIP whose hash does not match `SHA256SUMS.txt` stages nothing and shows one plain
   error. Same for a ZIP containing a `..` entry, an absolute path, or a symlink.
4. A feed URL on a non-loopback, non-GitHub host is ignored. A redirect to a
   non-allowlisted host aborts the download.
5. With no network, **Check for updates** shows one plain sentence and the app keeps
   working normally.
6. `POST /api/update/apply` against an app constructed without the launcher returns
   409 and does not exit the process.
7. A robocopy failure mid-apply restores the previous version and relaunches it.
8. After the D1 move, a fresh profile with no `%LOCALAPPDATA%\CanvasExpert\config.json`
   but a legacy in-folder `config.json` reads the legacy values once, writes the new
   location, and leaves the legacy file in place.
9. The preserve list in the applier still covers every runtime path named in
   `.gitignore`, asserted by test.
10. `/settings` and `/about` render in light and dark at 1440x900 and 760x900 with zero
    new console errors and no horizontal overflow.

## Named verification gate

```powershell
py -m pytest api/tests/test_self_update.py api/tests/test_route_contract.py api/tests/test_beta075_storage.py api/tests/test_workspace.py api/tests/test_presentation_contracts.py -q
```

Plus the real end-to-end run, which is the proof that matters and does not require
cutting a real release:

1. Build a ZIP of the current tree with a bumped `__version__` and its `SHA256SUMS.txt`.
2. Serve the folder with `py -m http.server` bound to `127.0.0.1`.
3. Set `CANVAS_EXPERT_UPDATE_FEED` to that loopback URL and launch through
   `Open Canvas Expert.bat`, not `py qf_ui.py`.
4. Walk the whole flow in the browser and confirm the app comes back on the bumped
   version with settings intact.

Then one live read against the public repository, with no staging and no apply:
`GET /api/update/status` must return the real latest tag, or a clean
`{ok: false, error}` if no release exists yet. This confirms the pinned URL, the
redirect handling, and the unauthenticated request in one call.

Record all three in the execution result, with counts and observed behavior.

## Explicit non-goals

- Checking for updates automatically, on a timer, or at launch.
- Silent or background installation.
- Delta or partial updates. The mirror is whole-folder and that is fine.
- Code signing or an embedded public key. Worth doing later; not here.
- Updating seeded workspace documents. That is the separate seed-manifest work and
  must not be started in this slice.
- Any migration of teacher content, workspace layout, or Canvas data.
- Changing how dependencies install. The existing `reqs.hash` guard already handles a
  changed `requirements.txt` on the relaunch.

## Stop conditions

Return RED and stop rather than guessing when:

- `%LOCALAPPDATA%` is unset and the fallback would place teacher state somewhere
  surprising.
- The two `CONFIG_PATH` definitions cannot be made to resolve to the same file without
  changing the MCP server's startup path.
- Presentation contracts require a card structure incompatible with D8.
- Any part of this brief would require touching a Canvas write path, the credential
  store, or student data.

Return YELLOW, with the rest complete, when the browser matrix in criterion 10 cannot
be exercised.

## Execution result

_Not started._
