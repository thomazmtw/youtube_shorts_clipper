# 🎬 Shorts Clipper — Hybrid AI Professional Shorts Editor

A powerful, intelligent hybrid AI video editor that turns long videos and podcasts into professionally edited **YouTube Shorts**, **TikToks**, and **Instagram Reels**. Combines **Ollama (local LLM brain)** for storytelling, cut planning, and retention directing with optional **Google Gemini (cloud AI)** for visual scene understanding.

Runs privately on your computer with complete offline resilience, smart fallbacks, and zero required subscriptions.

---

## ✨ Hybrid AI Video Editing Engine

### 🧠 1. Ollama — Primary Local AI Brain
- **Deep Narrative Understanding**: Analyzes speech transcripts to identify the most compelling stories, revelations, punchlines, and emotional peaks.
- **Hook Detection**: Locates irresistible opening hooks within the first 1–3 seconds to maximize short-form viewer retention.
- **Automated Jump Cuts & Pause Trimming**: Plans natural jump cuts to eliminate awkward dead air and rambling dialogue without cutting sentences in the middle.
- **Punch-In Zooms & Dynamic Framing**: Plans controlled punch-in zooms (1.1x–1.2x) on speaker revelations and punchlines.
- **Keyword Highlighting**: Selects high-impact keywords to pop dynamically with custom accent colors in the subtitles.
- **Local Model Auto-Discovery**: Detects installed Ollama models (`llama3.2`, `mistral`, `qwen2.5`, etc.) with in-app model selection and setup instructions.

### 👁️ 2. Google Gemini — Visual Understanding Assistant (Optional Cloud)
- **Keyframe Scene Analysis**: Efficiently samples lightweight frames across the video to detect speakers, facial expressions, actions, and camera framing opportunities.
- **Zero Full-Video Uploads**: Sends only small sampled keyframes to respect free-tier rate limits and bandwidth.
- **Graceful Fallback**: If Gemini is disabled, offline, or rate-limited (HTTP 429), automatically falls back to local Ollama directing with zero disruption.
- **Secure Key Management**: API keys are securely loaded from environment variables (`GEMINI_API_KEY`) or encrypted local config, never hardcoded.

### 🎙️ 3. Faster-Whisper Speech Recognition & Multilingual Support
- **100% Offline Local Speech Recognition**: Transcribes audio directly with `faster-whisper` without third-party cloud APIs.
- **Word-Level Timestamps**: Precise synchronization for captions and jump cuts.
- **Sentence Boundary Integrity**: Ensures clips never chop dialogue in the middle of a sentence.
- **Multilingual Support**: First-class support for **English (`en`)** and **Malayalam (`ml`)**, as well as automatic language detection.

### 🎨 4. Five Professional Editing Styles
1. **Viral Podcast Style**: Fast cuts, speaker-focused framing, punch-in zoom on punchlines, aggressive pause trimming.
2. **Cinematic Style**: Smooth pacing, dramatic moments, subtle 1.08x zooms, preserving emotional cadence and dramatic pauses.
3. **Fast Viral Shorts**: Opening hook <1.5s, rapid cuts every 2–4s, punch-in zooms (1.18x) on emotional spikes, dynamic keyword color pops.
4. **Educational Style**: Clear explanations, readable captions, structured chaptering, centered stable framing.
5. **Storytelling Style**: Emotional pacing, narrative continuity, meaningful scene changes, preserving dialogue nuance.

### ⚡ 5. Studio-Grade FFmpeg Execution
- **Dynamic Punch-In Zooms**: Executes center-focused zooms without distortion or fake camera angles.
- **Seamless Jump Cut Splices**: Eliminates boring pauses and dead air without audio pops or sync drift.
- **Keyword Highlighting Captions**: Generates ASS subtitles that highlight impactful words dynamically.
- **Broadcast Audio Normalization**: Applies EBU R128 loudness normalization (`loudnorm=I=-14:LRA=7:TP=-1.5`) matching YouTube Shorts standards.
- **PNG Logo Watermarking**: Overlays custom channel logos and watermarks at configurable opacity and position.


---

## ✨ Key Features

### 💬 Auto Subtitles & CapCut-Style Captions (Burned-in)
- **Automatic YouTube Subtitle Fetch**: Automatically downloads and syncs official or auto-generated captions from YouTube via `yt-dlp`.
- **Speech-to-Text Offline Whisper Fallback**: Transcribes speech directly from audio via `faster-whisper` if no subtitles exist.
- **Shorts Pacing (Word Bursts)**: Splits long sentences into punchy 3–5 word bursts that keep viewer retention high.
- **Dedicated Style Library (`caption_styles.py`)**: Edit fonts, colors, borders, shadows, alignments, and sizes without touching application code.
- **13+ Built-in Presets**:
  - `tiktok_yellow`: Vibrant yellow text with bold black stroke and drop shadow (classic TikTok/Reels look).
  - `neon_green`: Glowing electric green for gaming, tech, and hype clips.
  - `fire_orange`: Impact font in bold orange for motivational and fitness content.
  - `impact_red`: Heavy red impact styling for sports and breaking news.
  - `hot_pink` & `electric_blue`: Vibrant pop styles for lifestyle, beauty, and finance.
  - `clean_white` & `bold_stroke`: Minimal, crisp professional styles.
  - `cinema_box` & `podcast_minimal`: Sleek translucent black/gray backing box for interview dialogue.
  - `typewriter`, `reels_white`, `top_banner`, and more.
- **Caption Font Size Slider**: Dynamically adjust caption font size in px directly in the GUI or via `--caption-size`.

---

### 🖼️ PNG Logo Branding & Watermarking (`branding.py`)
- **Burn Custom PNG Logos**: Overlay transparent PNG logos or channel watermarks directly onto every exported clip.
- **Dedicated Configuration File (`branding.py`)**: Configure logo path, position, size percentage, opacity, and margin padding.
- **9 Positioning Anchors**: Top-Left, Top-Center, Top-Right, Middle-Left, Center, Middle-Right, Bottom-Left, Bottom-Center, Bottom-Right.
- **Logo Size & Opacity Controls**: Adjust logo scale (3%–50% of screen width) and opacity (0.0 to 1.0) with real-time feedback.

---

### 📱 Single Unified Live Preview
- **9:16 Phone Mockup Screen**: A single visual preview workspace showing both captions and logo together in real time.
- **Instant Updates**: Dragging the caption size slider, choosing caption styles, selecting logo positions, or tuning opacity updates the phone screen mockup immediately.

---

### 📊 Virality Potential Rating (0–100%)
Every segment is analyzed and graded by a 4-pillar algorithmic model:
1. **Hook Strength (0–25 pts)**: Evaluates speech onset, volume spikes in the first 3.5 seconds, and viral keyword hooks (*"how to", "secret", "never", "truth", "crazy", questions*).
2. **Audio Energy & Dynamics (0–30 pts)**: Analyzes loudness consistency and vocal intensity (`volumedetect`).
3. **Pacing & Cadence (0–25 pts)**: Evaluates pause cadence (optimal engagement rhythm is 1 natural pause every 7–10 seconds).
4. **Retention Duration (0–20 pts)**: Rewards the short-form algorithmic sweet spot (30–50 seconds).
- **Report Export**: Each clip filename includes its virality score (e.g. `short_01_viral89.mp4`), and a full breakdown is saved to `virality_report.json`.

---

### 🎙️ Podcast Video Cutting
- **Podcast Mode (`--mode podcast`)**: Specifically tuned for interviews, conversational dialogues, and talk shows. Detects conversational turn pauses (0.5s–1.5s) to avoid cutting off mid-story, and ranks clips by conversational hook strength.
- **Podcast Split-Screen Template (`--fit split`)**: Turns wide 16:9 two-person podcast videos (host & guest) into a 9:16 vertical layout by stacking the **Left Speaker on the Top** and the **Right Speaker on the Bottom**, with burnt captions centered in the reading zone!

---

### 🎨 Visual Framing Templates

| Template | Value | Best For | Description |
| :--- | :--- | :--- | :--- |
| **Center Crop** | `crop` | Solo videos, vlogs | Smart 9:16 center crop that handles any input aspect ratio |
| **Blurred Background** | `blur` | General clips, gaming | Full 16:9 video centered over an enlarged, blurred 9:16 backdrop |
| **Podcast Split Screen** | `split` | Podcasts, 2-person interviews | Stacks Host (left) on Top and Guest (right) on Bottom |
| **Headline Frame** | `headline` | News, reactions | Centered video with dedicated space for top hook header & captions |
| **Original** | `none` | Already vertical | Preserves original video dimensions without vertical scaling |

---

## 📋 Prerequisites

1. **Python 3.8+**
2. **FFmpeg & FFprobe** installed and accessible from `PATH`
3. **yt-dlp** Python package

---

## ⚙️ Installation

### 1. FFmpeg
```powershell
# Windows
winget install Gyan.FFmpeg

# macOS (Homebrew)
brew install ffmpeg

# Linux (Ubuntu / Debian)
sudo apt update && sudo apt install ffmpeg python3-tk -y
```

### 2. Python Dependencies
```bash
pip install yt-dlp
```

---

## 🚀 Quick Start

### Graphical User Interface (GUI)

- **Windows**: Double-click **`start_shorts_clipper.bat`**  
- **macOS / Linux**: Run `./start_shorts_clipper.sh`  
*(or run `python shorts_clipper_app.py` in your terminal)*

#### GUI Workflow:
1. Paste a **YouTube link** or click **Browse…** to select a video file.
2. Select **Cutting Mode**:
   - `Smart`: Cuts at natural pauses & ranks by virality.
   - `Podcast`: Cuts at conversational turns & dialogue hooks.
   - `Even chunks`: Sequential fixed-duration cuts.
3. Select **Video Template** (`Center Crop`, `Blur BG`, `Podcast Split Screen`, `Headline Frame`).
4. Select **Captions / Subtitles Style** (`TikTok Yellow`, `Clean White`, `Neon Green`, `Cinema Box`, or `No Subtitles`).
5. Click **Start Clipping**!

---

### Command Line Interface (CLI)

```bash
# Basic clip with smart cuts & viral yellow subtitles
python shorts_clipper.py "https://www.youtube.com/watch?v=VIDEO_ID"

# Podcast video: 2-speaker split-screen + dialogue turn cuts
python shorts_clipper.py podcast.mp4 --fit split --mode podcast --subtitle-style tiktok_yellow

# Blurred background with clean white subtitles
python shorts_clipper.py my_video.mp4 --fit blur --length 40 --subtitle-style clean_white

# Add burnt-in logo watermark and custom caption size
python shorts_clipper.py my_video.mp4 --logo logo.png --logo-position top_right --logo-size 15 --caption-size 70

# Headline frame with neon green captions
python shorts_clipper.py my_video.mp4 --fit headline --subtitle-style neon_green --max-clips 5
```

#### CLI Options Reference

| Argument | Options / Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `source` | `str` | *required* | YouTube URL or path to local video file |
| `--length` | `float` | `45` | Target clip duration in seconds (Shorts limit is 60s) |
| `--max-clips` | `int` | `10` | Maximum number of clips to export |
| `--mode` | `smart \| podcast \| even` | `smart` | Cutting mode algorithm |
| `--fit` | `crop \| blur \| split \| headline \| none` | `crop` | Visual framing template |
| `--subtitle-style` | `STYLE \| none` | `tiktok_yellow` | Caption aesthetic (any key in `caption_styles.py`) |
| `--caption-size` | `int` | `0` | Override caption font size in px (`0` = style default) |
| `--logo` | `str` | `""` | Path to transparent PNG logo to burn into every clip |
| `--logo-position`| `top_left \| top_right \| ...` | `top_right` | Screen position anchor for logo |
| `--logo-size` | `int` | `15` | Logo width as % of video width (1–50) |
| `--logo-opacity` | `float` | `1.0` | Logo opacity from 0.0 (transparent) to 1.0 (solid) |
| `--logo-padding` | `int` | `30` | Distance in pixels from screen edges |
| `--out` | `str` | `clips` | Folder to save exported clips & virality report |

---

## 📁 Output & Virality Report

Generated clips are named with their virality rating:
```text
clips/
├── short_01_viral92.mp4       # 92/100 (🔥 Viral Potential)
├── short_02_viral84.mp4       # 84/100 (⚡ High Engagement)
├── short_03_viral76.mp4       # 76/100 (✨ Good Clip)
└── virality_report.json       # Full metrics breakdown (hook, energy, pacing, duration)
```

Sample `virality_report.json`:
```json
[
  {
    "clip": "short_01_viral92.mp4",
    "start_time": 142.5,
    "end_time": 185.0,
    "duration": 42.5,
    "virality_score": 92,
    "tier": "🔥 Viral Potential",
    "hook_score": 24.0,
    "energy_score": 28.5,
    "pacing_score": 22.0,
    "duration_score": 20.0
  }
]
```

---

## 📄 License
Open-source and free for personal and commercial content creation.
