import os
import re
import io
import json
import base64
import random
import math
import threading
import time
import ctypes
import ctypes.wintypes as wt
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, colorchooser
import keyboard
import pyautogui
from plyer import notification
from PIL import Image, ImageDraw, ImageTk

# Files live next to this script (not the current working directory), so the app finds its
# saved state no matter where it is launched from.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "screenshot_config.json")
BG_IMAGE_FILE = os.path.join(BASE_DIR, "screenshot_background.jpg")
# Older versions saved into the current working directory; still read from there if needed.
LEGACY_CONFIG_FILE = "screenshot_config.json"
LEGACY_BG_IMAGE_FILE = "screenshot_background.jpg"

WIN_W = 520
WIN_H = 674
BAR_H = 32

MAX_LINES_LIMIT = 300

MIN_SCALE = 0.7
MAX_SCALE = 3.0
RESIZE_EDGE = 8
RESIZE_CORNER = 18
CTRL_RESIZE_STEP = 0.0
RESIZE_INTERVAL_MS = 6
BG_SRC_SCALE = 2

DRAG_INTERVAL_MS = 6
DRAG_SMOOTHING = 14.0
PAUSE_ANIM_WHILE_DRAGGING = True

PANEL_X1 = 16
PANEL_X2 = 504
SECTION_HEADER_H = 36
SECTION_ANIM_MS = 700
SECTION_ANIM_INTERVAL_MS = 4   # frame target for page / section animation (4 ms = up to 250 fps)
PAGE_FADE = True               # per-frame colour fade between pages (prettier but slower)
PAGE_ANIM_RESIZE_WINDOW = True   # True = the window height glides during a page slide; False = height steps once at each end
PAGE_RESIZE_MS = 16              # minimum time between height updates while gliding (16 ms = ~60 per second)
PAUSE_BG_WHILE_SECTION_ANIM = True
WIN_BOTTOM_PAD = 30
TILE_H = 32

BG_MAIN = "#12121f"
ACCENT_PURPLE = "#5c52a2"
ACCENT_BLUE = "#3b82f6"
TEXT_LIGHT = "#e2e8f0"
TEXT_MUTED = "#94a3b8"
BTN_GREEN = "#166534"
BTN_RED = "#991b1b"

DEFAULT_LINE_COLOUR = "#3b82f6"
DEFAULT_BORDER_COLOUR = "#3b82f6"
DEFAULT_BOX_COLOUR = "#323256"
DEFAULT_ACCENT_COLOUR = "#3b82f6"

PAGES = ("main", "prefs", "themes")
BG_IMG_H = 1000
BG_MAX_SIDE = 2600   # longest side of the stored background image
BG_MAX_ZOOM = 5.0
BG_MIN_ZOOM = 0.1    # below 1.0 the image is smaller than the window (gaps show)

PRESET_BTN_RADIUS = 7

PRESET_THEMES = [
    ("Default",   {"line": "#3b82f6", "border": "#3b82f6", "box": "#323256", "accent": "#3b82f6"}),
    ("Cyberpunk", {"line": "#ff2bd6", "border": "#00f0ff", "box": "#2a0f45", "accent": "#00f0ff"}),
    ("Sunset",    {"line": "#fb923c", "border": "#f43f5e", "box": "#4a1d2e", "accent": "#fb923c"}),
    ("Forest",    {"line": "#4ade80", "border": "#22c55e", "box": "#14342a", "accent": "#4ade80"}),
    ("Ocean",     {"line": "#38bdf8", "border": "#06b6d4", "box": "#0c3047", "accent": "#38bdf8"}),
    ("Crimson",   {"line": "#ef4444", "border": "#dc2626", "box": "#3b1219", "accent": "#ef4444"}),
    ("Royal",     {"line": "#a78bfa", "border": "#8b5cf6", "box": "#2e1f5e", "accent": "#a78bfa"}),
    ("Mono",      {"line": "#e5e7eb", "border": "#9ca3af", "box": "#2b2b2b", "accent": "#9ca3af"}),
]

PAGE_ANIM_MS = 1200   # length of a full page slide (Main <-> Preferences <-> Themes)
FADE_STEPS = 12
BG_FRAME_MS = 6
TAB_Y = 48

# Low quality mode (Preferences): cheaper animation for slow PCs
LOW_FRAME_MS = 33        # ~30 fps background
LOW_MAX_LINES = 25       # cap on animated lines
LOW_CURVE_STEPS = 4      # points per line (nearly straight)
LOW_RESIZE_MS = 40

# Background line curvature
CURVE_AMOUNT = 0.06   # bulge as a fraction of line length (lower = straighter)
CURVE_MAX = 10        # maximum bulge in pixels
CURVE_STEPS = 14      # points per line (higher = smoother)


def parse_hex(value):
    v = str(value).strip().lstrip("#")
    if re.fullmatch(r"[0-9a-fA-F]{6}", v):
        return "#" + v.lower()
    return None


def hex_to_rgb(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def mix_hex(c1, c2, t):
    a, b = hex_to_rgb(c1), hex_to_rgb(c2)
    return "#{:02x}{:02x}{:02x}".format(*(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3)))


def rounded_points(x1, y1, x2, y2, r=4):
    r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1
    ]


def round_rect_points(x1, y1, x2, y2, r, steps=6):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    if r <= 0:
        return [x1, y1, x2, y1, x2, y2, x1, y2]
    pts = []
    for cx, cy, a0 in ((x2 - r, y1 + r, -90), (x2 - r, y2 - r, 0),
                       (x1 + r, y2 - r, 90), (x1 + r, y1 + r, 180)):
        for i in range(steps + 1):
            a = math.radians(a0 + 90.0 * i / steps)
            pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
    return pts


def ease_in_out_cubic(t):
    if t < 0.5:
        return 4 * t * t * t
    return 1 - ((-2 * t + 2) ** 3) / 2


def cover_resize(img, w, h, resample=Image.LANCZOS):
    if img.mode != "RGB":
        img = img.convert("RGB")
    s = max(w / img.width, h / img.height)
    nw, nh = max(w, int(img.width * s + 0.5)), max(h, int(img.height * s + 0.5))
    img = img.resize((nw, nh), resample)
    left, top = (nw - w) // 2, (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def clean_view(zoom, ox, oy):
    """Clamp a saved background view to sane values -> [zoom, ox, oy]."""
    return [min(max(float(zoom), BG_MIN_ZOOM), BG_MAX_ZOOM),
            min(max(float(ox), -4.0), 4.0),
            min(max(float(oy), -4.0), 4.0)]


def image_layout(iw, ih, W, H, zoom, ox, oy):
    """Where an iw x ih image sits inside a W x H frame.

    zoom 1.0 is the "cover" size (fills the frame). ox / oy are the image centre's offset
    from the frame centre, as fractions of the frame size, and are not limited to keeping
    the frame covered: the image may be smaller than the frame or hang off its edges.
    Only a 15% strip of the image is always kept inside so it can't be lost completely.
    Returns (x0, y0, dw, dh, clamped_ox, clamped_oy).
    """
    k = max(W / iw, H / ih) * zoom
    dw, dh = iw * k, ih * k
    cx, cy = (0.5 + ox) * W, (0.5 + oy) * H
    mx, my = 0.15 * W, 0.15 * H
    cx = min(max(cx, mx - dw / 2), W + dw / 2 - mx)
    cy = min(max(cy, my - dh / 2), H + dh / 2 - my)
    return cx - dw / 2, cy - dh / 2, dw, dh, cx / W - 0.5, cy / H - 0.5


def paste_scaled(dest, src, x0, y0, dw, dh, resample):
    """Paste src scaled to dw x dh at (x0, y0) onto dest, drawing only the visible part.

    Anything that falls outside dest is cropped off, and never resized, so very large
    zoom levels stay cheap.
    """
    W, H = dest.size
    if dw <= 0 or dh <= 0:
        return
    ix0, iy0 = max(0, int(math.floor(x0))), max(0, int(math.floor(y0)))
    ix1, iy1 = min(W, int(math.ceil(x0 + dw))), min(H, int(math.ceil(y0 + dh)))
    if ix1 <= ix0 or iy1 <= iy0:
        return
    sw, sh = src.size
    box = ((ix0 - x0) / dw * sw, (iy0 - y0) / dh * sh,
           (ix1 - x0) / dw * sw, (iy1 - y0) / dh * sh)
    box = (max(0.0, box[0]), max(0.0, box[1]), min(float(sw), box[2]), min(float(sh), box[3]))
    if box[2] - box[0] < 0.01 or box[3] - box[1] < 0.01:
        return
    dest.paste(src.resize((ix1 - ix0, iy1 - iy0), resample, box=box), (ix0, iy0))


def smoothstep(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def _ui_scale(canvas):
    return getattr(canvas, "ui_scale", (1.0, 1.0))


class Section:
    def __init__(self, key, title, top, full_h, gap, panel=True, page="main"):
        self.key = key
        self.page = page
        self.title = title
        self.top = top
        self.full_h = full_h
        self.gap = gap
        self.panel = panel
        self.h = full_h
        self.tag = f"sec_{key}"
        self.ctag = f"sec_{key}_c"
        self.htag = f"sec_{key}_h"
        self.p = 1.0
        self.target = 1.0
        self.animating = False
        self.anim_from = 1.0
        self.anim_to = 1.0
        self.anim_dur = 0.0
        self.anim_start = 0.0
        self.widgets = []
        self.items = []
        self.chevron = None
        self.x = 0

    def height(self):
        if not self.panel:
            return self.full_h
        return int(round(SECTION_HEADER_H + (self.full_h - SECTION_HEADER_H) * self.p))


class AutoClearEntry(tk.Entry):
    def __init__(self, master, textvariable, default_value, **kwargs):
        super().__init__(master, textvariable=textvariable, insertbackground="white", **kwargs)
        self.textvariable = textvariable
        self.default_value = default_value

        if not self.textvariable.get():
            self.textvariable.set(default_value)
            self.config(fg="#64748b", bg="#161625", insertbackground="white")
            self.is_default = True
        else:
            self.config(fg=TEXT_LIGHT, bg="#161625", insertbackground="white")
            self.is_default = False

        self.bind("<FocusIn>", self._on_focus_in)

    def _on_focus_in(self, event):
        if self.is_default:
            self.textvariable.set("")
            self.config(fg=TEXT_LIGHT)
            self.is_default = False


class CanvasLabel:
    def __init__(self, canvas, x, y, text, fg, font, wrap=0, tags="ui_text"):
        self.canvas = canvas
        self.id = canvas.create_text(
            x, y, text=text, fill=fg, font=font, anchor="w", width=wrap, tags=tags
        )

    def config(self, **kw):
        opts = {}
        if "text" in kw:
            opts["text"] = kw["text"]
        if "fg" in kw:
            opts["fill"] = kw["fg"]
        if opts:
            self.canvas.itemconfig(self.id, **opts)


class CanvasButton:
    def __init__(self, canvas, x1, y1, x2, y2, text, command, fill, fg, border,
                 font=("Segoe UI", 9, "bold"), radius=PRESET_BTN_RADIUS, tags="ui_text"):
        self.canvas = canvas
        self.command = command
        self.fill, self.fg, self.border = fill, fg, border
        self.enabled = True
        self.hovered = False

        self.poly = canvas.create_polygon(
            *round_rect_points(x1, y1, x2, y2, radius),
            fill=fill, outline=border, width=1, tags=tags)
        self.label = canvas.create_text(
            (x1 + x2) / 2, (y1 + y2) / 2, text=text, fill=fg, font=font, tags=tags)

        canvas.bind("<Button-1>", self._on_click, add="+")
        canvas.bind("<Motion>", self._on_motion, add="+")

    def hit(self, x, y):
        if self.canvas.itemcget(self.poly, "state") == "hidden":
            return False
        bb = self.canvas.bbox(self.poly)
        return bb is not None and bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3]

    def _on_click(self, event):
        if self.enabled and self.hit(event.x, event.y):
            self.command()

    def _on_motion(self, event):
        if getattr(self.canvas, "busy", False):
            return
        h = self.enabled and self.hit(event.x, event.y)
        if h != self.hovered:
            self.hovered = h
            self.refresh()

    def refresh(self):
        if self.enabled:
            fill = mix_hex(self.fill, "#ffffff", 0.14) if self.hovered else self.fill
            outline, fg = self.border, self.fg
        else:
            fill = mix_hex(self.fill, BG_MAIN, 0.55)
            outline = mix_hex(self.border, BG_MAIN, 0.55)
            fg = "#64748b"
        self.canvas.itemconfigure(self.poly, fill=fill, outline=outline)
        self.canvas.itemconfigure(self.label, fill=fg)

    def config(self, **kw):
        if "state" in kw:
            self.enabled = kw["state"] != "disabled"
            if not self.enabled:
                self.hovered = False
            self.refresh()


class CanvasCheckbox:
    def __init__(self, canvas, x, y, text, variable, fg, font, size=14, tags="ui_text"):
        self.canvas = canvas
        self.var = variable
        self.enabled = True
        self.visible = True

        self.box = canvas.create_rectangle(
            x, y - size / 2, x + size, y + size / 2,
            outline=ACCENT_BLUE, width=1.5, fill="", tags=tags
        )
        self.tick = canvas.create_line(
            x + 3, y, x + 6, y + 4, x + size - 3, y - 4,
            fill=TEXT_LIGHT, width=2, tags=tags
        )
        self.label = canvas.create_text(
            x + size + 8, y, text=text, fill=fg, font=font, anchor="w", tags=tags
        )

        bx = canvas.bbox(self.label)
        self.hit_x = (x - 4, bx[2] + 4)

        canvas.bind("<Button-1>", self._on_click, add="+")
        variable.trace_add("write", lambda *a: self.refresh())
        self.refresh()

    def cur_y(self):
        c = self.canvas.coords(self.box)
        return (c[1] + c[3]) / 2 / _ui_scale(self.canvas)[1]

    def shift_x(self, dx):
        self.hit_x = (self.hit_x[0] + dx, self.hit_x[1] + dx)

    def _on_click(self, event):
        if not self.enabled or not self.visible:
            return
        sx, sy = _ui_scale(self.canvas)
        ex, ey = event.x / sx, event.y / sy
        cy = self.cur_y()
        if self.hit_x[0] <= ex <= self.hit_x[1] and cy - 12 <= ey <= cy + 12:
            self.var.set(not self.var.get())

    def set_visible(self, visible):
        if visible == self.visible:
            return
        self.visible = visible
        state = "normal" if visible else "hidden"
        self.canvas.itemconfigure(self.box, state=state)
        self.canvas.itemconfigure(self.label, state=state)
        self.refresh()

    def set_accent(self, colour):
        """Update the checkbox border to match the current accent colour."""
        if self.enabled:
            self.canvas.itemconfigure(self.box, outline=colour)

    def refresh(self):
        show_tick = self.var.get() and self.visible
        self.canvas.itemconfigure(self.tick, state="normal" if show_tick else "hidden")
        outline = ACCENT_BLUE if self.enabled else "#475569"
        text_col = TEXT_LIGHT if self.enabled else TEXT_MUTED
        self.canvas.itemconfigure(self.box, outline=outline)
        self.canvas.itemconfigure(self.tick, fill=text_col)
        self.canvas.itemconfigure(self.label, fill=text_col)

    def config(self, **kw):
        if "state" in kw:
            self.enabled = kw["state"] != "disabled"
            self.refresh()


class CanvasSlider:
    def __init__(self, canvas, x0, x1, y, from_, to, resolution, variable, command=None, tags="ui_text"):
        self.canvas = canvas
        self.x0, self.x1 = x0, x1
        self.from_, self.to, self.res = from_, to, resolution
        self.var = variable
        self.command = command
        self.enabled = True
        self.visible = True
        self.dragging = False
        self.extra_items = []

        self.decimals = 0
        r = resolution
        while self.decimals < 4 and abs(r - round(r)) > 1e-9:
            r *= 10
            self.decimals += 1

        self.track = canvas.create_line(
            x0, y, x1, y, fill="#2b2b45", width=4, capstyle="round", tags=tags)
        self.fill_line = canvas.create_line(
            x0, y, x0, y, fill=ACCENT_BLUE, width=4, capstyle="round", tags=tags)
        self.handle = canvas.create_polygon(
            *rounded_points(x0 - 6, y - 9, x0 + 6, y + 9, 4),
            smooth=True, fill=ACCENT_PURPLE, outline=TEXT_LIGHT, width=1, tags=tags)
        self.text = canvas.create_text(
            0, 0, anchor="s", fill=TEXT_LIGHT, font=("Segoe UI", 8), tags=tags)

        canvas.bind("<Button-1>", self._press, add="+")
        canvas.bind("<B1-Motion>", self._drag, add="+")
        canvas.bind("<ButtonRelease-1>", self._release, add="+")
        variable.trace_add("write", lambda *a: self.refresh())
        self.refresh()

    def cur_y(self):
        return self.canvas.coords(self.track)[1] / _ui_scale(self.canvas)[1]

    def shift_x(self, dx):
        self.x0 += dx
        self.x1 += dx

    def _in_hit_area(self, event):
        sx, sy = _ui_scale(self.canvas)
        ex, ey = event.x / sx, event.y / sy
        y = self.cur_y()
        return (self.x0 - 10 <= ex <= self.x1 + 10 and y - 14 <= ey <= y + 14)

    def _press(self, event):
        if self.enabled and self.visible and self._in_hit_area(event):
            self.dragging = True
            self._set_from_x(event.x / _ui_scale(self.canvas)[0])

    def _drag(self, event):
        if self.dragging:
            self._set_from_x(event.x / _ui_scale(self.canvas)[0])

    def _release(self, event):
        self.dragging = False

    def _set_from_x(self, x):
        frac = min(max((x - self.x0) / (self.x1 - self.x0), 0.0), 1.0)
        raw = self.from_ + frac * (self.to - self.from_)
        steps = round((raw - self.from_) / self.res)
        value = round(self.from_ + steps * self.res, 6)
        value = min(max(value, self.from_), self.to)
        if value != self.var.get():
            self.var.set(value)
            if self.command:
                self.command(value)

    def set_visible(self, visible):
        if visible == self.visible:
            return
        self.visible = visible
        if not visible:
            self.dragging = False
        state = "normal" if visible else "hidden"
        for item in (self.track, self.fill_line, self.handle, self.text, *self.extra_items):
            self.canvas.itemconfigure(item, state=state)

    def set_accent(self, colour):
        """Update the fill line colour to match the current accent colour."""
        if self.enabled:
            self.canvas.itemconfigure(self.fill_line, fill=colour)

    def refresh(self):
        try:
            v = float(self.var.get())
        except Exception:
            return
        frac = min(max((v - self.from_) / (self.to - self.from_), 0.0), 1.0)
        hx = self.x0 + frac * (self.x1 - self.x0)
        c = self.canvas
        sx, sy = _ui_scale(c)
        S = min(sx, sy)
        y = self.cur_y()
        px, py = hx * sx, y * sy
        c.coords(self.fill_line, self.x0 * sx, py, px, py)
        c.coords(self.handle, *rounded_points(px - 6 * S, py - 9 * S, px + 6 * S, py + 9 * S, 4 * S))
        c.coords(self.text, px, py - 12 * S)

        label = f"{v:.{self.decimals}f}"
        c.itemconfigure(self.text, text=label)

        track_col = "#2b2b45" if self.enabled else "#1f1f33"
        fill_col = ACCENT_BLUE if self.enabled else "#475569"
        handle_col = ACCENT_PURPLE if self.enabled else "#3b3b55"
        text_col = TEXT_LIGHT if self.enabled else TEXT_MUTED
        c.itemconfigure(self.track, fill=track_col)
        c.itemconfigure(self.fill_line, fill=fill_col)
        c.itemconfigure(self.handle, fill=handle_col)
        c.itemconfigure(self.text, fill=text_col)

    def config(self, **kw):
        if "state" in kw:
            self.enabled = kw["state"] != "disabled"
            if not self.enabled:
                self.dragging = False
            self.refresh()


class BackgroundAdjustDialog(tk.Toplevel):
    """Free-form editor for the background image, styled like the main window.

    The bright rectangle is the area of the app background. The image can be moved and
    zoomed freely, including past the edges of that rectangle or smaller than it; the
    parts outside the rectangle (shown dimmed) are cropped off when you press Apply.
    on_apply(zoom, ox, oy) is called with the final placement.
    """
    MAX_W = 300
    MARGIN = 40          # extra space around the frame so you can see what hangs off it
    PAD = PANEL_X1       # outer padding, same as the main window's panels

    def __init__(self, parent, img, aspect, visible_frac, opacity, view, on_apply, style):
        super().__init__(parent)
        self.overrideredirect(True)
        self.title("Adjust Background Image")
        self.configure(bg=BG_MAIN)
        self.attributes("-topmost", True)
        self.attributes("-alpha", style["window_alpha"])

        self._closed = False
        self._imgs = []
        self._tick_job = None
        self._render_job = None
        self._render_last = 0.0

        self.st = style
        self.accent = style["accent"]
        self.border = style["border"]
        self.on_apply = on_apply
        self.opacity = min(max(float(opacity), 0.0), 1.0)
        self.aspect = max(float(aspect), 0.05)
        self.visible_frac = min(max(float(visible_frac), 0.0), 1.0)

        # Preview frame size (same shape as the real background)
        M = self.MARGIN
        max_h = max(240, min(460, parent.winfo_screenheight() - 346 - 2 * M - 110))
        if self.aspect >= self.MAX_W / max_h:
            self.PREV_W = self.MAX_W
            self.PREV_H = max(40, int(round(self.MAX_W / self.aspect)))
        else:
            self.PREV_H = max_h
            self.PREV_W = max(40, int(round(max_h * self.aspect)))
        self.SW, self.SH = self.PREV_W + 2 * M, self.PREV_H + 2 * M

        self.orig = img.convert("RGB")
        self.work = self.orig.copy()
        self.work.thumbnail((1600, 1600), Image.LANCZOS)   # fast preview copy

        self.zoom, self.ox, self.oy = clean_view(*view)
        self._drag = None
        self._photo = None
        self.zoom_var = tk.DoubleVar(self, value=self.zoom)
        self.show_opacity = tk.BooleanVar(self, value=True)

        # Window dragging state (smoothed, same as the main window)
        self._win_drag = None
        self._native = False
        self._released = False
        self._pos = [0.0, 0.0]
        self._target = (0.0, 0.0)
        self._last_pos = (0, 0)
        self._last_t = 0.0
        self._drag_off = (0, 0)
        self._hwnd = None
        self._timer_on = False

        self._build()
        self._init_net()
        self._render()
        self.show_opacity.trace_add("write", lambda *a: self._render())

        # Place beside the main window if it fits, otherwise centre on the screen
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = parent.winfo_rootx() + parent.winfo_width() + 12
        if x + self.D_W > sw:
            x = max(0, (sw - self.D_W) // 2)
        y = max(0, min(parent.winfo_rooty(), sh - self.D_H - 40))
        self.geometry(f"{self.D_W}x{self.D_H}+{x}+{y}")

        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Return>", lambda e: self._apply())
        try:
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass
        self.focus_force()

        self._last_net_t = time.perf_counter()
        self._tick()

    # ---------- UI ----------
    def _panel(self, top, h):
        st = self.st
        w = self.D_W - 2 * self.PAD
        r = max(0, min(int(st["radius"]), h // 2, w // 2))
        a = int(255 * st["box_alpha"])
        fill = hex_to_rgb(st["box"])
        border = hex_to_rgb(self.border)
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        if r > 0:
            d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r,
                                fill=fill + (a,), outline=border + (255,), width=1)
        else:
            d.rectangle([0, 0, w - 1, h - 1], fill=fill + (a,), outline=border + (255,), width=1)
        ph = ImageTk.PhotoImage(im)
        self._imgs.append(ph)
        self.canvas.create_image(self.PAD, top, image=ph, anchor="nw", tags="panel")

    def _header(self, top, text):
        self.canvas.create_text(self.PAD + 14, top + 16, text=text, anchor="w",
                                font=("Segoe UI", 9, "bold"), fill=self.accent)

    def _build(self):
        PAD, M, st = self.PAD, self.MARGIN, self.st
        self.D_W = max(440, self.SW + 28 + 2 * PAD)
        panel_w = self.D_W - 2 * PAD

        p1_top = BAR_H + 12
        self.stage_x = PAD + (panel_w - self.SW) // 2
        self.stage_y = p1_top + 76
        p1_h = 76 + self.SH + 14
        p2_top = p1_top + p1_h + 10
        p2_h = 146
        btn_top = p2_top + p2_h + 14
        self.D_H = btn_top + 30 + 18

        c = self.canvas = tk.Canvas(self, width=self.D_W, height=self.D_H, bg=BG_MAIN,
                                    highlightthickness=0)
        c.ui_scale = (1.0, 1.0)
        c.pack()

        # Title bar (same translucent bar as the main window)
        bar = Image.new("RGBA", (self.D_W, BAR_H), (0, 0, 0, int(255 * st["bar_alpha"])))
        ImageDraw.Draw(bar).line([(0, BAR_H - 1), (self.D_W, BAR_H - 1)],
                                 fill=hex_to_rgb(self.border) + (255,), width=1)
        bar_ph = ImageTk.PhotoImage(bar)
        self._imgs.append(bar_ph)
        c.create_image(0, 0, image=bar_ph, anchor="nw", tags="bar")
        c.create_text(14, BAR_H / 2, text="ADJUST BACKGROUND IMAGE", anchor="w",
                      font=("Segoe UI", 10, "bold"), fill=TEXT_LIGHT)
        self.close_txt = c.create_text(self.D_W - 18, BAR_H / 2, text="\u2715",
                                       font=("Segoe UI", 11), fill=TEXT_LIGHT)

        # Preview panel
        self._panel(p1_top, p1_h)
        self._header(p1_top, "IMAGE PREVIEW")
        c.create_text(self.D_W / 2, p1_top + 40, anchor="n", justify="center",
                      text="Drag to move  \u2022  Scroll or use the slider to zoom\n"
                           "Anything outside the bright frame is cropped off",
                      font=("Segoe UI", 9), fill=TEXT_MUTED)

        # Controls panel
        self._panel(p2_top, p2_h)
        self._header(p2_top, "ADJUSTMENTS")
        c.create_text(PAD + 14, p2_top + 66, text="Zoom:", anchor="w",
                      font=("Segoe UI", 9), fill=TEXT_LIGHT)
        self.zoom_slider = CanvasSlider(
            c, PAD + 84, self.D_W - PAD - 14, p2_top + 66, BG_MIN_ZOOM, BG_MAX_ZOOM, 0.01,
            self.zoom_var, self._on_slider, tags="ui")
        self.opacity_check = CanvasCheckbox(
            c, PAD + 14, p2_top + 100, "Preview at current image opacity", self.show_opacity,
            TEXT_LIGHT, ("Segoe UI", 9), tags="ui")
        self.zoom_slider.set_accent(self.accent)
        self.opacity_check.set_accent(self.accent)
        c.create_text(PAD + 14, p2_top + 126, anchor="w",
                      text=f"Original: {self.orig.width} x {self.orig.height} px",
                      font=("Segoe UI", 8), fill=TEXT_MUTED)

        # Buttons (border matches fill, so no coloured outline)
        bw, gap = (panel_w - 2 * 10) // 3, 10
        specs = (("Reset", self._reset, ACCENT_PURPLE),
                 ("Cancel", self.destroy, BTN_RED),
                 ("Apply", self._apply, BTN_GREEN))
        self.buttons = []
        for i, (text, cmd, colour) in enumerate(specs):
            bx = PAD + i * (bw + gap)
            self.buttons.append(CanvasButton(
                c, bx, btn_top, bx + bw, btn_top + 30, text, cmd,
                fill=colour, fg="white", border=colour,
                font=("Segoe UI", 9, "bold"), radius=PRESET_BTN_RADIUS, tags="ui"))

        c.bind("<ButtonPress-1>", self._press, add="+")
        c.bind("<B1-Motion>", self._move, add="+")
        c.bind("<ButtonRelease-1>", self._release, add="+")
        c.bind("<MouseWheel>", self._wheel, add="+")
        c.bind("<Motion>", self._hover, add="+")

    # ---------- Animated line network (same settings as the main window) ----------
    def _init_net(self):
        st = self.st
        self.max_lines = min(MAX_LINES_LIMIT, int(st["line_count"]))
        self.low = bool(st.get("low_quality"))
        if self.low:
            self.max_lines = min(self.max_lines, LOW_MAX_LINES)
        self.steps = LOW_CURVE_STEPS if self.low else CURVE_STEPS
        n = int(5 * math.sqrt(self.max_lines)) if self.max_lines > 0 else 0
        self.particles = [{
            "x": random.uniform(0, self.D_W), "y": random.uniform(0, self.D_H),
            "vx": random.uniform(-0.5, 0.5), "vy": random.uniform(-0.5, 0.5),
            "id": random.getrandbits(32), "phase": random.uniform(0, math.tau),
        } for _ in range(n)]
        self.mx, self.my = self.D_W / 2, self.D_H / 2
        self.tx, self.ty = self.mx, self.my

    def _draw_net(self, t0, dt):
        st = self.st
        c = self.canvas
        c.delete("net")
        if self.max_lines <= 0 or not self.particles:
            return
        W, H = self.D_W, self.D_H
        f = min(dt / 0.025, 3.0)
        speed = st["anim_speed"]
        spread = st["spread"]
        repel = 0.0 if self.low else spread * 110
        link_max = 100 + spread * 140

        ease = 1.0 - (1.0 - min(0.1 * speed, 0.99)) ** f
        self.mx += (self.tx - self.mx) * ease
        self.my += (self.ty - self.my) * ease

        base = hex_to_rgb(st["line_colour"])
        a = st["line_alpha"]
        line_color = "#{:02x}{:02x}{:02x}".format(
            int(18 + (base[0] - 18) * a), int(18 + (base[1] - 18) * a), int(31 + (base[2] - 31) * a))

        P = self.particles
        for p in P:
            p["x"] += p["vx"] * speed * f
            p["y"] += p["vy"] * speed * f
            if p["x"] < 0 or p["x"] > W: p["vx"] *= -1
            if p["y"] < 0 or p["y"] > H: p["vy"] *= -1
            p["x"] = min(max(p["x"], 0), W)
            p["y"] = min(max(p["y"], 0), H)
            p["phase"] = (p["phase"] + 0.008 * speed * f) % math.tau

        if repel > 0:
            n = len(P)
            for i in range(n):
                p1 = P[i]
                for j in range(i + 1, n):
                    p2 = P[j]
                    dx, dy = p1["x"] - p2["x"], p1["y"] - p2["y"]
                    d = math.hypot(dx, dy)
                    if 0 < d < repel:
                        push = (repel - d) * 0.04 * f
                        nx, ny = dx / d, dy / d
                        p1["x"] += nx * push; p1["y"] += ny * push
                        p2["x"] -= nx * push; p2["y"] -= ny * push
            for p in P:
                p["x"] = min(max(p["x"], 0), W)
                p["y"] = min(max(p["y"], 0), H)

        nodes = P + [{"x": self.mx, "y": self.my}]
        links = []
        for i in range(len(nodes)):
            p1 = nodes[i]
            for j in range(i + 1, len(nodes)):
                p2 = nodes[j]
                dist = math.hypot(p1["x"] - p2["x"], p1["y"] - p2["y"])
                if dist < link_max:
                    links.append((dist, p1, p2))
        if len(links) > self.max_lines:
            links.sort(key=lambda l: l[0])
            links = links[:self.max_lines]

        for _, p1, p2 in links:
            ax, ay, bx, by = p1["x"], p1["y"], p2["x"], p2["y"]
            dx, dy = bx - ax, by - ay
            d = math.hypot(dx, dy)
            if d < 1:
                continue
            pxu, pyu = -dy / d, dx / d
            sign = 1 if (p1.get("id", 0) ^ p2.get("id", 0)) & 1 else -1
            wave = math.sin(t0 * 0.4 + (p1.get("phase", 0) + p2.get("phase", 0)) * 0.5)
            bulge = sign * min(CURVE_MAX, d * CURVE_AMOUNT * (1.0 + 0.25 * wave))
            cpx = (ax + bx) / 2 + pxu * bulge
            cpy = (ay + by) / 2 + pyu * bulge
            pts = []
            for s in range(self.steps + 1):
                t = s / self.steps
                mt = 1.0 - t
                pts += [mt * mt * ax + 2 * mt * t * cpx + t * t * bx,
                        mt * mt * ay + 2 * mt * t * cpy + t * t * by]
            c.create_line(*pts, fill=line_color, width=1.5, tags="net",
                          capstyle="round", joinstyle="round")
        c.tag_lower("net")

    def _tick(self):
        if self._closed:
            return
        t0 = time.perf_counter()
        dt = min(t0 - self._last_net_t, 0.1)
        self._last_net_t = t0
        try:
            if self._win_drag is None and self._drag is None:
                self._draw_net(t0, dt)
            work_ms = (time.perf_counter() - t0) * 1000.0
            frame_ms = LOW_FRAME_MS if self.low else BG_FRAME_MS
            self._tick_job = self.after(max(4, int(frame_ms - work_ms)), self._tick)
        except tk.TclError:
            pass

    # ---------- Rendering ----------
    def _schedule_render(self):
        """Coalesce renders so dragging / zooming updates at ~DRAG_INTERVAL_MS."""
        if self._render_job is not None:
            return
        wait = max(1, int(DRAG_INTERVAL_MS - (time.perf_counter() - self._render_last) * 1000.0))
        self._render_job = self.after(wait, self._render_now)

    def _render_now(self):
        self._render_job = None
        self._render(fast=True)
        self._render_last = time.perf_counter()

    def _render(self, fast=False):
        if self._closed:
            return
        PW, PH, M = self.PREV_W, self.PREV_H, self.MARGIN
        SW, SH = self.SW, self.SH
        iw, ih = self.work.size
        x0, y0, dw, dh, self.ox, self.oy = image_layout(iw, ih, PW, PH, self.zoom, self.ox, self.oy)

        # Whole stage with the image placed on it (parts outside the frame included)
        layer = Image.new("RGB", (SW, SH), (18, 18, 31))
        paste_scaled(layer, self.work, x0 + M, y0 + M, dw, dh,
                     Image.NEAREST if fast else Image.BILINEAR)

        # Outside the frame: dimmed. Inside: how it will really look.
        stage = Image.blend(Image.new("RGB", (SW, SH), (6, 6, 10)), layer, 0.45)
        inner = layer.crop((M, M, M + PW, M + PH))
        if self.show_opacity.get():
            inner = Image.blend(Image.new("RGB", inner.size, (18, 18, 31)), inner, self.opacity)
        stage.paste(inner, (M, M))

        self._photo = ImageTk.PhotoImage(stage)
        c = self.canvas
        c.delete("stage")
        sx, sy = self.stage_x, self.stage_y
        c.create_image(sx, sy, anchor="nw", image=self._photo, tags="stage")
        c.create_rectangle(sx + M, sy + M, sx + M + PW, sy + M + PH,
                           outline=self.accent, width=2, tags="stage")

        # Marker showing where the bottom of the app window currently sits
        if self.visible_frac < 0.99:
            y = sy + M + int(PH * self.visible_frac)
            c.create_line(sx + M, y, sx + M + PW, y, fill=self.accent, dash=(6, 4),
                          width=2, tags="stage")
            c.create_text(sx + M + 6, y - 8, text="window bottom", anchor="w",
                          fill="#000000", font=("Segoe UI", 8, "bold"), tags="stage")
            c.create_text(sx + M + 5, y - 9, text="window bottom", anchor="w",
                          fill="#ffffff", font=("Segoe UI", 8, "bold"), tags="stage")

    # ---------- Smooth window dragging (same as the main window) ----------
    def _start_native_drag(self):
        user32 = ctypes.windll.user32
        user32.GetParent.restype = wt.HWND
        user32.GetParent.argtypes = [wt.HWND]
        user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_int, wt.UINT]
        user32.SetWindowPos.restype = wt.BOOL

        hwnd = user32.GetParent(self.winfo_id())
        pt = wt.POINT()
        rect = wt.RECT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.GetWindowRect(hwnd, ctypes.byref(rect))

        self._hwnd = hwnd
        self._drag_off = (pt.x - rect.left, pt.y - rect.top)
        self._pos = [float(rect.left), float(rect.top)]
        self._target = (float(rect.left), float(rect.top))
        self._last_pos = (rect.left, rect.top)
        self._last_t = time.perf_counter()
        self._released = False
        self._native = True
        try:
            ctypes.windll.winmm.timeBeginPeriod(1)
            self._timer_on = True
        except Exception:
            pass
        self._drag_tick()

    def _drag_tick(self):
        if self._closed or not (self._win_drag is not None and self._native):
            return
        user32 = ctypes.windll.user32
        now = time.perf_counter()
        dt = min(now - self._last_t, 0.05)
        self._last_t = now

        if not self._released:
            if not (user32.GetAsyncKeyState(0x01) & 0x8000):
                self._released = True
            else:
                pt = wt.POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                self._target = (pt.x - self._drag_off[0], pt.y - self._drag_off[1])

        k = 1.0 - math.exp(-DRAG_SMOOTHING * dt)
        self._pos[0] += (self._target[0] - self._pos[0]) * k
        self._pos[1] += (self._target[1] - self._pos[1]) * k

        settled = (abs(self._target[0] - self._pos[0]) < 0.5 and
                   abs(self._target[1] - self._pos[1]) < 0.5)
        if self._released and settled:
            self._pos = [self._target[0], self._target[1]]

        nx, ny = int(round(self._pos[0])), int(round(self._pos[1]))
        if (nx, ny) != self._last_pos:
            user32.SetWindowPos(self._hwnd, None, nx, ny, 0, 0, 0x0001 | 0x0004 | 0x0010)
            self._last_pos = (nx, ny)

        if self._released and settled:
            self._end_win_drag()
            return
        self.after(DRAG_INTERVAL_MS, self._drag_tick)

    def _end_win_drag(self):
        self._win_drag = None
        self._native = False
        if self._timer_on:
            self._timer_on = False
            try:
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass

    # ---------- Interaction ----------
    def _in_stage(self, x, y):
        return (self.stage_x <= x <= self.stage_x + self.SW and
                self.stage_y <= y <= self.stage_y + self.SH)

    def _zoom_at(self, z1, ax, ay):
        """Zoom to z1 keeping the point (ax, ay) (frame pixels) fixed on screen."""
        z1 = min(max(float(z1), BG_MIN_ZOOM), BG_MAX_ZOOM)
        PW, PH = self.PREV_W, self.PREV_H
        r = z1 / self.zoom
        cx = ax + ((0.5 + self.ox) * PW - ax) * r
        cy = ay + ((0.5 + self.oy) * PH - ay) * r
        self.ox, self.oy = cx / PW - 0.5, cy / PH - 0.5
        self.zoom = z1
        self._schedule_render()

    def _on_slider(self, value):
        self._zoom_at(float(value), self.PREV_W / 2, self.PREV_H / 2)

    def _wheel(self, event):
        if not self._in_stage(event.x, event.y):
            return
        z = self.zoom * (1.1 if event.delta > 0 else 1 / 1.1)
        self._zoom_at(z, event.x - self.stage_x - self.MARGIN, event.y - self.stage_y - self.MARGIN)
        self.zoom_var.set(round(self.zoom, 2))

    def _press(self, event):
        if event.y < BAR_H:
            if event.x >= self.D_W - 36:
                self.destroy()
                return
            self._win_drag = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())
            self._native = False
            if os.name == "nt":
                try:
                    self._start_native_drag()
                except Exception:
                    self._native = False
        elif self._in_stage(event.x, event.y):
            self._drag = (event.x, event.y)

    def _move(self, event):
        if self._win_drag is not None:
            if not self._native:
                self.geometry(f"+{event.x_root - self._win_drag[0]}+{event.y_root - self._win_drag[1]}")
        elif self._drag is not None:
            dx, dy = event.x - self._drag[0], event.y - self._drag[1]
            self._drag = (event.x, event.y)
            self.ox += dx / self.PREV_W
            self.oy += dy / self.PREV_H
            self._schedule_render()

    def _release(self, event):
        if self._drag is not None:
            self._drag = None
            self._render()            # final high-quality render
        if self._win_drag is not None:
            if self._native:
                self._released = True  # let the smoothing settle, then it ends itself
            else:
                self._win_drag = None

    def _hover(self, event):
        self.tx, self.ty = event.x, event.y
        over_close = event.y < BAR_H and event.x >= self.D_W - 36
        self.canvas.itemconfigure(self.close_txt, fill="#ef4444" if over_close else TEXT_LIGHT)
        if self._in_stage(event.x, event.y):
            cursor = "fleur"
        elif over_close or any(b.hit(event.x, event.y) for b in self.buttons):
            cursor = "hand2"
        else:
            cursor = ""
        self.canvas.config(cursor=cursor)

    def _reset(self):
        self.zoom, self.ox, self.oy = 1.0, 0.0, 0.0
        self.zoom_var.set(1.0)
        self._render()

    def _apply(self):
        zoom, ox, oy = self.zoom, self.ox, self.oy
        self.destroy()
        self.on_apply(zoom, ox, oy)

    def destroy(self):
        if self._closed:
            return
        self._closed = True
        for job in (self._tick_job, self._render_job):
            if job is not None:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        self._end_win_drag()
        super().destroy()


class ScreenshotterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Screenshotter")
        self.root.geometry(f"{WIN_W}x{WIN_H}+100+10")
        self.root.resizable(False, False)
        self.root.configure(bg=BG_MAIN)

        self.root.overrideredirect(True)
        self.minimized = False
        self._dragging = False
        self._native_drag = False
        self._drag_dx = 0
        self._drag_dy = 0
        self._drag_hwnd = None
        self._drag_off = (0, 0)
        self._last_pos = (0, 0)
        self._released = False
        self._pos = [0.0, 0.0]
        self._target = (0.0, 0.0)
        self._last_t = 0.0

        self.sx = 1.0
        self.sy = 1.0
        self._rs_last = 0.0
        self._font_scale_applied = 1.0
        self._resizing = None
        self._rs_off = (0.0, 0.0)
        self._rs_target = None
        self._rs_job = None
        self._scalables = []
        self._ppp = 1.333
        self._bg_cache = None

        self.is_armed = False
        self.is_running = False
        self.stop_thread = False
        self.save_folder = ""
        self.count = 1
        self.worker_thread = None
        self._save_job = None

        self.page = "main"
        self.page_pos = 0.0
        self._page_anim = False
        self._fade_q = {p: 1.0 for p in PAGES}
        self._snap = None
        self._panels_dirty = True
        self._bar_sig = None
        self._timer_refs = 0
        self.page_from = 0.0
        self.page_to = 0.0
        self.page_dur = 0.0
        self.page_start = 0.0
        self.stack = []
        self.win_h = WIN_H
        self._h_last = 0.0
        self._anim_job = None
        self._timer_res_on = False
        self._dialog_open = False

        self.mouse_x = WIN_W / 2
        self.mouse_y = WIN_H / 2
        self.target_x = WIN_W / 2
        self.target_y = WIN_H / 2

        self.particles = []
        self.panel_cache = {}
        self._panel_items = {}
        self.bar_cache = {}
        self._blend_cache = {}

        saved_config = self.load_config()

        # Restore the window position and the page that was open last time
        self._restore_position(saved_config)
        saved_page = saved_config.get("page")
        if saved_page in PAGES:
            self.page = saved_page
            self.page_pos = float(PAGES.index(saved_page))

        self.dir_var = tk.StringVar(value=saved_config.get("dir", ""))
        self.max_shots_var = tk.StringVar(value=saved_config.get("max_shots", ""))
        self.max_mb_var = tk.StringVar(value=saved_config.get("max_mb", ""))
        self.delay_var = tk.StringVar(value=saved_config.get("delay", ""))
        self.name_var = tk.StringVar(value=saved_config.get("name", ""))
        self.toggle_key_var = tk.StringVar(value=saved_config.get("toggle_key", ""))
        self.single_key_var = tk.StringVar(value=saved_config.get("single_key", ""))
        self.quit_key_var = tk.StringVar(value=saved_config.get("quit_key", ""))
        self.notify_var = tk.BooleanVar(value=saved_config.get("notifications", True))
        self.low_quality_var = tk.BooleanVar(value=bool(saved_config.get("low_quality", False)))
        self.opacity_var = tk.DoubleVar(value=saved_config.get("opacity", 0.95))
        self.box_opacity_var = tk.DoubleVar(value=saved_config.get("box_opacity", 0.4))
        self.line_opacity_var = tk.DoubleVar(value=saved_config.get("line_opacity", 0.8))
        self.box_radius_var = tk.DoubleVar(value=saved_config.get("box_radius", 12.0))
        self.anim_speed_var = tk.DoubleVar(value=saved_config.get("anim_speed", 1.0))
        self.line_count_var = tk.DoubleVar(
            value=min(MAX_LINES_LIMIT, saved_config.get("line_count", 60)))
        self.spread_var = tk.DoubleVar(value=saved_config.get("spread", 0.5))
        self.bar_opacity_var = tk.DoubleVar(value=saved_config.get("bar_opacity", 0.85))

        self.line_colour_var = tk.StringVar(value=saved_config.get("line_colour", DEFAULT_LINE_COLOUR))
        self.border_colour_var = tk.StringVar(value=saved_config.get("border_colour", DEFAULT_BORDER_COLOUR))
        self.box_colour_var = tk.StringVar(value=saved_config.get("box_colour", DEFAULT_BOX_COLOUR))
        self.accent_colour_var = tk.StringVar(value=saved_config.get("accent_colour", DEFAULT_ACCENT_COLOUR))
        self.colour_widgets = []
        self.theme_widgets = []
        self.backup_widgets = []
        self.image_opacity_var = tk.DoubleVar(value=saved_config.get("image_opacity", 0.5))
        try:
            self.bg_view = clean_view(saved_config.get("bg_zoom", 1.0),
                                      saved_config.get("bg_ox", 0.0),
                                      saved_config.get("bg_oy", 0.0))
        except (TypeError, ValueError):
            self.bg_view = [1.0, 0.0, 0.0]
        self.bg_src = None
        self._bg_photo = None

        self.root.attributes('-alpha', self.opacity_var.get())

        self.max_screenshots = 0
        self.max_folder_size_mb = 0.0
        self.interval = 0.0
        self.file_prefix = "screenshot"
        self.toggle_hotkey = ""
        self.single_hotkey = ""
        self.quit_hotkey = ""
        self.send_notifications = True

        self.themed_widgets = []
        self.build_ui()
        self.update_box_theme()

        self._load_bg_source()
        self.render_background()
        self.image_opacity_var.trace_add("write", lambda *a: self.render_background())

        # Restore which boxes were collapsed last time
        collapsed = saved_config.get("collapsed", [])
        if isinstance(collapsed, list):
            for s in self.stack:
                if s.panel and s.key in collapsed:
                    s.p = s.target = 0.0

        self._apply_layout(self.stack)

        # Everything the user can change is saved automatically a moment after it changes
        for var in (self.opacity_var, self.bar_opacity_var, self.box_opacity_var,
                    self.line_opacity_var, self.box_radius_var, self.anim_speed_var,
                    self.line_count_var, self.spread_var, self.notify_var,
                    self.line_colour_var, self.border_colour_var, self.box_colour_var,
                    self.image_opacity_var, self.accent_colour_var, self.low_quality_var,
                    self.dir_var, self.max_shots_var, self.max_mb_var, self.delay_var,
                    self.name_var, self.toggle_key_var, self.single_key_var, self.quit_key_var):
            var.trace_add("write", lambda *a: self.schedule_save())

        for var in (self.box_opacity_var, self.box_radius_var,
                    self.box_colour_var, self.border_colour_var):
            var.trace_add("write", lambda *a: setattr(self, "_panels_dirty", True))

        # Live-update all accent-coloured canvas items when accent colour changes
        self.accent_colour_var.trace_add("write", lambda *a: self._apply_accent_colour())
        self.low_quality_var.trace_add("write", lambda *a: self._on_quality_change())

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.root.bind("<Motion>", self.on_mouse_motion)
        self.root.bind("<Map>", self.on_map)
        self.bg_canvas.bind("<ButtonPress-1>", self.bar_press, add="+")
        self.bg_canvas.bind("<ButtonPress-1>", self.section_press, add="+")
        self.bg_canvas.bind("<ButtonPress-1>", self.tab_press, add="+")
        self.bg_canvas.bind("<ButtonPress-1>", self.resize_press, add="+")
        self.bg_canvas.bind("<B1-Motion>", self.bar_drag, add="+")
        self.bg_canvas.bind("<B1-Motion>", self.resize_drag, add="+")
        self.bg_canvas.bind("<ButtonRelease-1>", self.bar_release, add="+")
        self.bg_canvas.bind("<ButtonRelease-1>", self.resize_release, add="+")
        self.bg_canvas.bind("<Motion>", self.bar_hover, add="+")

        try:
            old = float(saved_config.get("window_scale", 1.0))
            self.set_scale(float(saved_config.get("window_sx", old)),
                           float(saved_config.get("window_sy", old)))
        except (TypeError, ValueError):
            pass
        self._place_grip()

        self.root.after(50, self.show_in_taskbar)
        self._set_timer_resolution(True)
        self._bg_last = time.perf_counter()
        self.animate_background()

        # Apply the saved accent colour on startup
        self._apply_accent_colour()

    @property
    def scale(self):
        return min(self.sx, self.sy)

    def _on_quality_change(self):
        """Called when the Low quality checkbox is toggled."""
        on = self.low_quality_var.get()
        try:
            self.render_background()
            self.status_label.config(
                text="Status: Low quality mode " + ("on." if on else "off."), fg=TEXT_MUTED)
        except Exception:
            pass

    def _accent(self):
        """Current accent colour, falling back to the default blue."""
        return parse_hex(self.accent_colour_var.get()) or DEFAULT_ACCENT_COLOUR

    def _apply_accent_colour(self):
        """Repaint every canvas item that uses the accent (blue) colour."""
        colour = self._accent()
        c = self.bg_canvas

        # Tab indicator underline
        if hasattr(self, "tab_indicator"):
            c.itemconfigure(self.tab_indicator, fill=colour)

        # Section header titles and chevrons
        for s in self.stack:
            if s.panel and s.title:
                for item in c.find_withtag(s.htag):
                    kind = c.type(item)
                    if kind == "text":
                        c.itemconfigure(item, fill=colour)
                    elif kind == "line":
                        c.itemconfigure(item, fill=colour)

        # Sliders: fill lines and checkbox borders
        for s in self.stack:
            for w in s.widgets:
                if isinstance(w, CanvasSlider) and w.enabled:
                    c.itemconfigure(w.fill_line, fill=colour)
                elif isinstance(w, CanvasCheckbox) and w.enabled:
                    c.itemconfigure(w.box, outline=colour)

        # Colour swatch entry border highlight update (the swatch itself is handled by _refresh_swatch)
        ok = parse_hex(self.accent_colour_var.get())
        if hasattr(self, "accent_swatch") and ok:
            self.accent_swatch.config(bg=ok, activebackground=ok)

        # Update the global ACCENT_BLUE used by refresh() methods so newly drawn items use the new colour
        global ACCENT_BLUE
        ACCENT_BLUE = colour

    # ---------- Colour helpers ----------
    def _rgb(self, var, default):
        return hex_to_rgb(parse_hex(var.get()) or default)

    def _refresh_swatch(self, var, swatch, entry):
        ok = parse_hex(var.get())
        if ok:
            swatch.config(bg=ok, activebackground=ok)
        entry.config(fg=TEXT_LIGHT if ok else "#ef4444")

    def pick_colour(self, var, title, default):
        current = parse_hex(var.get()) or default
        result = colorchooser.askcolor(color=current, title=title, parent=self.root)
        if result and result[1]:
            var.set(result[1])

    # ---------- Window scaling ----------
    def _max_scales(self):
        try:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight() - 80
            return (max(MIN_SCALE, min(MAX_SCALE, sw / WIN_W)),
                    max(MIN_SCALE, min(MAX_SCALE, sh / self.win_h)))
        except Exception:
            return MAX_SCALE, MAX_SCALE

    def _font_base(self, spec):
        try:
            a = tkfont.Font(root=self.root, font=spec).actual()
            size = a["size"]
            px = -size if size < 0 else size * self._ppp
            return (a["family"], max(1.0, px), a["weight"], a["slant"])
        except tk.TclError:
            return None

    def _font_spec(self, base):
        family, px, weight, slant = base
        spec = [family, -max(1, int(round(px * self.scale)))]
        if weight == "bold":
            spec.append("bold")
        if slant == "italic":
            spec.append("italic")
        return tuple(spec)

    def _index_scalables(self):
        c = self.bg_canvas
        self._ppp = self.root.winfo_fpixels("1p")
        self._scalables = []
        for item in c.find_all():
            kind = c.type(item)
            rec = {"item": item, "kind": kind}
            if kind == "text":
                rec["font"] = self._font_base(c.itemcget(item, "font"))
                w = float(c.itemcget(item, "width") or 0)
                if w > 0:
                    rec["width"] = w
            elif kind in ("line", "rectangle", "polygon"):
                rec["lw"] = float(c.itemcget(item, "width"))
            elif kind == "window":
                try:
                    widget = self.root.nametowidget(c.itemcget(item, "window"))
                except Exception:
                    continue
                rec["widget"] = widget
                w = float(c.itemcget(item, "width") or 0)
                h = float(c.itemcget(item, "height") or 0)
                if w > 0:
                    rec["width"] = w
                if h > 0:
                    rec["height"] = h
                try:
                    rec["font"] = self._font_base(widget.cget("font"))
                except tk.TclError:
                    pass
            else:
                continue
            self._scalables.append(rec)

    def _rescale_items(self):
        c = self.bg_canvas
        sx, sy, S = self.sx, self.sy, self.scale
        do_fonts = abs(S - self._font_scale_applied) > 1e-4
        self._font_scale_applied = S
        for r in self._scalables:
            item, kind = r["item"], r["kind"]
            fspec = None
            if do_fonts and r.get("font"):
                fspec = self._font_spec(r["font"])
            try:
                if kind == "text":
                    opts = {}
                    if fspec:
                        opts["font"] = fspec
                    if "width" in r:
                        opts["width"] = r["width"] * sx
                    if opts:
                        c.itemconfigure(item, **opts)
                elif kind == "window":
                    opts = {}
                    if "width" in r:
                        opts["width"] = r["width"] * sx
                    if "height" in r:
                        opts["height"] = r["height"] * sy
                    if opts:
                        c.itemconfigure(item, **opts)
                    if fspec:
                        r["widget"].config(font=fspec)
                elif do_fonts:
                    c.itemconfigure(item, width=r["lw"] * S)
            except tk.TclError:
                pass

    def set_scale(self, sx=None, sy=None, fast=False):
        maxx, maxy = self._max_scales()
        sx = self.sx if sx is None else sx
        sy = self.sy if sy is None else sy
        sx = min(max(float(sx), MIN_SCALE), maxx)
        sy = min(max(float(sy), MIN_SCALE), maxy)
        if abs(sx - self.sx) < 0.001 and abs(sy - self.sy) < 0.001:
            return
        kx, ky = sx / self.sx, sy / self.sy
        self.sx, self.sy = sx, sy
        c = self.bg_canvas
        c.ui_scale = (sx, sy)

        c.delete("panel_bg")
        self._panel_items.clear()
        c.delete("bar_bg")
        c.scale("all", 0, 0, kx, ky)
        self._rescale_items()
        for sec in self.stack:
            for w in sec.widgets:
                w.refresh()

        self.panel_cache.clear()
        self.bar_cache.clear()
        self._draw_bar()
        self.render_background(fast=fast)
        self._update_geometry()
        self._apply_layout([])
        self._panels_dirty = False
        self.schedule_save()

    def _update_geometry(self):
        w = int(round(WIN_W * self.sx))
        h = int(round(self.win_h * self.sy))
        self.root.geometry(f"{w}x{h}")
        self._place_grip()

    def _place_grip(self):
        c = self.bg_canvas
        c.delete("grip")
        S = self.scale
        w, h = WIN_W * self.sx, self.win_h * self.sy
        for i in range(3):
            off = (5 + 4 * i) * S
            c.create_line(w - 3 * S, h - off, w - off, h - 3 * S,
                          fill="#475569", width=max(1.0, S), tags="grip")
        c.tag_raise("grip")

    def _resize_zone(self, x, y):
        w, h = WIN_W * self.sx, self.win_h * self.sy
        if x >= w - RESIZE_CORNER and y >= h - RESIZE_CORNER:
            return "corner"
        if x >= w - RESIZE_EDGE and y >= BAR_H * self.sy:
            return "right"
        if y >= h - RESIZE_EDGE:
            return "bottom"
        return None

    def resize_press(self, event):
        zone = self._resize_zone(event.x, event.y)
        if zone is None:
            return
        self._resizing = zone
        self._rs_off = (WIN_W * self.sx - event.x, self.win_h * self.sy - event.y)
        self._rs_target = None
        self._rs_last = 0.0
        self._set_timer_resolution(True)

    def resize_drag(self, event):
        if not self._resizing:
            return
        tx = (event.x + self._rs_off[0]) / WIN_W
        ty = (event.y + self._rs_off[1]) / self.win_h
        if event.state & 0x4:
            if self._resizing == "right":
                t = tx
            elif self._resizing == "bottom":
                t = ty
            else:
                t = (tx + ty) / 2.0
            if CTRL_RESIZE_STEP > 0:
                t = round(t / CTRL_RESIZE_STEP) * CTRL_RESIZE_STEP
            t = min(t, *self._max_scales())
            tx = ty = t
        else:
            if self._resizing == "bottom":
                tx = None
            elif self._resizing == "right":
                ty = None
        self._rs_target = (tx, ty)
        if self._rs_job is None:
            interval = LOW_RESIZE_MS if self.low_quality_var.get() else RESIZE_INTERVAL_MS
            wait = max(1, int(interval - (time.perf_counter() - self._rs_last) * 1000.0))
            self._rs_job = self.root.after(wait, self._resize_apply)

    def _resize_apply(self):
        self._rs_job = None
        t = self._rs_target
        if t is not None:
            self.set_scale(t[0], t[1], fast=True)
        self._rs_last = time.perf_counter()

    def resize_release(self, event):
        if not self._resizing:
            return
        self._resizing = None
        if self._rs_job is not None:
            self.root.after_cancel(self._rs_job)
            self._rs_job = None
        t, self._rs_target = self._rs_target, None
        if t is not None:
            self.set_scale(t[0], t[1])
        self.render_background()
        self._set_timer_resolution(False)

    # ---------- Collapsible boxes ----------
    def _header_at(self, x, y):
        for s in self.stack:
            if (s.panel and s.h >= 30 and s.top <= y <= s.top + 27
                    and PANEL_X1 + s.x <= x <= PANEL_X2 + s.x):
                return s
        return None

    def section_press(self, event):
        s = self._header_at(event.x / self.sx, event.y / self.sy)
        if s is not None:
            self.toggle_section(s)

    def _tab_at(self, x, y):
        if not (TAB_Y - 14 <= y <= TAB_Y + 16):
            return None
        for key, _, x0, x1 in self.tab_defs:
            if x0 <= x <= x1:
                return key
        return None

    def tab_press(self, event):
        key = self._tab_at(event.x / self.sx, event.y / self.sy)
        if key is not None:
            self.goto_page(key)

    def _update_tabs(self):
        sx, sy = self.sx, self.sy
        n = len(self.tab_defs)
        pos = min(max(self.page_pos, 0.0), n - 1.0)
        i = min(int(pos), n - 2)
        frac = pos - i
        _, _, a0, a1 = self.tab_defs[i]
        _, _, b0, b1 = self.tab_defs[i + 1]
        x0 = a0 + (b0 - a0) * frac
        x1 = a1 + (b1 - a1) * frac
        self.bg_canvas.coords(self.tab_indicator, x0 * sx, (TAB_Y + 14) * sy, x1 * sx, (TAB_Y + 14) * sy)
        active = int(round(pos))
        for idx, (key, _, _, _) in enumerate(self.tab_defs):
            self.bg_canvas.itemconfigure(self.tab_texts[key], fill=TEXT_LIGHT if idx == active else TEXT_MUTED)

    def _blend_colour(self, colour, a):
        key = (colour, a)
        hit = self._blend_cache.get(key)
        if hit is not None:
            return hit
        r, g, b = self.root.winfo_rgb(colour)
        r, g, b = r >> 8, g >> 8, b >> 8
        out = "#{:02x}{:02x}{:02x}".format(
            int(18 + (r - 18) * a), int(18 + (g - 18) * a), int(31 + (b - 31) * a))
        if len(self._blend_cache) > 5000:
            self._blend_cache.clear()
        self._blend_cache[key] = out
        return out

    def _take_snapshot(self, page):
        c = self.bg_canvas
        snap = {page: []}
        for s in self.stack:
            if s.page != page:
                continue
            for item in c.find_withtag(s.tag):
                kind = c.type(item)
                if kind in ("text", "line"):
                    opts = ["fill"]
                elif kind == "rectangle":
                    opts = ["outline"]
                elif kind == "polygon":
                    opts = ["fill", "outline"]
                elif kind == "window":
                    try:
                        w = self.root.nametowidget(c.itemcget(item, "window"))
                    except Exception:
                        continue
                    wopts = (["bg", "fg", "activebackground", "activeforeground",
                              "highlightbackground", "highlightcolor"]
                             if isinstance(w, tk.Button) else
                             ["bg", "fg", "highlightbackground", "highlightcolor"])
                    vals = {}
                    for o in wopts:
                        try:
                            vals[o] = w.cget(o)
                        except tk.TclError:
                            pass
                    snap[s.page].append(("widget", w, vals))
                    continue
                else:
                    continue
                vals = {}
                for o in opts:
                    v = c.itemcget(item, o)
                    if v:
                        vals[o] = v
                if vals:
                    snap[s.page].append(("item", item, vals))
        return snap[page]

    def _apply_colours(self, entries, a):
        c = self.bg_canvas
        for kind, target, vals in entries:
            conf = {o: (v if a >= 1.0 else self._blend_colour(v, a)) for o, v in vals.items()}
            try:
                if kind == "item":
                    c.itemconfigure(target, **conf)
                else:
                    target.config(**conf)
            except tk.TclError:
                pass

    def _update_fade(self):
        if not PAGE_FADE:
            return
        pg = self.page_pos
        if not self._page_anim and float(pg).is_integer():
            if self._snap is not None:
                for page, entries in self._snap.items():
                    self._apply_colours(entries, 1.0)
                self._snap = None
            self._fade_q = {p: 1.0 for p in PAGES}
            return

        if self._snap is None:
            self._snap = {}

        for idx, page in enumerate(PAGES):
            # A page that is a full page away and was never touched is not on screen: leave it alone
            if abs(pg - idx) >= 1.0 and page not in self._snap:
                continue
            a = smoothstep(1.0 - 2.0 * abs(pg - idx))
            q = round(a * FADE_STEPS) / FADE_STEPS
            if q != self._fade_q.get(page):
                if page not in self._snap:
                    self._snap[page] = self._take_snapshot(page)
                self._fade_q[page] = q
                self._apply_colours(self._snap[page], q)

    def goto_page(self, page):
        if page == self.page:
            return
        self.page = page
        self.schedule_save()
        if self.low_quality_var.get():
            self._page_anim = False
            self.page_pos = float(PAGES.index(page))
            self._apply_layout([])
            return
        self.page_from = self.page_pos
        self.page_to = float(PAGES.index(page))
        self.page_dur = max(0.05, (PAGE_ANIM_MS / 1000.0) * min(abs(self.page_to - self.page_from), 1.6))
        self.page_start = time.perf_counter()
        self._page_anim = True
        if self._anim_job is None:
            self._set_timer_resolution(True)
            self._anim_tick()

    def toggle_section(self, s):
        s.target = 0.0 if s.target > 0.5 else 1.0
        self.schedule_save()
        if self.low_quality_var.get():
            s.p = s.target
            s.animating = False
            self._apply_layout([s])
            return
        s.anim_from = s.p
        s.anim_to = s.target
        s.anim_dur = max(0.05, (SECTION_ANIM_MS / 1000.0) * abs(s.anim_to - s.anim_from))
        s.anim_start = time.perf_counter()
        s.animating = True
        if self._anim_job is None:
            self._set_timer_resolution(True)
            self._anim_tick()

    def _set_timer_resolution(self, on):
        if os.name != "nt":
            return
        try:
            if on:
                ctypes.windll.winmm.timeBeginPeriod(1)
                self._timer_refs += 1
            elif self._timer_refs > 0:
                ctypes.windll.winmm.timeEndPeriod(1)
                self._timer_refs -= 1
        except Exception:
            pass

    def _anim_tick(self):
        t0 = time.perf_counter()
        self.bg_canvas.busy = True
        changed = []
        still_running = False

        for s in self.stack:
            moved = False
            if s.animating:
                t = (t0 - s.anim_start) / s.anim_dur
                t = min(max(t, 0.0), 1.0)
                if t >= 1.0:
                    s.p = s.anim_to
                    s.animating = False
                else:
                    s.p = s.anim_from + (s.anim_to - s.anim_from) * ease_in_out_cubic(t)
                    still_running = True
                moved = True
            if moved:
                changed.append(s)

        page_moved = False
        if self._page_anim:
            t = (t0 - self.page_start) / self.page_dur
            t = min(max(t, 0.0), 1.0)
            if t >= 1.0:
                self.page_pos = self.page_to
                self._page_anim = False
            else:
                self.page_pos = self.page_from + (self.page_to - self.page_from) * ease_in_out_cubic(t)
                still_running = True
            page_moved = True

        if changed or page_moved:
            self._apply_layout(changed)
            self.bg_canvas.update_idletasks()

        if still_running:
            work_ms = (time.perf_counter() - t0) * 1000.0
            delay = max(1, int(SECTION_ANIM_INTERVAL_MS - work_ms))
            self._anim_job = self.root.after(delay, self._anim_tick)
        else:
            self._anim_job = None
            self.bg_canvas.busy = False
            self._set_timer_resolution(False)

    def _apply_layout(self, changed):
        c = self.bg_canvas
        pg = self.page_pos
        sx, sy = self.sx, self.sy

        tops = {}
        ends = {}
        for page in PAGES:
            y = 0
            for s in self.stack:
                if s.page == page:
                    y += s.gap
                    s.h = s.height()
                    tops[s.key] = y
                    y += s.h
            ends[page] = y

        pos = min(max(pg, 0.0), len(PAGES) - 1.0)
        i = min(int(pos), len(PAGES) - 2)
        frac = pos - i
        y = ends[PAGES[i]] + (ends[PAGES[i + 1]] - ends[PAGES[i]]) * frac
        y_base = y
        for s in self.stack:
            if s.page == "both":
                y += s.gap
                s.h = s.height()
                tops[s.key] = int(round(y))
                y += s.h
        both_h = y - y_base

        new_h = int(round(y)) + WIN_BOTTOM_PAD
        if self._page_anim and not PAGE_ANIM_RESIZE_WINDOW:
            # Hold the window at the taller of the pages being slid between, so it is
            # resized once at each end of the slide instead of every frame
            lo_i = int(math.floor(min(self.page_from, self.page_to) + 1e-6))
            hi_i = int(math.ceil(max(self.page_from, self.page_to) - 1e-6))
            hold = max(ends[PAGES[i]] for i in range(lo_i, hi_i + 1))
            new_h = int(round(hold + both_h)) + WIN_BOTTOM_PAD
        elif self._page_anim:
            # Glide the height with the slide, but only resize ~60 times a second: the page
            # content still moves every frame, only the (expensive) window resize is limited
            now = time.perf_counter()
            if now - self._h_last < PAGE_RESIZE_MS / 1000.0:
                new_h = self.win_h
            else:
                self._h_last = now
        if new_h != self.win_h:
            self.win_h = new_h
            self._update_geometry()

        for s in self.stack:
            if s.page == "both":
                nx = 0
            else:
                nx = int(round((PAGES.index(s.page) - pg) * WIN_W))
            dx = nx - s.x
            dy = tops[s.key] - s.top
            if self._page_anim and abs(nx) >= WIN_W and abs(s.x) >= WIN_W:
                continue   # off-screen before and after: skip, it catches up when it moves
            if dx or dy:
                c.move(s.tag, dx * sx, dy * sy)
            if dx:
                for w in s.widgets:
                    w.shift_x(dx)
            s.x = nx
            s.top = tops[s.key]

        for s in changed:
            self._update_visibility(s)
        for s in (changed if self._page_anim else self.stack):
            self._update_chevron(s)
        self._update_tabs()
        self._update_fade()

        self.draw_panels()

    def _update_visibility(self, s):
        c = self.bg_canvas
        for rec in s.items:
            vis = rec[1] <= s.h - rec[3]
            if vis != rec[2]:
                c.itemconfigure(rec[0], state="normal" if vis else "hidden")
                rec[2] = vis
        wlimit = s.h - 6
        for w in s.widgets:
            w.set_visible((w.cur_y() - s.top) + 18 <= wlimit)

    def _update_chevron(self, s):
        if s.chevron is None:
            return
        sx, sy, S = self.sx, self.sy, self.scale
        ang = math.radians(-90 * (1 - s.p))
        cos_a, sin_a = math.cos(ang), math.sin(ang)
        cx, cy = PANEL_X1 + s.x + 16, s.top + 16
        pts = []
        for (x, y) in ((-5, -3), (0, 3), (5, -3)):
            pts += [cx * sx + (x * cos_a - y * sin_a) * S, cy * sy + (x * sin_a + y * cos_a) * S]
        self.bg_canvas.coords(s.chevron, *pts)

    def _index_sections(self):
        c = self.bg_canvas
        for s in self.stack:
            if not s.panel:
                continue
            s.items = []
            for tag, margin in ((s.ctag, 8), (s.htag, 4)):
                for item in c.find_withtag(tag):
                    bb = c.bbox(item)
                    if bb:
                        s.items.append([item, bb[3] - s.top, True, margin])

    # ---------- Panel backgrounds ----------
    def _mid_tile(self, w, mh, a, ba, fill, border):
        key = ("mid", w, mh, a, ba, fill, border)
        img = self.panel_cache.get(key)
        if img is None:
            im = Image.new("RGBA", (w, mh), fill + (a,))
            d = ImageDraw.Draw(im)
            d.line([(0, 0), (0, mh - 1)], fill=border + (ba,))
            d.line([(w - 1, 0), (w - 1, mh - 1)], fill=border + (ba,))
            img = ImageTk.PhotoImage(im)
            self.panel_cache[key] = img
        return img

    def _panel_parts(self, w, h, radius, alpha, fade=1.0):
        sx, sy, S = self.sx, self.sy, self.scale
        wp = max(1, int(round(w * sx)))
        hp = max(2, int(round(h * sy)))
        tile = max(1, int(round(TILE_H * sy)))
        a = int(255 * alpha * fade)
        ba = int(255 * fade)
        fill = self._rgb(self.box_colour_var, DEFAULT_BOX_COLOUR)
        border = self._rgb(self.border_colour_var, DEFAULT_BORDER_COLOUR)
        r = max(0, min(int(round(radius * S)), hp // 2, wp // 2))
        cap = max(1, r)
        key = ("cap", wp, cap, r, a, ba, fill, border)
        caps = self.panel_cache.get(key)
        if caps is None:
            im = Image.new("RGBA", (wp, 2 * cap), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            if r > 0:
                d.rounded_rectangle(
                    [0, 0, wp - 1, 2 * cap - 1], radius=r,
                    fill=fill + (a,), outline=border + (ba,), width=1)
            else:
                d.rectangle(
                    [0, 0, wp - 1, 2 * cap - 1],
                    fill=fill + (a,), outline=border + (ba,), width=1)
            caps = (ImageTk.PhotoImage(im.crop((0, 0, wp, cap))),
                    ImageTk.PhotoImage(im.crop((0, cap, wp, 2 * cap))))
            self.panel_cache[key] = caps

        parts = [(0, caps[0])]
        y = cap
        mid = hp - 2 * cap
        while mid > 0:
            mh = min(tile, mid)
            parts.append((y, self._mid_tile(wp, mh, a, ba, fill, border)))
            y += mh
            mid -= mh
        parts.append((y, caps[1]))
        return parts

    def draw_panels(self, reorder=True):
        """Keeps one set of canvas images per panel and just moves them while sliding.

        Panels are only rebuilt when their size, colours, opacity or fade change.
        """
        c = self.bg_canvas
        if len(self.panel_cache) > 400:
            self.panel_cache.clear()   # panels in use keep their own image references

        sx, sy = self.sx, self.sy
        alpha = self.box_opacity_var.get()
        radius = self.box_radius_var.get()
        fill = self._rgb(self.box_colour_var, DEFAULT_BOX_COLOUR)
        border = self._rgb(self.border_colour_var, DEFAULT_BORDER_COLOUR)
        w = PANEL_X2 - PANEL_X1
        live = set()
        created = False
        for s in self.stack:
            if not s.panel or s.h < 4 or abs(s.x) >= WIN_W:
                continue
            fade = self._fade_q.get(s.page, 1.0)
            if fade <= 0.0:
                continue
            live.add(s.key)
            left = int(round((PANEL_X1 + s.x) * sx))
            top = int(round(s.top * sy))
            tag = "pnl_" + s.key
            sig = (s.h, w, round(sx, 4), round(sy, 4), radius, alpha, fade, fill, border)
            rec = self._panel_items.get(s.key)
            if rec is not None and rec["sig"] == sig:
                dx, dy = left - rec["x"], top - rec["y"]
                if dx or dy:
                    c.move(tag, dx, dy)
                    rec["x"], rec["y"] = left, top
                continue
            c.delete(tag)
            imgs = []
            for off, img in self._panel_parts(w, s.h, radius, alpha, fade):
                c.create_image(left, top + off, image=img, anchor="nw", tags=("panel_bg", tag))
                imgs.append(img)
            self._panel_items[s.key] = {"sig": sig, "imgs": imgs, "x": left, "y": top}
            created = True

        for key in [k for k in self._panel_items if k not in live]:
            c.delete("pnl_" + key)
            del self._panel_items[key]

        if reorder and created:
            c.tag_lower("panel_bg")
            c.tag_lower("net")
            c.tag_lower("bg_img")

    # ---------- Custom title bar ----------
    def show_in_taskbar(self):
        if os.name != "nt":
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            style = (style & ~0x00000080) | 0x00040000
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)
            self.root.withdraw()
            self.root.after(10, self.root.deiconify)
        except Exception:
            pass

    def minimize_window(self):
        self.minimized = True
        self.root.overrideredirect(False)
        self.root.iconify()

    def on_map(self, event):
        if event.widget is self.root and self.minimized:
            self.minimized = False
            self.root.overrideredirect(True)
            self.root.after(10, self.show_in_taskbar)

    def bar_press(self, event):
        lx, ly = event.x / self.sx, event.y / self.sy
        if ly >= BAR_H:
            return
        if lx >= WIN_W - 36:
            self.on_close()
        elif lx >= WIN_W - 72:
            self.minimize_window()
        else:
            self._dragging = True
            self._native_drag = False
            if os.name == "nt":
                try:
                    self._start_native_drag()
                except Exception:
                    self._native_drag = False
            if not self._native_drag:
                self._drag_dx = event.x_root - self.root.winfo_x()
                self._drag_dy = event.y_root - self.root.winfo_y()

    def _start_native_drag(self):
        user32 = ctypes.windll.user32
        user32.GetParent.restype = wt.HWND
        user32.GetParent.argtypes = [wt.HWND]
        user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_int, wt.UINT]
        user32.SetWindowPos.restype = wt.BOOL

        hwnd = user32.GetParent(self.root.winfo_id())
        pt = wt.POINT()
        rect = wt.RECT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.GetWindowRect(hwnd, ctypes.byref(rect))

        self._drag_hwnd = hwnd
        self._drag_off = (pt.x - rect.left, pt.y - rect.top)
        self._pos = [float(rect.left), float(rect.top)]
        self._target = (float(rect.left), float(rect.top))
        self._last_pos = (rect.left, rect.top)
        self._last_t = time.perf_counter()
        self._released = False
        self._native_drag = True

        try:
            ctypes.windll.winmm.timeBeginPeriod(1)
        except Exception:
            pass

        self._drag_tick()

    def _drag_tick(self):
        if not (self._dragging and self._native_drag):
            return
        user32 = ctypes.windll.user32

        now = time.perf_counter()
        dt = min(now - self._last_t, 0.05)
        self._last_t = now

        if not self._released:
            if not (user32.GetAsyncKeyState(0x01) & 0x8000):
                self._released = True
            else:
                pt = wt.POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                self._target = (pt.x - self._drag_off[0], pt.y - self._drag_off[1])

        k = 1.0 - math.exp(-DRAG_SMOOTHING * dt)
        self._pos[0] += (self._target[0] - self._pos[0]) * k
        self._pos[1] += (self._target[1] - self._pos[1]) * k

        settled = (abs(self._target[0] - self._pos[0]) < 0.5 and
                   abs(self._target[1] - self._pos[1]) < 0.5)
        if self._released and settled:
            self._pos = [self._target[0], self._target[1]]

        nx, ny = int(round(self._pos[0])), int(round(self._pos[1]))
        if (nx, ny) != self._last_pos:
            user32.SetWindowPos(self._drag_hwnd, None, nx, ny, 0, 0, 0x0001 | 0x0004 | 0x0010)
            self._last_pos = (nx, ny)

        if self._released and settled:
            self._end_drag()
            return

        self.root.after(DRAG_INTERVAL_MS, self._drag_tick)

    def _end_drag(self):
        was_dragging = self._dragging
        was_native = self._native_drag
        self._dragging = False
        self._native_drag = False
        if was_native:
            try:
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass
        if was_dragging:
            self.schedule_save()   # remember where the window was dropped

    def bar_drag(self, event):
        if self._dragging and not self._native_drag:
            self.root.geometry(f"+{event.x_root - self._drag_dx}+{event.y_root - self._drag_dy}")

    def bar_release(self, event):
        if self._native_drag:
            self._released = True
        else:
            self._end_drag()

    def bar_hover(self, event):
        if self.bg_canvas.busy:
            return
        lx, ly = event.x / self.sx, event.y / self.sy
        over_close = ly < BAR_H and lx >= WIN_W - 36
        over_min = ly < BAR_H and WIN_W - 72 <= lx < WIN_W - 36
        over_button = any(isinstance(b, CanvasButton) and b.enabled and b.hit(event.x, event.y)
                          for b in self.theme_widgets + self.backup_widgets) or \
            self.scale_reset_btn.hit(event.x, event.y)
        over_header = (self._header_at(lx, ly) is not None or
                       self._tab_at(lx, ly) is not None or over_button)
        self.bg_canvas.itemconfigure(self.close_txt, fill="#ef4444" if over_close else TEXT_LIGHT)
        self.bg_canvas.itemconfigure(self.min_txt, fill=self._accent() if over_min else TEXT_LIGHT)

        zone = self._resize_zone(event.x, event.y)
        cursor = {"corner": "size_nw_se", "right": "sb_h_double_arrow",
                  "bottom": "sb_v_double_arrow"}.get(zone)
        if cursor is None:
            cursor = "hand2" if over_header else ""
        self.bg_canvas.config(cursor=cursor)

    # ---------- Config / saved state ----------
    def load_config(self):
        for path in (CONFIG_FILE, LEGACY_CONFIG_FILE):
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        return data
                except Exception:
                    pass
        return {}

    @staticmethod
    def _write_json(path, data):
        """Write via a temp file so a crash can never leave a half-written config behind."""
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        os.replace(tmp, path)

    @staticmethod
    def _field_value(entry, var):
        """Text for a saved field; empty if it still shows its grey placeholder."""
        return "" if getattr(entry, "is_default", False) else var.get()

    def collect_settings(self):
        """Everything portable: this is what gets saved and what Export writes."""
        return {
            "dir": self.dir_var.get(),
            "max_shots": self._field_value(self.shots_entry, self.max_shots_var),
            "max_mb": self._field_value(self.mb_entry, self.max_mb_var),
            "delay": self._field_value(self.delay_entry, self.delay_var),
            "name": self._field_value(self.name_entry, self.name_var),
            "toggle_key": self._field_value(self.toggle_entry, self.toggle_key_var),
            "single_key": self._field_value(self.single_entry, self.single_key_var),
            "quit_key": self._field_value(self.quit_entry, self.quit_key_var),
            "notifications": self.notify_var.get(),
            "low_quality": self.low_quality_var.get(),
            "opacity": self.opacity_var.get(),
            "bar_opacity": self.bar_opacity_var.get(),
            "box_opacity": self.box_opacity_var.get(),
            "line_opacity": self.line_opacity_var.get(),
            "box_radius": self.box_radius_var.get(),
            "anim_speed": self.anim_speed_var.get(),
            "line_count": self.line_count_var.get(),
            "spread": self.spread_var.get(),
            "line_colour": self.line_colour_var.get(),
            "border_colour": self.border_colour_var.get(),
            "box_colour": self.box_colour_var.get(),
            "accent_colour": self.accent_colour_var.get(),
            "image_opacity": self.image_opacity_var.get(),
            "bg_zoom": round(self.bg_view[0], 4),
            "bg_ox": round(self.bg_view[1], 4),
            "bg_oy": round(self.bg_view[2], 4),
        }

    def _ui_state(self):
        """Layout state that is saved with the app but not exported: page, boxes, window."""
        state = {
            "window_sx": round(self.sx, 4),
            "window_sy": round(self.sy, 4),
            "page": self.page,
            "collapsed": [s.key for s in self.stack if s.panel and s.target < 0.5],
        }
        try:
            if not self.minimized and self.root.state() != "iconic":
                state["window_x"] = self.root.winfo_x()
                state["window_y"] = self.root.winfo_y()
        except Exception:
            pass
        return state

    def _restore_position(self, cfg):
        try:
            x, y = int(cfg["window_x"]), int(cfg["window_y"])
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        except (KeyError, TypeError, ValueError, tk.TclError):
            return
        # Ignore positions that would leave the window off-screen (e.g. a monitor was unplugged)
        if -WIN_W // 2 <= x <= sw - 100 and 0 <= y <= sh - 100:
            self.root.geometry(f"+{x}+{y}")

    def save_appearance(self):
        """Save all settings and UI state, keeping any other keys already in the file."""
        job, self._save_job = self._save_job, None
        if job is not None:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        config = self.load_config()
        config.update(self.collect_settings())
        config.update(self._ui_state())
        try:
            self._write_json(CONFIG_FILE, config)
        except Exception:
            pass

    def save_config(self):
        self.save_appearance()

    def schedule_save(self):
        if self._save_job is not None:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(400, self.save_appearance)

    def reset_defaults(self):
        for path in (CONFIG_FILE, LEGACY_CONFIG_FILE):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

        self.dir_var.set("")
        self.notify_var.set(True)
        self.low_quality_var.set(False)
        self.opacity_var.set(0.95)
        self.bar_opacity_var.set(0.85)
        self.box_opacity_var.set(0.4)
        self.line_opacity_var.set(0.8)
        self.box_radius_var.set(12.0)
        self.anim_speed_var.set(1.0)
        self.line_count_var.set(60)
        self.spread_var.set(0.5)
        self.line_colour_var.set(DEFAULT_LINE_COLOUR)
        self.border_colour_var.set(DEFAULT_BORDER_COLOUR)
        self.box_colour_var.set(DEFAULT_BOX_COLOUR)
        self.accent_colour_var.set(DEFAULT_ACCENT_COLOUR)
        self.image_opacity_var.set(0.5)
        self.clear_background_image()
        self.root.attributes('-alpha', 0.95)
        self.set_scale(1.0, 1.0)

        defaults = [
            (self.shots_entry, self.max_shots_var, "100"),
            (self.mb_entry, self.max_mb_var, "100.0"),
            (self.delay_entry, self.delay_var, "0.5"),
            (self.name_entry, self.name_var, "screenshot"),
            (self.toggle_entry, self.toggle_key_var, "q"),
            (self.single_entry, self.single_key_var, "e"),
            (self.quit_entry, self.quit_key_var, "'")
        ]

        for entry, var, val in defaults:
            var.set(val)
            entry.config(fg="#64748b")
            entry.is_default = True

        # Expand every box again
        for s in self.stack:
            if s.panel:
                s.p = s.target = 1.0
                s.animating = False
        self._apply_layout(self.stack)

        self.update_box_theme()
        self.schedule_save()
        self.status_label.config(text="Status: Settings reset to defaults.", fg=TEXT_MUTED)

    def change_window_opacity(self, val):
        self.root.attributes('-alpha', float(val))

    def update_box_theme(self, val=None):
        alpha = self.box_opacity_var.get()
        r = int(18 + (32 * alpha))
        g = int(18 + (32 * alpha))
        b = int(31 + (55 * alpha))
        current_box_bg = f"#{r:02x}{g:02x}{b:02x}"

        for w in self.themed_widgets:
            try:
                w.config(bg=current_box_bg)
            except Exception:
                pass

    def on_mouse_motion(self, event):
        self.target_x = (event.x_root - self.root.winfo_rootx()) / self.sx
        self.target_y = (event.y_root - self.root.winfo_rooty()) / self.sy

    def _bar_signature(self):
        return (round(self.bar_opacity_var.get(), 2),
                self._rgb(self.border_colour_var, DEFAULT_BORDER_COLOUR),
                round(self.sx, 3), round(self.sy, 3))

    def get_bar_image(self, alpha):
        border = self._rgb(self.border_colour_var, DEFAULT_BORDER_COLOUR)
        key = (round(alpha, 2), border, round(self.sx, 3), round(self.sy, 3))
        img = self.bar_cache.get(key)
        if img is None:
            if len(self.bar_cache) > 20:
                self.bar_cache.clear()
            wp = max(1, int(round(WIN_W * self.sx)))
            hp = max(2, int(round(BAR_H * self.sy)))
            im = Image.new("RGBA", (wp, hp), (0, 0, 0, int(255 * alpha)))
            d = ImageDraw.Draw(im)
            d.line([(0, hp - 1), (wp, hp - 1)], fill=border + (255,), width=1)
            img = ImageTk.PhotoImage(im)
            self.bar_cache[key] = img
        return img

    def _draw_bar(self):
        c = self.bg_canvas
        c.delete("bar_bg")
        c.create_image(0, 0, image=self.get_bar_image(self.bar_opacity_var.get()),
                       anchor="nw", tags="bar_bg")
        c.tag_lower("bar_bg")
        self._bar_sig = self._bar_signature()

    def sync_particles(self, target):
        while len(self.particles) < target:
            self.particles.append({
                'x': random.uniform(0, WIN_W),
                'y': random.uniform(0, self.win_h),
                'vx': random.uniform(-0.5, 0.5),
                'vy': random.uniform(-0.5, 0.5),
                # Unique identity used to seed a stable curve for each pair
                'id': random.getrandbits(32),
                # Slow sine-wave drift that animates the curve bulge over time
                'phase': random.uniform(0, math.tau),
            })
        if len(self.particles) > target:
            del self.particles[target:]

    def spread_particles(self, repel_radius, f=1.0):
        n = len(self.particles)
        for i in range(n):
            p1 = self.particles[i]
            for j in range(i + 1, n):
                p2 = self.particles[j]
                dx = p1['x'] - p2['x']
                dy = p1['y'] - p2['y']
                d = math.hypot(dx, dy)
                if 0 < d < repel_radius:
                    push = (repel_radius - d) * 0.04 * f
                    nx = dx / d
                    ny = dy / d
                    p1['x'] += nx * push
                    p1['y'] += ny * push
                    p2['x'] -= nx * push
                    p2['y'] -= ny * push

        for p in self.particles:
            p['x'] = min(max(p['x'], 0), WIN_W)
            p['y'] = min(max(p['y'], 0), self.win_h)

    def animate_background(self):
        t0 = time.perf_counter()
        dt = min(t0 - self._bg_last, 0.1)
        self._bg_last = t0

        if self._dialog_open or \
           (PAUSE_ANIM_WHILE_DRAGGING and (self._dragging or self._resizing)) or \
           (PAUSE_BG_WHILE_SECTION_ANIM and self._anim_job is not None):
            self.root.after(16, self.animate_background)
            return

        f = min(dt / 0.025, 3.0)

        sx, sy, S = self.sx, self.sy, self.scale
        speed_multiplier = self.anim_speed_var.get()
        line_alpha = self.line_opacity_var.get()
        low = self.low_quality_var.get()
        max_lines = min(MAX_LINES_LIMIT, int(self.line_count_var.get()))
        if low:
            max_lines = min(max_lines, LOW_MAX_LINES)
        steps = LOW_CURVE_STEPS if low else CURVE_STEPS
        spread = self.spread_var.get()

        repel_radius = 0.0 if low else spread * 110
        link_max = 100 + spread * 140

        ease = 1.0 - (1.0 - min(0.1 * speed_multiplier, 0.99)) ** f
        self.mouse_x += (self.target_x - self.mouse_x) * ease
        self.mouse_y += (self.target_y - self.mouse_y) * ease

        if hasattr(self, "bg_canvas"):
            c = self.bg_canvas
            c.delete("net")

            base = self._rgb(self.line_colour_var, DEFAULT_LINE_COLOUR)
            lr = int(18 + (base[0] - 18) * line_alpha)
            lg = int(18 + (base[1] - 18) * line_alpha)
            lb = int(31 + (base[2] - 31) * line_alpha)
            line_color = f"#{lr:02x}{lg:02x}{lb:02x}"

            target_particles = int(5 * math.sqrt(max_lines)) if max_lines > 0 else 0
            self.sync_particles(target_particles)

            if max_lines > 0:
                for p in self.particles:
                    p['x'] += p['vx'] * speed_multiplier * f
                    p['y'] += p['vy'] * speed_multiplier * f
                    if p['x'] < 0 or p['x'] > WIN_W: p['vx'] *= -1
                    if p['y'] < 0 or p['y'] > self.win_h: p['vy'] *= -1
                    p['x'] = min(max(p['x'], 0), WIN_W)
                    p['y'] = min(max(p['y'], 0), self.win_h)
                    # Slowly advance phase so each line's curve gently breathes
                    p['phase'] = (p.get('phase', 0) + 0.008 * speed_multiplier * f) % math.tau

                if repel_radius > 0:
                    self.spread_particles(repel_radius, f)

                all_nodes = self.particles + [{'x': self.mouse_x, 'y': self.mouse_y}]

                links = []
                for i in range(len(all_nodes)):
                    p1 = all_nodes[i]
                    for j in range(i + 1, len(all_nodes)):
                        p2 = all_nodes[j]
                        dist = math.hypot(p1['x'] - p2['x'], p1['y'] - p2['y'])
                        if dist < link_max:
                            links.append((dist, p1, p2))

                if len(links) > max_lines:
                    links.sort(key=lambda l: l[0])
                    links = links[:max_lines]

                now_t = t0  # current time for animating the curve bulge
                for _, p1, p2 in links:
                    ax, ay = p1['x'], p1['y']
                    bx, by = p2['x'], p2['y']
                    dx, dy = bx - ax, by - ay
                    dist_ab = math.hypot(dx, dy)
                    if dist_ab < 1:
                        continue

                    # Perpendicular unit vector
                    px_u, py_u = -dy / dist_ab, dx / dist_ab

                    # Each pair gets a stable curve direction from their id XOR
                    seed = p1.get('id', 0) ^ p2.get('id', 0)
                    sign = 1 if seed & 1 else -1

                    # Very gentle bulge: scales with length, capped so lines stay nearly straight
                    phase1 = p1.get('phase', 0)
                    phase2 = p2.get('phase', 0)
                    wave = math.sin(now_t * 0.4 + (phase1 + phase2) * 0.5)
                    bulge = sign * min(CURVE_MAX, dist_ab * CURVE_AMOUNT * (1.0 + 0.25 * wave))

                    # Single quadratic Bézier control point at the midpoint, pushed sideways.
                    # The peak deviation from the straight line is bulge / 2.
                    cpx = (ax + bx) / 2 + px_u * bulge
                    cpy = (ay + by) / 2 + py_u * bulge

                    # Sample the curve (no smooth=True needed, so no extra wobble)
                    pts = []
                    for step in range(steps + 1):
                        t = step / steps
                        mt = 1.0 - t
                        bpx = mt * mt * ax + 2 * mt * t * cpx + t * t * bx
                        bpy = mt * mt * ay + 2 * mt * t * cpy + t * t * by
                        pts += [bpx * sx, bpy * sy]

                    c.create_line(
                        *pts,
                        fill=line_color, width=1.5 * S, tags="net",
                        capstyle="round", joinstyle="round"
                    )

            restack = False
            if self._bar_signature() != self._bar_sig:
                self._draw_bar()
                restack = True
            if self._panels_dirty:
                self.draw_panels(reorder=False)
                self._panels_dirty = False
                restack = True

            if restack:
                c.tag_lower("bar_bg")
                c.tag_lower("panel_bg")
            c.tag_lower("net")
            c.tag_lower("bg_img")

        work_ms = (time.perf_counter() - t0) * 1000.0
        frame_ms = LOW_FRAME_MS if self.low_quality_var.get() else BG_FRAME_MS
        self.root.after(max(1, int(frame_ms - work_ms)), self.animate_background)

    def build_ui(self):
        self.bg_canvas = tk.Canvas(self.root, bg=BG_MAIN, highlightthickness=0)
        self.bg_canvas.ui_scale = (1.0, 1.0)
        self.bg_canvas.busy = False
        self.bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        c = self.bg_canvas

        self.themed_widgets = []
        X1, X2 = PANEL_X1, PANEL_X2

        specs = [
            ("save",     "SAVE LOCATION (REQUIRED)",     72, 72, True,  "main"),
            ("limits",   "LIMITS & TIMING (REQUIRED)",  156, 10, True,  "main"),
            ("keys",     "CUSTOM KEYBINDS (REQUIRED)",  128, 10, True,  "main"),
            ("prefs",    "PREFERENCES",                 456, 72, True,  "prefs"),
            ("colours",  "COLOURS",                     160, 10, True,  "prefs"),
            ("backup",   "SETTINGS FILE",               108, 10, True,  "prefs"),
            ("presets",  "PRESET THEMES",               182, 72, True,  "themes"),
            ("custom",   "CUSTOM THEMES",               218, 10, True,  "themes"),
            ("buttons",  "",                             36, 18, False, "both"),
            ("status",   "LIVE STATUS",                 130, 12, True,  "both"),
        ]
        self.stack = []
        y = 0
        for key, title, full_h, gap, panel, page in specs:
            y += gap
            self.stack.append(Section(key, title, y, full_h, gap, panel, page))
            y += full_h
        S = {s.key: s for s in self.stack}

        def tg(s, content=True):
            return ("ui_text", s.tag, s.ctag) if content else ("ui_text", s.tag)

        # --- Custom title bar ---
        c.create_text(14, BAR_H / 2, text="SCREENSHOTTER", font=("Segoe UI", 10, "bold"),
                      fill=TEXT_LIGHT, anchor="w", tags="ui_text")
        self.min_txt = c.create_text(WIN_W - 54, BAR_H / 2, text="—", font=("Segoe UI", 11),
                                     fill=TEXT_LIGHT, tags="ui_text")
        self.close_txt = c.create_text(WIN_W - 18, BAR_H / 2, text="✕", font=("Segoe UI", 11),
                                       fill=TEXT_LIGHT, tags="ui_text")

        # --- Page tabs ---
        self.tab_defs = [("main", "Main", X1, X1 + 84),
                         ("prefs", "Preferences", X1 + 90, X1 + 220),
                         ("themes", "Themes", X1 + 226, X1 + 316)]
        self.tab_texts = {}
        for key, label, tx0, tx1 in self.tab_defs:
            self.tab_texts[key] = c.create_text(
                (tx0 + tx1) / 2, TAB_Y, text=label, font=("Segoe UI", 10, "bold"),
                fill=TEXT_LIGHT, tags="ui_text")
        c.create_line(X1, TAB_Y + 14, X2, TAB_Y + 14, fill="#2b2b45", width=1, tags="ui_text")
        self.tab_indicator = c.create_line(0, 0, 0, 0, fill=ACCENT_BLUE, width=3,
                                           capstyle="round", tags="ui_text")
        self._update_tabs()

        def make_header(s):
            c.create_text(X1 + 32, s.top + 16, text=s.title, font=("Segoe UI", 9, "bold"),
                          fill=ACCENT_BLUE, anchor="w", tags=("ui_text", s.tag, s.htag))
            s.chevron = c.create_line(
                0, 0, 0, 0, 0, 0, fill=ACCENT_BLUE, width=2,
                capstyle="round", joinstyle="round", tags=("ui_text", s.tag, s.htag))
            self._update_chevron(s)

        def add_row(s, ry, label_text, var, default_val):
            c.create_text(X1 + 14, ry, text=label_text, font=("Segoe UI", 9),
                          fill=TEXT_LIGHT, anchor="w", tags=tg(s))
            entry = AutoClearEntry(c, textvariable=var, default_value=default_val,
                                   width=14, bd=1, relief="solid")
            c.create_window(X1 + 190, ry, window=entry, anchor="w", tags=tg(s))
            c.create_text(X1 + 330, ry, text=f"Default: {default_val}", font=("Segoe UI", 8),
                          fill=TEXT_MUTED, anchor="w", tags=tg(s))
            return entry

        # --- Save Directory ---
        s = S["save"]
        make_header(s)
        self.browse_btn = tk.Button(
            c, text="Browse...", command=self.browse_folder,
            bg=ACCENT_PURPLE, fg=TEXT_LIGHT, activebackground=ACCENT_BLUE, activeforeground="white",
            font=("Segoe UI", 9, "bold"), bd=0, padx=8, pady=2
        )
        c.create_window(X2 - 14, s.top + 46, window=self.browse_btn, anchor="e", tags=tg(s))

        self.dir_entry = tk.Entry(
            c, textvariable=self.dir_var,
            bg="#161625", fg=TEXT_LIGHT, insertbackground="white", bd=1, relief="solid"
        )
        c.create_window(X1 + 14, s.top + 46, window=self.dir_entry, anchor="w", width=340, tags=tg(s))

        # --- Limits & Timing ---
        s = S["limits"]
        make_header(s)
        self.shots_entry = add_row(s, s.top + 44, "Max Screenshots:", self.max_shots_var, "100")
        self.mb_entry = add_row(s, s.top + 72, "Max Storage (MB):", self.max_mb_var, "100.0")
        self.delay_entry = add_row(s, s.top + 100, "Delay (Seconds):", self.delay_var, "0.5")
        self.name_entry = add_row(s, s.top + 128, "Screenshot Name:", self.name_var, "screenshot")

        # --- Keybinds ---
        s = S["keys"]
        make_header(s)
        self.toggle_entry = add_row(s, s.top + 44, "Start / Pause Continuous:", self.toggle_key_var, "q")
        self.single_entry = add_row(s, s.top + 72, "Take 1 Screenshot:", self.single_key_var, "e")
        self.quit_entry = add_row(s, s.top + 100, "Quit Application:", self.quit_key_var, "'")

        # --- Preferences ---
        s = S["prefs"]
        make_header(s)

        self.notify_check = CanvasCheckbox(
            c, X1 + 14, s.top + 40, "Send desktop notifications", self.notify_var,
            TEXT_LIGHT, ("Segoe UI", 9), tags=tg(s, content=False)
        )
        s.widgets.append(self.notify_check)

        self.low_quality_check = CanvasCheckbox(
            c, X1 + 14, s.top + 66, "Low quality mode (smoother on slow PCs)", self.low_quality_var,
            TEXT_LIGHT, ("Segoe UI", 9), tags=tg(s, content=False)
        )
        s.widgets.append(self.low_quality_check)

        def add_slider(s_ref, cy, label, from_, to, res, var, command=None):
            label_id = c.create_text(X1 + 14, cy, text=label, font=("Segoe UI", 9),
                                     fill=TEXT_LIGHT, anchor="w", tags=tg(s_ref, content=False))
            slider = CanvasSlider(c, X2 - 14 - 200, X2 - 14, cy, from_, to, res, var, command,
                                  tags=tg(s_ref, content=False))
            slider.extra_items = [label_id]
            s_ref.widgets.append(slider)
            return slider

        sy = s.top + 108
        self.win_opacity_slider = add_slider(s, sy, "Window Opacity:", 0.4, 1.0, 0.05,
                                             self.opacity_var, self.change_window_opacity)
        self.bar_opacity_slider = add_slider(s, sy + 46, "Title Bar Opacity:", 0.0, 1.0, 0.05,
                                             self.bar_opacity_var)
        self.box_opacity_slider = add_slider(s, sy + 92, "Box Opacity:", 0.0, 1.0, 0.05,
                                             self.box_opacity_var, self.update_box_theme)
        self.line_opacity_slider = add_slider(s, sy + 138, "Line Opacity:", 0.1, 1.0, 0.05,
                                              self.line_opacity_var)
        self.box_radius_slider = add_slider(s, sy + 184, "Box Corner Radius:", 0, 25, 1,
                                            self.box_radius_var)
        self.speed_slider = add_slider(s, sy + 230, "Animation Speed:", 0.2, 2.5, 0.1,
                                       self.anim_speed_var)
        self.line_count_slider = add_slider(s, sy + 276, "Line Count (max):", 0, MAX_LINES_LIMIT, 10,
                                            self.line_count_var)
        self.spread_slider = add_slider(s, sy + 322, "Line Spread:", 0.0, 1.0, 0.05,
                                        self.spread_var)

        # --- Colours ---
        s = S["colours"]
        make_header(s)

        def add_colour_row(ry, label_text, var, default_val):
            c.create_text(X1 + 14, ry, text=label_text, font=("Segoe UI", 9),
                          fill=TEXT_LIGHT, anchor="w", tags=tg(s))
            swatch = tk.Button(
                c, bg=parse_hex(var.get()) or default_val, bd=1, relief="solid", width=3,
                command=lambda v=var, l=label_text, d=default_val: self.pick_colour(v, l.rstrip(":"), d))
            c.create_window(X1 + 190, ry, window=swatch, anchor="w", height=22, tags=tg(s))
            entry = tk.Entry(c, textvariable=var, width=10, bg="#161625", fg=TEXT_LIGHT,
                             insertbackground="white", bd=1, relief="solid")
            c.create_window(X1 + 236, ry, window=entry, anchor="w", tags=tg(s))
            c.create_text(X1 + 340, ry, text=f"Default: {default_val}", font=("Segoe UI", 8),
                          fill=TEXT_MUTED, anchor="w", tags=tg(s))
            var.trace_add("write", lambda *a, v=var, sw=swatch, en=entry: self._refresh_swatch(v, sw, en))
            self._refresh_swatch(var, swatch, entry)
            self.colour_widgets += [swatch, entry]
            return swatch

        add_colour_row(s.top + 44, "Line Colour:", self.line_colour_var, DEFAULT_LINE_COLOUR)
        add_colour_row(s.top + 72, "Border Colour:", self.border_colour_var, DEFAULT_BORDER_COLOUR)
        add_colour_row(s.top + 100, "Box Colour:", self.box_colour_var, DEFAULT_BOX_COLOUR)
        # Accent colour row: controls all the blue UI chrome
        self.accent_swatch = add_colour_row(s.top + 128, "Accent Colour:", self.accent_colour_var, DEFAULT_ACCENT_COLOUR)

        # --- Settings file (export / import) ---
        s = S["backup"]
        make_header(s)
        self.backup_widgets.append(CanvasButton(
            c, X1 + 14, s.top + 52 - 14, X1 + 14 + 222, s.top + 52 + 14,
            "Export Settings...", self.export_settings,
            fill=ACCENT_PURPLE, fg=TEXT_LIGHT, border=ACCENT_PURPLE,
            font=("Segoe UI", 9, "bold"), radius=PRESET_BTN_RADIUS, tags=tg(s)))
        self.backup_widgets.append(CanvasButton(
            c, X1 + 252, s.top + 52 - 14, X1 + 252 + 222, s.top + 52 + 14,
            "Import Settings...", self.import_settings,
            fill=ACCENT_PURPLE, fg=TEXT_LIGHT, border=ACCENT_PURPLE,
            font=("Segoe UI", 9, "bold"), radius=PRESET_BTN_RADIUS, tags=tg(s)))
        c.create_text(X1 + 14, s.top + 86,
                      text="Everything is also saved automatically as you change it.",
                      font=("Segoe UI", 8), fill=TEXT_MUTED, anchor="w", tags=tg(s))

        # --- Preset Themes ---
        s = S["presets"]
        make_header(s)
        for i, (name, theme) in enumerate(PRESET_THEMES):
            col, row = i % 2, i // 2
            bx = X1 + 14 + col * 238
            byc = s.top + 52 + row * 34
            btn = CanvasButton(
                c, bx, byc - 14, bx + 222, byc + 14, name,
                lambda n=name, t=theme: self.apply_preset(n, t),
                fill=theme["box"], fg=theme["line"], border=theme["border"],
                font=("Segoe UI", 9, "bold"), radius=PRESET_BTN_RADIUS, tags=tg(s))
            self.theme_widgets.append(btn)

        # --- Custom Themes ---
        s = S["custom"]
        make_header(s)

        def add_theme_button(x, y, text, command, w=222):
            return CanvasButton(
                c, x, y - 14, x + w, y + 14, text, command,
                fill=ACCENT_PURPLE, fg=TEXT_LIGHT, border=ACCENT_PURPLE,
                font=("Segoe UI", 9, "bold"), radius=PRESET_BTN_RADIUS, tags=tg(s))

        self.theme_widgets.append(add_theme_button(X1 + 14, s.top + 52, "Upload Image...", self.upload_background, w=146))
        self.theme_widgets.append(add_theme_button(X1 + 171, s.top + 52, "Adjust Image...", self.adjust_background, w=146))
        self.theme_widgets.append(add_theme_button(X1 + 328, s.top + 52, "Remove Image", self.remove_background, w=146))
        self.image_opacity_slider = add_slider(s, s.top + 104, "Image Opacity:", 0.1, 1.0, 0.05,
                                               self.image_opacity_var)
        self.theme_widgets.append(add_theme_button(X1 + 14, s.top + 146, "Export Settings...", self.export_settings))
        self.theme_widgets.append(add_theme_button(X1 + 252, s.top + 146, "Import Settings...", self.import_settings))
        self.scale_reset_btn = add_theme_button(X1 + 14, s.top + 188, "Reset Window Size",
                                                lambda: self.set_scale(1.0, 1.0), w=460)

        # --- Action Buttons ---
        s = S["buttons"]
        by = s.top + 18
        self.arm_btn = tk.Button(
            c, text="ARM HOTKEYS & CREATE FOLDER",
            bg=BTN_GREEN, fg="white", activebackground="#15803d", activeforeground="white",
            font=("Segoe UI", 10, "bold"), bd=0, command=self.arm_session
        )
        c.create_window(X1, by, window=self.arm_btn, anchor="w", width=340, height=36, tags=(s.tag,))

        self.reset_btn = tk.Button(
            c, text="RESET DEFAULTS",
            bg=BTN_RED, fg="white", activebackground="#b91c1c", activeforeground="white",
            font=("Segoe UI", 9, "bold"), bd=0, command=self.reset_defaults
        )
        c.create_window(X2, by, window=self.reset_btn, anchor="e", width=140, height=36, tags=(s.tag,))

        # --- Status ---
        s = S["status"]
        make_header(s)
        self.status_label = CanvasLabel(
            c, X1 + 14, s.top + 42, "Status: Idle (Configure settings and click Arm)",
            TEXT_MUTED, ("Segoe UI", 9), wrap=450, tags=tg(s))
        self.folder_label = CanvasLabel(
            c, X1 + 14, s.top + 72, "Session Folder: None",
            TEXT_MUTED, ("Segoe UI", 9), wrap=450, tags=tg(s))
        self.stats_label = CanvasLabel(
            c, X1 + 14, s.top + 100, "Captured: 0 files | 0.00 MB",
            TEXT_MUTED, ("Segoe UI", 9), wrap=450, tags=tg(s))

        self.config_entries = [
            self.dir_entry, self.browse_btn, self.shots_entry, self.mb_entry,
            self.delay_entry, self.name_entry, self.toggle_entry, self.single_entry,
            self.quit_entry, self.notify_check, self.win_opacity_slider, self.bar_opacity_slider,
            self.box_opacity_slider, self.line_opacity_slider, self.box_radius_slider,
            self.speed_slider, self.line_count_slider, self.spread_slider,
            *self.colour_widgets, *self.theme_widgets, *self.backup_widgets,
            self.image_opacity_slider, self.reset_btn
        ]

        self._index_sections()
        self._index_scalables()

    # ---------- Themes, background image, import / export ----------
    def apply_preset(self, name, theme):
        self.line_colour_var.set(theme["line"])
        self.border_colour_var.set(theme["border"])
        self.box_colour_var.set(theme["box"])
        # Apply the preset's accent colour if it defines one, otherwise use the line colour
        self.accent_colour_var.set(theme.get("accent", theme["line"]))
        self.status_label.config(text=f"Status: Theme '{name}' applied.", fg=TEXT_MUTED)

    def _load_bg_source(self):
        self.bg_src = None
        self._bg_cache = None
        for path in (BG_IMAGE_FILE, LEGACY_BG_IMAGE_FILE):
            if os.path.exists(path):
                try:
                    img = Image.open(path)
                    img.load()
                    self.bg_src = self._limit_bg_size(img.convert("RGB"))
                    return
                except Exception:
                    self.bg_src = None

    @staticmethod
    def _limit_bg_size(img):
        longest = max(img.size)
        if longest > BG_MAX_SIDE:
            k = BG_MAX_SIDE / longest
            img = img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.LANCZOS)
        return img

    def render_background(self, fast=False):
        c = self.bg_canvas
        c.delete("bg_img")
        self._bg_photo = None
        if self.bg_src is None:
            return
        try:
            a = min(max(float(self.image_opacity_var.get()), 0.0), 1.0)
        except Exception:
            return
        size = (max(1, int(round(WIN_W * self.sx))), max(1, int(round(BG_IMG_H * self.sy))))
        zoom, ox, oy = self.bg_view
        # The placement is recalculated from the original for the current window shape, so
        # the image keeps its position / zoom relative to the window and is never stretched.
        # Anything outside the window is cropped off; gaps show the plain background.
        x0, y0, dw, dh, _, _ = image_layout(self.bg_src.width, self.bg_src.height,
                                            size[0], size[1], zoom, ox, oy)
        frame = Image.new("RGB", size, (18, 18, 31))
        paste_scaled(frame, self.bg_src, x0, y0, dw, dh,
                     Image.NEAREST if (fast or self.low_quality_var.get()) else Image.BILINEAR)
        base = Image.new("RGB", size, (18, 18, 31))
        self._bg_photo = ImageTk.PhotoImage(Image.blend(base, frame, a))
        c.create_image(0, 0, image=self._bg_photo, anchor="nw", tags="bg_img")
        c.tag_lower("bg_img")

    def set_background_image(self, img, view=None):
        self.bg_src = self._limit_bg_size(img.convert("RGB"))
        self._bg_cache = None
        self.bg_view = clean_view(*view) if view else [1.0, 0.0, 0.0]
        try:
            self.bg_src.save(BG_IMAGE_FILE, "JPEG", quality=90)
        except Exception:
            pass
        self.render_background()
        self.schedule_save()

    def set_background_view(self, zoom, ox, oy):
        self.bg_view = clean_view(zoom, ox, oy)
        self.render_background()
        self.schedule_save()

    def clear_background_image(self):
        self.bg_src = None
        self._bg_cache = None
        self.bg_view = [1.0, 0.0, 0.0]
        for path in (BG_IMAGE_FILE, LEGACY_BG_IMAGE_FILE):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
        self.render_background()
        self.schedule_save()

    def _open_adjust_dialog(self, img, view, on_apply):
        aspect = (WIN_W * self.sx) / (BG_IMG_H * self.sy)
        visible_frac = self.win_h / BG_IMG_H
        style = {
            "accent": self._accent(),
            "border": parse_hex(self.border_colour_var.get()) or DEFAULT_BORDER_COLOUR,
            "box": parse_hex(self.box_colour_var.get()) or DEFAULT_BOX_COLOUR,
            "box_alpha": self.box_opacity_var.get(),
            "radius": self.box_radius_var.get(),
            "bar_alpha": self.bar_opacity_var.get(),
            "window_alpha": self.opacity_var.get(),
            "line_colour": parse_hex(self.line_colour_var.get()) or DEFAULT_LINE_COLOUR,
            "line_alpha": self.line_opacity_var.get(),
            "line_count": self.line_count_var.get(),
            "anim_speed": self.anim_speed_var.get(),
            "spread": self.spread_var.get(),
            "low_quality": self.low_quality_var.get(),
        }
        self._dialog_open = True
        try:
            dlg = BackgroundAdjustDialog(self.root, img, aspect, visible_frac,
                                         self.image_opacity_var.get(), view, on_apply, style)
        except Exception:
            self._dialog_open = False
            raise

        def _closed(event, d=dlg):
            if event.widget is d:
                self._dialog_open = False
                self._last_t = time.perf_counter()
                self._bg_last = time.perf_counter()

        dlg.bind("<Destroy>", _closed, add="+")

    def upload_background(self):
        path = filedialog.askopenfilename(
            title="Choose a background image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"), ("All files", "*.*")])
        if not path:
            return
        try:
            img = Image.open(path)
            img.load()
        except Exception as e:
            messagebox.showerror("Image Error", f"Could not open that image:\n{e}")
            return

        name = os.path.basename(path)

        def apply(zoom, ox, oy):
            self.set_background_image(img, view=(zoom, ox, oy))
            self.status_label.config(text=f"Status: Background set to {name}.", fg=TEXT_MUTED)

        self._open_adjust_dialog(img, (1.0, 0.0, 0.0), apply)

    def adjust_background(self):
        if self.bg_src is None:
            self.status_label.config(text="Status: Upload a background image first.", fg=TEXT_MUTED)
            return

        def apply(zoom, ox, oy):
            self.set_background_view(zoom, ox, oy)
            self.status_label.config(text="Status: Background image adjusted.", fg=TEXT_MUTED)

        self._open_adjust_dialog(self.bg_src, self.bg_view, apply)

    def remove_background(self):
        self.clear_background_image()
        self.status_label.config(text="Status: Background image removed.", fg=TEXT_MUTED)

    def export_settings(self):
        path = filedialog.asksaveasfilename(
            title="Export Settings", defaultextension=".json", initialfile="screenshotter_settings.json",
            filetypes=[("Screenshotter settings", "*.json"), ("All files", "*.*")])
        if not path:
            return
        data = {"screenshotter_settings": 1, "settings": self.collect_settings(), "background_image": None}
        if self.bg_src is not None:
            try:
                buf = io.BytesIO()
                self.bg_src.save(buf, "JPEG", quality=90)
                data["background_image"] = base64.b64encode(buf.getvalue()).decode("ascii")
            except Exception:
                pass
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            self.status_label.config(text=f"Status: Settings exported to {os.path.basename(path)}.", fg=TEXT_MUTED)
        except Exception as e:
            messagebox.showerror("Export Error", f"Could not write the file:\n{e}")

    def import_settings(self):
        path = filedialog.askopenfilename(
            title="Import Settings",
            filetypes=[("Screenshotter settings", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            settings = data.get("settings", data) if isinstance(data, dict) else None
            if not isinstance(settings, dict):
                raise ValueError("This doesn't look like a Screenshotter settings file.")
        except Exception as e:
            messagebox.showerror("Import Error", f"Could not read that file:\n{e}")
            return

        self.apply_settings(settings)

        if isinstance(data, dict) and "background_image" in data:
            blob = data["background_image"]
            if blob:
                try:
                    self.set_background_image(Image.open(io.BytesIO(base64.b64decode(blob))),
                                              view=self.bg_view)
                except Exception:
                    messagebox.showwarning("Import", "The settings loaded, but the embedded image could not be read.")
            else:
                self.clear_background_image()

        self.save_config()
        self.status_label.config(text=f"Status: Settings imported from {os.path.basename(path)}.", fg=TEXT_MUTED)

    def _set_field(self, entry, var, default, value):
        value = str(value).strip()
        if value:
            var.set(value)
            entry.config(fg=TEXT_LIGHT)
            entry.is_default = False
        else:
            var.set(default)
            entry.config(fg="#64748b")
            entry.is_default = True

    def apply_settings(self, cfg):
        ranges = {
            "opacity": (self.opacity_var, 0.4, 1.0), "bar_opacity": (self.bar_opacity_var, 0.0, 1.0),
            "box_opacity": (self.box_opacity_var, 0.0, 1.0), "line_opacity": (self.line_opacity_var, 0.1, 1.0),
            "box_radius": (self.box_radius_var, 0, 25), "anim_speed": (self.anim_speed_var, 0.2, 2.5),
            "line_count": (self.line_count_var, 0, MAX_LINES_LIMIT), "spread": (self.spread_var, 0.0, 1.0),
            "image_opacity": (self.image_opacity_var, 0.1, 1.0),
        }
        for key, (var, lo, hi) in ranges.items():
            if key in cfg:
                try:
                    var.set(min(max(float(cfg[key]), lo), hi))
                except (TypeError, ValueError):
                    pass
        if "notifications" in cfg:
            self.notify_var.set(bool(cfg["notifications"]))
        if "low_quality" in cfg:
            self.low_quality_var.set(bool(cfg["low_quality"]))
        for key, var in (("line_colour", self.line_colour_var), ("border_colour", self.border_colour_var),
                         ("box_colour", self.box_colour_var), ("accent_colour", self.accent_colour_var)):
            ok = parse_hex(cfg.get(key, ""))
            if ok:
                var.set(ok)
        if "dir" in cfg:
            self.dir_var.set(str(cfg["dir"]))
        for key, entry, var, default in (
                ("max_shots", self.shots_entry, self.max_shots_var, "100"),
                ("max_mb", self.mb_entry, self.max_mb_var, "100.0"),
                ("delay", self.delay_entry, self.delay_var, "0.5"),
                ("name", self.name_entry, self.name_var, "screenshot"),
                ("toggle_key", self.toggle_entry, self.toggle_key_var, "q"),
                ("single_key", self.single_entry, self.single_key_var, "e"),
                ("quit_key", self.quit_entry, self.quit_key_var, "'")):
            if key in cfg:
                self._set_field(entry, var, default, cfg[key])
        if any(k in cfg for k in ("bg_zoom", "bg_ox", "bg_oy")):
            try:
                self.bg_view = clean_view(cfg.get("bg_zoom", self.bg_view[0]),
                                          cfg.get("bg_ox", self.bg_view[1]),
                                          cfg.get("bg_oy", self.bg_view[2]))
            except (TypeError, ValueError):
                pass
            self.render_background()
        self.root.attributes('-alpha', self.opacity_var.get())
        self.update_box_theme()

    def browse_folder(self):
        selected = filedialog.askdirectory(title="Select Base Save Folder")
        if selected:
            self.dir_var.set(os.path.normpath(selected))

    def send_notification(self, title, message):
        if not self.send_notifications:
            return
        try:
            notification.notify(title=title, message=message, app_name="Screenshotter", timeout=2)
        except Exception:
            pass

    def arm_session(self):
        if self.is_armed:
            self.disarm_session()
            return

        raw_fields = {
            "Save Location": self.dir_var.get().strip(),
            "Max Screenshots": self.max_shots_var.get().strip(),
            "Max Storage (MB)": self.max_mb_var.get().strip(),
            "Delay (Seconds)": self.delay_var.get().strip(),
            "Screenshot Name": self.name_var.get().strip(),
            "Start / Pause Keybind": self.toggle_key_var.get().strip(),
            "Take 1 Screenshot Keybind": self.single_key_var.get().strip(),
            "Quit Application Keybind": self.quit_key_var.get().strip(),
        }

        missing = [name for name, val in raw_fields.items() if not val]
        if missing:
            messagebox.showerror(
                "Missing Required Fields",
                "Cannot start. Please fill in all required fields:\n\n• " + "\n• ".join(missing)
            )
            return

        base_dir = raw_fields["Save Location"].strip('"').strip("'")
        if not os.path.isdir(base_dir):
            messagebox.showerror("Invalid Folder", f"'{base_dir}' does not exist or is not a valid folder.")
            return

        try:
            self.max_screenshots = int(raw_fields["Max Screenshots"])
            if self.max_screenshots <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid Input", "Max Screenshots must be a whole number greater than 0.")
            return

        try:
            self.max_folder_size_mb = float(raw_fields["Max Storage (MB)"])
            if self.max_folder_size_mb <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid Input", "Max Storage (MB) must be a number greater than 0.")
            return

        try:
            self.interval = float(raw_fields["Delay (Seconds)"])
            if self.interval <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid Input", "Delay (Seconds) must be a number greater than 0.")
            return

        clean_name = re.sub(r'[<>:"/\\|?*]', "", raw_fields["Screenshot Name"]).strip(" .")
        if not clean_name:
            messagebox.showerror("Invalid Input", "Screenshot Name contains no usable characters.")
            return
        self.file_prefix = clean_name

        t_key = raw_fields["Start / Pause Keybind"].lower()
        s_key = raw_fields["Take 1 Screenshot Keybind"].lower()
        q_key = raw_fields["Quit Application Keybind"].lower()

        if len({t_key, s_key, q_key}) < 3:
            messagebox.showerror("Duplicate Keybinds", "Each action must have a unique keybind.")
            return

        for label, key in [("Start / Pause", t_key), ("Take 1 Screenshot", s_key), ("Quit Application", q_key)]:
            try:
                keyboard.parse_hotkey(key)
            except ValueError:
                messagebox.showerror("Invalid Keybind", f"'{key}' is not a valid key for {label}.")
                return

        self.toggle_hotkey = t_key
        self.single_hotkey = s_key
        self.quit_hotkey = q_key
        self.send_notifications = self.notify_var.get()

        self.save_config()

        folder_num = 1
        while True:
            candidate = os.path.join(base_dir, f"PythonScreenshots{folder_num}")
            if not os.path.exists(candidate):
                try:
                    os.makedirs(candidate)
                    self.save_folder = candidate
                    break
                except OSError as e:
                    messagebox.showerror("Folder Error", f"Cannot create folder in '{base_dir}':\n{e}")
                    return
            folder_num += 1

        for widget in self.config_entries:
            widget.config(state="disabled")

        self.is_armed = True
        self.is_running = False
        self.stop_thread = False
        self.count = 1

        try:
            keyboard.add_hotkey(self.toggle_hotkey, self.toggle_capture)
            keyboard.add_hotkey(self.single_hotkey, self.single_shot)
            keyboard.add_hotkey(self.quit_hotkey, self.quit_from_hotkey)
        except Exception as e:
            messagebox.showerror(
                "Hotkey Permission Error",
                f"Failed to register global hotkeys.\n\nNote: On Windows, the 'keyboard' library requires running your terminal or VS Code as Administrator.\n\nDetails: {e}"
            )
            self.disarm_session("Idle")
            return

        self.arm_btn.config(text="STOP & UNLOCK SETTINGS", bg=BTN_RED)
        self.status_label.config(text=f"Status: Armed & Paused (Press '{self.toggle_hotkey}' to start)", fg="#60a5fa")
        self.folder_label.config(text=f"Session Folder: {os.path.basename(self.save_folder)}")
        self.stats_label.config(text=f"Captured: 0 / {self.max_screenshots} files | 0.00 / {self.max_folder_size_mb} MB")

        self.worker_thread = threading.Thread(target=self.capture_loop, daemon=True)
        self.worker_thread.start()

    def disarm_session(self, reason="Idle"):
        self.is_armed = False
        self.is_running = False
        self.stop_thread = True
        try:
            keyboard.unhook_all()
        except Exception:
            pass

        for widget in self.config_entries:
            widget.config(state="normal")

        self.arm_btn.config(text="ARM HOTKEYS & CREATE FOLDER", bg=BTN_GREEN)
        self.status_label.config(text=f"Status: {reason}", fg=TEXT_MUTED)

    def toggle_capture(self):
        if not self.is_armed:
            return
        self.is_running = not self.is_running
        if self.is_running:
            self.root.after(0, lambda: self.status_label.config(text="Status: ▶ RECORDING", fg="#4ade80"))
            self.send_notification("Screenshotter", "Continuous capture started.")
        else:
            self.root.after(0, lambda: self.status_label.config(text="Status: ⏸ PAUSED", fg="#fbbf24"))
            self.send_notification("Screenshotter", "Continuous capture paused.")

    def single_shot(self):
        if self.is_armed:
            threading.Thread(target=self.take_screenshot, args=(True,), daemon=True).start()

    def take_screenshot(self, manual=False):
        if not self.is_armed:
            return False

        current_bytes = 0
        file_count = 0
        for root_dir, _, files in os.walk(self.save_folder):
            for f in files:
                current_bytes += os.path.getsize(os.path.join(root_dir, f))
                file_count += 1

        current_mb = current_bytes / (1024 * 1024)

        if file_count >= self.max_screenshots:
            msg = f"Stopped: Reached max limit ({self.max_screenshots} screenshots)."
            self.send_notification("Screenshotter", msg)
            self.root.after(0, lambda: self.disarm_session(msg))
            return False

        if current_mb >= self.max_folder_size_mb:
            msg = f"Stopped: Reached storage limit ({self.max_folder_size_mb} MB)."
            self.send_notification("Screenshotter", msg)
            self.root.after(0, lambda: self.disarm_session(msg))
            return False

        screenshot = pyautogui.screenshot()
        filename = os.path.join(self.save_folder, f"{self.file_prefix}_{self.count:03d}.png")
        screenshot.save(filename)

        new_size_mb = (current_bytes + os.path.getsize(filename)) / (1024 * 1024)
        new_count = file_count + 1

        if manual:
            self.send_notification("Screenshotter", f"Captured {os.path.basename(filename)}")

        self.count += 1
        self.root.after(0, lambda: self.stats_label.config(
            text=f"Captured: {new_count} / {self.max_screenshots} files | {new_size_mb:.2f} / {self.max_folder_size_mb} MB"
        ))
        return True

    def capture_loop(self):
        while not self.stop_thread:
            if self.is_running:
                if not self.take_screenshot(manual=False):
                    break
                elapsed = 0.0
                while elapsed < self.interval and self.is_running and not self.stop_thread:
                    time.sleep(0.05)
                    elapsed += 0.05
            else:
                time.sleep(0.05)

    def quit_from_hotkey(self):
        self.send_notification("Screenshotter", "Program closed by user.")
        self.root.after(0, self.on_close)

    def on_close(self):
        self._end_drag()
        if self._anim_job is not None:
            self.root.after_cancel(self._anim_job)
            self._anim_job = None
        while self._timer_refs > 0:
            self._set_timer_resolution(False)
        self.save_appearance()   # final save (also cancels any pending delayed save)
        self.stop_thread = True
        self.is_running = False
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ScreenshotterApp(root)
    root.mainloop()
