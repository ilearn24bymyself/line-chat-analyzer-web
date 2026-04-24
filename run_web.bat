@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d "%~dp0"

echo ===================================================
echo   LINE Chat Analyzer (Web Version)
echo ===================================================
echo.
echo 甇??? Flask 隡箸???..
echo 1.5 蝘?撠???汗?典?敺: http://127.0.0.1:5000
echo.

python chat_web.py

pause
