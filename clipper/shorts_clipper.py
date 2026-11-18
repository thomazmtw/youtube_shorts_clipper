#!/usr/bin/env python3
"""
Shorts Clipper: Free YouTube Shorts & Podcast Clipper with Auto Subtitles & Virality Scoring.
Runs 100% locally: no API keys, no subscriptions, no credit limits.

Usage:
  python shorts_clipper.py "https://www.youtube.com/watch?v=XXXX"
  python shorts_clipper.py URL --fit split --mode podcast          # podcast 2-speaker split
  python shorts_clipper.py URL --subtitle-style tiktok_yellow      # viral yellow captions
  python shorts_clipper.py my_video.mp4 --fit blur --length 45     # local video file

Requires: Python 3.8+, ffmpeg (with ffprobe), yt-dlp
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Load caption styles from caption_styles.py (editable without touching this file)
try:
    from caption_styles import STYLES as SUBTITLE_STYLES, get_style as _get_style, style_keys as _style_keys
    _USING_EXTERNAL_STYLES = True
except ImportError:
    _USING_EXTERNAL_STYLES = False
    # Minimal built-in fallback if caption_styles.py is missing
    SUBTITLE_STYLES = {
        "tiktok_yellow": {
            "display_name": "TikTok Yellow", "font": "Arial", "size": 62,
            "bold": -1, "italic": 0, "underline": 0,
            "primary": "&H0000FFFF", "secondary": "&H000000FF",
            "outline_color": "&H00000000", "back_color": "&H80000000",
            "border_style": 1, "outline": 4, "shadow": 2,
            "alignment": 2, "margin_v": 300, "scale_x": 100, "scale_y": 100, "letter_spacing": 0,
        },
    }
    def _get_style(key): return SUBTITLE_STYLES.get(key, SUBTITLE_STYLES["tiktok_yellow"])
    def _style_keys(): return list(SUBTITLE_STYLES.keys())


def ensure_tools_in_path():
    """Ensure ffmpeg and ffprobe are in PATH even if newly installed without a shell restart."""
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return

    if sys.platform.startswith("win"):
        try:
            import winreg
            extra_paths = []
            for root, sub in [
                (winreg.HKEY_CURRENT_USER, r"Environment"),
                (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            ]:
                try:
                    with winreg.OpenKey(root, sub) as key:
                        val, _ = winreg.QueryValueEx(key, "Path")
                        extra_paths.extend(val.split(";"))
                except OSError:
                    pass
            for p in extra_paths:
                p = os.path.expandvars(p.strip())
                if p and p not in os.environ.get("PATH", "") and os.path.isdir(p):
                    os.environ["PATH"] = p + os.pathsep + os.environ["PATH"]
        except Exception:
            pass

    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return

    search_dirs = [
        Path.cwd(),
        Path(sys.executable).parent,
        Path(sys.executable).parent / "Scripts",
        Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages",
        Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links",
        Path.home() / "scoop" / "shims",
        Path.home() / "scoop" / "apps" / "ffmpeg" / "current" / "bin",
        Path("C:/ffmpeg/bin"),
        Path("C:/ProgramData/chocolatey/bin"),
    ]
    for base in search_dirs:
        if not base.exists():
            continue
        if (base / "ffmpeg.exe").exists() or (base / "ffmpeg").exists():
            os.environ["PATH"] = str(base) + os.pathsep + os.environ["PATH"]
            if shutil.which("ffmpeg") and shutil.which("ffprobe"):
                return
        if "WinGet" in str(base):
            for ffmpeg_exe in base.glob("**/ffmpeg.exe"):
                bin_dir = ffmpeg_exe.parent
                os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ["PATH"]
                if shutil.which("ffmpeg") and shutil.which("ffprobe"):
                    return


# Automatically ensure tools are in PATH on import
ensure_tools_in_path()


def need(tool):
    ensure_tools_in_path()
    if not shutil.which(tool):
        sys.exit(f"Missing '{tool}'. Install it first (see README.md).")


def ytdlp_cmd():
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    return [sys.executable, "-m", "yt_dlp"]


def download(url, work):
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    out_tpl = str(work / "source.%(ext)s")

    # Step 1: Download video (guaranteed to succeed without subtitle 429 rate limit issues)
    cmd_video = ytdlp_cmd() + [
        "-f", "bv*[height<=1080]+ba/b[height<=1080]/b",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "-o", out_tpl, url,
    ]
    print("Downloading video from YouTube...")
    res = subprocess.run(cmd_video)

    # Step 2: Try fetching official/auto subtitles (optional, non-fatal if 429 rate-limited)
    cmd_subs = ytdlp_cmd() + [
        "--skip-download",
        "--write-subs", "--write-auto-subs",
        "--sub-lang", "en.*,en",
        "--convert-subs", "srt",
        "--no-playlist",
        "-o", out_tpl, url,
    ]
    try:
        subprocess.run(cmd_subs, capture_output=True, timeout=15)
    except Exception:
        pass

    target = work / "source.mp4"
    if target.exists() and target.stat().st_size > 1000:
        return target
    for cand in work.glob("source.*"):
        if cand.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov", ".avi", ".ts") and cand.stat().st_size > 1000:
            return cand
    if res.returncode != 0:
        raise RuntimeError(f"Video download failed with exit code {res.returncode}. Check link or update yt-dlp.")
    raise FileNotFoundError(f"Downloaded video file not found in: {work}")


def duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True, encoding="utf-8", errors="replace")
    out = r.stdout.strip()
    try:
        return float(out)
    except (ValueError, TypeError):
        pass
    r2 = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True, encoding="utf-8", errors="replace")
    return float(r2.stdout.strip())


def find_silences(path, noise="-30dB", dur=0.4):
    """Return midpoints of silent gaps; good places to cut without chopping speech."""
    r = subprocess.run(
        ["ffmpeg", "-i", str(path), "-vn", "-af",
         f"silencedetect=noise={noise}:d={dur}", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    return [(s + e) / 2 for s, e in zip(starts, ends)]


def loudness(path, start, dur):
    """Mean volume in dB (closer to 0 = louder/more energetic)."""
    r = subprocess.run(
        ["ffmpeg", "-ss", str(start), "-t", str(dur), "-i", str(path),
         "-vn", "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"mean_volume: (-?[\d.]+) dB", r.stderr)
    return float(m.group(1)) if m else -91.0


# ---------- Subtitle Parsing & Generation ----------
def parse_subtitles_file(path):
    """Parse SRT or VTT file into [{'start': float, 'end': float, 'text': str}]."""
    if not path or not Path(path).exists():
        return []
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    content = content.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", content)
    entries = []

    def to_seconds(ts):
        ts = ts.replace(",", ".").strip()
        parts = ts.split(":")
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        return 0.0

    for b in blocks:
        lines = [l.strip() for l in b.split("\n") if l.strip()]
        if not lines:
            continue
        time_idx = -1
        for i, line in enumerate(lines):
            if "-->" in line:
                time_idx = i
                break
        if time_idx == -1:
            continue
        m = re.search(r"(\d+:[\d:.,]+)\s*-->\s*(\d+:[\d:.,]+)", lines[time_idx])
        if not m:
            continue
        start_sec = to_seconds(m.group(1))
        end_sec = to_seconds(m.group(2))
        text = " ".join(lines[time_idx + 1:])
        text = re.sub(r"<[^>]+>", "", text)  # strip html
        text = re.sub(r"\{[^}]+\}", "", text)  # strip ass tags
        text = re.sub(r"\s+", " ", text).strip()
        if text and end_sec > start_sec:
            entries.append({"start": start_sec, "end": end_sec, "text": text})
    return entries


def chunk_captions(entries, max_words=4):
    """Break long subtitle entries into punchy 3-5 word bursts for high viewer retention."""
    chunked = []
    for e in entries:
        words = e["text"].split()
        if len(words) <= max_words:
            chunked.append({"start": e["start"], "end": e["end"], "text": e["text"].upper()})
            continue
        dur = e["end"] - e["start"]
        total_chars = max(1, sum(len(w) for w in words))
        cur_t = e["start"]
        for i in range(0, len(words), max_words):
            group = words[i:i + max_words]
            group_chars = sum(len(w) for w in group)
            c_dur = dur * (group_chars / total_chars)
            chunked.append({
                "start": cur_t,
                "end": cur_t + c_dur,
                "text": " ".join(group).upper()
            })
            cur_t += c_dur
    return chunked


def find_subtitles(video_path, work_dir=None):
    """Find subtitles from adjacent files, work directory, or extract from container."""
    v_path = Path(video_path)
    # Check adjacent files (e.g. video.srt, video.en.srt, video.vtt)
    candidates = list(v_path.parent.glob(f"{v_path.stem}*.srt")) + list(v_path.parent.glob(f"{v_path.stem}*.vtt"))
    if candidates:
        return candidates[0]

    # Check work directory (from yt-dlp download)
    if work_dir and Path(work_dir).exists():
        work_subs = list(Path(work_dir).glob("source*.srt")) + list(Path(work_dir).glob("source*.vtt"))
        if work_subs:
            return work_subs[0]

    # Attempt to extract embedded subtitle stream using ffmpeg
    try:
        out_sub = (work_dir or v_path.parent) / "extracted_subs.srt"
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", str(v_path), "-map", "0:s:0", str(out_sub)],
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        if out_sub.exists() and out_sub.stat().st_size > 50:
            return out_sub
    except Exception:
        pass

    return None


def transcribe_speech_whisper(video_path, out_dir=None, log_fn=print):
    """Transcribe speech directly from audio using faster-whisper (tiny.en)."""
    try:
        # pyrefly: ignore[missing-import]
        from faster_whisper import WhisperModel
        if log_fn:
            log_fn("🎙️ Transcribing speech directly from audio (using faster-whisper)...")
        model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
        segments, info = model.transcribe(str(video_path), beam_size=3, word_timestamps=True)
        words_list = []
        for s in segments:
            if s.words:
                for w in s.words:
                    clean = w.word.strip()
                    if clean:
                        words_list.append({"start": w.start, "end": w.end, "text": clean})
            else:
                clean = s.text.strip()
                if clean:
                    words_list.append({"start": s.start, "end": s.end, "text": clean})

        if not words_list:
            if log_fn:
                log_fn("ℹ️ No spoken words detected in the audio.")
            return []

        # Group into punchy 2-3 word bursts for high-engagement Shorts
        captions = []
        max_words = 3
        for i in range(0, len(words_list), max_words):
            grp = words_list[i:i + max_words]
            captions.append({
                "start": round(grp[0]["start"], 2),
                "end": round(grp[-1]["end"], 2),
                "text": " ".join(w["text"] for w in grp).upper()
            })

        # Save an SRT copy for convenience
        if out_dir:
            out_dir = Path(out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            srt_lines = []
            for idx, c in enumerate(captions, 1):
                def to_srt_time(sec):
                    h = int(sec // 3600)
                    m = int((sec % 3600) // 60)
                    s = int(sec % 60)
                    ms = int(round((sec - int(sec)) * 1000))
                    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
                srt_lines.append(f"{idx}\n{to_srt_time(c['start'])} --> {to_srt_time(c['end'])}\n{c['text']}\n")
            (out_dir / "transcribed_captions.srt").write_text("\n".join(srt_lines), encoding="utf-8")

        if log_fn:
            log_fn(f"✅ Generated {len(captions)} caption bursts directly from speech.")
        return captions
    except Exception as e:
        if log_fn:
            log_fn(f"⚠️ Speech transcription error: {e}")
        return []


def get_captions(video_path, work_dir=None, log_fn=print):
    """Retrieve subtitles from existing files or transcribe directly from audio."""
    sub_file = find_subtitles(video_path, work_dir)
    if sub_file:
        raw = parse_subtitles_file(sub_file)
        if raw:
            if log_fn:
                log_fn(f"💬 Found existing subtitles from: {sub_file.name}")
            return chunk_captions(raw)

    return transcribe_speech_whisper(video_path, work_dir, log_fn=log_fn)


def generate_ass(captions, clip_start, clip_end, style_key, out_ass_path, size_override=None):
    """Generate an Advanced SubStation Alpha (.ass) subtitle file for a specific clip window.

    size_override : int or None — if set and > 0, overrides the style's default font size.
    """
    style_def = _get_style(style_key)
    clip_dur = clip_end - clip_start

    # Build an internal ASS style name (strip emojis and spaces for safety)
    ass_style_name = re.sub(r"[^A-Za-z0-9_]", "", style_def.get("display_name", style_key)) or style_key

    # Read fields with safe fallbacks for both old and new format
    font          = style_def.get("font", "Arial")
    # Allow caller to override font size (GUI slider)
    size          = int(size_override) if size_override and int(size_override) > 0 else style_def.get("size", 60)
    bold          = style_def.get("bold", -1)
    italic        = style_def.get("italic", 0)
    underline     = style_def.get("underline", 0)
    primary       = style_def.get("primary", "&H0000FFFF")
    secondary     = style_def.get("secondary", "&H000000FF")
    outline_color = style_def.get("outline_color", "&H00000000")
    back_color    = style_def.get("back_color", "&H80000000")
    border_style  = style_def.get("border_style", 1)
    outline       = style_def.get("outline", 4)
    shadow        = style_def.get("shadow", 2)
    alignment     = style_def.get("alignment", 2)
    margin_v      = style_def.get("margin_v", 300)
    scale_x       = style_def.get("scale_x", 100)
    scale_y       = style_def.get("scale_y", 100)
    spacing       = style_def.get("letter_spacing", 0)

    # Filter overlapping captions and shift timestamps to start at 0
    rel_caps = []
    for c in captions:
        if c["end"] > clip_start and c["start"] < clip_end:
            s = max(0.0, c["start"] - clip_start)
            e = min(clip_dur, c["end"] - clip_start)
            if e > s:
                rel_caps.append({"start": s, "end": e, "text": c["text"]})

    def format_ass_time(sec):
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        cs = int(round((sec - int(sec)) * 100))
        if cs >= 100:
            cs = 99
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    # ASS Format: Name,Font,Size,PrimaryColour,SecondaryColour,OutlineColour,
    #             BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,
    #             Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,
    #             MarginL,MarginR,MarginV,Encoding
    style_line = (
        f"Style: {ass_style_name},{font},{size},"
        f"{primary},{secondary},{outline_color},{back_color},"
        f"{bold},{italic},{underline},0,"
        f"{scale_x},{scale_y},{spacing},0,"
        f"{border_style},{outline},{shadow},{alignment},"
        f"40,40,{margin_v},1"
    )

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "WrapStyle: 0",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        style_line,
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    for c in rel_caps:
        st = format_ass_time(c["start"])
        et = format_ass_time(c["end"])
        txt = c["text"].replace("\n", "\\N")
        # Add a subtle fade-in/fade-out (80ms each) for polish
        lines.append(f"Dialogue: 0,{st},{et},{ass_style_name},,0,0,0,,{{\\fad(80,80)}}{txt}")

    Path(out_ass_path).write_text("\n".join(lines), encoding="utf-8")
    return out_ass_path


# ---------- Virality Scoring Engine ----------
def calculate_virality_score(src, start, end, total, silences, captions=None):
    """
    Calculate a 0-100 Virality Potential Score for a clip based on:
    1. Hook Strength (speech onset, opening 3.5s volume spike, hook keywords)
    2. Audio Energy & Dynamics (loudness range & intensity)
    3. Pacing & Cadence (silence frequency and natural rhythm)
    4. Optimal Retention Duration (30-50s sweet spot)
    """
    dur = end - start

    # 1. Energy & Loudness Score (0 to 30 pts)
    clip_loudness = loudness(src, start, dur)
    # Broadcast sweet spot: -14 dB to -20 dB. Penalty for < -35 dB
    energy_score = max(5.0, min(30.0, (clip_loudness + 38.0) * (30.0 / 22.0)))

    # 2. Hook Strength (0 to 25 pts)
    # Opening 3.5 seconds dynamic change
    hook_loudness = loudness(src, start, min(3.5, dur))
    hook_diff = hook_loudness - clip_loudness
    hook_score = max(5.0, min(25.0, 16.0 + (hook_diff * 2.0)))

    # Hook keyword bonus
    hook_text_sample = ""
    if captions:
        hook_caps = [c["text"].lower() for c in captions if c["start"] <= start + 5.0 and c["end"] >= start]
        hook_text_sample = " ".join(hook_caps)
        viral_hook_words = [
            "how to", "secret", "why", "never", "best", "truth", "crazy",
            "listen", "stop", "what if", "look at", "actually", "mistake",
            "everybody", "nobody", "shocking", "million", "podcast", "rule",
            "revealed", "insane", "unbelievable", "don't", "watch"
        ]
        if any(w in hook_text_sample for w in viral_hook_words) or "?" in hook_text_sample or "!" in hook_text_sample:
            hook_score = min(25.0, hook_score + 5.0)

    # 3. Pacing & Cadence (0 to 25 pts)
    clip_silences = [s for s in silences if start <= s <= end]
    # Optimal cadence in engaging video: one pause every 7-10 seconds
    expected_pauses = dur / 8.5
    pacing_diff = abs(len(clip_silences) - expected_pauses)
    pacing_score = max(6.0, 25.0 - (pacing_diff * 3.2))

    # 4. Retention Duration Sweet Spot (0 to 20 pts)
    if 30.0 <= dur <= 50.0:
        duration_score = 20.0
    elif 20.0 <= dur < 30.0:
        duration_score = 16.0
    elif 50.0 < dur <= 60.0:
        duration_score = 17.0
    else:
        duration_score = max(5.0, 20.0 - abs(dur - 40.0) * 0.4)

    total_score = int(round(energy_score + hook_score + pacing_score + duration_score))
    total_score = max(15, min(99, total_score))

    if total_score >= 85:
        tier = "🔥 Viral Potential"
    elif total_score >= 70:
        tier = "⚡ High Engagement"
    elif total_score >= 50:
        tier = "✨ Good Clip"
    else:
        tier = "Average"

    return {
        "score": total_score,
        "tier": tier,
        "energy": round(energy_score, 1),
        "hook": round(hook_score, 1),
        "pacing": round(pacing_score, 1),
        "duration": round(duration_score, 1),
        "loudness_db": clip_loudness,
        "hook_sample": hook_text_sample[:60] if hook_text_sample else ""
    }


# ---------- Cut Planning ----------
def plan_cuts(total, length, snap, silences, mode="smart"):
    """Plan cut points according to target length, silences, and cutting mode."""
    if total <= 0:
        return []
    if total <= length:
        return [(0.0, round(total, 2))]

    cuts = [0.0]
    min_tail = length * 0.5
    is_smart = mode in ("smart", "podcast")
    actual_snap = snap * 1.3 if mode == "podcast" else snap

    while cuts[-1] + length < total - min_tail:
        target = cuts[-1] + length
        if is_smart:
            near = [s for s in silences if abs(s - target) <= actual_snap and s > cuts[-1] + length * 0.5 and s < total - min_tail]
            if near:
                target = min(near, key=lambda s: abs(s - target))
        if target <= cuts[-1]:
            target = cuts[-1] + length
        cuts.append(target)
    if cuts[-1] < total:
        cuts.append(total)

    result = []
    for s, e in zip(cuts[:-1], cuts[1:]):
        if e > s:
            result.append((round(s, 2), round(e, 2)))
    return result


# ---------- Export & Rendering ----------
def export(src, start, dur, out, fit="crop", ass_file=None, logo_config=None):
    """Export vertical clip with framing template, burnt subtitles, and optional logo overlay.

    logo_config : dict with keys:
        path       — path to PNG logo file
        position   — one of: top_left top_center top_right mid_left center
                              mid_right bot_left bot_center bot_right
        size_pct   — logo width as % of video width  (1–50)
        opacity    — 0.0–1.0
        padding    — pixels from edge
    """
    has_ass = bool(ass_file and Path(ass_file).exists())
    has_logo = bool(
        logo_config
        and logo_config.get("path")
        and Path(str(logo_config["path"])).exists()
    )

    # ── ASS filter string ────────────────────────────────────────────────────
    ass_simple = ""   # used in simple -vf chains: ",ass='path'"
    ass_fc     = ""   # used as a filter_complex node: "ass='path'"
    if has_ass:
        sub_path = str(Path(ass_file).resolve()).replace("\\", "/").replace(":", "\\:")
        ass_simple = f",ass='{sub_path}'"
        ass_fc     = f"ass='{sub_path}'"

    # ── Logo filter components ────────────────────────────────────────────────
    logo_inputs = []
    logo_scale  = ""
    logo_xy     = ""
    if has_logo:
        lc       = logo_config
        pos      = lc.get("position", "top_right")
        size_pct = int(lc.get("size_pct", 15))
        opacity  = float(lc.get("opacity", 1.0))
        pad      = int(lc.get("padding", 30))
        pos_map  = {
            "top_left":   f"{pad}:{pad}",
            "top_center": f"(W-w)/2:{pad}",
            "top_right":  f"W-w-{pad}:{pad}",
            "mid_left":   f"{pad}:(H-h)/2",
            "center":     "(W-w)/2:(H-h)/2",
            "mid_right":  f"W-w-{pad}:(H-h)/2",
            "bot_left":   f"{pad}:H-h-{pad}",
            "bot_center": f"(W-w)/2:H-h-{pad}",
            "bot_right":  f"W-w-{pad}:H-h-{pad}",
        }
        logo_xy    = pos_map.get(pos, f"W-w-{pad}:{pad}")
        logo_inputs = ["-i", str(lc["path"])]
        logo_scale  = f"[1:v]scale=iw*{size_pct}/100:-1"
        if opacity < 1.0:
            logo_scale += f",format=rgba,colorchannelmixer=aa={opacity:.2f}"
        logo_scale += "[logo_sc]"

    def _post(stream, segs):
        """Append logo + ass filter segments after the main framing stream."""
        cur = stream
        if has_logo:
            segs.append(logo_scale)
            segs.append(f"{cur}[logo_sc]overlay={logo_xy}[after_logo]")
            cur = "[after_logo]"
        if has_ass:
            segs.append(f"{cur}{ass_fc}[vout]")
            cur = "[vout]"
        elif cur != "[vout]":
            segs.append(f"{cur}null[vout]")
            cur = "[vout]"
        return cur, segs

    # ══════════════════════════════════════════════════════════════════════════
    # FAST PATH — no logo: use simple -vf (original behaviour, maximum compat)
    # ══════════════════════════════════════════════════════════════════════════
    if not has_logo:
        if fit == "crop":
            vf = ["-vf",
                  f"crop=w='if(gt(a,9/16),ih*9/16,iw)':h='if(gt(a,9/16),ih,iw*16/9)',"
                  f"scale=1080:1920,setsar=1{ass_simple}"]
            map_a = []
        elif fit == "blur":
            vf = ["-filter_complex",
                  "[0:v]split[a][b];"
                  "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:5[bg];"
                  "[b]scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2[fg];"
                  f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1{ass_simple}[v]",
                  "-map", "[v]", "-map", "0:a?"]
            map_a = None
        elif fit == "split":
            vf = ["-filter_complex",
                  "[0:v]split[top][bot];"
                  "[top]crop=iw/2:ih:0:0,scale=1080:960:force_original_aspect_ratio=decrease,"
                  "pad=1080:960:(ow-iw)/2:(oh-ih)/2[t];"
                  "[bot]crop=iw/2:ih:iw/2:0,scale=1080:960:force_original_aspect_ratio=decrease,"
                  "pad=1080:960:(ow-iw)/2:(oh-ih)/2[b];"
                  f"[t][b]vstack,setsar=1{ass_simple}[v]",
                  "-map", "[v]", "-map", "0:a?"]
            map_a = None
        elif fit == "headline":
            vf = ["-filter_complex",
                  "[0:v]split[bg_in][fg_in];"
                  "[bg_in]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg];"
                  "[fg_in]scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2[fg];"
                  f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1{ass_simple}[v]",
                  "-map", "[v]", "-map", "0:a?"]
            map_a = None
        else:  # none
            vf    = (["-vf", ass_simple[1:]] if has_ass else [])
            map_a = []

        cmd = (["ffmpeg", "-y", "-loglevel", "error",
                "-ss", f"{start:.2f}", "-i", str(src), "-t", f"{dur:.2f}"]
               + vf + (map_a if map_a is not None else [])
               + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                  "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)])
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res.returncode != 0:
            err_msg = res.stderr.strip() or f"ffmpeg exited with code {res.returncode}"
            raise RuntimeError(f"FFmpeg export failed: {err_msg}")
        return

    # ══════════════════════════════════════════════════════════════════════════
    # FILTER_COMPLEX PATH — logo present (± ass)
    # ══════════════════════════════════════════════════════════════════════════
    segs = []
    if fit == "crop":
        segs.append(
            "[0:v]crop=w='if(gt(a,9/16),ih*9/16,iw)':h='if(gt(a,9/16),ih,iw*16/9)',"
            "scale=1080:1920,setsar=1[main_v]")
        last = "[main_v]"
    elif fit == "blur":
        segs += [
            "[0:v]split[__a][__b]",
            "[__a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:5[__bg]",
            "[__b]scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2[__fg]",
            "[__bg][__fg]overlay=(W-w)/2:(H-h)/2,setsar=1[main_v]",
        ]
        last = "[main_v]"
    elif fit == "split":
        segs += [
            "[0:v]split[__top][__bot]",
            "[__top]crop=iw/2:ih:0:0,scale=1080:960:force_original_aspect_ratio=decrease,"
            "pad=1080:960:(ow-iw)/2:(oh-ih)/2[__t]",
            "[__bot]crop=iw/2:ih:iw/2:0,scale=1080:960:force_original_aspect_ratio=decrease,"
            "pad=1080:960:(ow-iw)/2:(oh-ih)/2[__b]",
            "[__t][__b]vstack,setsar=1[main_v]",
        ]
        last = "[main_v]"
    elif fit == "headline":
        segs += [
            "[0:v]split[__bg_in][__fg_in]",
            "[__bg_in]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[__bg]",
            "[__fg_in]scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2[__fg]",
            "[__bg][__fg]overlay=(W-w)/2:(H-h)/2,setsar=1[main_v]",
        ]
        last = "[main_v]"
    else:  # none
        last = "[0:v]"

    final, segs = _post(last, segs)
    fc = ";".join(segs)

    cmd = (["ffmpeg", "-y", "-loglevel", "error",
            "-ss", f"{start:.2f}", "-i", str(src)]
           + logo_inputs + ["-t", f"{dur:.2f}",
           "-filter_complex", fc,
           "-map", final, "-map", "0:a?",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)])
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        err_msg = res.stderr.strip() or f"ffmpeg exited with code {res.returncode}"
        raise RuntimeError(f"FFmpeg export failed: {err_msg}")


def main():
    p = argparse.ArgumentParser(description="Shorts Clipper: Free YouTube Shorts & Podcast Clipper")
    p.add_argument("source", help="YouTube URL or local video file")
    p.add_argument("--length", type=float, default=45, help="target clip length in seconds (default 45)")
    p.add_argument("--max-clips", type=int, default=10, help="max number of clips to export")
    p.add_argument("--mode", choices=["smart", "podcast", "even"], default="smart",
                   help="smart=silence cuts+virality rank; podcast=dialogue cuts; even=equal chunks")
    p.add_argument("--fit", choices=["crop", "blur", "split", "headline", "none"], default="crop",
                   help="framing template: crop (9:16), blur (blurred bg), split (podcast top/bot), headline, none")
    _valid_styles = _style_keys() + ["none"]
    p.add_argument("--subtitle-style", choices=_valid_styles, metavar="STYLE",
                   default="tiktok_yellow",
                   help=f"caption style. Available: {', '.join(_valid_styles)}")
    p.add_argument("--caption-size", type=int, default=0, metavar="PX",
                   help="override caption font size in px (0 = use style default)")
    p.add_argument("--out", default="clips", help="output folder")
    # Logo / branding
    p.add_argument("--logo", metavar="PNG", default="",
                   help="path to PNG logo to burn into every clip")
    p.add_argument("--logo-position", default="top_right",
                   choices=["top_left","top_center","top_right","mid_left","center",
                            "mid_right","bot_left","bot_center","bot_right"],
                   help="logo position (default top_right)")
    p.add_argument("--logo-size", type=int, default=15, metavar="PCT",
                   help="logo width as %% of video width (default 15)")
    p.add_argument("--logo-opacity", type=float, default=1.0, metavar="0-1",
                   help="logo opacity 0.0–1.0 (default 1.0)")
    p.add_argument("--logo-padding", type=int, default=30, metavar="PX",
                   help="logo distance from edge in px (default 30)")
    a = p.parse_args()

    need("ffmpeg"); need("ffprobe")
    out_dir = Path(a.out); out_dir.mkdir(parents=True, exist_ok=True)

    source_path = Path(a.source)
    try:
        is_local = source_path.exists()
    except (OSError, ValueError):
        is_local = False

    if is_local:
        src = source_path
    else:
        src = download(a.source, out_dir)

    total = duration(src)
    print(f"🎬 Video length: {total / 60:.1f} min ({total:.0f}s)")

    # Build logo config (CLI args override branding.py defaults)
    logo_config = None
    logo_path = a.logo.strip()
    if not logo_path:
        # Try branding.py as fallback
        try:
            import branding as _br
            if _br.is_enabled():
                logo_config = _br.get_config()
                print(f"🖼️  Logo from branding.py: {logo_config['path']}")
        except ImportError:
            pass
    elif Path(logo_path).exists():
        logo_config = {
            "path":     logo_path,
            "position": a.logo_position,
            "size_pct": a.logo_size,
            "opacity":  a.logo_opacity,
            "padding":  a.logo_padding,
        }
        print(f"🖼️  Logo: {logo_path}")
    else:
        print(f"⚠️  Logo file not found: {logo_path}")

    # Subtitle discovery & direct speech transcription
    captions = get_captions(src, out_dir) if a.subtitle_style != "none" else []
    if captions:
        print(f"💬 Ready to burn {len(captions)} caption bursts directly into output videos.")
    else:
        print("💬 No speech or subtitles detected.")

    # Silence detection
    silence_dur = 0.6 if a.mode == "podcast" else 0.4
    silences = find_silences(src, dur=silence_dur) if a.mode != "even" else []
    segments = plan_cuts(total, a.length, snap=6, silences=silences, mode=a.mode)

    # Score segments for Virality
    print("\n🔥 Calculating Virality Scores & Pacing...")
    scored_clips = []
    for s, e in segments:
        v_info = calculate_virality_score(src, s, e, total, silences, captions)
        scored_clips.append((v_info["score"], s, e, v_info))

    if a.mode != "even":
        scored_clips.sort(key=lambda x: x[0], reverse=True)
        selected = scored_clips[:a.max_clips]
        selected.sort(key=lambda x: x[1])
    else:
        selected = scored_clips[:a.max_clips]

    # Export clips
    report = []
    print(f"\n🚀 Exporting top {len(selected)} clips with template '{a.fit}'...\n")
    for i, (score, s, e, v_info) in enumerate(selected, 1):
        out_name = f"short_{i:02d}_viral{score}.mp4"
        out_clip = out_dir / out_name

        ass_file = None
        if a.subtitle_style != "none" and captions:
            ass_path = out_dir / f"temp_{i}.ass"
            ass_file = generate_ass(captions, s, e, a.subtitle_style, ass_path,
                                    size_override=a.caption_size or None)

        print(f"[{i}/{len(selected)}] {s:6.1f}s -> {e:6.1f}s ({e-s:.0f}s) | "
              f"Score: {score}/100 {v_info['tier']} | {out_name}")
        export(src, s, e - s, out_clip, fit=a.fit,
               ass_file=ass_file, logo_config=logo_config)

        if ass_file and Path(ass_file).exists():
            try:
                Path(ass_file).unlink()
            except OSError:
                pass

        report.append({
            "clip":           out_name,
            "start_time":     s,
            "end_time":       e,
            "duration":       round(e - s, 2),
            "virality_score": score,
            "tier":           v_info["tier"],
            "hook_score":     v_info["hook"],
            "energy_score":   v_info["energy"],
            "pacing_score":   v_info["pacing"],
            "duration_score": v_info["duration"],
        })

    # Save summary report
    report_file = out_dir / "virality_report.json"
    report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\n✅ All clips exported to: {out_dir.resolve()}")
    print(f"📊 Virality report saved to: {report_file.resolve()}\n")


if __name__ == "__main__":
    main()
