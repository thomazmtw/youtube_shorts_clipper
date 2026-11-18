"""Full runtime error sweep for shorts_clipper + caption_styles."""
import sys, traceback, tempfile, subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

ERRORS = []

def check(label, fn):
    try:
        result = fn()
        print(f"  OK  {label}" + (f" -> {result}" if result is not None else ""))
        return result
    except Exception as e:
        msg = f"FAIL {label}: {e}"
        print(msg)
        traceback.print_exc()
        ERRORS.append(msg)
        return None

# ── 1. Imports ────────────────────────────────────────────────────────────────
print("\n=== 1. Imports ===")
import caption_styles as cs
import shorts_clipper as core

check("caption_styles has STYLES",    lambda: len(cs.STYLES))
check("caption_styles.list_styles",   lambda: len(cs.list_styles()))
check("caption_styles.get_style",     lambda: cs.get_style("tiktok_yellow")["font"])
check("caption_styles.get_display_names", lambda: len(cs.get_display_names()))
check("caption_styles.style_keys",    lambda: len(cs.style_keys()))
check("core._USING_EXTERNAL_STYLES",  lambda: core._USING_EXTERNAL_STYLES)
check("core._style_keys()",           lambda: len(core._style_keys()))
check("core._get_style fallback",     lambda: core._get_style("NONEXISTENT")["font"])

# ── 2. Tools ─────────────────────────────────────────────────────────────────
print("\n=== 2. Tools in PATH ===")
core.ensure_tools_in_path()
import shutil
check("ffmpeg found",   lambda: shutil.which("ffmpeg") is not None)
check("ffprobe found",  lambda: shutil.which("ffprobe") is not None)
check("yt-dlp found",   lambda: shutil.which("yt-dlp") is not None)

# ── 3. Create test video ──────────────────────────────────────────────────────
print("\n=== 3. Test video ===")
tmp = Path(tempfile.mkdtemp())
test_vid = tmp / "test.mp4"
r = subprocess.run([
    "ffmpeg", "-y", "-f", "lavfi",
    "-i", "color=c=blue:size=1920x1080:rate=30:duration=15",
    "-f", "lavfi", "-i", "sine=frequency=440:duration=15",
    "-c:v", "libx264", "-c:a", "aac", "-shortest", str(test_vid)
], capture_output=True)
check("test video created", lambda: test_vid.exists())

# ── 4. Core functions ─────────────────────────────────────────────────────────
print("\n=== 4. Core functions ===")
dur = check("duration()", lambda: round(core.duration(test_vid), 1))
silences = check("find_silences()", lambda: core.find_silences(test_vid)) or []
cuts = check("plan_cuts() smart",   lambda: core.plan_cuts(dur or 15, 7, 3, silences, "smart"))
check("plan_cuts() podcast",         lambda: core.plan_cuts(dur or 15, 7, 3, silences, "podcast"))
check("plan_cuts() even",            lambda: core.plan_cuts(dur or 15, 7, 3, [], "even"))

captions_fake = [
    {"start": 0.0, "end": 1.5, "text": "HELLO WORLD"},
    {"start": 1.5, "end": 3.0, "text": "SAMPLE TEXT"},
    {"start": 3.0, "end": 5.0, "text": "MORE WORDS"},
]

check("calculate_virality_score()",  lambda: core.calculate_virality_score(
    test_vid, 0, 7, dur or 15, silences, captions_fake)["score"])

check("parse_subtitles_file() empty", lambda: core.parse_subtitles_file(None))
check("chunk_captions()",            lambda: len(core.chunk_captions(captions_fake)))
check("find_subtitles() no subs",    lambda: core.find_subtitles(test_vid, tmp))

# ── 5. generate_ass for ALL 13 styles ────────────────────────────────────────
print("\n=== 5. generate_ass — all styles ===")
out_dir = tmp / "out"
out_dir.mkdir()

for style_key in cs.style_keys():
    ass_path = out_dir / f"{style_key}.ass"
    def _gen(k=style_key, p=ass_path):
        core.generate_ass(captions_fake, 0.0, 7.0, k, p)
        content = p.read_text(encoding="utf-8")
        assert "Dialogue:" in content, "No Dialogue lines in ASS"
        assert r"\fad" in content,     "Missing fade tag"
        assert "PlayResX: 1080" in content
        return f"{p.stat().st_size}b, fade=OK"
    check(f"generate_ass({style_key})", _gen)

# ── 6. Export — all 4 templates + 2 styles ────────────────────────────────────
print("\n=== 6. export() — all templates ===")
seg_start, seg_end = 0.0, 7.0
for fit in ["crop", "blur", "split", "headline", "none"]:
    for style_key in ["tiktok_yellow", "cinema_box"]:
        ass_path = out_dir / f"tmp_{fit}_{style_key}.ass"
        core.generate_ass(captions_fake, seg_start, seg_end, style_key, ass_path)
        out_clip = out_dir / f"clip_{fit}_{style_key}.mp4"
        def _export(f=fit, s=style_key, o=out_clip, a=ass_path):
            core.export(test_vid, seg_start, seg_end - seg_start, o, fit=f, ass_file=a)
            assert o.exists() and o.stat().st_size > 1000, "Output too small"
            return f"{o.stat().st_size // 1024}KB"
        check(f"export(fit={fit}, style={style_key})", _export)

# ── 7. CLI --help ─────────────────────────────────────────────────────────────
print("\n=== 7. CLI --help ===")
r2 = subprocess.run([sys.executable, "shorts_clipper.py", "--help"],
                    capture_output=True, text=True)
check("CLI --help exit 0",         lambda: r2.returncode == 0)
check("CLI lists style names",     lambda: "tiktok_yellow" in r2.stdout)
check("CLI lists fire_orange",     lambda: "fire_orange" in r2.stdout)

# ── 8. App GUI class ─────────────────────────────────────────────────────────
print("\n=== 8. GUI class ===")
import tkinter as tk
root = tk.Tk(); root.withdraw()
from shorts_clipper_app import App, CaptionStylePicker

def _build_app():
    a = App()
    a.withdraw()
    # Check all style keys trigger picker selection without crash
    for key in cs.style_keys() + ["none"]:
        a.style_picker._select(key, animate=False)
    a.destroy()
    return "all selections OK"
check("App() + style selection", _build_app)

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
if ERRORS:
    print(f"FAILED with {len(ERRORS)} error(s):")
    for e in ERRORS:
        print(f"  ✗ {e}")
    sys.exit(1)
else:
    print(f"ALL CHECKS PASSED  ({7 + len(cs.style_keys()) + 10} tests)")
