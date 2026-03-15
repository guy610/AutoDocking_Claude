@echo off
title Stephen Docking
cd /d "%~dp0"

:: Force UTF-8 mode and prevent bytecode caching
set PYTHONUTF8=1
set PYTHONDONTWRITEBYTECODE=1
set PYTHONIOENCODING=utf-8

:: Clean ALL cached bytecode to prevent stale .pyc issues
echo Cleaning cached files...
if exist autodock_pipeline\__pycache__ rd /s /q autodock_pipeline\__pycache__
if exist autodock_pipeline\core\__pycache__ rd /s /q autodock_pipeline\core\__pycache__
if exist autodock_pipeline\utils\__pycache__ rd /s /q autodock_pipeline\utils\__pycache__
if exist autodock_pipeline\web\__pycache__ rd /s /q autodock_pipeline\web\__pycache__
if exist autodock_pipeline\stages\__pycache__ rd /s /q autodock_pipeline\stages\__pycache__

echo Starting Stephen Docking...
python web_app.py
pause
