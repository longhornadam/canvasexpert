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
pause
