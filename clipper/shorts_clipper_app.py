#!/usr/bin/env python3
"""
Shorts Clipper App — Free YouTube Shorts & Podcast Clipper
100% local: no API keys, no watermarks, no cloud.
"""
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

import shorts_clipper as core

# ── Optional Pillow for logo preview ─────────────────────────────────────────
try:
    from PIL import Image, ImageTk  # type: ignore
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False
    Image = None    # type: ignore
    ImageTk = None  # type: ignore

# ── Caption styles ───────────────────────────────────────────────────────────
try:
    import caption_styles as _cs
    _STYLE_MAP       = _cs.STYLES
    _STYLE_KEYS      = _cs.style_keys()
    _DISPLAY_NAMES   = _cs.get_display_names()
except ImportError:
    _STYLE_MAP       = core.SUBTITLE_STYLES
    _STYLE_KEYS      = list(core.SUBTITLE_STYLES.keys())
    _DISPLAY_NAMES   = {k: k.replace("_", " ").title() for k in _STYLE_KEYS}

# ── Branding defaults ─────────────────────────────────────────────────────────
try:
    import branding as _br
    _BR_DEFAULT = _br.get_config()
    _BR_POSITIONS = list(_br.POSITION_OPTIONS.keys())
    _BR_POS_LABELS = _br.POSITION_OPTIONS
except ImportError:
    _BR_DEFAULT = {"path": "", "position": "top_right",
                   "size_pct": 15, "opacity": 1.0, "padding": 30}
    _BR_POSITIONS = ["top_left","top_center","top_right","mid_left","center",
                     "mid_right","bot_left","bot_center","bot_right"]
    _BR_POS_LABELS = {k: k.replace("_", " ").title() for k in _BR_POSITIONS}

STYLES_FILE   = Path(__file__).parent / "caption_styles.py"
BRANDING_FILE = Path(__file__).parent / "branding.py"


# ═════════════════════════════════════════════════════════════════════════════
#  Caption Style Card Strip
# ═════════════════════════════════════════════════════════════════════════════
class CaptionStylePicker(ttk.Frame):
    """Scrollable row of styled cards. Calls on_change(key) when selection changes."""

    CARD_W = 100
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
        self.canvas = tk.Canvas(self, height=self.CARD_H + 18,
                                highlightthickness=0, bg="#1e1e1e")
        sb = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=sb.set)
        self.canvas.pack(fill="x")
        sb.pack(fill="x")

        self.inner = tk.Frame(self.canvas, bg="#1e1e1e")
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
        frm = tk.Frame(self.inner, bg="#2a2a2a", cursor="hand2",
                       relief="flat", padx=2, pady=2)
        frm.pack(side="left", padx=3, pady=6)

        sw_bg = self._swatch_bg(key)
        cv = tk.Canvas(frm, width=W, height=SH, highlightthickness=1,
                       highlightbackground="#444", bg=sw_bg)
        cv.pack()
        cv.create_text(W//2, SH//2, text="Aa",
                       font=("Arial", 14, "bold"),
                       fill=self._swatch_fg(key), anchor="center")

        display = "No Captions" if key == "none" else _DISPLAY_NAMES.get(key, key)
        short   = (display[:12] + "…") if len(display) > 13 else display
        lbl = tk.Label(frm, text=short, bg="#2a2a2a", fg="#cccccc",
                       font=("", 7), wraplength=W, justify="center")
        lbl.pack(fill="x")

        for w in (frm, cv, lbl):
            w.bind("<Button-1>", lambda e, k=key: self._select(k))

        self._cards[key] = dict(frame=frm, canvas=cv, label=lbl)

    def _select(self, key, notify=True, **kwargs):
        if self._selected in self._cards:
            p = self._cards[self._selected]
            p["frame"].config(bg="#2a2a2a")
            p["canvas"].config(highlightbackground="#444", highlightthickness=1)
            p["label"].config(bg="#2a2a2a", fg="#cccccc")

        self._selected = key
        self.style_var.set(key)

        if key in self._cards:
            c = self._cards[key]
            hl = "#003366" if key != "none" else "#2a2a2a"
            c["frame"].config(bg=hl)
            c["canvas"].config(highlightbackground="#4FC3F7", highlightthickness=2)
            c["label"].config(bg=hl, fg="#ffffff")

        if notify and self.on_change:
            self.on_change(key)

    @staticmethod
    def _swatch_bg(key):
        if key == "none": return "#333333"
        return _STYLE_MAP.get(key, {}).get("preview_color", "#444444")

    @staticmethod
    def _swatch_fg(key):
        if key == "none": return "#666666"
        pc = _STYLE_MAP.get(key, {}).get("preview_color", "#444444")
        try:
            r, g, b = int(pc[1:3],16), int(pc[3:5],16), int(pc[5:7],16)
            return "#000000" if 0.299*r+0.587*g+0.114*b > 160 else "#FFFFFF"
        except Exception:
            return "#FFFFFF"

    @staticmethod
    def ass_to_tk(ass: str) -> str:
        """Convert ASS &HAABBGGRR or &HBBGGRR → Tkinter #RRGGBB."""
        try:
            c = str(ass).replace("&H","").replace("&h","").strip()
            if len(c) == 8:
                bb, gg, rr = c[2:4], c[4:6], c[6:8]
                return f"#{rr}{gg}{bb}"
            elif len(c) == 6:
                bb, gg, rr = c[0:2], c[2:4], c[4:6]
                return f"#{rr}{gg}{bb}"
        except Exception:
            pass
        return "#FFFFFF"


# ═════════════════════════════════════════════════════════════════════════════
#  Unified Preview Canvas  (phone mockup + caption + logo)
# ═════════════════════════════════════════════════════════════════════════════
class UnifiedPreview(ttk.Frame):
    """
    Live phone-screen mockup (9:16) showing:
      • Caption text at the bottom in chosen style + size
      • Logo PNG thumbnail at chosen position
    All vars are watched — preview updates automatically.
    """
    PW = 135    # preview canvas width  (9:16 aspect ratio)
    PH = 240    # preview canvas height (135x240)
    BORDER = 3  # phone border thickness

    def __init__(self, parent,
                 style_var, size_var,
                 logo_enabled_var, logo_path_var,
                 logo_pos_var, logo_size_var, logo_opacity_var,
                 **kw):
        super().__init__(parent, **kw)
        self.style_var       = style_var
        self.size_var        = size_var
        self.logo_enabled    = logo_enabled_var
        self.logo_path_var   = logo_path_var
        self.logo_pos_var    = logo_pos_var
        self.logo_size_var   = logo_size_var
        self.logo_opacity_var = logo_opacity_var
        self._logo_tk        = None   # keep reference to avoid GC
        self._refresh_job    = None

        self._build()
        self._bind_all()
        self.after(80, self.refresh)

    # ── Build ─────────────────────────────────────────────────────────────────
    def _build(self):
        ttk.Label(self, text="Live Preview", font=("", 9, "bold")).pack()

        self.cv = tk.Canvas(self, width=self.PW, height=self.PH,
                            bg="#111111", highlightthickness=1,
                            highlightbackground="#444444")
        self.cv.pack(padx=4, pady=(2, 4))

        # Phone screen rect
        b = self.BORDER
        self.cv.create_rectangle(b, b, self.PW-b, self.PH-b,
                                  fill="#161616", outline="#2a2a2a", width=2)

        # Caption bar (bottom area)
        self._cap_bar  = self.cv.create_rectangle(
            b, self.PH-52, self.PW-b, self.PH-b,
            fill="#1a1a1a", outline="")
        self._cap_text = self.cv.create_text(
            self.PW//2, self.PH-26,
            text="SAMPLE TEXT", anchor="center",
            font=("Arial", 9, "bold"), fill="#FFFF00",
            width=self.PW - 12)

        # Logo elements (placeholder rect + text, hidden by default)
        self._logo_img_id  = self.cv.create_image(0, 0, anchor="nw")
        self._logo_rect    = self.cv.create_rectangle(0,0,0,0,
                                fill="#444444", outline="#888888")
        self._logo_lbl     = self.cv.create_text(0,0,
                                text="", font=("Arial", 7, "bold"), fill="#cccccc")

    # ── Bindings ──────────────────────────────────────────────────────────────
    def _bind_all(self):
        def _schedule_refresh(*_):
            if self._refresh_job is not None:
                try:
                    self.after_cancel(self._refresh_job)
                except Exception:
                    pass
            self._refresh_job = self.after(25, self.refresh)

        for v in (self.style_var, self.size_var,
                  self.logo_enabled, self.logo_path_var,
                  self.logo_pos_var, self.logo_size_var,
                  self.logo_opacity_var):
            try:
                v.trace_add("write", _schedule_refresh)
            except Exception:
                pass

    # ── Refresh ───────────────────────────────────────────────────────────────
    def refresh(self):
        self._refresh_job = None
        try:
            self._draw_caption()
        except Exception:
            pass
        try:
            self._draw_logo()
        except Exception:
            pass

    def _draw_caption(self):
        try:
            key = str(self.style_var.get())
        except Exception:
            key = "tiktok_yellow"

        if key == "none":
            self.cv.itemconfig(self._cap_bar,  fill="#161616")
            self.cv.itemconfig(self._cap_text, text="No captions",
                               fill="#555555", font=("Arial", 10, "italic"))
            return

        style    = _STYLE_MAP.get(key, {})
        fg       = CaptionStylePicker.ass_to_tk(style.get("primary", "&H00FFFFFF"))
        fname    = style.get("font", "Arial")
        bold     = style.get("bold", -1)
        weight   = "bold" if bold else "normal"

        # Scale font size from video px → preview px
        style_sz  = style.get("size", 60)
        try:
            override = int(float(self.size_var.get()))
        except (ValueError, TypeError, tk.TclError):
            override = 0
        vid_sz    = override if override > 0 else style_sz
        # video canvas = 1080px wide; preview = PW px
        prev_sz   = max(7, min(18, int(vid_sz * self.PW / 1080 * 2.8)))

        box_fill  = "#282828" if style.get("border_style", 1) == 3 else "#1a1a1a"
        self.cv.itemconfig(self._cap_bar, fill=box_fill)
        try:
            self.cv.itemconfig(self._cap_text,
                               text="SAMPLE CAPTION TEXT",
                               fill=fg, font=(fname, prev_sz, weight))
        except tk.TclError:
            self.cv.itemconfig(self._cap_text,
                               text="SAMPLE CAPTION TEXT",
                               fill=fg, font=("Arial", prev_sz, "bold"))

    def _draw_logo(self):
        PW, PH, b = self.PW, self.PH, self.BORDER
        pad = 7  # inner padding from phone edge

        try:
            enabled = bool(self.logo_enabled.get())
        except Exception:
            enabled = False

        if not enabled:
            self.cv.coords(self._logo_rect, 0, 0, 0, 0)
            self.cv.itemconfig(self._logo_lbl, text="")
            self.cv.itemconfig(self._logo_img_id, image="")
            return

        try:
            logo_path = str(self.logo_path_var.get()).strip().strip('"').strip("'")
        except Exception:
            logo_path = ""

        try:
            size_pct = max(1, min(50, int(float(self.logo_size_var.get()))))
        except Exception:
            size_pct = 15

        try:
            pos = str(self.logo_pos_var.get())
        except Exception:
            pos = "top_right"

        try:
            opacity = max(0.0, min(1.0, float(self.logo_opacity_var.get())))
        except Exception:
            opacity = 1.0

        # Logo size in preview pixels
        lw = max(10, int((PW - b*2) * size_pct / 100))
        lh = lw   # default square; fixed below if real image

        # Try to load actual PNG for preview
        loaded = False
        if logo_path and Path(logo_path).exists():
            try:
                if _HAS_PIL and Image and ImageTk:
                    img   = Image.open(logo_path).convert("RGBA")
                    ratio = img.height / max(1, img.width)
                    lh    = max(5, int(lw * ratio))
                    resample_mode = getattr(getattr(Image, "Resampling", Image), "LANCZOS", getattr(Image, "ANTIALIAS", 1))
                    img   = img.resize((lw, lh), resample_mode)
                    if opacity < 0.99:
                        r, g, bch, a = img.split()
                        a = a.point(lambda x: int(x * opacity))
                        img.putalpha(a)
                    self._logo_tk = ImageTk.PhotoImage(img, master=self.cv)
                    loaded = True
                else:
                    # Tkinter native PNG (Tk 8.6+)
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

        # Compute (x, y) for the top-left corner of the logo rect
        inner_x1, inner_y1 = b + pad, b + pad
        inner_x2, inner_y2 = PW - b - pad, PH - b - pad

        pos_map = {
            "top_left":   (inner_x1,              inner_y1),
            "top_center": ((PW-lw)//2,             inner_y1),
            "top_right":  (inner_x2 - lw,          inner_y1),
            "mid_left":   (inner_x1,               (PH-lh)//2),
            "center":     ((PW-lw)//2,              (PH-lh)//2),
            "mid_right":  (inner_x2 - lw,           (PH-lh)//2),
            "bot_left":   (inner_x1,                inner_y2 - lh),
            "bot_center": ((PW-lw)//2,              inner_y2 - lh),
            "bot_right":  (inner_x2 - lw,           inner_y2 - lh),
        }
        x, y = pos_map.get(pos, (inner_x2 - lw, inner_y1))

        draw_loaded = False
        if loaded and self._logo_tk:
            try:
                self.cv.coords(self._logo_img_id, x, y)
                self.cv.itemconfig(self._logo_img_id, image=self._logo_tk)
                self.cv.coords(self._logo_rect, 0, 0, 0, 0)
                self.cv.itemconfig(self._logo_lbl, text="")
                draw_loaded = True
            except Exception:
                draw_loaded = False

        if not draw_loaded:
            # Placeholder box
            self.cv.itemconfig(self._logo_img_id, image="")
            self.cv.coords(self._logo_rect, x, y, x+lw, y+lh)
            cx, cy = x + lw//2, y + lh//2
            self.cv.coords(self._logo_lbl, cx, cy)
            self.cv.itemconfig(self._logo_lbl, text="LOGO")


# ═════════════════════════════════════════════════════════════════════════════
#  Main App Window
# ═════════════════════════════════════════════════════════════════════════════
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Shorts Clipper — AI Shorts & Podcast Clipper")
        self.geometry("900x830")
        self.minsize(820, 740)
        self.configure(bg="#1a1a1a")
        self.log_q      = queue.Queue()
        self.worker     = None
        self.stop_flag  = threading.Event()
        self.proc       = None
        self._build()
        self.after(100, self._drain_log)

    def report_callback_exception(self, exc, val, tb):
        """Catch callback exceptions so mainloop does not crash."""
        err_msg = "".join(traceback.format_exception(exc, val, tb))
        print("Exception in Tkinter callback:\n", err_msg, file=sys.stderr)
        try:
            self.say(f"⚠️ UI Error: {val}")
        except Exception:
            pass

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background="#1a1a1a", foreground="#e0e0e0",
                        fieldbackground="#2d2d2d")
        style.configure("TFrame",         background="#1a1a1a")
        style.configure("TLabel",         background="#1a1a1a", foreground="#e0e0e0")
        style.configure("TLabelframe",    background="#1a1a1a", foreground="#888888")
        style.configure("TLabelframe.Label", background="#1a1a1a",
                        foreground="#aaaaaa", font=("", 9, "bold"))
        style.configure("TButton",        padding=4)
        style.configure("TRadiobutton",   background="#1a1a1a", foreground="#e0e0e0")
        style.configure("TCheckbutton",   background="#1a1a1a", foreground="#e0e0e0")
        style.configure("TEntry",         fieldbackground="#2d2d2d", foreground="#e0e0e0")
        style.configure("TSpinbox",       fieldbackground="#2d2d2d", foreground="#e0e0e0")
        style.configure("TScale",         background="#1a1a1a", troughcolor="#2d2d2d")

        P = dict(padx=12, pady=4)
        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=10, pady=8)

        # ── Source ────────────────────────────────────────────────────────────
        ttk.Label(main, text="YouTube Link or Local Video File",
                  font=("", 11, "bold")).pack(anchor="w", **P)
        row = ttk.Frame(main); row.pack(fill="x", **P)
        self.src = tk.StringVar()
        ttk.Entry(row, textvariable=self.src).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse…", command=self._browse).pack(side="left", padx=(8,0))

        # ── Clip settings ──────────────────────────────────────────────────────
        opts = ttk.LabelFrame(main, text="Clipping & Viral Settings")
        opts.pack(fill="x", **P)
        opts.columnconfigure(1, weight=1)

        self.length   = tk.IntVar(value=45)
        self.maxclips = tk.IntVar(value=8)
        self.mode     = tk.StringVar(value="smart")
        self.fit      = tk.StringVar(value="crop")
        default_out   = (Path(__file__).parent / "clips").resolve()
        self.outdir   = tk.StringVar(value=str(default_out))

        ttk.Label(opts, text="Clip length (sec)").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        f = ttk.Frame(opts); f.grid(row=0, column=1, sticky="w")
        ttk.Spinbox(f, from_=10, to=90, textvariable=self.length, width=6).pack(side="left")
        ttk.Label(f, text="Max clips:").pack(side="left", padx=(18,6))
        ttk.Spinbox(f, from_=1, to=50, textvariable=self.maxclips, width=6).pack(side="left")

        ttk.Label(opts, text="Cutting Mode").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        f = ttk.Frame(opts); f.grid(row=1, column=1, sticky="w")
        for txt, val in [("Smart (Pauses & Energy)","smart"),
                         ("Podcast (Dialogue & Hook)","podcast"),
                         ("Even chunks","even")]:
            ttk.Radiobutton(f, text=txt, variable=self.mode, value=val).pack(side="left", padx=(0,10))

        ttk.Label(opts, text="Video Template").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        f = ttk.Frame(opts); f.grid(row=2, column=1, sticky="w")
        for txt, val in [("Center Crop (9:16)","crop"),("Blur BG","blur"),
                         ("Podcast Split","split"),("Headline","headline"),("Original","none")]:
            ttk.Radiobutton(f, text=txt, variable=self.fit, value=val).pack(side="left", padx=(0,8))

        ttk.Label(opts, text="Save clips to").grid(row=3, column=0, sticky="w", padx=10, pady=5)
        f = ttk.Frame(opts); f.grid(row=3, column=1, sticky="ew", padx=(0,10))
        ttk.Entry(f, textvariable=self.outdir).pack(side="left", fill="x", expand=True)
        ttk.Button(f, text="Change…", command=self._pick_out).pack(side="left", padx=(8,0))

        # ── Caption style section ─────────────────────────────────────────────
        cap_frame = ttk.LabelFrame(main, text="Caption / Subtitle Style  —  ✏️ edit caption_styles.py to add styles")
        cap_frame.pack(fill="x", **P)

        self.subtitle_style = tk.StringVar(value="tiktok_yellow")
        self.caption_size   = tk.IntVar(value=0)   # 0 = use style default

        self.style_picker = CaptionStylePicker(
            cap_frame, style_var=self.subtitle_style,
            on_change=lambda k: None)
        self.style_picker.pack(fill="x", padx=8, pady=(6,2))

        # Caption size row
        size_row = ttk.Frame(cap_frame)
        size_row.pack(fill="x", padx=8, pady=(2,6))
        ttk.Label(size_row, text="Caption Size:").pack(side="left")
        self._size_lbl = ttk.Label(size_row, text="Style default", width=14)
        self._size_lbl.pack(side="left", padx=(8,0))
        ttk.Scale(size_row, from_=20, to=120, orient="horizontal",
                  variable=self.caption_size,
                  command=self._on_size_slide).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(size_row, text="Reset", width=5,
                   command=self._reset_size).pack(side="left")
        ttk.Button(size_row, text="✏️ Styles File",
                   command=lambda: self._open_file(STYLES_FILE)).pack(side="right")

        # ── Branding + Preview (side by side) ─────────────────────────────────
        bottom = ttk.Frame(main)
        bottom.pack(fill="x", **P)

        # Left: branding panel
        br_frame = ttk.LabelFrame(bottom, text="Logo / Branding  —  ✏️ edit branding.py")
        br_frame.pack(side="left", fill="both", expand=True, padx=(0,8))

        self.logo_enabled  = tk.BooleanVar(value=False)
        self.logo_path_v   = tk.StringVar(value=_BR_DEFAULT.get("path", ""))
        self.logo_pos_v    = tk.StringVar(value=_BR_DEFAULT.get("position", "top_right"))
        self.logo_size_v   = tk.IntVar(value=_BR_DEFAULT.get("size_pct", 15))
        self.logo_opacity_v = tk.DoubleVar(value=_BR_DEFAULT.get("opacity", 1.0))

        # Enable toggle
        ttk.Checkbutton(br_frame, text="Enable Logo Watermark",
                        variable=self.logo_enabled).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(8,4))

        # File picker
        ttk.Label(br_frame, text="Logo PNG:").grid(row=1, column=0, sticky="w", padx=10, pady=4)
        f = ttk.Frame(br_frame); f.grid(row=1, column=1, sticky="ew", padx=(0,10))
        br_frame.columnconfigure(1, weight=1)
        ttk.Entry(f, textvariable=self.logo_path_v, width=28).pack(side="left", fill="x", expand=True)
        ttk.Button(f, text="📁", width=3,
                   command=self._browse_logo).pack(side="left", padx=(4,0))

        # Position grid
        ttk.Label(br_frame, text="Position:").grid(row=2, column=0, sticky="nw", padx=10, pady=4)
        pos_grid = ttk.Frame(br_frame)
        pos_grid.grid(row=2, column=1, sticky="w", pady=4)
        layout = [
            ["top_left","top_center","top_right"],
            ["mid_left","center",    "mid_right"],
            ["bot_left","bot_center","bot_right"],
        ]
        for r, row_keys in enumerate(layout):
            for c, k in enumerate(row_keys):
                lbl = _BR_POS_LABELS.get(k, k).split()[0].replace("⭐","")
                ttk.Radiobutton(pos_grid, text=lbl, variable=self.logo_pos_v,
                                value=k).grid(row=r, column=c, padx=4, pady=1, sticky="w")

        # Size slider
        ttk.Label(br_frame, text="Size:").grid(row=3, column=0, sticky="w", padx=10, pady=4)
        f = ttk.Frame(br_frame); f.grid(row=3, column=1, sticky="ew", padx=(0,10))
        self._logo_sz_lbl = ttk.Label(f, text="15 %", width=6)
        self._logo_sz_lbl.pack(side="left")
        ttk.Scale(f, from_=3, to=50, orient="horizontal",
                  variable=self.logo_size_v,
                  command=lambda v: self._logo_sz_lbl.config(
                      text=f"{int(float(v))} %")).pack(side="left", fill="x", expand=True)

        # Opacity slider
        ttk.Label(br_frame, text="Opacity:").grid(row=4, column=0, sticky="w", padx=10, pady=4)
        f = ttk.Frame(br_frame); f.grid(row=4, column=1, sticky="ew", padx=(0,10))
        self._logo_op_lbl = ttk.Label(f, text="100 %", width=6)
        self._logo_op_lbl.pack(side="left")
        ttk.Scale(f, from_=0.0, to=1.0, orient="horizontal",
                  variable=self.logo_opacity_v,
                  command=lambda v: self._logo_op_lbl.config(
                      text=f"{int(float(v)*100)} %")).pack(side="left", fill="x", expand=True)

        # Open branding.py button
        ttk.Button(br_frame, text="✏️ Open branding.py",
                   command=lambda: self._open_file(BRANDING_FILE)).grid(
            row=5, column=0, columnspan=2, pady=(6,8))

        # Right: unified preview
        self.preview = UnifiedPreview(
            bottom,
            style_var       = self.subtitle_style,
            size_var        = self.caption_size,
            logo_enabled_var= self.logo_enabled,
            logo_path_var   = self.logo_path_v,
            logo_pos_var    = self.logo_pos_v,
            logo_size_var   = self.logo_size_v,
            logo_opacity_var= self.logo_opacity_v,
        )
        self.preview.pack(side="right", anchor="n", padx=(0,0))

        # ── Buttons + progress ────────────────────────────────────────────────
        btns = ttk.Frame(main); btns.pack(fill="x", **P)
        self.start_btn = ttk.Button(btns, text="▶  Start Clipping", command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(btns, text="■  Stop", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=8)
        ttk.Button(btns, text="📂 Open Output Folder",
                   command=self._open_out).pack(side="right")
        ttk.Button(btns, text="🔄 Reload Styles",
                   command=self._reload_styles).pack(side="right", padx=6)

        self.bar    = ttk.Progressbar(main, mode="determinate")
        self.bar.pack(fill="x", **P)
        self.status = tk.StringVar(value="Ready to create viral clips.")
        ttk.Label(main, textvariable=self.status,
                  font=("", 9, "italic")).pack(anchor="w", padx=12)

        # ── Log ───────────────────────────────────────────────────────────────
        logf = ttk.Frame(main); logf.pack(fill="both", expand=True, **P)
        self.log = tk.Text(logf, height=8, state="disabled", wrap="word",
                           font=("Consolas", 9), bg="#111111", fg="#cccccc")
        sb2 = ttk.Scrollbar(logf, command=self.log.yview)
        self.log.configure(yscrollcommand=sb2.set)
        self.log.pack(side="left", fill="both", expand=True)
        sb2.pack(side="right", fill="y")

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _browse(self):
        p = filedialog.askopenfilename(
            filetypes=[("Video files","*.mp4 *.mkv *.mov *.webm *.avi"),("All","*.*")])
        if p: self.src.set(p)

    def _browse_logo(self):
        p = filedialog.askopenfilename(
            filetypes=[("PNG images","*.png"),("All","*.*")])
        if p:
            self.logo_path_v.set(p)
            self.logo_enabled.set(True)

    def _pick_out(self):
        p = filedialog.askdirectory()
        if p: self.outdir.set(p)

    def _open_out(self):
        raw = self.outdir.get().strip().strip('"').strip("'")
        p = Path(raw) if raw else (Path(__file__).parent / "clips").resolve()
        try:
            p.mkdir(parents=True, exist_ok=True)
            if sys.platform.startswith("win"): os.startfile(str(p))
            elif sys.platform == "darwin":      subprocess.run(["open", str(p)])
            else:                               subprocess.run(["xdg-open", str(p)])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open folder '{p}': {e}")

    def _open_file(self, path):
        try:
            if sys.platform.startswith("win"): os.startfile(str(path))
            elif sys.platform == "darwin":      subprocess.Popen(["open", str(path)])
            else:                               subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:
            messagebox.showerror("Cannot open file", str(e))

    def _on_size_slide(self, val):
        v = int(float(val))
        if v <= 20:
            self.caption_size.set(0)
            self._size_lbl.config(text="Style default")
        else:
            self.caption_size.set(v)
            self._size_lbl.config(text=f"{v} px")

    def _reset_size(self):
        self.caption_size.set(0)
        self._size_lbl.config(text="Style default")

    def _reload_styles(self):
        try:
            import importlib, caption_styles as _cs_mod
            importlib.reload(_cs_mod)
            global _STYLE_MAP, _STYLE_KEYS, _DISPLAY_NAMES
            _STYLE_MAP     = _cs_mod.STYLES
            _STYLE_KEYS    = _cs_mod.style_keys()
            _DISPLAY_NAMES = _cs_mod.get_display_names()
            self.preview.refresh()
            messagebox.showinfo("Reloaded", "caption_styles.py reloaded successfully!")
        except Exception as e:
            messagebox.showwarning("Reload failed", str(e))

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
        for tool in ("ffmpeg","ffprobe"):
            if not core.shutil.which(tool):
                messagebox.showerror("Tool Missing",
                    f"'{tool}' not found. Install ffmpeg first (see README.md).")
                return
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
        out_tpl = str(out_dir / "source.%(ext)s")
        flags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0

        # Step 1: Download video (reliable & fast, not aborted by subtitle rate-limiting)
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

        # Step 2: Try fetching subtitles (non-fatal; if 429 blocked, Whisper will auto-transcribe)
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
            if cand.suffix.lower() in (".mp4",".mkv",".webm",".mov",".avi",".ts") and cand.stat().st_size > 1000:
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
            if not source:
                self.set_status("Please select a video file or enter a YouTube URL.", 0)
                self.say("⚠️ No source video specified.")
                return

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
            cap_size  = int(self.caption_size.get()) or None   # None = style default

            self.say(f"🎬 Video duration: {total/60:.1f} min ({total:.0f}s)")

            # Build logo config from GUI
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
                    self.say(f"🖼️  Logo: {Path(lp).name} at {logo_config['position']}"
                             f" ({logo_config['size_pct']}%)")
                else:
                    self.say("⚠️  Logo enabled but file not found — skipping logo.")

            # Captions
            self.set_status("Scanning for captions or transcribing speech…", 28)
            captions = (core.get_captions(src, out_dir, log_fn=self.say)
                        if sub_style != "none" else [])
            if captions:
                self.say(f"💬 Ready to burn {len(captions)} caption bursts.")
            else:
                self.say("💬 No speech / subtitles detected.")

            # Silence + cuts
            self.set_status("Analyzing dialogue pauses & speech cadence…", 34)
            silence_dur = 0.6 if mode == "podcast" else 0.4
            silences  = core.find_silences(src, dur=silence_dur) if mode != "even" else []
            segments  = core.plan_cuts(total, length, snap=6, silences=silences, mode=mode)
            if not segments:
                self.set_status("Video too short for the chosen clip length.", 100)
                self.say("⚠️ Video duration is shorter than target clip length. Try a smaller clip length.")
                return

            # Virality scoring
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
            if n == 0:
                self.set_status("No clips could be planned.", 100)
                self.say("⚠️ No clips could be planned. Try adjusting duration or cutting mode.")
                return
            style_lbl = (_DISPLAY_NAMES.get(sub_style, sub_style)
                         if sub_style != "none" else "No Captions")
            self.say(f"\n🚀 Exporting {n} clips | Template: '{fit}' | "
                     f"Captions: '{style_lbl}'"
                     + (f" size={cap_size}px" if cap_size else " (style default)")
                     + (f" | Logo: ON" if logo_config else ""))

            report = []
            for i, (score, s, e, vi) in enumerate(selected, 1):
                if self.stop_flag.is_set(): raise InterruptedError

                out_name = f"short_{i:02d}_viral{score}.mp4"
                out_clip = out_dir / out_name
                pct = 45 + 50 * (i-1) / max(1, n)
                self.set_status(
                    f"Exporting clip {i}/{n}  |  Virality: {score}/100  |  {out_name}", pct)

                ass_file = None
                if sub_style != "none" and captions:
                    ass_path = out_dir / f"temp_{i}.ass"
                    ass_file = core.generate_ass(captions, s, e, sub_style, ass_path,
                                                 size_override=cap_size)

                self.say(f"[{i}/{n}] {s:.1f}s → {e:.1f}s | Virality: {score}/100 "
                         f"{vi['tier']} | {out_name}")
                self.say(f"       Hook={vi['hook']}/25 | Energy={vi['energy']}/30 | "
                         f"Pacing={vi['pacing']}/25")

                core.export(src, s, e-s, out_clip,
                            fit=fit, ass_file=ass_file, logo_config=logo_config)

                if ass_file and Path(ass_file).exists():
                    try: Path(ass_file).unlink()
                    except OSError: pass

                report.append({
                    "clip":           out_name,
                    "start_time":     s,
                    "end_time":       e,
                    "duration":       round(e-s, 2),
                    "virality_score": score,
                    "tier":           vi["tier"],
                    "hook_score":     vi["hook"],
                    "energy_score":   vi["energy"],
                    "pacing_score":   vi["pacing"],
                    "duration_score": vi["duration"],
                    "caption_style":  sub_style,
                    "caption_size":   cap_size or "style_default",
                    "template":       fit,
                    "logo":           logo_config["path"] if logo_config else None,
                })

            report_file = out_dir / "virality_report.json"
            report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
            self.set_status(f"Done! {n} viral clips saved.", 100)
            self.say(f"\n✅ All clips saved in: {out_dir}")
            self.say(f"📊 Virality report: {report_file}")

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
