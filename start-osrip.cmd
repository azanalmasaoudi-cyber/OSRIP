@echo off
rem Starts OSRIP locally (PostgreSQL, API, frontend) and opens the website.
rem Close this window or press Ctrl+C to stop what it started. Options: --setup --no-browser --keep-db --check
setlocal
set "LAUNCHER=%~dp0tools\start_osrip.py"
if exist "%~dp0backend\.venv\Scripts\python.exe" (
  "%~dp0backend\.venv\Scripts\python.exe" "%LAUNCHER%" %*
) else (
  py -3 "%LAUNCHER%" %*
)
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" pause
exit /b %CODE%
