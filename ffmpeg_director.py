"""FFmpeg AI Director Execution Engine for YouTube Shorts.

Executes AI-generated director plans:
- Intelligent cuts and jump cut pause removal.
- Punch-in zooms (1.1x - 1.25x) centered on speaker.
- Dynamic 9:16 reframing.
- ASS subtitle generation with dynamic keyword highlighting.
- Broadcast loudness audio normalization (EBU R128 loudnorm target -14 LUFS).
- Logo / Watermark integration.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import caption_styles

logger = logging.getLogger("ffmpeg_director")


def format_ass_time(sec: float) -> str:
    """Format seconds into ASS timestamp format H:MM:SS.cs."""
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = int(round((sec - int(sec)) * 100))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def highlight_keywords_in_text(
    text: str,
    keywords: List[str],
    highlight_color: str = "&H0000FFFF",
    primary_color: str = "&H00FFFFFF",
) -> str:
    """Wrap target keywords in ASS color overrides for high-retention keyword pops."""
    if not keywords or not text:
        return text

    words = text.split()
    processed_words = []
    # Normalize keywords for case-insensitive lookup
    clean_kws = {re.sub(r"[^\w]", "", k.upper()): k for k in keywords if k}

    # Format colors with trailing & for ASS inline \c tags
    h_col = highlight_color if highlight_color.endswith("&") else f"{highlight_color}&"
    p_col = primary_color if primary_color.endswith("&") else f"{primary_color}&"

    for w in words:
        clean_w = re.sub(r"[^\w]", "", w.upper())
        if clean_w in clean_kws and len(clean_w) > 2:
            # Highlight keyword and restore primary color without wiping styles
            processed_words.append(f"{{\\c{h_col}\\b1}}{w}{{\\c{p_col}\\b0}}")
        else:
            processed_words.append(w)

    return " ".join(processed_words)


def generate_director_ass(
    captions: List[Dict[str, Any]],
    clip_start: float,
    clip_end: float,
    style_key: str,
    highlight_keywords: List[str],
    out_ass_path: Path,
    size_override: Optional[int] = None,
    cuts: Optional[List[Dict[str, Any]]] = None,
    karaoke: bool = True,
    margin_v_override: Optional[int] = None,
    alignment_override: Optional[int] = None,
) -> Path:
    """Generate ASS subtitle file with keyword highlighting and dynamic karaoke timing."""
    style_def = caption_styles.get_style(style_key)
    clip_dur = clip_end - clip_start

    ass_style_name = re.sub(r"[^A-Za-z0-9_]", "", style_def.get("display_name", style_key)) or style_key

    font = style_def.get("font", "Arial")
    size = int(size_override) if size_override and int(size_override) > 0 else style_def.get("size", 60)
    bold = style_def.get("bold", -1)
    italic = style_def.get("italic", 0)
    underline = style_def.get("underline", 0)
    primary = style_def.get("primary", "&H0000FFFF")
    secondary = style_def.get("secondary", "&H00FFFFFF")
    # For karaoke mode, ensure secondary is a clean pre-highlight color (white/silver)
    if secondary == "&H000000FF":
        secondary = "&H00FFFFFF"

    outline_color = style_def.get("outline_color", "&H00000000")
    back_color = style_def.get("back_color", "&H80000000")
    border_style = style_def.get("border_style", 1)
    outline = style_def.get("outline", 4)
    shadow = style_def.get("shadow", 2)
    alignment = int(alignment_override) if alignment_override is not None else style_def.get("alignment", 2)
    margin_v = int(margin_v_override) if margin_v_override is not None and int(margin_v_override) > 0 else style_def.get("margin_v", 300)
    scale_x = style_def.get("scale_x", 100)
    scale_y = style_def.get("scale_y", 100)
    spacing = style_def.get("letter_spacing", 0)

    # Accent color for highlighted keywords
    accent_color = style_def.get("accent_color", "&H0000FFFF")
    if accent_color == primary:
        accent_color = "&H0033FF33"  # Vibrant Neon Green pop if primary is already yellow

    # Map captions to timeline (supports contiguous camera zooms and jump cuts)
    rel_caps = []
    if cuts:
        is_contiguous = True
        for i in range(1, len(cuts)):
            if abs(float(cuts[i]["start"]) - float(cuts[i - 1]["end"])) > 0.15:
                is_contiguous = False
                break

        if is_contiguous:
            for c in captions:
                if c["end"] > clip_start and c["start"] < clip_end:
                    s = max(0.0, c["start"] - clip_start)
                    e = min(clip_dur, c["end"] - clip_start)
                    if e > s:
                        # Shift word timings
                        w_rel = []
                        for w in c.get("words", []):
                            ws = max(0.0, w["start"] - clip_start)
                            we = min(clip_dur, w["end"] - clip_start)
                            if we > ws:
                                w_rel.append({"start": ws, "end": we, "text": w["text"]})
                        rel_caps.append({
                            "start": s,
                            "end": e,
                            "text": c["text"],
                            "words": w_rel,
                        })
        else:
            out_t = 0.0
            for cut in cuts:
                cs = float(cut["start"])
                ce = float(cut["end"])
                cdur = ce - cs
                for c in captions:
                    if c["end"] > cs and c["start"] < ce:
                        s_rel = max(0.0, c["start"] - cs)
                        e_rel = min(cdur, c["end"] - cs)
                        if e_rel > s_rel:
                            w_rel = []
                            for w in c.get("words", []):
                                if w["end"] > cs and w["start"] < ce:
                                    ws = max(0.0, w["start"] - cs)
                                    we = min(cdur, w["end"] - cs)
                                    if we > ws:
                                        w_rel.append({"start": out_t + ws, "end": out_t + we, "text": w["text"]})
                            rel_caps.append({
                                "start": out_t + s_rel,
                                "end": out_t + e_rel,
                                "text": c["text"],
                                "words": w_rel,
                            })
                out_t += cdur
    else:
        for c in captions:
            if c["end"] > clip_start and c["start"] < clip_end:
                s = max(0.0, c["start"] - clip_start)
                e = min(clip_dur, c["end"] - clip_start)
                if e > s:
                    w_rel = []
                    for w in c.get("words", []):
                        ws = max(0.0, w["start"] - clip_start)
                        we = min(clip_dur, w["end"] - clip_start)
                        if we > ws:
                            w_rel.append({"start": ws, "end": we, "text": w["text"]})
                    rel_caps.append({"start": s, "end": e, "text": c["text"], "words": w_rel})

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

    clean_kws = {re.sub(r"[^\w]", "", k.upper()): k for k in highlight_keywords if k}
    h_col = accent_color if accent_color.endswith("&") else f"{accent_color}&"
    p_col = primary if primary.endswith("&") else f"{primary}&"

    for c in rel_caps:
        st = format_ass_time(c["start"])
        et = format_ass_time(c["end"])

        if karaoke:
            words = c.get("words")
            if not words:
                raw_w = str(c.get("text", "")).split()
                if raw_w:
                    dur_w = (c["end"] - c["start"]) / len(raw_w)
                    cw_t = c["start"]
                    words = []
                    for rw in raw_w:
                        words.append({"start": cw_t, "end": cw_t + dur_w, "text": rw})
                        cw_t += dur_w

            k_parts = []
            cur_t = c["start"]
            for i, w in enumerate(words or []):
                ws = max(c["start"], min(c["end"], float(w.get("start", cur_t))))
                if ws > cur_t + 0.04:
                    gap_cs = max(1, int((ws - cur_t) * 100))
                    k_parts.append(f"{{\\k{gap_cs}}}")
                    cur_t = ws
                if i < len(words) - 1:
                    nxt = max(ws, min(c["end"], float(words[i + 1].get("start", ws + 0.3))))
                    dur = max(0.08, nxt - ws)
                else:
                    dur = max(0.08, c["end"] - ws)
                dur_cs = max(5, int(dur * 100))
                wt = str(w.get("text", "")).strip()
                clean_w = re.sub(r"[^\w]", "", wt.upper())

                # If word is in highlighted keywords, apply accent color pop
                if clean_w in clean_kws and len(clean_w) > 2:
                    k_parts.append(f"{{\\c{h_col}\\b1}}{{\\kf{dur_cs}}}{wt}{{\\c{p_col}\\b0}} ")
                else:
                    k_parts.append(f"{{\\kf{dur_cs}}}{wt} ")
                cur_t = ws + dur

            txt = "".join(k_parts).strip()
            if not txt:
                txt = c["text"]
            lines.append(f"Dialogue: 0,{st},{et},{ass_style_name},,0,0,0,,{{\\fad(40,40)}}{txt}")
        else:
            txt = c["text"].replace("\n", " ")
            txt = highlight_keywords_in_text(txt, highlight_keywords, highlight_color=accent_color, primary_color=primary)
            lines.append(f"Dialogue: 0,{st},{et},{ass_style_name},,0,0,0,,{{\\fad(70,70)}}{txt}")

    out_ass_path.write_text("\n".join(lines), encoding="utf-8")
    return out_ass_path

    out_ass_path.write_text("\n".join(lines), encoding="utf-8")
    return out_ass_path


def render_subsegment(
    src_video: Path,
    start: float,
    duration: float,
    out_segment: Path,
    zoom: float = 1.0,
    fit: str = "crop",
) -> None:
    """Render a single subsegment with proper 9:16 framing and punch-in zoom."""
    # Base 9:16 crop filter
    if fit == "crop":
        base_v = "crop=w='if(gt(a,9/16),ih*9/16,iw)':h='if(gt(a,9/16),ih,iw*16/9)',scale=1080:1920,setsar=1"
    elif fit == "blur":
        base_v = (
            "split[bg][fg];"
            "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:5[bg_b];"
            "[fg]scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2[fg_s];"
            "[bg_b][fg_s]overlay=(W-w)/2:(H-h)/2,setsar=1"
        )
    else:
        base_v = "crop=w='if(gt(a,9/16),ih*9/16,iw)':h='if(gt(a,9/16),ih,iw*16/9)',scale=1080:1920,setsar=1"

    # Add punch-in zoom if zoom > 1.01
    zoom = max(1.0, min(1.30, float(zoom)))
    if zoom > 1.01:
        zw = int(1080 / zoom)
        zh = int(1920 / zoom)
        zoom_filter = f",crop={zw}:{zh}:(1080-{zw})/2:(1920-{zh})/2,scale=1080:1920"
        vf = base_v + zoom_filter
    else:
        vf = base_v

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{start:.2f}",
        "-i", str(src_video),
        "-t", f"{duration:.2f}",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-c:a", "aac", "-b:a", "192k",
        "-ar", "48000",
        "-movflags", "+faststart",
        str(out_segment)
    ]

    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg subsegment render failed: {res.stderr.strip()}")


def concatenate_and_finalize_clip(
    segment_files: List[Path],
    out_final: Path,
    ass_file: Optional[Path] = None,
    logo_config: Optional[Dict[str, Any]] = None,
    normalize_audio: bool = True,
    temp_dir: Optional[Path] = None,
) -> None:
    """Concatenate sub-segments, burn subtitles, apply logo, and normalize loudness."""
    t_dir = temp_dir or out_final.parent

    # 1. Concat file list
    concat_txt = t_dir / f"concat_list_{out_final.stem}.txt"
    lines = [f"file '{str(p.resolve()).replace('\\', '/')}'" for p in segment_files]
    concat_txt.write_text("\n".join(lines), encoding="utf-8")

    # 2. Build filters for subtitles and logo
    filter_chains = []

    has_logo = bool(
        logo_config
        and logo_config.get("path")
        and Path(str(logo_config["path"])).exists()
    )
    has_ass = bool(ass_file and Path(ass_file).exists())

    logo_inputs = []
    if has_logo:
        lc = logo_config
        pos = lc.get("position", "top_right")
        size_pct = int(lc.get("size_pct", 15))
        opacity = float(lc.get("opacity", 1.0))
        pad = int(lc.get("padding", 30))
        pos_map = {
            "top_left": f"{pad}:{pad}",
            "top_center": f"(W-w)/2:{pad}",
            "top_right": f"W-w-{pad}:{pad}",
            "mid_left": f"{pad}:(H-h)/2",
            "center": "(W-w)/2:(H-h)/2",
            "mid_right": f"W-w-{pad}:(H-h)/2",
            "bot_left": f"{pad}:H-h-{pad}",
            "bot_center": f"(W-w)/2:H-h-{pad}",
            "bot_right": f"W-w-{pad}:H-h-{pad}",
        }
        logo_xy = pos_map.get(pos, f"W-w-{pad}:{pad}")
        logo_inputs = ["-i", str(lc["path"])]

    # 3. Formulate filter string
    post_vf = []
    if has_ass:
        sub_path = str(Path(ass_file).resolve()).replace("\\", "/").replace(":", "\\\\:")
        post_vf.append(f"ass={sub_path}")

    audio_filters = []
    if normalize_audio:
        audio_filters.append("loudnorm=I=-14:LRA=7:TP=-1.5")

    # Fast path: If single segment and no concat needed
    input_args = ["-f", "concat", "-safe", "0", "-i", str(concat_txt)]
    if has_logo:
        input_args += logo_inputs
        logo_scale = f"[1:v]scale=iw*{size_pct}/100:-1"
        if opacity < 1.0:
            logo_scale += f",format=rgba,colorchannelmixer=aa={opacity:.2f}"
        logo_scale += "[logo_sc]"
        fc = f"{logo_scale};[0:v][logo_sc]overlay={logo_xy}"
        if has_ass:
            fc += f",ass={sub_path}"
        fc += "[vout]"
        filter_args = ["-filter_complex", fc, "-map", "[vout]", "-map", "0:a"]
    elif post_vf:
        filter_args = ["-vf", ",".join(post_vf)]
    else:
        filter_args = []

    af_args = ["-af", ",".join(audio_filters)] if audio_filters else []

    cmd = (
        ["ffmpeg", "-y", "-loglevel", "error"]
        + input_args
        + filter_args
        + af_args
        + [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(out_final)
        ]
    )

    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")

    # Clean up concat txt
    try:
        if concat_txt.exists():
            concat_txt.unlink()
    except Exception:
        pass

    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg finalization failed: {res.stderr.strip()}")


def execute_director_clip(
    src_video: Path,
    plan: Any,  # ClipPlan
    out_clip: Path,
    captions: List[Dict[str, Any]],
    caption_style: str = "tiktok_yellow",
    caption_size: Optional[int] = None,
    karaoke: bool = True,
    caption_margin_v: Optional[int] = None,
    caption_alignment: Optional[int] = None,
    logo_config: Optional[Dict[str, Any]] = None,
    fit: str = "crop",
    work_dir: Optional[Path] = None,
    log_fn=print,
) -> Path:
    """Execute full AI director plan for a single clip."""
    w_dir = work_dir or out_clip.parent
    temp_clip_dir = w_dir / f"temp_render_clip_{plan.clip_id}"
    temp_clip_dir.mkdir(parents=True, exist_ok=True)

    cuts = plan.cuts
    if not cuts:
        cuts = [{"start": plan.start_time, "end": plan.end_time, "zoom": 1.0, "focus": "speaker"}]

    if log_fn:
        log_fn(f"🎬 Executing Director Plan for Clip #{plan.clip_id}: '{plan.title}' ({len(cuts)} cuts/zooms)")

    # 1. Render each subsegment
    segment_files: List[Path] = []
    for idx, cut in enumerate(cuts, 1):
        c_start = float(cut["start"])
        c_end = float(cut["end"])
        c_dur = max(0.2, c_end - c_start)
        c_zoom = float(cut.get("zoom", 1.0))

        seg_file = temp_clip_dir / f"seg_{idx:02d}_z{c_zoom:.2f}.mp4"
        render_subsegment(
            src_video=src_video,
            start=c_start,
            duration=c_dur,
            out_segment=seg_file,
            zoom=c_zoom,
            fit=fit,
        )
        if seg_file.exists() and seg_file.stat().st_size > 1000:
            segment_files.append(seg_file)

    if not segment_files:
        raise RuntimeError("No video segments could be rendered for this clip.")

    # 2. Generate synchronized captions with highlighted keywords and dynamic karaoke
    ass_file = None
    if caption_style != "none" and captions:
        ass_path = temp_clip_dir / "captions.ass"
        ass_file = generate_director_ass(
            captions=captions,
            clip_start=plan.start_time,
            clip_end=plan.end_time,
            style_key=caption_style,
            highlight_keywords=plan.highlight_keywords,
            out_ass_path=ass_path,
            size_override=caption_size,
            cuts=cuts,
            karaoke=karaoke,
            margin_v_override=caption_margin_v,
            alignment_override=caption_alignment,
        )

    # 3. Concatenate segments, burn captions, apply logo, and normalize audio
    concatenate_and_finalize_clip(
        segment_files=segment_files,
        out_final=out_clip,
        ass_file=ass_file,
        logo_config=logo_config,
        normalize_audio=plan.audio.get("normalize", True),
        temp_dir=temp_clip_dir,
    )

    # 4. Clean up temporary segment directory
    try:
        shutil.rmtree(temp_clip_dir, ignore_errors=True)
    except Exception:
        pass

    return out_clip
