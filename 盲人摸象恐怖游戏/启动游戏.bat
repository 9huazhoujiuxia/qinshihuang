@echo off
chcp 65001 >nul
title BLIND HORROR
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found in PATH. Please install Python first.
    pause
    exit /b 1
)
python blind_horror.py
if errorlevel 1 pause
