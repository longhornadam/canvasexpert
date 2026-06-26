@echo off
setlocal
cd /d "%~dp0api"

REM --- Python present? (the only prerequisite a bat can't install without admin) ---
where py >nul 2>&1
if errorlevel 1 (
  echo Python is not installed.
  echo Install the per-user Python 3.13 from https://www.python.org/downloads/
  echo  ^(tick "Install for me only" - no admin needed^), then run this again.
  pause & exit /b 1
)

REM --- First-run / dependency-change guard --------------------------------------
REM Provision only when requirements.txt differs from what we last installed, so
REM normal launches go straight to the app (pip + the ~150MB Chromium download are
REM slow). The marker lives in %LOCALAPPDATA% (per-user, no admin, off the repo).
set "MARKER=%LOCALAPPDATA%\CanvasExpert\reqs.hash"
set "CUR="
for /f "skip=1 delims=" %%H in ('certutil -hashfile requirements.txt SHA256 2^>nul') do (
  if not defined CUR set "CUR=%%H"
)
set "OLD="
if exist "%MARKER%" set /p OLD=<"%MARKER%"

if not "%CUR%"=="%OLD%" (
  echo.
  echo First-time setup ^(or dependencies changed^) - installing into your user account...
  echo This runs once and needs no admin rights. Please wait.
  echo.
  py -m pip install --user -r requirements.txt || (echo. & echo Setup failed - check your internet connection and try again. & pause & exit /b 1)
  py -m playwright install chromium || (echo. & echo Browser download failed - check your internet connection and try again. & pause & exit /b 1)
  if not exist "%LOCALAPPDATA%\CanvasExpert" mkdir "%LOCALAPPDATA%\CanvasExpert"
  if defined CUR ( >"%MARKER%" echo %CUR% )
  echo.
  echo Setup complete.
  echo.
)

py qf_ui.py
pause
