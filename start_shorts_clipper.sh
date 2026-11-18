#!/usr/bin/env bash
# Mac/Linux launcher. Run: chmod +x start_shorts_clipper.sh && ./start_shorts_clipper.sh
cd "$(dirname "$0")"
python3 -c "import yt_dlp" 2>/dev/null || python3 -m pip install --user yt-dlp
python3 shorts_clipper_app.py
