@echo off
cd /d "%~dp0"
if not exist "dist\index.html" (
  node audit.mjs
  if errorlevel 1 exit /b 1
  node build.mjs
  if errorlevel 1 exit /b 1
)
node server.mjs
pause
