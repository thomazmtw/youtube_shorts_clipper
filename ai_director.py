"""AI Editing Director for Hybrid Video Clipper.

Acts as an automated video editing director combining:
- Local dialogue transcription (faster-whisper) with sentence boundaries.
- Visual event analysis (Google Gemini).
- Local cognitive reasoning & director planning (Ollama).
- Specialized editing style rules.
- Structured JSON output with strict schema validation and fallback recovery.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import gemini_client
import ollama_client

logger = logging.getLogger("ai_director")

# ═════════════════════════════════════════════════════════════════════════════
# Editing Style Specifications
# ═════════════════════════════════════════════════════════════════════════════

EDITING_STYLES = {
    "viral_podcast": {
        "name": "Viral Podcast Style",
        "description": "Fast cuts, punch-in zooms on punchlines, speaker focus, tight pause trimming.",
        "target_duration": (25, 45),
        "hook_window": 2.5,
        "zoom_punch_factor": 1.16,
        "pause_trim_threshold": 0.45,
        "bgm_style": "lofi_ambient_podcast",
    },
    "cinematic": {
        "name": "Cinematic Style",
        "description": "Smooth pacing, dramatic moments, subtle zooms, preserving dramatic pauses.",
        "target_duration": (35, 55),
        "hook_window": 4.0,
        "zoom_punch_factor": 1.08,
        "pause_trim_threshold": 0.90,
        "bgm_style": "cinematic_drone",
    },
    "fast_viral": {
        "name": "Fast Viral Shorts",
        "description": "Ultra-fast hook (<1.5s), rapid cuts every 2-4s, punch-in zooms on high energy words.",
        "target_duration": (20, 35),
        "hook_window": 1.5,
        "zoom_punch_factor": 1.20,
        "pause_trim_threshold": 0.35,
        "bgm_style": "upbeat_trap_beat",
    },
    "educational": {
        "name": "Educational Style",
        "description": "Clear explanations, readable captions, structured chaptering, stable framing.",
        "target_duration": (30, 50),
        "hook_window": 3.0,
        "zoom_punch_factor": 1.10,
        "pause_trim_threshold": 0.60,
        "bgm_style": "minimal_acoustic",
    },
    "storytelling": {
        "name": "Storytelling Style",
        "description": "Emotional pacing, narrative continuity, meaningful scene progression.",
        "target_duration": (35, 60),
        "hook_window": 3.0,
        "zoom_punch_factor": 1.12,
        "pause_trim_threshold": 0.70,
        "bgm_style": "warm_piano_story",
    },
}


# ═════════════════════════════════════════════════════════════════════════════
# Data Classes
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class CutSegment:
    start: float
    end: float
    zoom: float = 1.0  # 1.0 = standard 9:16 crop, 1.15 = punch-in zoom
    focus: str = "speaker"


@dataclass
class Transition:
    time: float
    type: str = "jump_cut"  # jump_cut, cut, crossfade
    duration: float = 0.0


@dataclass
class ClipPlan:
    clip_id: int
    title: str
    hook: str
    start_time: float
    end_time: float
    duration: float
    virality_score: int
    reasoning: str
    editing_style: str
    cuts: List[Dict[str, Any]] = field(default_factory=list)
    transitions: List[Dict[str, Any]] = field(default_factory=list)
    highlight_keywords: List[str] = field(default_factory=list)
    audio: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ═════════════════════════════════════════════════════════════════════════════
# Prompt Builder
# ═════════════════════════════════════════════════════════════════════════════

def _format_transcript_summary(transcript_entries: List[Dict[str, Any]], max_chars: int = 12000) -> str:
    """Format transcript segments with timestamps for LLM ingestion."""
    lines = []
    total_len = 0
    for e in transcript_entries:
        s = e.get("start", 0.0)
        e_time = e.get("end", 0.0)
        txt = e.get("text", "").strip()
        line = f"[{s:.1f}s - {e_time:.1f}s] {txt}"
        total_len += len(line) + 1
        lines.append(line)
        if total_len > max_chars:
            lines.append("... (transcript truncated for length)")
            break
    return "\n".join(lines)


def _format_visual_events_summary(visual_events: List[Dict[str, Any]]) -> str:
    """Format Gemini visual observations for Ollama ingestion."""
    if not visual_events:
        return "None available (Audio/transcript based directing)."
    lines = []
    for ev in visual_events:
        ts = ev.get("timestamp", 0.0)
        pos = ev.get("speaker_pos", "center")
        expr = ev.get("action_or_expression", "")
        interest = ev.get("visual_interest", 5)
        zoom = "Zoom recommended" if ev.get("zoom_recommended") else "Normal framing"
        hook = " [VISUAL HOOK]" if ev.get("is_hook") else ""
        lines.append(f"At {ts:.1f}s: Position={pos}, Score={interest}/10, {expr}, {zoom}{hook}")
    return "\n".join(lines)


def build_director_prompt(
    transcript_entries: List[Dict[str, Any]],
    visual_events: List[Dict[str, Any]],
    style_key: str,
    target_duration: float,
    max_clips: int,
    video_duration: float,
) -> str:
    """Construct a rigorous prompt for the AI Video Director."""
    style_info = EDITING_STYLES.get(style_key, EDITING_STYLES["viral_podcast"])
    transcript_txt = _format_transcript_summary(transcript_entries)
    visual_txt = _format_visual_events_summary(visual_events)

    min_dur = max(15.0, target_duration - 10.0)
    max_dur = min(60.0, target_duration + 10.0)

    prompt = f"""You are the Master AI Video Editor and Director for YouTube Shorts.
Your mission is to transform this long video footage into {max_clips} viral, high-retention YouTube Shorts.

EDITING STYLE: {style_info['name']}
Style Rules:
- {style_info['description']}
- Target clip duration: {min_dur:.0f}s to {max_dur:.0f}s (Hard limit: Never exceed 60 seconds).
- Hook window: First {style_info['hook_window']} seconds must grip the audience immediately.
- Punch-in zoom level: {style_info['zoom_punch_factor']}x zoom on emotional peaks, key revelations, or punchlines.

TOTAL VIDEO DURATION: {video_duration:.1f} seconds.

DIALOGUE TRANSCRIPT WITH TIMESTAMPS:
{transcript_txt}

OPTIONAL VISUAL UNDERSTANDING (FROM GEMINI):
{visual_txt}

CRITICAL DIRECTING DIRECTIVES:
1. SENTENCE INTEGRITY: Never cut a speaker mid-sentence! Start at the beginning of a complete thought and end cleanly after a concluding sentence.
2. COMPELLING HOOK: Clip 0-3 seconds must be an irresistible question, bold statement, or high-energy moment.
3. REMOVE BORING GAPS: Identify awkward pauses, repetitive phrases, and dead air.
4. PUNCH-IN ZOOMS: For each clip, plan 2 to 4 camera cuts. Alternate between normal 1.0x framing and {style_info['zoom_punch_factor']}x punch-in zoom during key emphasis words.
5. KEYWORDS: Choose 3 to 6 high-impact words per clip (e.g. "SECRET", "MILLION", "MISTAKE", "WHY") to highlight dynamically in the captions.

OUTPUT FORMAT:
Respond with ONLY a JSON object conforming strictly to this schema:
{{
  "clips": [
    {{
      "clip_id": 1,
      "title": "Short Catchy YouTube Shorts Title",
      "hook": "Description of the hook in the first 2 seconds",
      "start_time": float (e.g. 14.5),
      "end_time": float (e.g. 46.2),
      "duration": float (end_time - start_time),
      "virality_score": integer (70 to 99),
      "reasoning": "Why this moment will retain viewers and generate engagement",
      "editing_style": "{style_key}",
      "cuts": [
        {{"start": 14.5, "end": 22.0, "zoom": 1.0, "focus": "speaker"}},
        {{"start": 22.0, "end": 28.5, "zoom": {style_info['zoom_punch_factor']}, "focus": "speaker"}},
        {{"start": 28.5, "end": 46.2, "zoom": 1.0, "focus": "speaker"}}
      ],
      "transitions": [
        {{"time": 22.0, "type": "jump_cut", "duration": 0.0}}
      ],
      "highlight_keywords": ["WORD1", "WORD2", "WORD3"],
      "audio": {{
        "normalize": true,
        "bgm_recommendation": "{style_info['bgm_style']}",
        "sfx_recommendations": [{{"time": 15.0, "sound": "whoosh"}}]
      }}
    }}
  ]
}}
"""
    return prompt


# ═════════════════════════════════════════════════════════════════════════════
# Fallback Rule-Based Director (100% Offline Guaranteed)
# ═════════════════════════════════════════════════════════════════════════════

def plan_clips_rule_based(
    transcript_entries: List[Dict[str, Any]],
    video_duration: float,
    silences: List[float],
    target_duration: float,
    max_clips: int,
    style_key: str = "viral_podcast",
) -> List[ClipPlan]:
    """Reliable sentence-boundary aware rule-based director when AI models are unavailable."""
    style_info = EDITING_STYLES.get(style_key, EDITING_STYLES["viral_podcast"])
    zoom_val = style_info["zoom_punch_factor"]

    # If no transcript, use silence-based slicing
    if not transcript_entries:
        cuts = []
        cur = 0.0
        while cur + target_duration < video_duration:
            cuts.append((cur, min(video_duration, cur + target_duration)))
            cur += target_duration
        plans = []
        for idx, (s, e) in enumerate(cuts[:max_clips], 1):
            dur = e - s
            mid = s + dur * 0.4
            plans.append(ClipPlan(
                clip_id=idx,
                title=f"Viral Short #{idx}",
                hook="Opening scene hook",
                start_time=round(s, 2),
                end_time=round(e, 2),
                duration=round(dur, 2),
                virality_score=75,
                reasoning="Energy-optimized silence-based cut",
                editing_style=style_key,
                cuts=[
                    {"start": round(s, 2), "end": round(mid, 2), "zoom": 1.0, "focus": "speaker"},
                    {"start": round(mid, 2), "end": round(e, 2), "zoom": zoom_val, "focus": "speaker"},
                ],
                highlight_keywords=["WATCH", "MOMENT", "CLIP"],
                audio={"normalize": True, "bgm_recommendation": style_info["bgm_style"]},
            ))
        return plans

    # Sentence boundary grouping
    min_dur = max(18.0, target_duration - 10.0)
    max_dur = min(58.0, target_duration + 8.0)

    candidate_windows: List[Tuple[int, int, float, float, str]] = []
    n_entries = len(transcript_entries)

    for i in range(n_entries):
        s_time = transcript_entries[i]["start"]
        cur_text = []
        for j in range(i, n_entries):
            e_time = transcript_entries[j]["end"]
            dur = e_time - s_time
            cur_text.append(transcript_entries[j]["text"])
            if min_dur <= dur <= max_dur:
                combined_txt = " ".join(cur_text)
                candidate_windows.append((i, j, s_time, e_time, combined_txt))
            elif dur > max_dur:
                break

    if not candidate_windows:
        # Fallback to simple windowing
        s_time = transcript_entries[0]["start"]
        e_time = min(video_duration, s_time + target_duration)
        candidate_windows.append((0, min(5, n_entries - 1), s_time, e_time, "Sample clip"))

    # Score windows based on hook words, questions, and duration
    viral_words = {
        "how", "why", "secret", "never", "best", "truth", "crazy", "listen",
        "stop", "what", "mistake", "money", "rule", "insane", "million", "watch"
    }

    scored_windows = []
    for (i, j, s, e, text) in candidate_windows:
        text_lower = text.lower()
        score = 65
        # Hook bonus in opening 10 words
        opening_words = text_lower.split()[:10]
        if any(w in viral_words for w in opening_words) or "?" in text[:40] or "!" in text[:40]:
            score += 18
        if any(w in text_lower for w in viral_words):
            score += 8
        dur = e - s
        if 25.0 <= dur <= 45.0:
            score += 9
        scored_windows.append((score, s, e, text))

    scored_windows.sort(key=lambda x: x[0], reverse=True)

    # Select non-overlapping top windows
    selected: List[Tuple[int, float, float, str]] = []
    for sc, s, e, txt in scored_windows:
        # Check overlap with existing selected
        overlap = False
        for _, ex_s, ex_e, _ in selected:
            if not (e <= ex_s + 5.0 or s >= ex_e - 5.0):
                overlap = True
                break
        if not overlap:
            selected.append((sc, s, e, txt))
            if len(selected) >= max_clips:
                break

    # Sort chronologically
    selected.sort(key=lambda x: x[1])

    plans: List[ClipPlan] = []
    for idx, (score, s, e, txt) in enumerate(selected, 1):
        dur = e - s
        words = [w.strip(".,!?\"'") for w in txt.split() if len(w) > 4]
        high_keys = [w.upper() for w in words[:4]] if words else ["HIGHLIGHT"]

        # Build punch-in sub-cuts
        mid1 = s + dur * 0.35
        mid2 = s + dur * 0.70
        cuts = [
            {"start": round(s, 2), "end": round(mid1, 2), "zoom": 1.0, "focus": "speaker"},
            {"start": round(mid1, 2), "end": round(mid2, 2), "zoom": zoom_val, "focus": "speaker"},
            {"start": round(mid2, 2), "end": round(e, 2), "zoom": 1.0, "focus": "speaker"},
        ]
        hook_preview = txt[:50] + "..." if len(txt) > 50 else txt
        plans.append(ClipPlan(
            clip_id=idx,
            title=f"Viral Short #{idx}: {high_keys[0].title() if high_keys else 'Key Moment'}",
            hook=hook_preview,
            start_time=round(s, 2),
            end_time=round(e, 2),
            duration=round(dur, 2),
            virality_score=min(98, score),
            reasoning="Dialogue-complete sentence boundary with strong keyword concentration",
            editing_style=style_key,
            cuts=cuts,
            highlight_keywords=high_keys,
            audio={"normalize": True, "bgm_recommendation": style_info["bgm_style"]},
        ))

    return plans


# ═════════════════════════════════════════════════════════════════════════════
# Validation and Execution
# ═════════════════════════════════════════════════════════════════════════════

def validate_and_sanitize_plans(
    raw_clips: List[Dict[str, Any]],
    video_duration: float,
    max_clips: int,
    style_key: str,
) -> List[ClipPlan]:
    """Ensure generated JSON conforms strictly to duration bounds and valid timestamps."""
    style_info = EDITING_STYLES.get(style_key, EDITING_STYLES["viral_podcast"])
    zoom_val = style_info["zoom_punch_factor"]

    valid_plans: List[ClipPlan] = []
    for idx, c in enumerate(raw_clips[:max_clips], 1):
        try:
            s = float(c.get("start_time", 0.0))
            e = float(c.get("end_time", 0.0))
            if s < 0:
                s = 0.0
            if e > video_duration:
                e = video_duration
            if e <= s + 5.0:
                continue

            dur = round(e - s, 2)
            if dur > 60.0:  # Clamp to YouTube Shorts 60s hard ceiling
                e = s + 59.5
                dur = round(e - s, 2)

            title = str(c.get("title", f"AI Short #{idx}")).strip()
            hook = str(c.get("hook", "Engaging hook")).strip()
            score = int(c.get("virality_score", 85))
            score = max(50, min(99, score))
            reasoning = str(c.get("reasoning", "Engaging conversation")).strip()

            # Sanitize cuts
            cuts_raw = c.get("cuts", [])
            sanitized_cuts = []
            if cuts_raw and isinstance(cuts_raw, list):
                for cut in cuts_raw:
                    cs = float(cut.get("start", s))
                    ce = float(cut.get("end", e))
                    # If LLM returned relative timestamps (e.g. 0.0 to 12.0 instead of s to s+12)
                    if ce <= dur and s > 0 and cs < s:
                        cs = s + cs
                        ce = s + ce
                    # Clamp strictly within [s, e]
                    cs = max(s, min(e, cs))
                    ce = max(s, min(e, ce))
                    cz = float(cut.get("zoom", 1.0))
                    # Clamp zoom to sensible range (1.0 to 1.30 max to avoid distortion)
                    cz = max(1.0, min(1.30, cz))
                    if ce > cs:
                        sanitized_cuts.append({
                            "start": round(cs, 2),
                            "end": round(ce, 2),
                            "zoom": round(cz, 2),
                            "focus": cut.get("focus", "speaker")
                        })
            if not sanitized_cuts:
                # Default cut schedule: wide -> punch-in -> wide
                mid = s + dur * 0.45
                sanitized_cuts = [
                    {"start": round(s, 2), "end": round(mid, 2), "zoom": 1.0, "focus": "speaker"},
                    {"start": round(mid, 2), "end": round(e, 2), "zoom": zoom_val, "focus": "speaker"},
                ]

            keywords = [str(k).upper().strip() for k in c.get("highlight_keywords", []) if str(k).strip()]
            audio_info = c.get("audio", {})
            if not isinstance(audio_info, dict):
                audio_info = {}
            audio_info.setdefault("normalize", True)
            audio_info.setdefault("bgm_recommendation", style_info["bgm_style"])

            plan = ClipPlan(
                clip_id=idx,
                title=title,
                hook=hook,
                start_time=round(s, 2),
                end_time=round(e, 2),
                duration=dur,
                virality_score=score,
                reasoning=reasoning,
                editing_style=style_key,
                cuts=sanitized_cuts,
                transitions=c.get("transitions", []),
                highlight_keywords=keywords[:6],
                audio=audio_info,
            )
            valid_plans.append(plan)
        except Exception as ex:
            logger.warning("Error sanitizing clip %s: %s", idx, ex)

    return valid_plans


# ═════════════════════════════════════════════════════════════════════════════
# Main Hybrid Director Orchestrator
# ═════════════════════════════════════════════════════════════════════════════

def run_hybrid_director(
    transcript_entries: List[Dict[str, Any]],
    video_path: Path,
    video_duration: float,
    silences: List[float],
    target_duration: float = 35.0,
    max_clips: int = 5,
    style_key: str = "viral_podcast",
    ai_mode: str = "hybrid",  # "hybrid" | "ollama" | "gemini" | "rule_based"
    ollama_model: str = "llama3.2",
    gemini_model: str = "gemini-2.0-flash",
    gemini_api_key: Optional[str] = None,
    work_dir: Optional[Path] = None,
    log_fn: Callable[[str], None] = print,
) -> List[ClipPlan]:
    """Orchestrate dialogue transcription, Gemini vision, and Ollama directing."""
    work_path = work_dir or video_path.parent

    # 1. Handle rule-based immediately if requested
    if ai_mode == "rule_based":
        if log_fn:
            log_fn("📐 Using Rule-Based Director (silence detection & dialogue cadence)...")
        return plan_clips_rule_based(
            transcript_entries, video_duration, silences, target_duration, max_clips, style_key
        )

    # 2. Step 1: Optional Gemini Visual Scene Analysis
    visual_events: List[Dict[str, Any]] = []
    if ai_mode in ("hybrid", "gemini"):
        # Select sample timestamps across dialogue entries or every 5 seconds
        sample_times = []
        if transcript_entries:
            step = max(1, len(transcript_entries) // 10)
            sample_times = [e["start"] for e in transcript_entries[::step]]
        else:
            sample_times = [i * 5.0 for i in range(min(12, int(video_duration // 5)))]

        visual_events = gemini_client.analyze_visual_scenes(
            video_path=video_path,
            timestamps=sample_times,
            work_dir=work_path,
            api_key=gemini_api_key,
            model=gemini_model,
            style=style_key,
            log_fn=log_fn,
        )

    # 3. Step 2: AI Directing Decision Maker
    plans: List[ClipPlan] = []

    # Attempt Ollama directing if mode is hybrid or ollama
    if ai_mode in ("hybrid", "ollama"):
        if log_fn:
            log_fn(f"🧠 Prompting local AI Director ({ollama_model}) to craft viral shorts plan...")

        prompt = build_director_prompt(
            transcript_entries=transcript_entries,
            visual_events=visual_events,
            style_key=style_key,
            target_duration=target_duration,
            max_clips=max_clips,
            video_duration=video_duration,
        )

        messages = [
            {"role": "user", "content": prompt}
        ]

        resp_json, err = ollama_client.generate_chat_json(
            model=ollama_model,
            messages=messages,
            schema={"required": ["clips"]},
            temperature=0.25,
            timeout=90.0,
        )

        if resp_json and "clips" in resp_json:
            plans = validate_and_sanitize_plans(
                resp_json["clips"], video_duration, max_clips, style_key
            )
            if plans and log_fn:
                log_fn(f"🎯 Ollama ({ollama_model}) generated {len(plans)} professional shorts plans!")
        else:
            if log_fn:
                log_fn(f"⚠️ Ollama directing unvailable ({err}).")

    # If Ollama failed or mode was gemini-only, attempt Gemini directing
    if not plans and (ai_mode == "gemini" or (ai_mode == "hybrid" and gemini_client.get_api_key())):
        if log_fn:
            log_fn(f"☁️ Prompting Gemini Cloud Director ({gemini_model}) to craft editing plan...")
        key = gemini_api_key or gemini_client.get_api_key()
        if key:
            prompt = build_director_prompt(
                transcript_entries=transcript_entries,
                visual_events=visual_events,
                style_key=style_key,
                target_duration=target_duration,
                max_clips=max_clips,
                video_duration=video_duration,
            )
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={key}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"response_mime_type": "application/json", "temperature": 0.2},
                }
                import urllib.request
                req = urllib.request.Request(
                    url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=30.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    txt = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    cand_json = json.loads(txt) if txt else {}
                    if cand_json and "clips" in cand_json:
                        plans = validate_and_sanitize_plans(
                            cand_json["clips"], video_duration, max_clips, style_key
                        )
                        if plans and log_fn:
                            log_fn(f"🎯 Gemini generated {len(plans)} professional shorts plans!")
            except Exception as e:
                if log_fn:
                    log_fn(f"⚠️ Gemini directing error: {e}")

    # 4. Final Fallback: If AI engines were unavailable or offline, use smart rule-based director
    if not plans:
        if log_fn:
            log_fn("⚡ AI models offline or unavailable. Gracefully switching to Smart Rule-Based Director...")
        plans = plan_clips_rule_based(
            transcript_entries, video_duration, silences, target_duration, max_clips, style_key
        )

    return plans


def generate_shorts_plans(
    video_duration: float,
    transcript_entries: Optional[List[Dict[str, Any]]] = None,
    visual_scenes: Optional[List[Dict[str, Any]]] = None,
    silence_intervals: Optional[List[float]] = None,
    style_key: str = "viral_podcast",
    max_clips: int = 5,
    target_duration: float = 35.0,
    ai_mode: str = "hybrid",
    ollama_model: str = "llama3.2",
    gemini_model: str = "gemini-3.5-flash-lite",
    gemini_api_key: Optional[str] = None,
    log_fn: Callable[[str], None] = print,
    **kwargs,
) -> List[ClipPlan]:
    """Generate structured AI shorts plans using Ollama, Gemini, or rule-based fallback."""
    transcript = transcript_entries or []
    silences = silence_intervals or []
    visuals = visual_scenes or []

    # 1. If rule-based mode, generate rule-based plans directly
    if ai_mode == "rule_based":
        if log_fn:
            log_fn("⚡ Using Smart Dialogue & Silence-based Director...")
        return plan_clips_rule_based(transcript, video_duration, silences, target_duration, max_clips, style_key)

    plans: List[ClipPlan] = []

    # 2. Primary Brain: Local Ollama
    if ai_mode in ("hybrid", "ollama"):
        if log_fn:
            log_fn(f"🧠 Prompting local AI Director ({ollama_model}) to craft viral shorts plan...")

        prompt = build_director_prompt(
            transcript_entries=transcript,
            visual_events=visuals,
            style_key=style_key,
            target_duration=target_duration,
            max_clips=max_clips,
            video_duration=video_duration,
        )

        resp_json, err = ollama_client.generate_chat_json(
            model=ollama_model,
            messages=[{"role": "user", "content": prompt}],
            schema={"required": ["clips"]},
            temperature=0.25,
            timeout=90.0,
        )

        if resp_json and "clips" in resp_json:
            plans = validate_and_sanitize_plans(
                resp_json["clips"], video_duration, max_clips, style_key
            )
            if plans and log_fn:
                log_fn(f"🎯 Ollama ({ollama_model}) generated {len(plans)} professional shorts plans!")
        else:
            if log_fn:
                log_fn(f"⚠️ Ollama directing unavailable ({err}).")

    # 3. Cloud Assistant fallback: Google Gemini
    if not plans and (ai_mode == "gemini" or (ai_mode == "hybrid" and gemini_client.get_api_key())):
        key = gemini_api_key or gemini_client.get_api_key()
        if key:
            if log_fn:
                log_fn(f"☁️ Prompting Gemini Cloud Director ({gemini_model}) to craft editing plan...")
            prompt = build_director_prompt(
                transcript_entries=transcript,
                visual_events=visuals,
                style_key=style_key,
                target_duration=target_duration,
                max_clips=max_clips,
                video_duration=video_duration,
            )
            try:
                import urllib.request
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={key}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"response_mime_type": "application/json", "temperature": 0.2},
                }
                req = urllib.request.Request(
                    url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=30.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    txt = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    cand_json = json.loads(txt) if txt else {}
                    if cand_json and "clips" in cand_json:
                        plans = validate_and_sanitize_plans(
                            cand_json["clips"], video_duration, max_clips, style_key
                        )
                        if plans and log_fn:
                            log_fn(f"🎯 Gemini generated {len(plans)} professional shorts plans!")
            except Exception as e:
                if log_fn:
                    log_fn(f"⚠️ Gemini directing error: {e}")

    # 4. Graceful Fallback: Smart Rule-Based Director
    if not plans:
        if log_fn:
            log_fn("⚡ Local/Cloud models offline or unavailable. Gracefully switching to Smart Rule-Based Director...")
        plans = plan_clips_rule_based(
            transcript, video_duration, silences, target_duration, max_clips, style_key
        )

    return plans
