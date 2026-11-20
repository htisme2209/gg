@echo off
chcp 65001 >nul
title [BlueStacks] Bat Root va ADB

:: Kiem tra va tu dong xin quyen Administrator neu can
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ========================================================
    echo   YEU CAU QUYEN ADMINISTRATOR
    echo   File cau hinh BlueStacks can quyen Admin de chinh sua.
    echo ========================================================
    powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

python enable_bluestacks_root.py

echo.
pause
