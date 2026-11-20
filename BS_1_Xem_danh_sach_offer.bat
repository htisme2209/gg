@echo off
chcp 65001 >nul
title [BlueStacks] Liet ke offer (khong mua)
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

if exist "C:\Program Files\BlueStacks_polar\HD-Adb.exe" (
    set "ADB_PATH=C:\Program Files\BlueStacks_polar\HD-Adb.exe"
) else if exist "C:\Program Files\BlueStacks_nxt\HD-Adb.exe" (
    set "ADB_PATH=C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
)

echo ========================================================
echo   [BlueStacks] Liet ke tat ca offer cua Pro 5TB (KHONG mua)
echo   Serial: 127.0.0.1:6610
echo ========================================================
python ultra0.py --serial "127.0.0.1:6610" --account "current@device" --no-add --force --list --plan pro12
echo.
pause
