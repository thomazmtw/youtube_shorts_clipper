"""
branding.py — Logo & Watermark Configuration for Shorts Clipper
===============================================================
Burn a PNG logo/watermark into every exported clip.

QUICK START
-----------
1. Set LOGO_PATH to the full path of your PNG logo file.
   (Transparent backgrounds work best — save as PNG-24 with alpha.)
2. Pick a POSITION from the options below.
3. Adjust SIZE_PCT  (logo width as % of video width, e.g. 15 = 15%).
4. Set OPACITY      (1.0 = fully opaque, 0.5 = 50% transparent).
5. Set PADDING      (pixels from the edge of the screen).

The logo is burned directly into every exported MP4 clip by FFmpeg.
No watermark service, no cloud, 100% local.

EXAMPLE
-------
LOGO_PATH = r"C:\\Users\\You\\Desktop\\my_channel_logo.png"
POSITION  = "top_right"
SIZE_PCT  = 12
OPACITY   = 0.9
PADDING   = 24
"""

from pathlib import Path

# =============================================================================
# EDIT THESE VALUES ↓
# =============================================================================

# Full path to your PNG logo. Leave empty string "" to disable.
LOGO_PATH = ""

# Where to place the logo on screen:
#   "top_left"   "top_center"   "top_right"
#   "mid_left"   "center"       "mid_right"
#   "bot_left"   "bot_center"   "bot_right"
POSITION = "top_right"

# Logo width as % of video width  (1 – 50).
#   At 1080px wide: 10% → 108px wide,  20% → 216px wide.
SIZE_PCT = 15

# Opacity: 0.0 (invisible) → 1.0 (fully opaque).
OPACITY = 1.0

# Distance from the nearest screen edges, in pixels.
PADDING = 30

# =============================================================================
# POSITION OPTIONS (copy any value into POSITION above)
# =============================================================================
POSITION_OPTIONS = {
    "top_left":   "Top Left",
    "top_center": "Top Center",
    "top_right":  "Top Right ⭐ (recommended for channel branding)",
    "mid_left":   "Middle Left",
    "center":     "Center",
    "mid_right":  "Middle Right",
    "bot_left":   "Bottom Left",
    "bot_center": "Bottom Center",
    "bot_right":  "Bottom Right",
}

# =============================================================================
# HELPER FUNCTIONS — used by shorts_clipper.py (do not edit)
# =============================================================================

def get_config():
    """Return current branding config as a dict for the clipper engine."""
    path = str(LOGO_PATH).strip()
    return {
        "enabled":  bool(path and Path(path).exists()),
        "path":     path,
        "position": POSITION,
        "size_pct": int(SIZE_PCT),
        "opacity":  float(OPACITY),
        "padding":  int(PADDING),
    }


def is_enabled():
    """Return True if logo file is set and exists on disk."""
    path = str(LOGO_PATH).strip()
    return bool(path and Path(path).exists())


def get_ffmpeg_logo_filter(logo_input_idx, size_pct, opacity, position, padding):
    """
    Build FFmpeg filter strings for logo overlay.

    Returns:
        (scale_filter_str, overlay_xy_str)

    scale_filter_str : e.g. '[1:v]scale=iw*15/100:-1[logo_sc]'
    overlay_xy_str   : e.g. 'W-w-30:30'  (used in overlay=X:Y)
    """
    pos_map = {
        "top_left":   f"{padding}:{padding}",
        "top_center": f"(W-w)/2:{padding}",
        "top_right":  f"W-w-{padding}:{padding}",
        "mid_left":   f"{padding}:(H-h)/2",
        "center":     "(W-w)/2:(H-h)/2",
        "mid_right":  f"W-w-{padding}:(H-h)/2",
        "bot_left":   f"{padding}:H-h-{padding}",
        "bot_center": f"(W-w)/2:H-h-{padding}",
        "bot_right":  f"W-w-{padding}:H-h-{padding}",
    }
    xy = pos_map.get(position, f"W-w-{padding}:{padding}")

    scale = f"[{logo_input_idx}:v]scale=iw*{int(size_pct)}/100:-1"
    if float(opacity) < 1.0:
        scale += f",format=rgba,colorchannelmixer=aa={float(opacity):.2f}"
    scale += "[logo_sc]"

    return scale, xy
