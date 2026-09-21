@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_release.ps1"
if errorlevel 1 (
  echo.
  echo BUILD FAILED - see the error above.
  pause
  exit /b 1
)
echo.
echo Build complete. Open the releases folder for the installer, update file, and latest.json feed.
explorer.exe "%~dp0releases"
pause
