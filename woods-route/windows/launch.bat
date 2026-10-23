@echo off
setlocal
cd /d "%~dp0"
if not exist "WoodsRoutePlanner.exe" (
  echo Woods Route Planner executable not found.
  echo Download the Windows installer or portable package from GitHub Actions.
  pause
  exit /b 1
)
start "" "WoodsRoutePlanner.exe"
endlocal
