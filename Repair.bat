@echo off
setlocal
REM Force a clean reinstall of dependencies on the next launch. Use this if the app
REM stops starting or a dependency looks broken. Removes only the per-user setup
REM marker (no admin, touches nothing in the app folder); "Open Canvas Expert.bat"
REM will then reinstall everything automatically.
set "MARKER=%LOCALAPPDATA%\CanvasExpert\reqs.hash"
if exist "%MARKER%" (
  del "%MARKER%"
  echo Setup marker cleared. Double-click "Open Canvas Expert.bat" to reinstall and run.
) else (
  echo Nothing to repair - no setup marker found. Just run "Open Canvas Expert.bat".
)

REM --- Restore from the last self-update backup, if one exists ------------------
REM Every in-app update keeps one generation of the previous version here before
REM it changes anything. If an update left the app in a bad state, this rolls
REM that folder back without touching your settings, courses, or workspace pin
REM (those all live outside the app folder already).
set "BACKUP_DIR=%LOCALAPPDATA%\CanvasExpert\backup\previous"
if exist "%BACKUP_DIR%\Open Canvas Expert.bat" (
  echo.
  choice /c YN /n /m "A backup from the last update is available. Restore the previous version? [Y/N] "
  if errorlevel 2 goto :done
  if errorlevel 1 (
    set "PRESERVE_XF=config.json config.json.lock profiles.json curve_events.json teks_outcomes.json .experiment_state.json .env .env.*"
    set "PRESERVE_XD=temp out .git __pycache__"
    robocopy "%BACKUP_DIR%" "%~dp0." /MIR /XF %PRESERVE_XF% /XD %PRESERVE_XD% >nul
    if errorlevel 8 (
      echo Restore failed - nothing was changed further. Try again, or reinstall from a fresh download.
    ) else (
      echo Restored the previous version.
    )
  )
) else (
  echo.
  echo No update backup found to restore from.
)

:done
pause
