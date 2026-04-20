@echo off
:: Fast Launcher for PDF Genius
SETLOCAL
cd /d "%~dp0"

echo Launching PDF Genius...

:: Start the dev server
start "PDF Genius Server" cmd /c "npm run dev"

:: Wait 1 second (Vite starts in ~0.2s)
timeout /t 1 /nobreak > nul

:: Open browser
start http://localhost:8080
exit
