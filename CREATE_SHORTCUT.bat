@echo off
:: ════════════════════════════════════════════════════════════════
::  ClimateIQ v5  —  CREATE DESKTOP SHORTCUT ONLY
::  Run this AFTER BUILD.bat has already created dist\ClimateIQ\
:: ════════════════════════════════════════════════════════════════
title ClimateIQ — Shortcut Creator

set EXE_PATH=%CD%\dist\ClimateIQ\ClimateIQ.exe
set ICO_PATH=%CD%\climateiq.ico

if not exist "%EXE_PATH%" (
    echo [ERROR] EXE not found at: %EXE_PATH%
    echo         Run BUILD.bat first.
    pause & exit /b 1
)

:: Desktop shortcut
set SHORTCUT_D=%USERPROFILE%\Desktop\ClimateIQ.lnk
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; ^
   $sc = $ws.CreateShortcut('%SHORTCUT_D%'); ^
   $sc.TargetPath = '%EXE_PATH%'; ^
   $sc.WorkingDirectory = '%CD%\dist\ClimateIQ'; ^
   $sc.IconLocation = '%ICO_PATH%'; ^
   $sc.Description = 'ClimateIQ - Climate Sentiment Dashboard'; ^
   $sc.WindowStyle = 1; ^
   $sc.Save()"
echo Desktop shortcut: %SHORTCUT_D%

:: Start Menu shortcut
set STARTMENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs
set SHORTCUT_S=%STARTMENU%\ClimateIQ.lnk
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; ^
   $sc = $ws.CreateShortcut('%SHORTCUT_S%'); ^
   $sc.TargetPath = '%EXE_PATH%'; ^
   $sc.WorkingDirectory = '%CD%\dist\ClimateIQ'; ^
   $sc.IconLocation = '%ICO_PATH%'; ^
   $sc.Description = 'ClimateIQ - Climate Sentiment Dashboard'; ^
   $sc.WindowStyle = 1; ^
   $sc.Save()"
echo Start Menu shortcut: %SHORTCUT_S%

echo.
echo Done! ClimateIQ icon added to Desktop and Start Menu.
pause
