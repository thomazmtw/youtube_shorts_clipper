#!/usr/bin/env python3
"""Shorts Clipper App — Hybrid AI Professional Shorts Editor.

Features:
- Premium Dark Studio Theme with polished UI components and full MouseWheel/Touchpad window scrolling.
- Caption Style Dropdown + synchronized interactive visual card carousel.
- Hybrid AI Architecture: Ollama (Primary Local Brain) + Google Gemini (Visual Assistant).
- Faster-Whisper local speech recognition (English, Malayalam, Auto-detect).
- Sentence-boundary aware cutting (never chops mid-sentence).
- AI Director Plan with punch-in zooms, jump cuts, and highlighted keywords.
- 5 Professional Editing Styles: Viral Podcast, Cinematic, Fast Viral, Educational, Storytelling.
- Dynamic ASS caption styling & logo watermark branding with live 9:16 phone mockup.
- Generated Shorts list with individual playback and export options.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional

import shorts_clipper as core
import caption_styles as _cs
import branding as _br
import ollama_client
import gemini_client
import ai_director
import ffmpeg_director

# Optional Pillow for high-quality logo and preview rendering
try:
    from PIL import Image, ImageTk  # type: ignore
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False
    Image = None    # type: ignore
    ImageTk = None  # type: ignore

_STYLE_MAP       = _cs.STYLES
_STYLE_KEYS      = _cs.style_keys()
_DISPLAY_NAMES   = _cs.get_display_names()

_BR_DEFAULT = _br.get_config()
_BR_POSITIONS = list(_br.POSITION_OPTIONS.keys())
_BR_POS_LABELS = _br.POSITION_OPTIONS

STYLES_FILE   = Path(__file__).parent / "caption_styles.py"
BRANDING_FILE = Path(__file__).parent / "branding.py"


# ═════════════════════════════════════════════════════════════════════════════
#  Caption Style Card Strip
# ═════════════════════════════════════════════════════════════════════════════
class CaptionStylePicker(ttk.Frame):
    """Scrollable row of styled cards. Calls on_change(key) when selection changes."""

    CARD_W = 104
    CARD_H = 60
    SWATCH_H = 36

    def __init__(self, parent, style_var: tk.StringVar, on_change=None, **kw):
        super().__init__(parent, **kw)
        self.style_var = style_var
        self.on_change = on_change
        self._cards = {}
        self._selected = style_var.get()
        self._build()
        self._select(self._selected, notify=False)

    def _build(self):
        self.canvas = tk.Canvas(self, height=self.CARD_H + 16,
                                highlightthickness=0, bg="#161b22")
        sb = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=sb.set)
        self.canvas.pack(fill="x")
        sb.pack(fill="x")

        self.inner = tk.Frame(self.canvas, bg="#161b22")
        self._win  = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>",
                        lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<MouseWheel>", self._on_wheel)

        for key in ["none"] + _STYLE_KEYS:
            self._make_card(key)

    def _on_wheel(self, event):
        delta = getattr(event, "delta", 0) or 0
        if delta:
            units = -1 if delta > 0 else 1
            self.canvas.xview_scroll(units, "units")

    def _make_card(self, key):
        W, H, SH = self.CARD_W, self.CARD_H, self.SWATCH_H
        frm = tk.Frame(self.inner, bg="#21262d", cursor="hand2",
                       relief="flat", padx=3, pady=3)
        frm.pack(side="left", padx=4, pady=4)

        sw_bg = self._swatch_bg(key)
        cv = tk.Canvas(frm, width=W, height=SH, highlightthickness=1,
                       highlightbackground="#30363d", bg=sw_bg)
        cv.pack()
        cv.create_text(W // 2, SH // 2, text="Aa",
                       font=("Arial", 13, "bold"),
                       fill=self._swatch_fg(key), anchor="center")

        display = "No Captions" if key == "none" else _DISPLAY_NAMES.get(key, key)
        # Clean title for card label
        display_clean = display.split()[0] + (" " + display.split()[1] if len(display.split()) > 1 else "")
        short = (display_clean[:14] + "…") if len(display_clean) > 15 else display_clean
        lbl = tk.Label(frm, text=short, bg="#21262d", fg="#c9d1d9",
                       font=("Segoe UI", 8), wraplength=W, justify="center")
        lbl.pack(fill="x", pady=(2, 0))

        for w in (frm, cv, lbl):
            w.bind("<Button-1>", lambda e, k=key: self._select(k))

        self._cards[key] = dict(frame=frm, canvas=cv, label=lbl)

    def _select(self, key, notify=True, **kwargs):
        if self._selected in self._cards:
            p = self._cards[self._selected]
            p["frame"].config(bg="#21262d")
            p["canvas"].config(highlightbackground="#30363d", highlightthickness=1)
            p["label"].config(bg="#21262d", fg="#8b949e")

        self._selected = key
        self.style_var.set(key)

        if key in self._cards:
            c = self._cards[key]
            hl = "#1f3a5f" if key != "none" else "#2b303c"
            c["frame"].config(bg=hl)
            c["canvas"].config(highlightbackground="#38bdf8", highlightthickness=2)
            c["label"].config(bg=hl, fg="#ffffff")

        if notify and self.on_change:
            self.on_change(key)

    def select_key(self, key, notify=True):
        """Programmatically select a style key (e.g. from dropdown)."""
        self._select(key, notify=notify)

    @staticmethod
    def _swatch_bg(key):
        if key == "none": return "#21262d"
        return _STYLE_MAP.get(key, {}).get("preview_color", "#38bdf8")

    @staticmethod
    def _swatch_fg(key):
        if key == "none": return "#484f58"
        return _STYLE_MAP.get(key, {}).get("preview_text", "#FFFFFF")


# ═════════════════════════════════════════════════════════════════════════════
#  Live Preview (Subtitles + Logo in 9:16 Frame)
# ═════════════════════════════════════════════════════════════════════════════
class UnifiedPreview(ttk.Frame):
    """Draws a scaled 9:16 phone mockup showing subtitle style and logo watermark."""

    PW = 140
    PH = 248
    BORDER = 4

    def __init__(self, parent, style_var, size_var,
                 logo_enabled_var, logo_path_var,
                 logo_pos_var, logo_size_var, logo_opacity_var,
                 karaoke_var=None,
                 pos_var=None, margin_var=None,
                 **kw):
        super().__init__(parent, **kw)
        self.style_var        = style_var
        self.size_var         = size_var
        self.logo_enabled     = logo_enabled_var
        self.logo_path_var    = logo_path_var
        self.logo_pos_var     = logo_pos_var
        self.logo_size_var    = logo_size_var
        self.logo_opacity_var = logo_opacity_var
        self.karaoke_var      = karaoke_var
        self.pos_var          = pos_var
        self.margin_var       = margin_var
        self._logo_tk         = None
        self._refresh_job     = None

        self._build()
        self._bind_all()
        self.after(80, self.refresh)

    def _build(self):
        ttk.Label(self, text="📱 Live 9:16 Preview", font=("Segoe UI", 9, "bold")).pack(pady=(0, 2))
        self.cv = tk.Canvas(self, width=self.PW, height=self.PH,
                            bg="#0d1117", highlightthickness=1,
                            highlightbackground="#30363d")
        self.cv.pack(padx=2, pady=(1, 2))

        b = self.BORDER
        # Phone body
        self.cv.create_rectangle(b, b, self.PW - b, self.PH - b,
                                 fill="#161b22", outline="#30363d", width=2)
        # Phone top speaker bar
        self.cv.create_line(self.PW // 2 - 16, b + 5, self.PW // 2 + 16, b + 5, fill="#484f58", width=2)

        # Caption backing box
        self._cap_bar = self.cv.create_rectangle(
            b + 2, self.PH - 54, self.PW - b - 2, self.PH - 14,
            fill="#1c2128", outline="")
        self._cap_text = self.cv.create_text(
            self.PW // 2, self.PH - 34,
            text="SAMPLE CAPTION\nTEXT", anchor="center",
            font=("Arial", 8, "bold"), fill="#FFFF00",
            width=self.PW - 12)

        self._logo_img_id = self.cv.create_image(0, 0, anchor="nw")
        self._logo_rect   = self.cv.create_rectangle(0, 0, 0, 0,
                                fill="#21262d", outline="#484f58")
        self._logo_lbl    = self.cv.create_text(0, 0, text="",
                                font=("Arial", 7, "bold"), fill="#8b949e")

    def _bind_all(self):
        def _schedule_refresh(*_):
            if self._refresh_job is not None:
                try:
                    self.after_cancel(self._refresh_job)
                except Exception:
                    pass
            self._refresh_job = self.after(25, self.refresh)

        vars_to_watch = [
            self.style_var, self.size_var,
            self.logo_enabled, self.logo_path_var,
            self.logo_pos_var, self.logo_size_var,
            self.logo_opacity_var
        ]
        if self.karaoke_var:
            vars_to_watch.append(self.karaoke_var)
        if self.pos_var:
            vars_to_watch.append(self.pos_var)
        if self.margin_var:
            vars_to_watch.append(self.margin_var)

        for v in vars_to_watch:
            try:
                v.trace_add("write", _schedule_refresh)
            except Exception:
                pass

    def refresh(self):
        self._refresh_job = None
        self._draw_caption()
        self._draw_logo()

    def _draw_caption(self):
        b = self.BORDER
        key = self.style_var.get()
        if key == "none":
            self.cv.coords(self._cap_bar, b + 2, self.PH - 54, self.PW - b - 2, self.PH - 14)
            self.cv.coords(self._cap_text, self.PW // 2, self.PH - 34)
            self.cv.itemconfig(self._cap_text, text="(captions disabled)",
                               fill="#484f58", font=("Segoe UI", 7, "italic"))
            self.cv.itemconfig(self._cap_bar, fill="#161b22")
            return

        st = _STYLE_MAP.get(key, {})
        fg = st.get("preview_color", "#FFFF00")
        bg = "#11161d"

        slider_sz = self.size_var.get()
        base_sz   = slider_sz if slider_sz and slider_sz > 0 else st.get("size", 60)
        font_sz   = max(7, min(13, int(base_sz * (self.PH / 1920.0) * 1.5)))
        weight    = "bold" if st.get("bold", -1) != 0 else "normal"
        slant     = "italic" if st.get("italic", 0) else "roman"

        # Calculate dynamic vertical position & margin
        pos = self.pos_var.get() if self.pos_var else "bottom"
        margin_v = self.margin_var.get() if self.margin_var else 300

        # Scale ASS pixel margin to preview canvas (PH = 248)
        scaled_margin = int(margin_v * (self.PH / 1920.0))

        if pos == "top":
            center_y = max(20, min(self.PH - 20, b + 14 + scaled_margin))
        elif pos == "middle":
            center_y = self.PH // 2
        else:  # bottom
            center_y = max(20, min(self.PH - 20, self.PH - b - 14 - scaled_margin))

        box_h = font_sz * 2 + 10
        half_h = max(10, box_h // 2)
        y1 = max(b + 2, center_y - half_h)
        y2 = min(self.PH - b - 2, center_y + half_h)

        self.cv.coords(self._cap_bar, b + 2, y1, self.PW - b - 2, y2)
        self.cv.coords(self._cap_text, self.PW // 2, center_y)

        self.cv.itemconfig(self._cap_bar, fill=bg)
        is_k = self.karaoke_var.get() if self.karaoke_var else True
        if is_k:
            display_text = "SAMPLE CAPTION\n(✨ KARAOKE POP)"
        else:
            display_text = "SAMPLE CAPTION\nTEXT"

        self.cv.itemconfig(self._cap_text,
                           text=display_text,
                           fill=fg,
                           font=(st.get("font", "Arial"), font_sz, f"{weight} {slant}".strip()))

    def _draw_logo(self):
        b = self.BORDER
        if not self.logo_enabled.get():
            self.cv.coords(self._logo_img_id, 0, 0)
            self.cv.itemconfig(self._logo_img_id, image="")
            self.cv.coords(self._logo_rect, 0, 0, 0, 0)
            self.cv.itemconfig(self._logo_lbl, text="")
            return

        logo_path = self.logo_path_var.get().strip().strip('"').strip("'")
        pos       = self.logo_pos_var.get()
        size_pct  = max(3, min(50, self.logo_size_var.get()))
        opacity   = max(0.0, min(1.0, self.logo_opacity_var.get()))

        screen_w = self.PW - 2 * b
        lw = max(12, int(screen_w * size_pct / 100))
        lh = lw
        pad = max(3, int(25 * self.PW / 1080))

        loaded = False
        if logo_path and Path(logo_path).exists():
            try:
                if _HAS_PIL and Image and ImageTk:
                    img = Image.open(logo_path).convert("RGBA")
                    ratio = img.height / max(1, img.width)
                    lh = max(6, int(lw * ratio))
                    resample_mode = getattr(getattr(Image, "Resampling", Image), "LANCZOS", 1)
                    img = img.resize((lw, lh), resample_mode)
                    if opacity < 0.99:
                        r, g, bch, a = img.split()
                        a = a.point(lambda x: int(x * opacity))
                        img.putalpha(a)
                    self._logo_tk = ImageTk.PhotoImage(img, master=self.cv)
                    loaded = True
                else:
                    ph = tk.PhotoImage(master=self.cv, file=logo_path)
                    ow, oh = ph.width(), ph.height()
                    if ow > lw:
                        factor = max(1, ow // lw)
                        ph = ph.subsample(factor, factor)
                    lh = ph.height()
                    self._logo_tk = ph
                    loaded = True
            except Exception:
                loaded = False

        inner_x1, inner_y1 = b + pad, b + pad + 6
        inner_x2, inner_y2 = self.PW - b - pad, self.PH - b - pad

        pos_map = {
            "top_left":   (inner_x1,              inner_y1),
            "top_center": ((self.PW-lw)//2,        inner_y1),
            "top_right":  (inner_x2 - lw,          inner_y1),
            "mid_left":   (inner_x1,              (self.PH-lh)//2),
            "center":     ((self.PW-lw)//2,         (self.PH-lh)//2),
            "mid_right":  (inner_x2 - lw,          (self.PH-lh)//2),
            "bot_left":   (inner_x1,               inner_y2 - lh),
            "bot_center": ((self.PW-lw)//2,         inner_y2 - lh),
            "bot_right":  (inner_x2 - lw,          inner_y2 - lh),
        }
        x, y = pos_map.get(pos, (inner_x2 - lw, inner_y1))

        if loaded and self._logo_tk:
            try:
                self.cv.coords(self._logo_img_id, x, y)
                self.cv.itemconfig(self._logo_img_id, image=self._logo_tk)
                self.cv.coords(self._logo_rect, 0, 0, 0, 0)
                self.cv.itemconfig(self._logo_lbl, text="")
                return
            except Exception:
                pass

        # Placeholder box
        self.cv.itemconfig(self._logo_img_id, image="")
        self.cv.coords(self._logo_rect, x, y, x + lw, y + lh)
        cx, cy = x + lw // 2, y + lh // 2
        self.cv.coords(self._logo_lbl, cx, cy)
        self.cv.itemconfig(self._logo_lbl, text="LOGO")


# ═════════════════════════════════════════════════════════════════════════════
#  Main Application Window (Modern Dark Studio Theme)
# ═════════════════════════════════════════════════════════════════════════════
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Shorts Clipper — Hybrid AI Professional Shorts Editor")
        self.geometry("1040x920")
        self.minsize(880, 700)
        self.configure(bg="#0d1117")

        self.log_q     = queue.Queue()
        self.worker    = None
        self.stop_flag = threading.Event()
        self.proc      = None

        # ── State Variables ──────────────────────────────────────────────────
        self.src             = tk.StringVar()
        self.length          = tk.IntVar(value=35)
        self.maxclips        = tk.IntVar(value=5)
        self.mode            = tk.StringVar(value="smart")
        self.fit             = tk.StringVar(value="crop")
        default_out          = (Path(__file__).parent / "clips").resolve()
        self.outdir          = tk.StringVar(value=str(default_out))

        # AI Professional Editor Variables
        self.ai_mode         = tk.StringVar(value="hybrid")   # hybrid, ollama, gemini, rule_based
        self.editing_style   = tk.StringVar(value="viral_podcast")
        self.ollama_model    = tk.StringVar(value="llama3.2")
        self.ollama_status   = tk.StringVar(value="Checking Ollama...")
        self.gemini_enabled  = tk.BooleanVar(value=bool(gemini_client.get_api_key()))
        self.gemini_model    = tk.StringVar(value="gemini-3.5-flash-lite")
        self.gemini_key_v    = tk.StringVar(value=gemini_client.get_api_key())
        self.gemini_status   = tk.StringVar(value="Configured" if gemini_client.get_api_key() else "No Key")
        self.language        = tk.StringVar(value="auto")     # auto, en, ml

        # Subtitle Variables
        self.subtitle_style  = tk.StringVar(value="tiktok_yellow")
        self.caption_size    = tk.IntVar(value=0)  # 0 = style default
        self.caption_pos     = tk.StringVar(value="bottom")  # bottom, middle, top
        self.caption_margin_v = tk.IntVar(value=300) # vertical margin in px
        self.karaoke_enabled = tk.BooleanVar(value=True)  # Dynamic word-by-word karaoke animation

        # Branding Variables
        self.logo_enabled    = tk.BooleanVar(value=_BR_DEFAULT.get("enabled", False))
        self.logo_path_v     = tk.StringVar(value=_BR_DEFAULT.get("path", ""))
        self.logo_pos_v      = tk.StringVar(value=_BR_DEFAULT.get("position", "top_right"))
        self.logo_size_v     = tk.IntVar(value=_BR_DEFAULT.get("size_pct", 15))
        self.logo_opacity_v  = tk.DoubleVar(value=_BR_DEFAULT.get("opacity", 1.0))

        # Build display-to-key and key-to-display maps for caption dropdown
        self._display_to_key = {"No Captions": "none"}
        self._key_to_display = {"none": "No Captions"}
        for k in _STYLE_KEYS:
            dn = _DISPLAY_NAMES.get(k, k.replace("_", " ").title())
            self._display_to_key[dn] = k
            self._key_to_display[k]  = dn

        # Results state
        self.generated_shorts: List[Dict[str, Any]] = []

        self._build()
        self._drain_log()
        self._async_check_services()

    # ── UI Construction ───────────────────────────────────────────────────────
    def _build(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        # Dark Studio Palette
        BG_MAIN = "#0d1117"
        BG_CARD = "#161b22"
        BORDER  = "#30363d"
        TEXT_PR = "#f0f6fc"
        TEXT_SEC = "#8b949e"
        ACCENT  = "#38bdf8"
        BTN_BG  = "#21262d"

        style.configure(".", background=BG_CARD, foreground=TEXT_PR, fieldbackground="#21262d")
        style.configure("TFrame", background=BG_CARD)
        style.configure("TLabel", background=BG_CARD, foreground=TEXT_PR, font=("Segoe UI", 9))
        style.configure("TLabelframe", background=BG_CARD, foreground=TEXT_SEC, bordercolor=BORDER)
        style.configure("TLabelframe.Label", background=BG_CARD, foreground=ACCENT, font=("Segoe UI", 9, "bold"))

        style.configure("TButton", padding=(8, 4), background=BTN_BG, foreground=TEXT_PR, font=("Segoe UI", 9))
        style.map("TButton",
                  background=[("active", "#30363d"), ("pressed", "#1f242c")],
                  foreground=[("active", "#ffffff")])

        style.configure("Accent.TButton", padding=(12, 6), font=("Segoe UI", 10, "bold"),
                        background="#0284c7", foreground="#ffffff")
        style.map("Accent.TButton",
                  background=[("active", "#0369a1"), ("pressed", "#075985")])

        style.configure("Stop.TButton", padding=(8, 6), font=("Segoe UI", 9, "bold"),
                        background="#b91c1c", foreground="#ffffff")
        style.map("Stop.TButton",
                  background=[("active", "#991b1b"), ("pressed", "#7f1d1d")])

        style.configure("TRadiobutton", background=BG_CARD, foreground=TEXT_PR, font=("Segoe UI", 9))
        style.configure("TCheckbutton", background=BG_CARD, foreground=TEXT_PR, font=("Segoe UI", 9))
        style.configure("TEntry", fieldbackground="#21262d", foreground=TEXT_PR, insertcolor="#ffffff")
        style.configure("TSpinbox", fieldbackground="#21262d", foreground=TEXT_PR)
        style.configure("TCombobox", fieldbackground="#21262d", foreground=TEXT_PR)
        style.configure("TNotebook", background=BG_CARD, tabmargins=[2, 4, 2, 0])
        style.configure("TNotebook.Tab", background="#21262d", foreground=TEXT_SEC, padding=[14, 6], font=("Segoe UI", 9, "bold"))
        style.map("TNotebook.Tab",
                  background=[("selected", "#1f3a5f")],
                  foreground=[("selected", "#38bdf8")])

        style.configure("Treeview", background="#161b22", foreground=TEXT_PR, fieldbackground="#161b22", rowheight=24, font=("Segoe UI", 8))
        style.configure("Treeview.Heading", background="#21262d", foreground=ACCENT, font=("Segoe UI", 8, "bold"))
        style.map("Treeview", background=[("selected", "#1f3a5f")], foreground=[("selected", "#ffffff")])

        # ── Master Scrollable Container ───────────────────────────────────────
        self.main_canvas = tk.Canvas(self, bg=BG_MAIN, highlightthickness=0)
        self.v_scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.main_canvas.yview)
        self.main_canvas.configure(yscrollcommand=self.v_scrollbar.set)

        self.v_scrollbar.pack(side="right", fill="y")
        self.main_canvas.pack(side="left", fill="both", expand=True)

        self.scrollable_frame = ttk.Frame(self.main_canvas)
        self._canvas_win = self.main_canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")

        def _on_frame_configure(event):
            self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all"))

        def _on_canvas_configure(event):
            self.main_canvas.itemconfig(self._canvas_win, width=event.width)

        self.scrollable_frame.bind("<Configure>", _on_frame_configure)
        self.main_canvas.bind("<Configure>", _on_canvas_configure)

        # Smooth mouse wheel scrolling
        self.bind_all("<MouseWheel>", self._on_mousewheel)

        P = dict(padx=12, pady=4)
        main = self.scrollable_frame

        # ── Header Banner ─────────────────────────────────────────────────────
        header = tk.Frame(main, bg="#161b22", padx=14, pady=8, highlightthickness=1, highlightbackground="#30363d")
        header.pack(fill="x", padx=12, pady=(8, 4))

        t_box = tk.Frame(header, bg="#161b22")
        t_box.pack(side="left")
        tk.Label(t_box, text="🎬 SHORTS CLIPPER AI", font=("Segoe UI", 13, "bold"),
                 bg="#161b22", fg="#38bdf8").pack(anchor="w")
        tk.Label(t_box, text="Hybrid AI Professional Video Editor • Ollama (Local Brain) + Google Gemini (Visual AI)",
                 font=("Segoe UI", 8), bg="#161b22", fg="#8b949e").pack(anchor="w")

        pills = tk.Frame(header, bg="#161b22")
        pills.pack(side="right")
        self.ollama_pill = tk.Label(pills, textvariable=self.ollama_status, font=("Segoe UI", 8, "bold"),
                                    bg="#1f3a5f", fg="#38bdf8", padx=10, pady=4, relief="flat")
        self.ollama_pill.pack(side="right", padx=(6, 0))

        self.gemini_pill = tk.Label(pills, textvariable=self.gemini_status, font=("Segoe UI", 8, "bold"),
                                    bg="#1a2e26", fg="#34d399", padx=10, pady=4, relief="flat")
        self.gemini_pill.pack(side="right")

        # ── 1. Video Source & Output Card ─────────────────────────────────────
        src_card = ttk.LabelFrame(main, text="1. Video Input & Output Destination")
        src_card.pack(fill="x", **P)

        row_s = ttk.Frame(src_card); row_s.pack(fill="x", padx=10, pady=(6, 3))
        ttk.Label(row_s, text="Video Source:", font=("Segoe UI", 9, "bold"), width=13).pack(side="left")
        ttk.Entry(row_s, textvariable=self.src).pack(side="left", fill="x", expand=True, padx=(4, 6))
        ttk.Button(row_s, text="📁 Browse…", command=self._browse).pack(side="left")

        row_o = ttk.Frame(src_card); row_o.pack(fill="x", padx=10, pady=(3, 6))
        ttk.Label(row_o, text="Save Clips To:", font=("Segoe UI", 9, "bold"), width=13).pack(side="left")
        ttk.Entry(row_o, textvariable=self.outdir).pack(side="left", fill="x", expand=True, padx=(4, 6))
        ttk.Button(row_o, text="📂 Change…", command=self._pick_out).pack(side="left")

        # ── 2. Notebook Settings (AI Director vs Classic) ─────────────────────
        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill="x", **P)

        tab_ai = ttk.Frame(self.notebook)
        tab_classic = ttk.Frame(self.notebook)
        self.notebook.add(tab_ai, text="  🧠 AI Professional Editor (Ollama + Gemini)  ")
        self.notebook.add(tab_classic, text="  ⚡ Classic Rule-Based Clipper  ")

        self._build_ai_tab(tab_ai)
        self._build_classic_tab(tab_classic)

        # ── 3. Shared Clip Parameters Row ────────────────────────────────────
        param_card = ttk.LabelFrame(main, text="3. Target Clip Parameters & Framing")
        param_card.pack(fill="x", **P)

        p_row = ttk.Frame(param_card); p_row.pack(fill="x", padx=10, pady=6)
        ttk.Label(p_row, text="Target Duration:").pack(side="left", padx=(0, 4))
        ttk.Spinbox(p_row, from_=15, to=60, textvariable=self.length, width=4).pack(side="left", padx=(0, 10))
        ttk.Label(p_row, text="s").pack(side="left", padx=(0, 16))

        ttk.Label(p_row, text="Max Clips:").pack(side="left", padx=(0, 4))
        ttk.Spinbox(p_row, from_=1, to=20, textvariable=self.maxclips, width=4).pack(side="left", padx=(0, 20))

        ttk.Label(p_row, text="Framing Template:").pack(side="left", padx=(0, 6))
        for txt, val in [("Center Crop (9:16)", "crop"), ("Blur BG", "blur"), ("Split Screen", "split")]:
            ttk.Radiobutton(p_row, text=txt, variable=self.fit, value=val).pack(side="left", padx=(0, 10))

        # ── 4. Caption Style Section (Dropdown + Card Carousel) ──────────────
        cap_frame = ttk.LabelFrame(main, text="4. Subtitles & Dynamic Captions Studio")
        cap_frame.pack(fill="x", **P)

        drop_row = ttk.Frame(cap_frame)
        drop_row.pack(fill="x", padx=10, pady=(6, 3))

        ttk.Label(drop_row, text="Caption Preset Dropdown:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 6))

        combo_vals = ["No Captions"] + [_DISPLAY_NAMES.get(k, k.replace("_", " ").title()) for k in _STYLE_KEYS]
        self.caption_combo = ttk.Combobox(drop_row, values=combo_vals, state="readonly", width=22)
        self.caption_combo.set(self._key_to_display.get(self.subtitle_style.get(), "TikTok Yellow 🔥"))
        self.caption_combo.pack(side="left", padx=(0, 14))
        self.caption_combo.bind("<<ComboboxSelected>>", self._on_combo_style_selected)

        ttk.Label(drop_row, text="Font Size:").pack(side="left", padx=(8, 4))
        self._size_lbl = ttk.Label(drop_row, text="Style default", width=12)
        self._size_lbl.pack(side="left", padx=(0, 4))
        ttk.Scale(drop_row, from_=20, to=120, orient="horizontal",
                  variable=self.caption_size, command=self._on_size_slide).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(drop_row, text="Reset", width=6, command=self._reset_size).pack(side="left", padx=(2, 6))
        ttk.Button(drop_row, text="✏️ Edit Styles", command=lambda: self._open_file(STYLES_FILE)).pack(side="right")

        # Dynamic Karaoke & Options Row
        k_row = ttk.Frame(cap_frame)
        k_row.pack(fill="x", padx=10, pady=(1, 3))
        ttk.Checkbutton(
            k_row,
            text="✨ Dynamic Word-by-Word Karaoke (Alex Hormozi / Viral Pop Highlight)",
            variable=self.karaoke_enabled
        ).pack(side="left")
        ttk.Label(k_row, text="💡 Words light up frame-by-frame in real-time as they are spoken",
                  font=("Segoe UI", 8, "italic"), foreground="#8b949e").pack(side="left", padx=(12, 0))

        # Position & Vertical Margin Controls Row
        pos_row = ttk.Frame(cap_frame)
        pos_row.pack(fill="x", padx=10, pady=(2, 4))

        ttk.Label(pos_row, text="Caption Position:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 6))
        for pos_txt, pos_val in [("Bottom (Standard)", "bottom"), ("Middle / Center", "middle"), ("Top", "top")]:
            ttk.Radiobutton(
                pos_row, text=pos_txt, variable=self.caption_pos, value=pos_val,
                command=self._on_pos_changed
            ).pack(side="left", padx=(0, 8))

        ttk.Label(pos_row, text="Vertical Offset:").pack(side="left", padx=(10, 4))
        self._margin_lbl = ttk.Label(pos_row, text=f"{self.caption_margin_v.get()} px", width=8)
        self._margin_lbl.pack(side="left", padx=(0, 4))
        ttk.Scale(
            pos_row, from_=100, to=900, orient="horizontal",
            variable=self.caption_margin_v, command=self._on_margin_slide
        ).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(pos_row, text="Reset", width=6, command=self._reset_pos).pack(side="left", padx=(2, 6))

        self.style_picker = CaptionStylePicker(
            cap_frame, style_var=self.subtitle_style,
            on_change=self._on_style_card_clicked
        )
        self.style_picker.pack(fill="x", padx=8, pady=(2, 6))

        # ── 5. Branding & Preview Side-by-Side ────────────────────────────────
        bottom_split = ttk.Frame(main)
        bottom_split.pack(fill="x", **P)

        br_frame = ttk.LabelFrame(bottom_split, text="5. Logo Watermark Branding")
        br_frame.pack(side="left", fill="both", expand=True, padx=(0, 8))

        chk_top = ttk.Frame(br_frame)
        chk_top.pack(fill="x", padx=10, pady=(6, 4))

        self.branding_chk = ttk.Checkbutton(
            chk_top,
            text="Enable Custom PNG Logo Watermark (Click to expand options)",
            variable=self.logo_enabled,
            command=self._on_logo_toggle
        )
        self.branding_chk.pack(side="left")

        # Collapsible Panel (pops down when checkbox is clicked)
        self.branding_panel = ttk.Frame(br_frame)

        ttk.Label(self.branding_panel, text="Logo File:").grid(row=0, column=0, sticky="w", padx=4, pady=3)
        f_logo = ttk.Frame(self.branding_panel); f_logo.grid(row=0, column=1, sticky="ew", padx=(0, 4))
        self.branding_panel.columnconfigure(1, weight=1)
        ttk.Entry(f_logo, textvariable=self.logo_path_v).pack(side="left", fill="x", expand=True)
        ttk.Button(f_logo, text="📁", width=3, command=self._browse_logo).pack(side="left", padx=(4, 0))

        ttk.Label(self.branding_panel, text="Position:").grid(row=1, column=0, sticky="nw", padx=4, pady=4)
        pos_grid = ttk.Frame(self.branding_panel)
        pos_grid.grid(row=1, column=1, sticky="w", pady=2)
        layout = [
            ["top_left", "top_center", "top_right"],
            ["mid_left", "center",     "mid_right"],
            ["bot_left", "bot_center", "bot_right"],
        ]
        for r, row_keys in enumerate(layout):
            for c, pos_key in enumerate(row_keys):
                short_lbl = _BR_POS_LABELS.get(pos_key, pos_key).replace("Top-", "T-").replace("Bottom-", "B-").replace("Middle-", "M-")
                ttk.Radiobutton(pos_grid, text=short_lbl, variable=self.logo_pos_v,
                                value=pos_key).grid(row=r, column=c, padx=3, pady=1, sticky="w")

        ttk.Label(self.branding_panel, text="Size:").grid(row=2, column=0, sticky="w", padx=4, pady=3)
        f_sz = ttk.Frame(self.branding_panel); f_sz.grid(row=2, column=1, sticky="ew", padx=(0, 4))
        self.logo_size_lbl = ttk.Label(f_sz, text=f"{self.logo_size_v.get()}%", width=5)
        self.logo_size_lbl.pack(side="left")
        ttk.Scale(f_sz, from_=3, to=40, orient="horizontal",
                  variable=self.logo_size_v, command=lambda v: self.logo_size_lbl.config(text=f"{int(float(v))}%")).pack(side="left", fill="x", expand=True)

        ttk.Label(self.branding_panel, text="Opacity:").grid(row=3, column=0, sticky="w", padx=4, pady=(3, 6))
        f_op = ttk.Frame(self.branding_panel); f_op.grid(row=3, column=1, sticky="ew", padx=(0, 4), pady=(0, 4))
        self.logo_op_lbl = ttk.Label(f_op, text=f"{int(self.logo_opacity_v.get()*100)}%", width=5)
        self.logo_op_lbl.pack(side="left")
        ttk.Scale(f_op, from_=0.1, to=1.0, orient="horizontal",
                  variable=self.logo_opacity_v, command=lambda v: self.logo_op_lbl.config(text=f"{int(float(v)*100)}%")).pack(side="left", fill="x", expand=True)

        if self.logo_enabled.get():
            self.branding_chk.config(text="☑️ Custom PNG Logo Watermark Enabled (Click to collapse)")
            self.branding_panel.pack(fill="x", padx=10, pady=(2, 6))

        # 9:16 Mockup Preview Frame
        prev_card = ttk.LabelFrame(bottom_split, text="Live Phone Preview")
        prev_card.pack(side="right", fill="y", anchor="n")
        self.preview = UnifiedPreview(
            prev_card,
            style_var       = self.subtitle_style,
            size_var        = self.caption_size,
            logo_enabled_var= self.logo_enabled,
            logo_path_var   = self.logo_path_v,
            logo_pos_var    = self.logo_pos_v,
            logo_size_var   = self.logo_size_v,
            logo_opacity_var= self.logo_opacity_v,
            karaoke_var     = self.karaoke_enabled,
            pos_var         = self.caption_pos,
            margin_var      = self.caption_margin_v,
        )
        self.preview.pack(padx=6, pady=4)

        # ── 6. Generated Moments / Shorts Table ───────────────────────────────
        moments_frame = ttk.LabelFrame(main, text="6. AI Generated Moments & Shorts Export List")
        moments_frame.pack(fill="x", **P)

        tree_scroll = ttk.Scrollbar(moments_frame, orient="vertical")
        self.tree = ttk.Treeview(
            moments_frame,
            columns=("#", "Title", "Hook", "Duration", "Virality", "Status"),
            show="headings",
            height=4,
            yscrollcommand=tree_scroll.set
        )
        tree_scroll.config(command=self.tree.yview)

        self.tree.heading("#", text="#", anchor="center")
        self.tree.heading("Title", text="Short Title", anchor="w")
        self.tree.heading("Hook", text="Opening Hook", anchor="w")
        self.tree.heading("Duration", text="Duration", anchor="center")
        self.tree.heading("Virality", text="Virality", anchor="center")
        self.tree.heading("Status", text="Status / Output File", anchor="w")

        self.tree.column("#", width=35, anchor="center")
        self.tree.column("Title", width=220, anchor="w")
        self.tree.column("Hook", width=260, anchor="w")
        self.tree.column("Duration", width=65, anchor="center")
        self.tree.column("Virality", width=70, anchor="center")
        self.tree.column("Status", width=180, anchor="w")

        self.tree.pack(side="left", fill="x", expand=True, padx=(6, 0), pady=4)
        tree_scroll.pack(side="left", fill="y", padx=(0, 6), pady=4)

        tree_btns = ttk.Frame(moments_frame)
        tree_btns.pack(side="right", fill="y", padx=6, pady=4)
        ttk.Button(tree_btns, text="▶ Play Selected", command=self._play_selected_short).pack(fill="x", pady=2)
        ttk.Button(tree_btns, text="📂 Open Folder", command=self._open_out).pack(fill="x", pady=2)

        # ── 7. Action Bar & Progress ──────────────────────────────────────────
        action_card = ttk.Frame(main)
        action_card.pack(fill="x", padx=12, pady=(8, 2))

        self.start_btn = ttk.Button(action_card, text="🚀  START AI CLIPPING", command=self._start, style="Accent.TButton")
        self.start_btn.pack(side="left", ipadx=12, ipady=4)
        self.stop_btn = ttk.Button(action_card, text="⏹  Stop", command=self._stop, state="disabled", style="Stop.TButton")
        self.stop_btn.pack(side="left", padx=8, ipady=4)

        ttk.Button(action_card, text="📂 Open Output Folder", command=self._open_out).pack(side="right")
        ttk.Button(action_card, text="🔄 Reload Styles", command=self._reload_styles).pack(side="right", padx=6)

        self.bar = ttk.Progressbar(main, mode="determinate")
        self.bar.pack(fill="x", padx=12, pady=(6, 2))

        self.status = tk.StringVar(value="Ready. Select video source and click 'START AI CLIPPING'.")
        ttk.Label(main, textvariable=self.status, font=("Segoe UI", 9, "italic")).pack(anchor="w", padx=14, pady=(0, 4))

        # ── 8. Real-Time Log Console ──────────────────────────────────────────
        logf = ttk.LabelFrame(main, text="7. AI Activity & Reasoning Console")
        logf.pack(fill="both", expand=True, padx=12, pady=(2, 12))

        self.log = tk.Text(logf, height=7, state="disabled", wrap="word",
                           font=("Consolas", 9), bg="#0d1117", fg="#c9d1d9",
                           highlightthickness=1, highlightbackground="#30363d")
        sb2 = ttk.Scrollbar(logf, command=self.log.yview)
        self.log.configure(yscrollcommand=sb2.set)
        self.log.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        sb2.pack(side="right", fill="y", padx=(0, 6), pady=6)

    # ── Mouse Wheel Event Handler ─────────────────────────────────────────────
    def _on_mousewheel(self, event):
        """Scroll the main window smoothly unless over a scrollable inner widget."""
        widget = self.winfo_containing(event.x_root, event.y_root)
        if widget:
            if widget == self.log or (hasattr(self, 'style_picker') and widget == self.style_picker.canvas):
                return
            if hasattr(self, 'tree') and widget == self.tree:
                return

        bbox = self.main_canvas.bbox("all")
        if bbox:
            content_h = bbox[3] - bbox[1]
            win_h = self.main_canvas.winfo_height()
            if content_h > win_h:
                delta = getattr(event, "delta", 0) or 0
                if delta:
                    units = -1 if delta > 0 else 1
                    self.main_canvas.yview_scroll(units, "units")

    # ── Caption Dropdown <-> Card Strip Synchronization ──────────────────────
    def _on_combo_style_selected(self, event=None):
        """Called when user selects a preset from the caption dropdown."""
        disp_name = self.caption_combo.get()
        key = self._display_to_key.get(disp_name, "tiktok_yellow")
        self.subtitle_style.set(key)
        self.style_picker.select_key(key, notify=False)
        self.preview.refresh()

    def _on_style_card_clicked(self, key):
        """Called when user clicks a card in the visual picker strip."""
        disp_name = self._key_to_display.get(key, key)
        self.caption_combo.set(disp_name)
        self.preview.refresh()

    # ── AI Tab Controls ───────────────────────────────────────────────────────
    def _build_ai_tab(self, tab):
        r1 = ttk.Frame(tab); r1.pack(fill="x", padx=10, pady=(8, 4))
        ttk.Label(r1, text="AI Mode:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 8))
        for txt, val in [
            ("Hybrid (Ollama + Gemini)", "hybrid"),
            ("Ollama Only (Local AI)", "ollama"),
            ("Gemini Only (Cloud AI)", "gemini"),
            ("Rule-Based (Classic)", "rule_based")
        ]:
            ttk.Radiobutton(r1, text=txt, variable=self.ai_mode, value=val).pack(side="left", padx=(0, 12))

        r2 = ttk.Frame(tab); r2.pack(fill="x", padx=10, pady=4)
        ttk.Label(r2, text="Editing Style:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 8))
        self.style_combo = ttk.Combobox(
            r2, textvariable=self.editing_style, width=22, state="readonly",
            values=[
                "viral_podcast",
                "cinematic",
                "fast_viral",
                "educational",
                "storytelling",
            ]
        )
        self.style_combo.pack(side="left", padx=(0, 16))

        ttk.Label(r2, text="Speech Language:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 6))
        lang_combo = ttk.Combobox(
            r2, textvariable=self.language, width=12, state="readonly",
            values=["auto", "en", "ml"]
        )
        lang_combo.pack(side="left")
        ttk.Label(r2, text="(English / Malayalam / Auto)", font=("Segoe UI", 8, "italic")).pack(side="left", padx=(4, 0))

        # Row 3: Service Panels
        r3 = ttk.Frame(tab); r3.pack(fill="x", padx=10, pady=(6, 8))

        # Left: Ollama Brain
        ollama_frame = ttk.LabelFrame(r3, text="🧠 Local Ollama Brain (Primary Director)")
        ollama_frame.pack(side="left", fill="both", expand=True, padx=(0, 6))

        o_row1 = ttk.Frame(ollama_frame); o_row1.pack(fill="x", padx=8, pady=3)
        ttk.Label(o_row1, textvariable=self.ollama_status, font=("Segoe UI", 8, "bold")).pack(side="left")
        ttk.Button(o_row1, text="❓ Setup Guide", width=12, command=self._show_ollama_guide).pack(side="right")

        o_row2 = ttk.Frame(ollama_frame); o_row2.pack(fill="x", padx=8, pady=3)
        ttk.Label(o_row2, text="Model:").pack(side="left", padx=(0, 4))
        self.ollama_combo = ttk.Combobox(o_row2, textvariable=self.ollama_model, width=18)
        self.ollama_combo.pack(side="left", fill="x", expand=True)
        ttk.Button(o_row2, text="🔄 Refresh", width=9, command=self._refresh_ollama_models).pack(side="left", padx=(4, 0))

        # Right: Gemini Assistant
        gemini_frame = ttk.LabelFrame(r3, text="👁️ Google Gemini Visual Assistant (Optional Cloud)")
        gemini_frame.pack(side="right", fill="both", expand=True, padx=(6, 0))

        g_row1 = ttk.Frame(gemini_frame); g_row1.pack(fill="x", padx=8, pady=3)
        ttk.Checkbutton(g_row1, text="Enable Gemini Visual AI", variable=self.gemini_enabled).pack(side="left")
        ttk.Button(g_row1, text="⚡ Test Key", width=10, command=self._test_gemini_key).pack(side="right")

        g_row2 = ttk.Frame(gemini_frame); g_row2.pack(fill="x", padx=8, pady=3)
        ttk.Label(g_row2, text="API Key:").pack(side="left", padx=(0, 4))
        self.key_entry = ttk.Entry(g_row2, textvariable=self.gemini_key_v, show="*", width=16)
        self.key_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(g_row2, text="👁", width=3, command=self._toggle_key_visibility).pack(side="left", padx=(2, 2))
        ttk.Button(g_row2, text="💾 Save", width=6, command=self._save_gemini_key).pack(side="left")

        g_row3 = ttk.Frame(gemini_frame); g_row3.pack(fill="x", padx=8, pady=3)
        ttk.Label(g_row3, text="Model:").pack(side="left", padx=(0, 4))
        self.gemini_combo = ttk.Combobox(
            g_row3, textvariable=self.gemini_model, width=18, state="readonly",
            values=["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.7-flash"]
        )
        self.gemini_combo.pack(side="left", fill="x", expand=True)

    # ── Classic Tab Controls ──────────────────────────────────────────────────
    def _build_classic_tab(self, tab):
        c_row = ttk.Frame(tab); c_row.pack(fill="x", padx=12, pady=12)
        ttk.Label(c_row, text="Cutting Mode:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 8))
        for txt, val in [("Smart (Pauses & Energy)", "smart"),
                         ("Podcast (Dialogue & Hook)", "podcast"),
                         ("Even Chunks", "even")]:
            ttk.Radiobutton(c_row, text=txt, variable=self.mode, value=val).pack(side="left", padx=(0, 14))

    # ── Helpers & Async Service Checks ────────────────────────────────────────
    def _async_check_services(self):
        is_running = ollama_client.is_ollama_running()
        if is_running:
            models = ollama_client.list_local_models()
            self.ollama_status.set(f"🟢 Ollama Running ({len(models)} models)")
            if models:
                self.ollama_combo["values"] = models
                if self.ollama_model.get() not in models:
                    best = ollama_client.get_best_available_model() or models[0]
                    self.ollama_model.set(best)
        else:
            self.ollama_status.set("🔴 Ollama Offline (Click Setup Guide)")

        key = gemini_client.get_api_key()
        if key:
            self.gemini_status.set("🟢 Gemini Configured")
        else:
            self.gemini_status.set("⚪ No Key Configured")

    def _refresh_ollama_models(self):
        self.ollama_status.set("Checking Ollama...")
        threading.Thread(target=self._async_check_services, daemon=True).start()

    def _show_ollama_guide(self):
        guide = ollama_client.get_installation_instructions()
        win = tk.Toplevel(self)
        win.title("Ollama Setup Instructions")
        win.geometry("580x420")
        win.configure(bg="#161b22")
        txt = tk.Text(win, bg="#0d1117", fg="#c9d1d9", wrap="word", padx=10, pady=10, font=("Consolas", 10))
        txt.insert("1.0", guide)
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True)
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=6)

    def _toggle_key_visibility(self):
        cur = self.key_entry.cget("show")
        self.key_entry.config(show="" if cur == "*" else "*")

    def _save_gemini_key(self):
        k = self.gemini_key_v.get().strip()
        if not k:
            messagebox.showwarning("Empty Key", "Please enter a valid Gemini API key first.")
            return
        gemini_client.save_api_key(k)
        self.gemini_status.set("🟢 Key Saved")
        self.gemini_enabled.set(True)
        messagebox.showinfo("Gemini API Key", "Gemini API key has been securely saved!")

    def _test_gemini_key(self):
        k = self.gemini_key_v.get().strip() or gemini_client.get_api_key()
        if not k:
            messagebox.showwarning("Missing Key", "No Gemini API key provided to test.")
            return

        def _test_bg():
            self.say("⚡ Testing Google Gemini API connection...")
            try:
                res = gemini_client.test_connection(k, self.gemini_model.get())
                if isinstance(res, tuple):
                    ok, msg = res
                elif isinstance(res, dict):
                    ok = (res.get("status") == "success")
                    msg = res.get("message", "")
                else:
                    ok, msg = bool(res), str(res)

                if ok:
                    self.say(f"✅ Gemini API test successful: {msg}")
                    self.gemini_status.set("🟢 Verified Active")
                    messagebox.showinfo("Gemini Success", f"Connection verified successfully!\n\nModel: {self.gemini_model.get()}\nMessage: {msg}")
                else:
                    self.say(f"❌ Gemini connection failed: {msg}")
                    self.gemini_status.set("🔴 Key Error")
                    messagebox.showerror("Gemini Error", f"Connection failed:\n\n{msg}")
            except Exception as ex:
                self.say(f"❌ Gemini connection exception: {ex}")
                self.gemini_status.set("🔴 Error")
                messagebox.showerror("Gemini Error", f"Connection test failed with exception:\n\n{ex}")

        threading.Thread(target=_test_bg, daemon=True).start()

    def _browse(self):
        f = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=[("Video files", "*.mp4 *.mkv *.mov *.webm *.avi *.ts"), ("All files", "*.*")])
        if f: self.src.set(f)

    def _pick_out(self):
        d = filedialog.askdirectory(title="Select Output Folder")
        if d: self.outdir.set(d)

    def _open_out(self):
        d = Path(self.outdir.get())
        d.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"): os.startfile(str(d))
            elif sys.platform == "darwin":      subprocess.run(["open", str(d)])
            else:                               subprocess.run(["xdg-open", str(d)])
        except Exception as e:
            messagebox.showwarning("Open Folder Failed", str(e))

    def _browse_logo(self):
        f = filedialog.askopenfilename(
            title="Select Logo (PNG with transparency recommended)",
            filetypes=[("PNG images", "*.png"), ("All images", "*.png *.jpg *.jpeg *.webp"), ("All files", "*.*")])
        if f:
            self.logo_path_v.set(f)
            self.logo_enabled.set(True)
            self._on_logo_toggle()

    def _on_logo_toggle(self):
        if self.logo_enabled.get():
            if hasattr(self, "branding_chk"):
                self.branding_chk.config(text="☑️ Custom PNG Logo Watermark Enabled (Click to collapse)")
            if hasattr(self, "branding_panel"):
                self.branding_panel.pack(fill="x", padx=10, pady=(2, 6))
        else:
            if hasattr(self, "branding_chk"):
                self.branding_chk.config(text="Enable Custom PNG Logo Watermark (Click to expand options)")
            if hasattr(self, "branding_panel"):
                self.branding_panel.pack_forget()
        if hasattr(self, "preview"):
            self.preview.refresh()

    def _on_pos_changed(self):
        p = self.caption_pos.get()
        if p == "top":
            self.caption_margin_v.set(250)
            if hasattr(self, "_margin_lbl"): self._margin_lbl.config(text="250 px")
        elif p == "middle":
            self.caption_margin_v.set(960)
            if hasattr(self, "_margin_lbl"): self._margin_lbl.config(text="960 px")
        else:
            self.caption_margin_v.set(300)
            if hasattr(self, "_margin_lbl"): self._margin_lbl.config(text="300 px")
        if hasattr(self, "preview"):
            self.preview.refresh()

    def _on_margin_slide(self, val):
        iv = int(float(val))
        self.caption_margin_v.set(iv)
        if hasattr(self, "_margin_lbl"):
            self._margin_lbl.config(text=f"{iv} px")
        if hasattr(self, "preview"):
            self.preview.refresh()

    def _reset_pos(self):
        self.caption_pos.set("bottom")
        self.caption_margin_v.set(300)
        if hasattr(self, "_margin_lbl"):
            self._margin_lbl.config(text="300 px")
        if hasattr(self, "preview"):
            self.preview.refresh()

    def _on_size_slide(self, val):
        sz = int(float(val))
        self._size_lbl.config(text=f"{sz} px")

    def _reset_size(self):
        self.caption_size.set(0)
        self._size_lbl.config(text="Style default")

    def _open_file(self, path):
        try:
            if sys.platform.startswith("win"): os.startfile(str(path))
            elif sys.platform == "darwin":      subprocess.run(["open", str(path)])
            else:                               subprocess.run(["xdg-open", str(path)])
        except Exception as e:
            messagebox.showwarning("Open file failed", str(e))

    def _reload_styles(self):
        global _STYLE_MAP, _STYLE_KEYS, _DISPLAY_NAMES
        try:
            import importlib
            _cs_mod = importlib.reload(_cs)
            _STYLE_MAP     = _cs_mod.STYLES
            _STYLE_KEYS    = _cs_mod.style_keys()
            _DISPLAY_NAMES = _cs_mod.get_display_names()
            self._display_to_key = {"No Captions": "none"}
            self._key_to_display = {"none": "No Captions"}
            for k in _STYLE_KEYS:
                dn = _DISPLAY_NAMES.get(k, k.replace("_", " ").title())
                self._display_to_key[dn] = k
                self._key_to_display[k]  = dn
            combo_vals = ["No Captions"] + [_DISPLAY_NAMES.get(k, k.replace("_", " ").title()) for k in _STYLE_KEYS]
            self.caption_combo["values"] = combo_vals
            self.preview.refresh()
            messagebox.showinfo("Reloaded", "caption_styles.py reloaded successfully!")
        except Exception as e:
            messagebox.showwarning("Reload failed", str(e))

    def _play_selected_short(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Play Short", "Please select a Short from the list first.")
            return
        item = self.tree.item(sel[0])
        vals = item.get("values", [])
        if len(vals) >= 6:
            raw_target = str(vals[5])
            raw_out = self.outdir.get().strip().strip('"').strip("'")
            out_dir = Path(raw_out) if raw_out else (Path(__file__).parent / "clips").resolve()
            clip_path = Path(raw_target) if Path(raw_target).is_absolute() else (out_dir / raw_target)
            if clip_path.exists():
                try:
                    if sys.platform.startswith("win"): os.startfile(str(clip_path))
                    elif sys.platform == "darwin":      subprocess.run(["open", str(clip_path)])
                    else:                               subprocess.run(["xdg-open", str(clip_path)])
                except Exception as ex:
                    messagebox.showerror("Play Error", f"Could not launch player: {ex}")
            else:
                messagebox.showwarning("File Missing", f"Clip file not found: {clip_path}")

    def say(self, msg):
        self.log_q.put(("log", msg))

    def set_status(self, msg, pct=None):
        self.log_q.put(("status", (msg, pct)))

    def _drain_log(self):
        try:
            while True:
                kind, val = self.log_q.get_nowait()
                if kind == "log":
                    self.log.configure(state="normal")
                    self.log.insert("end", val + "\n")
                    self.log.see("end")
                    self.log.configure(state="disabled")
                elif kind == "status":
                    msg, pct = val
                    self.status.set(msg)
                    if pct is not None: self.bar["value"] = pct
                elif kind == "done":
                    self.start_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
                elif kind == "add_moment":
                    self.tree.insert("", "end", values=val)
        except queue.Empty:
            pass
        self.after(100, self._drain_log)

    # ── Execution ─────────────────────────────────────────────────────────────
    def _start(self):
        if not self.src.get().strip():
            messagebox.showwarning("Missing source",
                "Please paste a YouTube link or select a video file first.")
            return
        core.ensure_tools_in_path()
        for tool in ("ffmpeg", "ffprobe"):
            if not core.shutil.which(tool):
                messagebox.showerror("Tool Missing",
                    f"'{tool}' not found. Install ffmpeg first (see README.md).")
                return

        for item in self.tree.get_children():
            self.tree.delete(item)

        self.stop_flag.clear()
        self.bar["value"] = 0
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    def _stop(self):
        self.stop_flag.set()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        self.set_status("Stopping…")

    def _download(self, url, out_dir):
        self.set_status("Downloading video from YouTube…", 0)

        # Clean up any leftover source.* from previous runs in out_dir so they don't pollute subtitles
        for old in out_dir.glob("source*"):
            try:
                if old.is_file(): old.unlink()
            except Exception:
                pass

        out_tpl = str(out_dir / "source.%(ext)s")
        flags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0

        cmd = core.ytdlp_cmd() + [
            "-f", "bv*[height<=1080]+ba/b[height<=1080]/b",
            "--merge-output-format", "mp4", "--newline",
            "--no-playlist",
            "-o", out_tpl, url,
        ]
        self.proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", creationflags=flags)
        for line in self.proc.stdout:
            line = line.strip()
            if line.startswith("[download]") and "%" in line:
                try:
                    pct = float(line.split("%")[0].split()[-1])
                    self.set_status(f"Downloading video… {pct:.0f}%", pct * 0.25)
                except ValueError:
                    pass
            elif line:
                self.say(line)
            if self.stop_flag.is_set():
                self.proc.terminate(); break
        self.proc.wait()
        if self.stop_flag.is_set(): raise InterruptedError

        self.set_status("Checking for official YouTube subtitles…", 25)
        cmd_subs = core.ytdlp_cmd() + [
            "--skip-download",
            "--write-subs", "--write-auto-subs",
            "--sub-lang", "en.*,en",
            "--convert-subs", "srt",
            "--no-playlist",
            "-o", out_tpl, url,
        ]
        try:
            p_sub = subprocess.Popen(
                cmd_subs, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", creationflags=flags)
            p_sub.wait(timeout=15)
        except Exception:
            pass

        target = out_dir / "source.mp4"
        if target.exists() and target.stat().st_size > 1000:
            return target
        for cand in out_dir.glob("source.*"):
            if cand.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov", ".avi", ".ts") and cand.stat().st_size > 1000:
                return cand
        raise RuntimeError("Download failed. YouTube may be rate-limiting or the link is invalid.")

    def _run(self):
        try:
            raw_out = self.outdir.get().strip().strip('"').strip("'")
            out_dir = Path(raw_out) if raw_out else (Path(__file__).parent / "clips").resolve()
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
                test_f = out_dir / ".perm_test"
                test_f.touch()
                test_f.unlink()
            except Exception as pe:
                fallback = (Path(__file__).parent / "clips").resolve()
                fallback.mkdir(parents=True, exist_ok=True)
                self.say(f"⚠️ Cannot write to '{out_dir}' ({pe}). Using '{fallback}' instead.")
                out_dir = fallback
                self.outdir.set(str(fallback))

            source = self.src.get().strip().strip('"').strip("'")
            try:
                is_local = Path(source).exists()
            except (OSError, ValueError):
                is_local = False

            src = Path(source) if is_local else self._download(source, out_dir)

            total     = core.duration(src)
            mode      = self.mode.get()
            length    = float(self.length.get())
            maxc      = max(1, int(self.maxclips.get()))
            fit       = self.fit.get()
            sub_style = self.subtitle_style.get()
            cap_size  = int(self.caption_size.get()) or None
            lang      = self.language.get()
            ai_mode_val = self.ai_mode.get()
            edit_style_val = self.editing_style.get()
            selected_tab = self.notebook.index(self.notebook.select())

            align_map = {"bottom": 2, "middle": 5, "top": 8}
            align_val = align_map.get(self.caption_pos.get(), 2)
            margin_val = int(self.caption_margin_v.get())

            self.say(f"🎬 Video duration: {total/60:.1f} min ({total:.0f}s)")

            # Build logo config
            logo_config = None
            if self.logo_enabled.get():
                lp = self.logo_path_v.get().strip().strip('"').strip("'")
                if lp and Path(lp).exists():
                    logo_config = {
                        "path":     lp,
                        "position": self.logo_pos_v.get(),
                        "size_pct": int(self.logo_size_v.get()),
                        "opacity":  float(self.logo_opacity_v.get()),
                        "padding":  30,
                    }
                    self.say(f"🖼️  Logo: {Path(lp).name} at {logo_config['position']} ({logo_config['size_pct']}%)")
                else:
                    self.say("⚠️  Logo enabled but file not found — skipping logo.")

            # 1. Speech Transcription
            self.set_status("Transcribing speech and detecting sentence boundaries…", 28)
            captions, sentences = core.get_captions_and_sentences(src, out_dir, language=lang, log_fn=self.say)

            if captions:
                self.say(f"💬 Subtitle cues detected: {len(captions)} phrases.")
                if sub_style != "none":
                    self.say(f"🎨 Subtitle burn-in style: '{sub_style}' (Size: {cap_size or 'Default'})")
                    self.say(f"🎤 Dynamic Karaoke Animation: {'✨ Enabled (Word-by-word Alex Hormozi pop)' if self.karaoke_enabled.get() else 'Disabled'}")
                else:
                    self.say("ℹ️ Subtitles disabled ('No Captions' selected).")
            else:
                self.say("ℹ️ No spoken dialogue detected or no subtitles generated.")

            # 2. Silence detection
            self.set_status("Analyzing dialogue pauses & speech cadence…", 34)
            silence_dur = 0.6 if mode == "podcast" else 0.4
            silences = core.find_silences(src, dur=silence_dur) if mode != "even" else []

            # ═════════════════════════════════════════════════════════════════
            # PATH A: AI Professional Editor
            # ═════════════════════════════════════════════════════════════════
            if selected_tab == 0 and ai_mode_val != "rule_based":
                self.say(f"\n🧠 AI Editing Director [{ai_mode_val.upper()}] - Style: '{edit_style_val}'")
                self.set_status("🧠 AI Director analyzing moments, hooks, and cuts…", 40)

                # Optional Gemini Visual Scene Analysis
                visual_scenes = None
                if ai_mode_val in ("hybrid", "gemini") and self.gemini_enabled.get():
                    gemini_key = self.gemini_key_v.get().strip() or gemini_client.get_api_key()
                    if gemini_key:
                        self.set_status("👁️ Google Gemini analyzing visual scenes & speakers…", 45)
                        self.say("👁️ Running Gemini Visual Scene Understanding...")
                        try:
                            visual_scenes = gemini_client.sample_and_analyze_scenes(
                                video_path=src,
                                api_key=gemini_key,
                                model=self.gemini_model.get(),
                                num_samples=6,
                                style=edit_style_val,
                                work_dir=out_dir,
                                log_fn=self.say,
                            )
                        except Exception as ge:
                            self.say(f"⚠️ Gemini visual analysis failed: {ge}. Continuing with local AI.")
                            visual_scenes = None
                        if visual_scenes:
                            self.say(f"✅ Gemini detected {len(visual_scenes)} key visual scene moments.")
                        else:
                            self.say("⚠️ Gemini analysis returned empty or was throttled — continuing with local AI.")

                # Ollama / AI Director Decision Engine
                plans = ai_director.generate_shorts_plans(
                    video_duration=total,
                    transcript_entries=sentences or captions,
                    visual_scenes=visual_scenes,
                    silence_intervals=silences,
                    style_key=edit_style_val,
                    max_clips=maxc,
                    target_duration=length,
                    ai_mode=ai_mode_val,
                    ollama_model=self.ollama_model.get(),
                    log_fn=self.say,
                )

                if not plans:
                    self.set_status("Could not identify viral clips with AI.", 100)
                    self.say("⚠️ AI Director did not find sufficient candidate moments.")
                    return

                n = len(plans)
                self.say(f"\n🎬 AI Director approved {n} high-retention Shorts plans!")
                report = []

                for i, plan in enumerate(plans, 1):
                    if self.stop_flag.is_set(): raise InterruptedError

                    out_name = f"short_{i:02d}_{plan.editing_style}_score{plan.virality_score}.mp4"
                    out_clip = out_dir / out_name
                    pct = 50 + 48 * (i - 1) / max(1, n)
                    self.set_status(f"Exporting AI Short {i}/{n} | '{plan.title}' ({plan.virality_score}/100)", pct)

                    self.say(f"\n[{i}/{n}] ✂️ Rendering Short #{plan.clip_id}: '{plan.title}'")
                    self.say(f"     Hook (0-2s): \"{plan.hook}\"")
                    self.say(f"     Virality: {plan.virality_score}/100 | Time: {plan.start_time:.1f}s → {plan.end_time:.1f}s ({plan.duration:.1f}s)")
                    if plan.highlight_keywords:
                        self.say(f"     Highlighted Keywords: {', '.join(plan.highlight_keywords)}")

                    out_clip = ffmpeg_director.execute_director_clip(
                        src_video=src,
                        plan=plan,
                        out_clip=out_clip,
                        captions=captions,
                        caption_style=sub_style,
                        caption_size=cap_size,
                        karaoke=self.karaoke_enabled.get(),
                        caption_margin_v=margin_val,
                        caption_alignment=align_val,
                        logo_config=logo_config,
                        fit=fit,
                        work_dir=out_dir,
                        log_fn=self.say,
                    )

                    self.log_q.put(("add_moment", (
                        f"✓ {plan.clip_id}", plan.title, plan.hook, f"{plan.duration:.1f}s", f"{plan.virality_score}/100", str(out_clip.name)
                    )))

                self.set_status(f"Done! {n} AI Shorts saved.", 100)
                self.say(f"\n✅ All AI Shorts saved in: {out_dir}")
                return

            # ═════════════════════════════════════════════════════════════════
            # PATH B: Classic Rule-Based Clipper
            # ═════════════════════════════════════════════════════════════════
            segments = core.plan_cuts(total, length, snap=6, silences=silences, mode=mode)
            if not segments:
                self.set_status("Video too short for chosen clip length.", 100)
                self.say("⚠️ Video duration is shorter than target clip length.")
                return

            self.set_status("Scoring virality, hook strength & dynamics…", 40)
            self.say("🔥 Calculating Virality Scores...")
            scored = []
            for s, e in segments:
                if self.stop_flag.is_set(): raise InterruptedError
                vi = core.calculate_virality_score(src, s, e, total, silences, captions)
                scored.append((vi["score"], s, e, vi))

            if mode != "even":
                scored.sort(key=lambda x: x[0], reverse=True)
                selected = scored[:maxc]
                selected.sort(key=lambda x: x[1])
            else:
                selected = scored[:maxc]

            n = len(selected)
            report = []
            for i, (score, s, e, vi) in enumerate(selected, 1):
                if self.stop_flag.is_set(): raise InterruptedError

                out_name = f"short_{i:02d}_viral{score}.mp4"
                out_clip = out_dir / out_name
                pct = 45 + 50 * (i - 1) / max(1, n)
                self.set_status(f"Exporting clip {i}/{n} | Virality: {score}/100 | {out_name}", pct)

                ass_file = None
                if sub_style != "none" and captions:
                    ass_path = out_dir / f"temp_{i}.ass"
                    ass_file = core.generate_ass(
                        captions, s, e, sub_style, ass_path,
                        size_override=cap_size,
                        karaoke=self.karaoke_enabled.get(),
                        margin_v_override=margin_val,
                        alignment_override=align_val,
                    )

                self.say(f"[{i}/{n}] {s:.1f}s → {e:.1f}s | Virality: {score}/100 {vi['tier']} | {out_name}")
                core.export(src, s, e - s, out_clip, fit=fit, ass_file=ass_file, logo_config=logo_config)

                if ass_file and Path(ass_file).exists():
                    try: Path(ass_file).unlink()
                    except OSError: pass

                self.log_q.put(("add_moment", (
                    i, f"Clip #{i}", vi.get("hook_sample", "Classic Cut"), f"{e-s:.1f}s", f"{score}/100", str(out_clip.name)
                )))

            self.set_status(f"Done! {n} viral clips saved.", 100)
            self.say(f"\n✅ All clips saved in: {out_dir}")

        except InterruptedError:
            self.set_status("Stopped by user.")
            self.say("Operation stopped.")
        except Exception as ex:
            err_msg = str(ex)
            self.set_status(f"Error: {err_msg[:50]}")
            self.say(f"ERROR: {err_msg}")
            self.say(traceback.format_exc())
            try:
                messagebox.showerror("Clipping Error", f"An error occurred:\n\n{err_msg}\n\nCheck the log window for details.")
            except Exception:
                pass
        finally:
            self.log_q.put(("done", None))


if __name__ == "__main__":
    App().mainloop()
