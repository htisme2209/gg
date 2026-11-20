@echo off
chcp 65001 >nul
title [BlueStacks] Kiem tra moi truong
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

if exist "C:\Program Files\BlueStacks_polar\HD-Adb.exe" (
    set "ADB_PATH=C:\Program Files\BlueStacks_polar\HD-Adb.exe"
) else if exist "C:\Program Files\BlueStacks_nxt\HD-Adb.exe" (
    set "ADB_PATH=C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
)

echo ========================================================
echo   [BlueStacks] Kiem tra gia lap / root / frida
echo   Cong ADB: 127.0.0.1:6610
echo ========================================================
echo.

if defined ADB_PATH (
    echo [1] Dang ket noi ADB toi BlueStacks 127.0.0.1:6610...
    "%ADB_PATH%" connect 127.0.0.1:6610
    echo.
)

echo [2] Chay kiem tra he thong qua ultra0.py:
python ultra0.py --serial "127.0.0.1:6610" --check
echo.
pause
