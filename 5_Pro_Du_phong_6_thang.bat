@echo off
chcp 65001 >nul
title Pro 6 thang - offer ss-2026
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo ============================================
echo   Google AI Pro - offer 6months-eft-ss-2026
echo   Nang cap goi bang purchaseToken dung tai khoan, mode 5.
echo   Ket qua va thoi gian quy doi do Google Play quyet dinh.
echo ============================================
python ultra0.py --account "current@device" --no-add --force --stack --plan pro6c
echo.
pause
