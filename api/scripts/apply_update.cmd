@echo off
setlocal
REM Applies a staged Canvas Expert update. Copied to %TEMP% and launched by
REM "Open Canvas Expert.bat" when qf_ui.py exits with code 7, so the swap
REM happens at the one moment nothing in the app folder is running: a live
REM Python process can't reliably replace its own folder, and cmd.exe can't
REM overwrite a .bat file it is currently reading. Never edit this file in
REM place inside the app folder -- it must run from a copy in %TEMP%.
REM
REM Argument 1: the app root, with a trailing backslash (from %~dp0).

set "APP_ROOT=%~1"
if "%APP_ROOT%"=="" (
  echo Canvas Expert update: missing app root argument.
  exit /b 1
)

set "CE_DATA=%LOCALAPPDATA%\CanvasExpert"
set "UPDATE_DIR=%CE_DATA%\update"
set "STAGED_DIR=%UPDATE_DIR%\staged"
set "BACKUP_DIR=%CE_DATA%\backup\previous"

REM This list mirrors the repo's .gitignore "machine-local config" and
REM "Runtime / user data" sections -- every teacher state file that lives
REM inside the app folder despite being machine-local must survive an update
REM untouched. Keep the two in step; api/tests/test_self_update.py fails
REM loudly if they drift apart.
set "PRESERVE_XF=config.json config.json.lock profiles.json curve_events.json teks_outcomes.json .experiment_state.json .env .env.*"
set "PRESERVE_XD=temp out .git __pycache__"

REM Give the parent launcher, and cmd.exe (which had this very file open a
REM moment ago), time to fully release their handles before anything here
REM touches the app folder. timeout needs an interactive console; ping does not.
ping -n 3 127.0.0.1 >nul

REM The release zip wraps its payload in a single top-level folder (see
REM .github/workflows/release.yml), so the batch file at depth 0 (no wrapper)
REM or depth 1 (one wrapper folder) is fine either way -- resolve whichever
REM one actually holds the app.
set "PAYLOAD_ROOT=%STAGED_DIR%"
if not exist "%STAGED_DIR%\Open Canvas Expert.bat" (
  for /d %%D in ("%STAGED_DIR%\*") do (
    if exist "%%D\Open Canvas Expert.bat" set "PAYLOAD_ROOT=%%D"
  )
)

if not exist "%PAYLOAD_ROOT%\Open Canvas Expert.bat" (
  REM A missing or unrecognized payload is never a wipe -- just relaunch the
  REM app unchanged.
  start "" "%APP_ROOT%Open Canvas Expert.bat"
  exit /b 0
)

REM One-generation backup of the current app, overwritten every update.
robocopy "%APP_ROOT%." "%BACKUP_DIR%" /MIR /XF %PRESERVE_XF% /XD %PRESERVE_XD% >nul
set "BACKUP_RC=%ERRORLEVEL%"
if %BACKUP_RC% GEQ 8 (
  > "%UPDATE_DIR%\last_apply.json" echo {"ok": false, "error": "could not back up the current version before applying the update; nothing was changed", "robocopy_exit": %BACKUP_RC%}
  start "" "%APP_ROOT%Open Canvas Expert.bat"
  exit /b 0
)

REM Mirror the staged build over the app root. /MIR also removes files the
REM new build no longer ships, which is the point of a whole-folder update.
robocopy "%PAYLOAD_ROOT%" "%APP_ROOT%." /MIR /XF %PRESERVE_XF% /XD %PRESERVE_XD% >nul
set "APPLY_RC=%ERRORLEVEL%"
if %APPLY_RC% GEQ 8 (
  robocopy "%BACKUP_DIR%" "%APP_ROOT%." /MIR /XF %PRESERVE_XF% /XD %PRESERVE_XD% >nul
  > "%UPDATE_DIR%\last_apply.json" echo {"ok": false, "error": "applying the update failed; restored the previous version", "robocopy_exit": %APPLY_RC%}
  start "" "%APP_ROOT%Open Canvas Expert.bat"
  exit /b 0
)

rmdir /s /q "%STAGED_DIR%" 2>nul
if exist "%UPDATE_DIR%\pending.json" move /y "%UPDATE_DIR%\pending.json" "%UPDATE_DIR%\last_apply.json" >nul

start "" "%APP_ROOT%Open Canvas Expert.bat"
exit /b 0
