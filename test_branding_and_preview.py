"""Comprehensive test for branding, caption size override, and unified preview."""
import sys, tempfile, subprocess, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import branding as br
import shorts_clipper as core

core.ensure_tools_in_path()

tmp = Path(tempfile.mkdtemp())
print(f"Temporary test dir: {tmp}")

# 1. Test branding module
print("\n--- 1. Testing branding.py ---")
cfg = br.get_config()
print("Default config:", cfg)
scale_filter, xy = br.get_ffmpeg_logo_filter(1, 15, 0.8, "top_right", 30)
print(f"Scale filter: {scale_filter}")
print(f"Overlay xy: {xy}")
assert "[1:v]scale=" in scale_filter
assert "W-w-30:30" == xy

# 2. Create test video and test PNG logo
print("\n--- 2. Creating test video & PNG logo ---")
test_vid = tmp / "test_src.mp4"
subprocess.run([
    "ffmpeg", "-y", "-f", "lavfi",
    "-i", "color=c=navy:size=1920x1080:rate=30:duration=6",
    "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
    "-c:v", "libx264", "-c:a", "aac", "-shortest", str(test_vid)
], capture_output=True, check=True)

test_logo = tmp / "test_logo.png"
subprocess.run([
    "ffmpeg", "-y", "-f", "lavfi",
    "-i", "color=c=red@0.8:size=200x200:rate=1:duration=1",
    "-vframes", "1", str(test_logo)
], capture_output=True, check=True)
print("Created test video and logo:", test_vid.exists(), test_logo.exists())

# 3. Test generate_ass with size_override
print("\n--- 3. Testing generate_ass with size override ---")
caps = [{"start": 0.5, "end": 4.5, "text": "TEST CAPTION WITH CUSTOM SIZE"}]
ass_file = tmp / "custom_size.ass"
core.generate_ass(caps, 0.0, 5.0, "tiktok_yellow", ass_file, size_override=85)
ass_content = ass_file.read_text(encoding="utf-8")
assert ",85," in ass_content, "Size override 85 not found in ASS style line"
print("ASS generated successfully with font size 85.")

# 4. Test export with ASS subtitles and logo across templates
print("\n--- 4. Testing export with subtitles + logo across templates ---")
logo_cfg = {
    "path": str(test_logo),
    "position": "top_right",
    "size_pct": 18,
    "opacity": 0.85,
    "padding": 30
}

templates = ["crop", "blur", "split", "headline", "none"]
for fit in templates:
    out_clip = tmp / f"clip_{fit}_with_logo.mp4"
    core.export(test_vid, 0.0, 4.0, out_clip, fit=fit, ass_file=ass_file, logo_config=logo_cfg)
    assert out_clip.exists() and out_clip.stat().st_size > 5000, f"Export failed for {fit}"
    print(f"  Exported {fit} successfully: {out_clip.stat().st_size} bytes")

# 5. Test GUI headless initialization
print("\n--- 5. Testing GUI headless initialization ---")
import tkinter as tk
import shorts_clipper_app as app_mod
app = app_mod.App()
app.withdraw()

# Test updating vars to trigger UnifiedPreview.refresh()
app.subtitle_style.set("neon_green")
app.caption_size.set(65)
app.logo_enabled.set(True)
app.logo_path_v.set(str(test_logo))
app.logo_pos_v.set("bot_right")
app.logo_size_v.set(22)
app.logo_opacity_v.set(0.75)
app.preview.refresh()
print("UnifiedPreview refreshed without error.")
app.destroy()

print("\nALL VERIFICATION TESTS COMPLETED SUCCESSFULLY!")
