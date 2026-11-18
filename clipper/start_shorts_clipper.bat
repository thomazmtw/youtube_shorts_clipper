@echo off
title Shorts Clipper
cd /d "%~dp0"

echo Checking requirements...
python -c "import yt_dlp, PIL" >nul 2>&1
if errorlevel 1 (
    echo Installing missing requirements...
    python -m pip install -r requirements.txt
)

echo Starting Shorts Clipper...
python shorts_clipper_app.py
if errorlevel 1 (
    echo.
    echo An error occurred while running Shorts Clipper.
    pause
)
