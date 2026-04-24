@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8

echo ===================================================
echo   LINE Chat Analyzer (Local Version)
echo ===================================================
echo.

python chat_analyzer.py

pause
