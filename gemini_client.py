"""Google Gemini Visual Understanding Assistant for Hybrid Video Clipper.

Optional cloud-based visual assistant:
- Analyzes sampled frames to identify speakers, actions, emotional expressions, and visual hooks.
- Secure API key management via environment variables and local config.
- Zero hardcoded keys, full user disable toggle.
- Batch frame sampling (never uploads full video) to respect free-tier rate limits.
- Graceful fallback on quota exhaustion (HTTP 429) or offline state.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger("gemini_client")

# Use local project file with fallback to home dir
CONFIG_FILE = Path(__file__).parent / ".gemini_config.json"

DEFAULT_GEMINI_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-2.0-flash",
]


def get_api_key() -> str:
    """Retrieve Gemini API key from environment variable or local config file."""
    # 1. Environment variable (preferred)
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key:
        return env_key

    # 2. Local config file
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return data.get("api_key", "").strip()
        except Exception:
            pass

    return ""


def save_api_key(api_key: str) -> None:
    """Save API key to user config file for persistence across sessions."""
    api_key = api_key.strip()
    try:
        CONFIG_FILE.write_text(json.dumps({"api_key": api_key}, indent=2), encoding="utf-8")
        os.environ["GEMINI_API_KEY"] = api_key
    except Exception as e:
        logger.warning("Failed to save Gemini API key: %s", e)


def clear_api_key() -> None:
    """Remove stored API key."""
    if CONFIG_FILE.exists():
        try:
            CONFIG_FILE.unlink()
        except Exception:
            pass
    if "GEMINI_API_KEY" in os.environ:
        del os.environ["GEMINI_API_KEY"]


def test_connection(api_key: Optional[str] = None, model: str = "gemini-3.5-flash-lite") -> Tuple[bool, str]:
    """Test if Gemini API key and model are active and valid."""
    key = api_key or get_api_key()
    if not key:
        return False, "No Gemini API key provided. Enter key or disable Gemini."

    models_to_test = [model] + [m for m in DEFAULT_GEMINI_MODELS if m != model]

    payload = {
        "contents": [
            {"parts": [{"text": "Reply with 'OK' in a JSON object: {\"status\": \"OK\"}"}]}
        ],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.0,
        },
    }

    last_error = ""
    for m in models_to_test:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}"
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=12.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                txt = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if "status" in txt or "OK" in txt:
                    return True, f"Connected successfully to Google Gemini ({m})!"
                return True, f"Connected to {m}."
        except urllib.error.HTTPError as e:
            if e.code == 400:
                return False, "Invalid API key."
            elif e.code == 403:
                return False, "Access denied. Ensure Gemini API is enabled for this key."
            elif e.code in (404, 503):
                last_error = f"{m} ({e.code}: {e.reason})"
                continue  # Try next model candidate
            elif e.code == 429:
                return False, "Gemini rate limit or quota exceeded (HTTP 429). Will use local Ollama."
            last_error = f"Gemini HTTP Error {e.code}: {e.reason}"
        except Exception as e:
            last_error = f"Connection error: {e}"

    return False, f"Connection failed: {last_error}"


def list_gemini_models(api_key: Optional[str] = None) -> List[str]:
    """Return available Gemini models for content generation."""
    key = api_key or get_api_key()
    if not key:
        return DEFAULT_GEMINI_MODELS

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=6.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = data.get("models", [])
            valid = []
            for m in models:
                name = m.get("name", "").replace("models/", "")
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" in methods and ("flash" in name or "pro" in name):
                    valid.append(name)
            if valid:
                # Place flash models first
                valid.sort(key=lambda x: (not ("flash" in x), x))
                return valid
    except Exception:
        pass

    return DEFAULT_GEMINI_MODELS


def extract_sampled_frames(
    video_path: Path,
    timestamps: List[float],
    work_dir: Path,
    max_width: int = 640,
    max_frames: int = 12,
) -> List[Dict[str, Any]]:
    """Extract small, lightweight JPEG frames using FFmpeg at specific timestamps.

    Returns list of dicts: [{'timestamp': float, 'path': Path, 'base64': str}].
    """
    if not shutil.which("ffmpeg"):
        return []

    # Downsample if too many timestamps
    ts_list = sorted(set(round(t, 1) for t in timestamps if t >= 0))
    if len(ts_list) > max_frames:
        step = len(ts_list) / max_frames
        ts_list = [ts_list[int(i * step)] for i in range(max_frames)]

    frames_dir = work_dir / "gemini_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    extracted = []
    for idx, ts in enumerate(ts_list):
        out_jpg = frames_dir / f"frame_{idx:03d}_{ts:.1f}s.jpg"
        if not out_jpg.exists():
            cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-ss", f"{ts:.2f}",
                "-i", str(video_path),
                "-frames:v", "1",
                "-vf", f"scale='min({max_width},iw)':-2",
                "-q:v", "3",
                str(out_jpg)
            ]
            try:
                subprocess.run(cmd, capture_output=True, timeout=10)
            except Exception:
                continue

        if out_jpg.exists() and out_jpg.stat().st_size > 100:
            try:
                raw_bytes = out_jpg.read_bytes()
                b64 = base64.b64encode(raw_bytes).decode("ascii")
                extracted.append({
                    "timestamp": ts,
                    "path": out_jpg,
                    "base64": b64,
                })
            except Exception:
                pass

    return extracted


def analyze_visual_scenes(
    video_path: Path,
    timestamps: List[float],
    work_dir: Path,
    api_key: Optional[str] = None,
    model: str = "gemini-2.0-flash",
    style: str = "viral_podcast",
    log_fn=print,
) -> List[Dict[str, Any]]:
    """Sample frames and invoke Gemini to extract visual cues and framing suggestions.

    Returns list of visual event dicts:
    [{
      'timestamp': float,
      'speaker_pos': 'left' | 'center' | 'right',
      'action_or_expression': str,
      'visual_interest': int (1-10),
      'is_hook': bool,
      'zoom_recommended': bool,
      'description': str
    }]
    """
    key = api_key or get_api_key()
    if not key:
        if log_fn:
            log_fn("ℹ️ Gemini visual assistant: No API key configured. Skipping cloud visual analysis.")
        return []

    if log_fn:
        log_fn(f"👁️ Extracting sample frames for Gemini ({model}) visual understanding...")

    frames = extract_sampled_frames(video_path, timestamps, work_dir, max_frames=12)
    if not frames:
        if log_fn:
            log_fn("ℹ️ No video frames could be extracted for visual analysis.")
        return []

    if log_fn:
        log_fn(f"👁️ Sending {len(frames)} keyframes to Gemini ({model}) for visual analysis...")

    # Build prompt and parts
    parts: List[Dict[str, Any]] = []
    intro_text = (
        f"You are a professional video editing visual director analyzing a video for {style.upper()} Shorts. "
        "Review these sequential video frames sampled at specific timestamps. "
        "Analyze visible subjects, speaker locations, emotional reactions, facial expressions, and visual hooks. "
        "Return a JSON object containing a list named 'visual_events' with an entry for each frame.\n\n"
        "Schema:\n"
        "{\n"
        '  "visual_events": [\n'
        '    {\n'
        '      "timestamp": float (exact frame timestamp),\n'
        '      "speaker_pos": "left" | "center" | "right",\n'
        '      "action_or_expression": "string describing face/gesture/action",\n'
        '      "visual_interest": integer (1 to 10),\n'
        '      "is_hook": boolean (true if visually arresting hook moment),\n'
        '      "zoom_recommended": boolean (true if a 1.15x punch-in zoom highlights speaker/reaction),\n'
        '      "description": "brief summary of scene"\n'
        '    }\n'
        '  ]\n'
        "}\n"
    )
    parts.append({"text": intro_text})

    for f in frames:
        parts.append({"text": f"--- Frame at {f['timestamp']:.1f}s ---"})
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": f["base64"],
            }
        })

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.2,
        },
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=35.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        raw_txt = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        parsed = json.loads(raw_txt) if raw_txt else {}
        events = parsed.get("visual_events", [])
        if log_fn:
            log_fn(f"✅ Gemini detected {len(events)} visual events & framing insights.")
        return events

    except urllib.error.HTTPError as e:
        if e.code == 429:
            msg = "⚠️ Gemini rate limit / quota exceeded (HTTP 429). Gracefully falling back to Ollama local intelligence."
        else:
            msg = f"⚠️ Gemini visual analysis error (HTTP {e.code}): {e.reason}. Falling back to local intelligence."
        if log_fn:
            log_fn(msg)
        return []
    except Exception as e:
        if log_fn:
            log_fn(f"⚠️ Gemini request failed ({e}). Proceeding with local AI intelligence.")
        return []


def sample_and_analyze_scenes(
    video_path: Path,
    api_key: Optional[str] = None,
    model: str = "gemini-3.5-flash-lite",
    num_samples: int = 6,
    style: str = "viral_podcast",
    work_dir: Optional[Path] = None,
    log_fn=print,
) -> List[Dict[str, Any]]:
    """Sample frames evenly across video and analyze scenes using Google Gemini."""
    import shorts_clipper as _core
    try:
        total_dur = _core.duration(Path(video_path))
    except Exception:
        total_dur = 30.0

    if total_dur <= 2.0:
        return []

    # Generate evenly spaced sample timestamps avoiding very start and very end
    step = total_dur / (num_samples + 1)
    timestamps = [round(step * (i + 1), 2) for i in range(num_samples)]

    w_dir = Path(work_dir or Path(video_path).parent)
    return analyze_visual_scenes(
        video_path=Path(video_path),
        timestamps=timestamps,
        work_dir=w_dir,
        api_key=api_key,
        model=model,
        style=style,
        log_fn=log_fn,
    )
