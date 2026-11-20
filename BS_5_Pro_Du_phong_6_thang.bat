@echo off
chcp 65001 >nul
title [BlueStacks] Pro 6 thang - offer ss-2026
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

if exist "C:\Program Files\BlueStacks_polar\HD-Adb.exe" (
    set "ADB_PATH=C:\Program Files\BlueStacks_polar\HD-Adb.exe"
) else if exist "C:\Program Files\BlueStacks_nxt\HD-Adb.exe" (
    set "ADB_PATH=C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
)

echo ========================================================
echo   [BlueStacks] Google AI Pro - offer 6months-eft-ss-2026
echo   Serial: 127.0.0.1:6610
echo ========================================================
python ultra0.py --serial "127.0.0.1:6610" --account "htisme223@gmail.com" --no-add --no-switch --stack --plan pro6c --mode 5 --token-product g1.play.2tb.ai
echo.
pause
