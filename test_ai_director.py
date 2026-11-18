"""Test script for AI Director and FFmpeg Execution Engine."""

import sys
import tempfile
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import ollama_client
import gemini_client
import ai_director
import ffmpeg_director

print("--- 1. Testing Ollama Client ---")
print("Ollama installed:", ollama_client.is_ollama_installed())
print("Ollama running:", ollama_client.is_ollama_running())
print("Ollama models:", ollama_client.list_local_models())
guide = ollama_client.get_installation_instructions()
assert len(guide) > 50
print("Installation guide verified.")

print("\n--- 2. Testing Gemini Client ---")
key = gemini_client.get_api_key()
print("Stored Gemini API key present:", bool(key))
models = gemini_client.list_gemini_models()
print("Gemini models:", models)
assert "gemini-2.0-flash" in models

print("\n--- 3. Testing AI Director (Rule-based & Plan Generation) ---")
test_transcript = [
    {"start": 1.0, "end": 4.5, "text": "Here is the big secret nobody tells you about money."},
    {"start": 4.8, "end": 8.2, "text": "Most people spend everything they make on stupid things."},
    {"start": 8.5, "end": 14.0, "text": "If you invest in assets, you will never have to worry again."},
    {"start": 14.2, "end": 20.0, "text": "And that is why financial freedom starts today."},
]
plans = ai_director.plan_clips_rule_based(
    transcript_entries=test_transcript,
    video_duration=22.0,
    silences=[4.6, 8.3, 14.1],
    target_duration=18.0,
    max_clips=2,
    style_key="viral_podcast",
)
assert len(plans) >= 1
p = plans[0]
print(f"Generated plan: ID={p.clip_id}, Title='{p.title}', Dur={p.duration}s, Virality={p.virality_score}")
print(f"  Cuts planned: {p.cuts}")
print(f"  Highlight keywords: {p.highlight_keywords}")

print("\n--- 4. Testing FFmpeg Director Execution ---")
tmp = Path(tempfile.mkdtemp())
test_vid = tmp / "test_src.mp4"
# Generate 22s test video with audio
subprocess.run([
    "ffmpeg", "-y", "-f", "lavfi",
    "-i", "testsrc=size=1280x720:rate=30:duration=22",
    "-f", "lavfi", "-i", "sine=frequency=440:duration=22",
    "-c:v", "libx264", "-c:a", "aac", "-shortest", str(test_vid)
], capture_output=True, check=True)

out_clip = tmp / "test_director_short.mp4"
captions = [
    {"start": 1.0, "end": 4.5, "text": "HERE IS THE BIG SECRET"},
    {"start": 4.8, "end": 8.2, "text": "NOBODY TELLS YOU ABOUT MONEY"},
    {"start": 8.5, "end": 14.0, "text": "IF YOU INVEST IN ASSETS"},
    {"start": 14.2, "end": 19.5, "text": "FINANCIAL FREEDOM STARTS TODAY"},
]

ffmpeg_director.execute_director_clip(
    src_video=test_vid,
    plan=p,
    out_clip=out_clip,
    captions=captions,
    caption_style="tiktok_yellow",
    caption_size=40,
    fit="crop",
    work_dir=tmp,
    log_fn=print,
)

assert out_clip.exists() and out_clip.stat().st_size > 50000
print(f"Final clip generated successfully! Size: {out_clip.stat().st_size} bytes")

print("\nALL AI DIRECTOR & FFMPEG TESTS PASSED!")
