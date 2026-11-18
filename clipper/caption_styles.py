"""
caption_styles.py — Shorts Clipper Caption Style Library
=========================================================
Customize or add your own caption styles here — no coding required!

HOW TO ADD A CUSTOM STYLE
--------------------------
Copy any existing style block below, give it a new key name, and tweak the values.
The key name is what you pass to --subtitle-style on the CLI, or pick in the GUI.

ASS COLOR FORMAT: &HAABBGGRR  (hex, 2 digits each, in this order)
  AA = Alpha transparency  00 = fully visible, FF = fully invisible
  BB = Blue value          00–FF
  GG = Green value         00–FF
  RR = Red value           00–FF

  Quick color reference:
    Yellow:       &H0000FFFF    White:        &H00FFFFFF
    Black:        &H00000000    Red:          &H000000FF
    Neon Green:   &H0014FF39    Cyan:         &H00FFFF00
    Orange:       &H000080FF    Pink/Magenta: &H00FF00FF
    Blue:         &H00FF0000    Purple:       &H00800080

FIELD REFERENCE
---------------
  font          : Font family name. Use any font installed on your system.
                  Common safe choices: Arial, Impact, Verdana, Trebuchet MS,
                  Georgia, Courier New, Comic Sans MS, Tahoma

  size          : Font size in pixels (for 1080x1920 canvas). Range: 30–100.
                  Recommended: 56 (subtle) → 70 (punchy)

  bold          : -1 = bold, 0 = normal

  italic        : 1 = italic, 0 = normal

  underline     : 1 = underline, 0 = none

  primary       : Main text fill color (see ASS COLOR FORMAT above)

  secondary     : Word-highlight color for karaoke mode (rarely used)

  outline_color : Color of the text stroke/border

  back_color    : Background box or shadow color

  border_style  : 1 = Outline + drop shadow (most common)
                  3 = Opaque box behind text (cinematic/subtitle style)

  outline       : Thickness of the outline stroke in pixels. Range: 0–8.
                  0 = no outline (use with border_style 3)

  shadow        : Drop shadow distance in pixels. Range: 0–5.
                  0 = no shadow

  alignment     : Where captions appear on screen (numpad layout):
                  7=top-left   8=top-center    9=top-right
                  4=mid-left   5=mid-center    6=mid-right
                  1=bot-left   2=bot-center    3=bot-right
                  Recommended: 2 (bottom center, like all major apps)

  margin_v      : Vertical margin from the alignment edge, in pixels.
                  For alignment=2 (bottom), higher = farther from bottom.
                  Range: 50–600. Sweet spot for 9:16: 280–400.

  scale_x       : Horizontal text scale %. 100 = normal, 110 = slightly wider.
  scale_y       : Vertical text scale %. 100 = normal.

  letter_spacing: Extra space between letters in pixels. 0 = normal.

  display_name  : Human-readable label shown in the GUI dropdown.
  description   : Short tooltip description shown in the GUI.
  preview_color : Hex color (#RRGGBB) used for the GUI color swatch preview.

TIPS
----
- Pair Impact font + size 72 + outline 5 for maximum punch (meme/sports style).
- Use border_style=3 + outline=0 + shadow=0 for a clean podcast/interview look.
- margin_v=180 pushes captions closer to the bottom edge (good for TikTok).
- Scale_x=110 makes text feel wider and more confident.
- Want animated fade? The core engine will add \\fad(80,80) to each line automatically
  if you set "fade": True in the style (supported in future versions).
"""

# =============================================================================
# STYLE DEFINITIONS
# Each key is a style ID used in --subtitle-style and the GUI.
# =============================================================================

STYLES = {

    # ── VIRAL / TIKTOK ────────────────────────────────────────────────────────

    "tiktok_yellow": {
        "display_name":   "TikTok Yellow 🔥",
        "description":    "Bold yellow, thick black outline — highest virality",
        "preview_color":  "#FFFF00",
        "font":           "Arial",
        "size":           62,
        "bold":           -1,
        "italic":         0,
        "underline":      0,
        "primary":        "&H0000FFFF",   # Yellow
        "secondary":      "&H000000FF",
        "outline_color":  "&H00000000",   # Black
        "back_color":     "&H80000000",
        "border_style":   1,
        "outline":        4,
        "shadow":         2,
        "alignment":      2,
        "margin_v":       300,
        "scale_x":        100,
        "scale_y":        100,
        "letter_spacing": 0,
    },

    "neon_green": {
        "display_name":   "Neon Green ⚡",
        "description":    "Glowing neon green — gaming, tech, hype",
        "preview_color":  "#39FF14",
        "font":           "Arial",
        "size":           62,
        "bold":           -1,
        "italic":         0,
        "underline":      0,
        "primary":        "&H0014FF39",   # Neon Green
        "secondary":      "&H000000FF",
        "outline_color":  "&H00000000",
        "back_color":     "&H99000000",
        "border_style":   1,
        "outline":        4,
        "shadow":         3,
        "alignment":      2,
        "margin_v":       300,
        "scale_x":        100,
        "scale_y":        100,
        "letter_spacing": 1,
    },

    "fire_orange": {
        "display_name":   "Fire Orange 🔥",
        "description":    "Bold orange — motivational, fitness, hustle content",
        "preview_color":  "#FF8C00",
        "font":           "Impact",
        "size":           66,
        "bold":           0,
        "italic":         0,
        "underline":      0,
        "primary":        "&H000080FF",   # Orange
        "secondary":      "&H000000FF",
        "outline_color":  "&H00000000",
        "back_color":     "&H99000000",
        "border_style":   1,
        "outline":        5,
        "shadow":         2,
        "alignment":      2,
        "margin_v":       280,
        "scale_x":        105,
        "scale_y":        100,
        "letter_spacing": 1,
    },

    "impact_red": {
        "display_name":   "Impact Red 🔴",
        "description":    "Impact font, red — sports, news, breaking content",
        "preview_color":  "#FF2222",
        "font":           "Impact",
        "size":           70,
        "bold":           0,
        "italic":         0,
        "underline":      0,
        "primary":        "&H000000FF",   # Red
        "secondary":      "&H00FFFFFF",
        "outline_color":  "&H00000000",
        "back_color":     "&H99000000",
        "border_style":   1,
        "outline":        5,
        "shadow":         2,
        "alignment":      2,
        "margin_v":       270,
        "scale_x":        108,
        "scale_y":        100,
        "letter_spacing": 2,
    },

    "hot_pink": {
        "display_name":   "Hot Pink 💗",
        "description":    "Vibrant pink — beauty, lifestyle, fashion content",
        "preview_color":  "#FF1493",
        "font":           "Arial",
        "size":           60,
        "bold":           -1,
        "italic":         0,
        "underline":      0,
        "primary":        "&H00931DFF",   # Hot Pink
        "secondary":      "&H00FFFFFF",
        "outline_color":  "&H00000000",
        "back_color":     "&H80000000",
        "border_style":   1,
        "outline":        4,
        "shadow":         2,
        "alignment":      2,
        "margin_v":       300,
        "scale_x":        100,
        "scale_y":        100,
        "letter_spacing": 0,
    },

    "electric_blue": {
        "display_name":   "Electric Blue 💙",
        "description":    "Electric blue — finance, edu, calm authority",
        "preview_color":  "#0088FF",
        "font":           "Arial",
        "size":           60,
        "bold":           -1,
        "italic":         0,
        "underline":      0,
        "primary":        "&H00FF8800",   # Electric Blue
        "secondary":      "&H00FFFFFF",
        "outline_color":  "&H00000000",
        "back_color":     "&H80000000",
        "border_style":   1,
        "outline":        4,
        "shadow":         2,
        "alignment":      2,
        "margin_v":       300,
        "scale_x":        100,
        "scale_y":        100,
        "letter_spacing": 0,
    },

    # ── CLEAN / MINIMAL ───────────────────────────────────────────────────────

    "clean_white": {
        "display_name":   "Clean White ✨",
        "description":    "Crisp white, thin outline — universal, professional",
        "preview_color":  "#FFFFFF",
        "font":           "Arial",
        "size":           56,
        "bold":           -1,
        "italic":         0,
        "underline":      0,
        "primary":        "&H00FFFFFF",   # White
        "secondary":      "&H000000FF",
        "outline_color":  "&H00000000",
        "back_color":     "&H80000000",
        "border_style":   1,
        "outline":        3,
        "shadow":         2,
        "alignment":      2,
        "margin_v":       300,
        "scale_x":        100,
        "scale_y":        100,
        "letter_spacing": 0,
    },

    "bold_stroke": {
        "display_name":   "Bold Stroke 🖊️",
        "description":    "White fill with thick stroke — clean, loud, legible",
        "preview_color":  "#FFFFFF",
        "font":           "Arial",
        "size":           64,
        "bold":           -1,
        "italic":         0,
        "underline":      0,
        "primary":        "&H00FFFFFF",   # White
        "secondary":      "&H000000FF",
        "outline_color":  "&H00000000",
        "back_color":     "&HA0000000",
        "border_style":   1,
        "outline":        6,
        "shadow":         0,
        "alignment":      2,
        "margin_v":       300,
        "scale_x":        100,
        "scale_y":        100,
        "letter_spacing": 1,
    },

    # ── CINEMATIC / BOX STYLES ────────────────────────────────────────────────

    "cinema_box": {
        "display_name":   "Cinema Box 🎬",
        "description":    "White text in dark translucent box — film subtitle look",
        "preview_color":  "#E0E0E0",
        "font":           "Arial",
        "size":           52,
        "bold":           0,
        "italic":         0,
        "underline":      0,
        "primary":        "&H00FFFFFF",
        "secondary":      "&H000000FF",
        "outline_color":  "&H00000000",
        "back_color":     "&H99000000",   # Semi-transparent black box
        "border_style":   3,              # Opaque box mode
        "outline":        0,
        "shadow":         0,
        "alignment":      2,
        "margin_v":       280,
        "scale_x":        100,
        "scale_y":        100,
        "letter_spacing": 0,
    },

    "podcast_minimal": {
        "display_name":   "Podcast Minimal 🎙️",
        "description":    "Light gray box — clean interview & podcast style",
        "preview_color":  "#CCCCCC",
        "font":           "Trebuchet MS",
        "size":           48,
        "bold":           0,
        "italic":         0,
        "underline":      0,
        "primary":        "&H00FFFFFF",
        "secondary":      "&H000000FF",
        "outline_color":  "&H00000000",
        "back_color":     "&HBB1A1A1A",   # Darker semi-transparent box
        "border_style":   3,
        "outline":        0,
        "shadow":         0,
        "alignment":      2,
        "margin_v":       220,
        "scale_x":        100,
        "scale_y":        100,
        "letter_spacing": 0,
    },

    # ── SPECIALTY ─────────────────────────────────────────────────────────────

    "typewriter": {
        "display_name":   "Typewriter 🖨️",
        "description":    "Monospace Courier — tutorial, code, retro",
        "preview_color":  "#00FF88",
        "font":           "Courier New",
        "size":           50,
        "bold":           -1,
        "italic":         0,
        "underline":      0,
        "primary":        "&H0088FF00",   # Green terminal color
        "secondary":      "&H000000FF",
        "outline_color":  "&H00000000",
        "back_color":     "&HCC000000",
        "border_style":   3,
        "outline":        0,
        "shadow":         0,
        "alignment":      2,
        "margin_v":       260,
        "scale_x":        100,
        "scale_y":        100,
        "letter_spacing": 2,
    },

    "reels_white": {
        "display_name":   "Reels White 📸",
        "description":    "Instagram Reels style — smaller, airy, centered low",
        "preview_color":  "#F5F5F5",
        "font":           "Arial",
        "size":           50,
        "bold":           -1,
        "italic":         0,
        "underline":      0,
        "primary":        "&H00FFFFFF",
        "secondary":      "&H000000FF",
        "outline_color":  "&H00000000",
        "back_color":     "&H80000000",
        "border_style":   1,
        "outline":        3,
        "shadow":         1,
        "alignment":      2,
        "margin_v":       200,
        "scale_x":        100,
        "scale_y":        100,
        "letter_spacing": 0,
    },

    "top_banner": {
        "display_name":   "Top Banner 📢",
        "description":    "Bold yellow at top — good for hook opening lines",
        "preview_color":  "#FFFF00",
        "font":           "Impact",
        "size":           64,
        "bold":           0,
        "italic":         0,
        "underline":      0,
        "primary":        "&H0000FFFF",   # Yellow
        "secondary":      "&H000000FF",
        "outline_color":  "&H00000000",
        "back_color":     "&H80000000",
        "border_style":   1,
        "outline":        5,
        "shadow":         2,
        "alignment":      8,              # TOP center
        "margin_v":       80,
        "scale_x":        105,
        "scale_y":        100,
        "letter_spacing": 2,
    },

}

# =============================================================================
# HELPER FUNCTIONS — used by shorts_clipper.py
# =============================================================================

def list_styles():
    """Return list of (key, display_name, description) tuples."""
    return [(k, v["display_name"], v["description"]) for k, v in STYLES.items()]


def get_style(key):
    """Return a style dict by key. Falls back to tiktok_yellow if not found."""
    return STYLES.get(key, STYLES["tiktok_yellow"])


def get_display_names():
    """Return dict mapping key → display_name for GUI dropdowns."""
    return {k: v["display_name"] for k, v in STYLES.items()}


def style_keys():
    """Return list of valid style keys."""
    return list(STYLES.keys())


# =============================================================================
# ADD YOUR OWN STYLES BELOW THIS LINE
# Just follow the template above and add a new entry to STYLES dict.
# =============================================================================
#
# Example custom style:
#
# STYLES["my_custom"] = {
#     "display_name":   "My Custom Style",
#     "description":    "Yellow Impact at the top",
#     "preview_color":  "#FF9900",
#     "font":           "Impact",
#     "size":           68,
#     "bold":           0,
#     "italic":         0,
#     "underline":      0,
#     "primary":        "&H000099FF",
#     "secondary":      "&H000000FF",
#     "outline_color":  "&H00000000",
#     "back_color":     "&H80000000",
#     "border_style":   1,
#     "outline":        5,
#     "shadow":         2,
#     "alignment":      2,
#     "margin_v":       300,
#     "scale_x":        110,
#     "scale_y":        100,
#     "letter_spacing": 2,
# }
