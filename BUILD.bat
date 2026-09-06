@echo off
:: ════════════════════════════════════════════════════════════════
::  ClimateIQ v5  —  BUILD + DESKTOP SHORTCUT INSTALLER
::  Double-click this file from inside the ClimateIQ_v5 folder
:: ════════════════════════════════════════════════════════════════
title ClimateIQ v5 — Build Tool
cd /d "%~dp0"

echo.
echo  =============================================
echo     ClimateIQ v5  --  Desktop App Builder
echo  =============================================
echo.

:: ── Check Python ────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Install from https://python.org
    pause & exit /b 1
)

:: ── Install dependencies ────────────────────────────────────────
echo  [1/4] Installing dependencies...
python -m pip install pyinstaller PyQt6 pandas numpy matplotlib vaderSentiment reportlab anthropic pillow pyparsing -q
echo        Done.

:: ── Check database ──────────────────────────────────────────────
echo  [2/4] Checking database...
if not exist "database\climate_data.db" (
    echo.
    echo  [ERROR] Database not found!
    echo.
    echo  Please run this command first:
    echo     python scripts\csv_to_sqlite.py "path\to\your_file.csv"
    echo.
    echo  Then run BUILD.bat again.
    pause & exit /b 1
)
echo        Database found OK.

:: ── Build EXE ───────────────────────────────────────────────────
echo  [3/4] Building ClimateIQ.exe  (1-3 minutes, please wait)...
if exist "dist\ClimateIQ" rmdir /s /q "dist\ClimateIQ"
if exist "build"          rmdir /s /q "build"

python -m PyInstaller ClimateIQ.spec --noconfirm
if errorlevel 1 (
    echo.
    echo  [ERROR] Build failed. Read the errors above.
    pause & exit /b 1
)
echo        Build complete!

:: ── Desktop Shortcut ────────────────────────────────────────────
echo  [4/4] Creating Desktop shortcut...

set EXE_PATH=%CD%\dist\ClimateIQ\ClimateIQ.exe
set ICO_PATH=%CD%\climateiq.ico
set SHORTCUT=%USERPROFILE%\Desktop\ClimateIQ.lnk

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%SHORTCUT%'); $sc.TargetPath = '%EXE_PATH%'; $sc.WorkingDirectory = '%CD%\dist\ClimateIQ'; $sc.IconLocation = '%ICO_PATH%'; $sc.Description = 'ClimateIQ - Climate Sentiment Dashboard'; $sc.WindowStyle = 1; $sc.Save()"

if exist "%SHORTCUT%" (
    echo        Desktop shortcut created successfully!
) else (
    echo  [WARN] Shortcut not created. Make it manually from:
    echo         %EXE_PATH%
)

echo.
echo  =====================================================
echo   DONE!  EXE is at:  dist\ClimateIQ\ClimateIQ.exe
echo   Icon added to your Desktop.
echo  =====================================================
echo.
set /p LAUNCH= Launch ClimateIQ now? (y/n): 
if /i "%LAUNCH%"=="y" start "" "%EXE_PATH%"

pause
