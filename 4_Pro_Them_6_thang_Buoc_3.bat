@echo off
chcp 65001 >nul
title Pro 6 thang - offer 6months-eft-2
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo ============================================
echo   Google AI Pro - offer 6months-eft-2
echo   Nang cap goi bang purchaseToken dung tai khoan, mode 5.
echo ============================================
python ultra0.py --account "current@device" --no-add --force --stack --plan pro6b
echo.
pause
