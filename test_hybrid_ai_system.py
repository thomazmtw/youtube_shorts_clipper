"""Comprehensive Verification Test Suite for Hybrid AI Shorts Editor."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Ensure clipper dir is in sys.path
sys.path.insert(0, str(Path(__file__).parent))

import ollama_client
import gemini_client
import ai_director
import ffmpeg_director
import shorts_clipper as core


def test_ollama_client():
    print("\n[TEST 1] Testing Ollama Client...")
    installed = ollama_client.is_ollama_installed()
    running = ollama_client.is_ollama_running()
    models = ollama_client.list_local_models()
    print(f"  Installed: {installed}, Running: {running}, Models: {models}")
    
    # Test vision detection
    assert ollama_client.is_vision_model("llava:7b") is True
    assert ollama_client.is_vision_model("llama3.2-vision") is True
    assert ollama_client.is_vision_model("llama3.2:latest") is False
    assert ollama_client.is_vision_model("mistral") is False
    print("  Vision capability detection verified.")

    # Test JSON repair
    noisy_json = "```json\n{\n  \"status\": \"success\",\n  \"count\": 5,\n}\n```"
    repaired = ollama_client.repair_json(noisy_json)
    assert repaired is not None and repaired.get("status") == "success"
    print("  JSON repair and markdown stripping verified.")


def test_gemini_client():
    print("\n[TEST 2] Testing Gemini Client...")
    models = gemini_client.list_gemini_models()
    assert "gemini-2.0-flash" in models
    assert "gemini-1.5-flash" in models
    print(f"  Gemini models list verified: {models[:3]}")

    # Test API key save and load
    test_key = "test_gemini_key_12345"
    gemini_client.save_api_key(test_key)
    loaded = gemini_client.get_api_key()
    assert loaded == test_key
    gemini_client.clear_api_key()
    assert gemini_client.get_api_key() == ""
    print("  Secure API key persistence verified.")

    # Test graceful fallback when key is invalid or offline
    ok, msg = gemini_client.test_connection(api_key="invalid_dummy_key")
    assert ok is False
    print(f"  Graceful fallback on invalid key verified: '{msg}'")


def test_editing_styles():
    print("\n[TEST 3] Testing 5 Editing Styles...")
    expected_styles = ["viral_podcast", "cinematic", "fast_viral", "educational", "storytelling"]
    for s in expected_styles:
        assert s in ai_director.EDITING_STYLES
        info = ai_director.EDITING_STYLES[s]
        assert "target_duration" in info
        assert "zoom_punch_factor" in info
        print(f"  Style '{s}': {info['name']} (Zoom punch: {info['zoom_punch_factor']}x)")


def test_hybrid_director_and_fallback():
    print("\n[TEST 4] Testing AI Director Planning & Fallback...")
    sample_transcript = [
        {"start": 0.5, "end": 3.2, "text": "Why do 99% of people fail to build wealth?"},
        {"start": 3.4, "end": 7.0, "text": "Because they focus on saving pennies instead of making dollars."},
        {"start": 7.2, "end": 12.5, "text": "If you master one high-income skill, your life changes forever."},
        {"start": 12.8, "end": 18.0, "text": "Invest in yourself first before anything else."},
        {"start": 18.2, "end": 22.0, "text": "And that is the brutal truth about success."},
    ]
    silences = [3.3, 7.1, 12.6, 18.1]

    # Test rule-based director fallback
    plans = ai_director.run_hybrid_director(
        transcript_entries=sample_transcript,
        video_path=Path("dummy.mp4"),
        video_duration=25.0,
        silences=silences,
        target_duration=18.0,
        max_clips=2,
        style_key="fast_viral",
        ai_mode="hybrid",  # Will fallback cleanly to rule-based since Ollama isn't running
        ollama_model="llama3.2",
        gemini_model="gemini-2.0-flash",
        log_fn=lambda m: print(f"    [Director] {m}")
    )

    assert len(plans) >= 1
    p = plans[0]
    assert p.start_time >= 0.0
    assert p.end_time > p.start_time
    assert p.duration > 10.0
    assert len(p.cuts) >= 2
    print(f"  AI Director Plan produced: '{p.title}' ({p.duration}s, Virality {p.virality_score}/100)")
    print(f"  Cuts/Zooms planned: {p.cuts}")


def test_ffmpeg_execution():
    print("\n[TEST 5] Testing FFmpeg Video Execution Engine (Cuts, Punch-in Zoom & ASS)...")
    tmp = Path(tempfile.mkdtemp())
    try:
        src = tmp / "src_test.mp4"
        # Generate 15s test video with audio
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "testsrc=size=1280x720:rate=30:duration=15",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=15",
            "-c:v", "libx264", "-c:a", "aac", "-shortest", str(src)
        ], capture_output=True, check=True)

        plan = ai_director.ClipPlan(
            clip_id=1,
            title="Why Wealth Fails",
            hook="Why do 99% fail?",
            start_time=1.0,
            end_time=13.0,
            duration=12.0,
            virality_score=94,
            reasoning="Strong hook and punch-in climax",
            editing_style="viral_podcast",
            cuts=[
                {"start": 1.0, "end": 6.5, "zoom": 1.0, "focus": "speaker"},
                {"start": 6.5, "end": 13.0, "zoom": 1.16, "focus": "speaker"},  # Punch-in zoom
            ],
            highlight_keywords=["WEALTH", "SECRET", "FAIL"],
            audio={"normalize": True}
        )

        captions = [
            {"start": 1.0, "end": 4.0, "text": "WHY DO 99 PERCENT FAIL"},
            {"start": 4.2, "end": 8.0, "text": "THE SECRET OF WEALTH"},
            {"start": 8.2, "end": 12.5, "text": "MASTER ONE HIGH INCOME SKILL"},
        ]

        out_clip = tmp / "final_short.mp4"
        ffmpeg_director.execute_director_clip(
            src_video=src,
            plan=plan,
            out_clip=out_clip,
            captions=captions,
            caption_style="tiktok_yellow",
            caption_size=40,
            fit="crop",
            work_dir=tmp,
            log_fn=lambda m: print(f"    [FFmpeg] {m}")
        )

        assert out_clip.exists()
        sz = out_clip.stat().st_size
        assert sz > 50000
        print(f"  Output Short verified: {out_clip.name} ({sz} bytes)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_gui_initialization():
    print("\n[TEST 6] Testing GUI Headless Initialization...")
    import shorts_clipper_app as app_mod
    gui = app_mod.App()
    gui.update_idletasks()
    assert gui.notebook is not None
    assert gui.tree is not None
    assert gui.preview is not None
    assert gui.ai_mode.get() == "hybrid"
    print("  GUI components and variables initialized cleanly.")
    gui.destroy()


if __name__ == "__main__":
    print("=" * 60)
    print("RUNNING HYBRID AI SHORTS EDITOR VERIFICATION SUITE")
    print("=" * 60)
    test_ollama_client()
    test_gemini_client()
    test_editing_styles()
    test_hybrid_director_and_fallback()
    test_ffmpeg_execution()
    test_gui_initialization()
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)
