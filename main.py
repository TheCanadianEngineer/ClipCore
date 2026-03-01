import threading
import time
from monitor import *
from database import *
import tkinter as tk
import tkinter.messagebox
from ttkbootstrap.constants import *
from PIL import Image, ImageTk, ImageDraw
import pystray
from pystray import MenuItem as item
import io
import win32clipboard
from io import BytesIO
import webbrowser
from rapidfuzz import process, fuzz
import math
import os
import sys


def resource_path(relative_path):
    """Get the correct path whether running as script or compiled EXE."""
    if hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS
    elif getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)


def app_data_path(filename):
    """Return a writable path for persistent app data (database, icons, etc.).

    When frozen the EXE directory may be read-only or inside a temp folder
    that gets cleaned up by Windows or antivirus mid-session.
    %APPDATA%\\ClipCore is always writable and survives reboots and cleanup.
    """
    if getattr(sys, "frozen", False):
        folder = os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")), "ClipCore"
        )
    else:
        folder = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, filename)


# ─── Database setup ───────────────────────────────────────────────
db = Database(app_data_path("clipboard.db"))
organized_info = []

# ─── THEME PALETTE ────────────────────────────────────────────────
BG_DEEP   = "#050A0F"
BG_PANEL  = "#0A1520"
BG_CARD   = "#0D1B2A"
ACCENT    = "#00D4FF"
ACCENT2   = "#0090CC"
ACCENT3   = "#00FF9F"
WARN      = "#FFB300"
DANGER    = "#FF3366"
TEXT_PRI  = "#E0F4FF"
TEXT_SEC  = "#5A8FA8"
TEXT_DIM  = "#1E3A4A"
BORDER    = "#1A3A50"


def create_tray_icon_image():
    try:
        img = Image.open(resource_path("images/ClipCore.png"))
        return img
    except Exception:
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((4, 4, 60, 60), fill=(0, 212, 255))
        return img


# ─── ANIMATED PARTICLE BACKGROUND ────────────────────────────────
class ParticleCanvas(tk.Canvas):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG_DEEP, highlightthickness=0, **kwargs)
        import random
        self._running = True
        self._particles = [
            {
                "x": random.uniform(0, 1400),
                "y": random.uniform(0, 900),
                "vx": random.uniform(-0.25, 0.25),
                "vy": random.uniform(-0.12, 0.12),
                "r": random.uniform(1, 2.5),
                "phase": random.uniform(0, math.pi * 2),
            }
            for _ in range(60)
        ]
        self._animate()

    def _alpha_color(self, hex_col, a):
        r = int(int(hex_col[1:3], 16) * a)
        g = int(int(hex_col[3:5], 16) * a)
        b = int(int(hex_col[5:7], 16) * a)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _animate(self):
        if not self._running:
            return
        self.delete("anim")
        t = time.time()
        w = self.winfo_width() or 1400
        h = self.winfo_height() or 900

        # Grid overlay
        for x in range(0, w + 60, 60):
            self.create_line(x, 0, x, h, fill="#08131C", width=1, tags="anim")
        for y in range(0, h + 60, 60):
            self.create_line(0, y, w, y, fill="#08131C", width=1, tags="anim")

        # Horizontal scan line
        sy = int((t * 70) % (h + 20)) - 10
        self.create_line(0, sy, w, sy, fill="#00D4FF15", width=2, tags="anim")

        # Particles
        for p in self._particles:
            p["x"] = (p["x"] + p["vx"]) % w
            p["y"] = (p["y"] + p["vy"]) % h
            a = (math.sin(t * 1.4 + p["phase"]) + 1) / 2 * 0.55 + 0.1
            col = self._alpha_color(ACCENT, a)
            r = p["r"]
            self.create_oval(p["x"]-r, p["y"]-r, p["x"]+r, p["y"]+r,
                             fill=col, outline="", tags="anim")

        self.after(33, self._animate)

    def stop(self):
        self._running = False


# ─── CLIP CARD ────────────────────────────────────────────────────
class ClipCard(tk.Frame):
    CAT_COLORS = {"image": "#FF6B9D", "link": ACCENT3, "text": ACCENT,
                  "file": WARN, "default": ACCENT}
    CAT_ICONS  = {"image": "🖼", "link": "🔗", "text": "📄", "file": "📁"}

    def __init__(self, parent, text, category, is_fav,
                 on_select, on_delete, on_fav, on_copy, **kwargs):
        super().__init__(parent, bg=BG_CARD, bd=0, highlightthickness=0, **kwargs)
        col = self.CAT_COLORS.get(category, self.CAT_COLORS["default"])
        icon = self.CAT_ICONS.get(category, "📋")

        # Accent strip
        tk.Frame(self, bg=col, width=4, highlightthickness=0).pack(side=LEFT, fill=Y)

        # Category icon
        tk.Label(self, text=icon, bg=BG_CARD, fg=col,
                 font=("Segoe UI Emoji", 13)).pack(side=LEFT, padx=(8, 2))

        # Clip text button
        btn = tk.Button(
            self, text=text, bg=BG_CARD, fg=TEXT_PRI,
            activebackground=BG_PANEL, activeforeground=ACCENT,
            relief="flat", bd=0, cursor="hand2",
            font=("Consolas", 11), anchor="w",
            command=on_select
        )
        btn.pack(side=LEFT, fill=X, expand=True, pady=7, padx=(0, 4))

        # Action buttons
        for sym, cmd, fcol, hover in [
            ("⧉", on_copy, TEXT_SEC, ACCENT),
            ("★" if is_fav else "☆", on_fav, WARN if is_fav else TEXT_DIM, WARN),
            ("✕", on_delete, DANGER, DANGER),
        ]:
            b = tk.Button(
                self, text=sym, bg=BG_CARD, fg=fcol,
                activebackground=BG_PANEL, activeforeground=hover,
                relief="flat", bd=0, cursor="hand2",
                font=("Segoe UI", 12), width=2, command=cmd
            )
            b.pack(side=RIGHT, padx=2, pady=3)
            b.bind("<Enter>", lambda e, w=b, hc=hover: w.config(fg=hc))
            b.bind("<Leave>", lambda e, w=b, oc=fcol: w.config(fg=oc))

        # Hover highlight
        def _enter(_=None):
            self.config(bg="#0F2035")
            for ch in self.winfo_children():
                try: ch.config(bg="#0F2035")
                except Exception: pass
        def _leave(_=None):
            self.config(bg=BG_CARD)
            for ch in self.winfo_children():
                try: ch.config(bg=BG_CARD)
                except Exception: pass
        self.bind("<Enter>", _enter)
        self.bind("<Leave>", _leave)
        for ch in self.winfo_children():
            ch.bind("<Enter>", _enter)
            ch.bind("<Leave>", _leave)

        # Divider stored for clean destruction
        self._divider = tk.Frame(parent, bg=BORDER, height=1, highlightthickness=0)
        self._divider.pack(fill=X)

    def destroy(self):
        try: self._divider.destroy()
        except Exception: pass
        super().destroy()


# ─── DETAIL PANEL ────────────────────────────────────────────────
class DetailPanel(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG_PANEL, bd=0, **kwargs)
        # Permanent header
        hdr = tk.Frame(self, bg=BG_PANEL)
        hdr.pack(fill=X, padx=14, pady=(14, 4))
        tk.Label(hdr, text="◈  CLIP DETAIL",
                 bg=BG_PANEL, fg=ACCENT,
                 font=("Consolas", 10, "bold"), anchor="w").pack(side=LEFT)
        tk.Frame(self, bg=BORDER, height=1).pack(fill=X, padx=10, pady=(0, 4))

    def _clear_body(self):
        for w in list(self.winfo_children())[2:]:
            w.destroy()

    def show_welcome(self):
        self._clear_body()
        f = tk.Frame(self, bg=BG_PANEL)
        f.pack(expand=True, fill=BOTH)
        tk.Label(f, text="⌗", bg=BG_PANEL, fg=TEXT_DIM,
                 font=("Consolas", 52)).pack(pady=(60, 8))
        tk.Label(f, text="Select a clip to preview",
                 bg=BG_PANEL, fg=TEXT_SEC,
                 font=("Consolas", 10)).pack()

    def show_clip(self, content, category, favourite, timestamp):
        self._clear_body()
        cat_cols = {"image": "#FF6B9D", "link": ACCENT3,
                    "text": ACCENT, "file": WARN}
        col = cat_cols.get(category, ACCENT)

        # Badge row
        br = tk.Frame(self, bg=BG_PANEL)
        br.pack(fill=X, padx=14, pady=(8, 4))
        tk.Label(br, text=f"  {category.upper()}  ",
                 bg=col, fg="#000000",
                 font=("Consolas", 8, "bold"),
                 padx=6, pady=2).pack(side=LEFT)
        if favourite:
            tk.Label(br, text=" ★ PINNED ",
                     bg=WARN, fg="#000000",
                     font=("Consolas", 8, "bold"),
                     padx=6, pady=2).pack(side=LEFT, padx=(4, 0))

        # Content card
        card = tk.Frame(self, bg="#081420", bd=0)
        card.pack(fill=X, padx=14, pady=6)
        tk.Frame(card, bg=col, height=2).pack(fill=X)

        if category == "image":
            try:
                img = Image.open(io.BytesIO(content))
                img.thumbnail((270, 220))
                photo = ImageTk.PhotoImage(img)
                lbl = tk.Label(card, image=photo, bg="#081420")
                lbl.image = photo
                lbl.pack(pady=10)
            except Exception:
                tk.Label(card, text="⚠  Cannot render image",
                         bg="#081420", fg=DANGER,
                         font=("Consolas", 10)).pack(pady=18)
        elif category == "link":
            short = content[:55] + "..." if len(content) > 55 else content
            lbtn = tk.Button(
                card, text=f"↗  {short}",
                bg="#081420", fg=ACCENT3,
                activebackground=BG_PANEL, activeforeground="#ffffff",
                relief="flat", bd=0, cursor="hand2",
                font=("Consolas", 10),
                wraplength=240, justify=LEFT,
                command=lambda: webbrowser.open(content)
            )
            lbtn.pack(pady=10, padx=10, anchor=W)
        else:
            txt = tk.Text(card, height=6, width=28,
                          bg="#081420", fg=TEXT_PRI,
                          insertbackground=ACCENT,
                          relief="flat", bd=0,
                          font=("Consolas", 10), wrap=WORD)
            txt.insert("1.0", content)
            txt.config(state="disabled")
            txt.pack(pady=8, padx=10, fill=X)

        # Meta
        meta = tk.Frame(self, bg=BG_PANEL)
        meta.pack(fill=X, padx=14, pady=4)
        for ico, val in [("⏱", timestamp), ("⊞", category)]:
            row = tk.Frame(meta, bg=BG_PANEL)
            row.pack(fill=X, pady=2)
            tk.Label(row, text=ico, bg=BG_PANEL, fg=col,
                     font=("Segoe UI Emoji", 9)).pack(side=LEFT, padx=(0, 6))
            tk.Label(row, text=val, bg=BG_PANEL, fg=TEXT_SEC,
                     font=("Consolas", 9)).pack(side=LEFT)


# ─── SEARCH BAR ──────────────────────────────────────────────────
class FancySearchBar(tk.Frame):
    CATEGORIES = ["All", "Text", "Link", "Image", "File"]

    def __init__(self, parent, on_search, on_filter, **kwargs):
        super().__init__(parent, bg=BG_DEEP, **kwargs)
        self._on_search = on_search
        self._on_filter = on_filter
        self._pill_btns = {}
        self._build()

    def _build(self):
        # Search wrapper with border
        wrap = tk.Frame(self, bg=BORDER, padx=1, pady=1)
        wrap.pack(side=LEFT, padx=(0, 10), fill=Y)
        inner = tk.Frame(wrap, bg=BG_CARD)
        inner.pack()
        tk.Label(inner, text="⌕", bg=BG_CARD, fg=TEXT_SEC,
                 font=("Consolas", 13)).pack(side=LEFT, padx=8)
        self._var = tk.StringVar()
        self._entry = tk.Entry(
            inner, textvariable=self._var,
            bg=BG_CARD, fg=TEXT_SEC,
            insertbackground=ACCENT,
            relief="flat", bd=0,
            font=("Consolas", 11), width=38
        )
        self._entry.pack(side=LEFT, padx=(0, 10), pady=7)
        self._entry.insert(0, "Search clips…")
        self._entry.bind("<FocusIn>",  self._focus_in)
        self._entry.bind("<FocusOut>", self._focus_out)
        self._entry.bind("<KeyRelease>",
                         lambda _: self._on_search(self._query()))

        # Filter pills
        pill_wrap = tk.Frame(self, bg=BG_DEEP)
        pill_wrap.pack(side=LEFT, fill=Y)
        for cat in self.CATEGORIES:
            active = cat == "All"
            b = tk.Button(
                pill_wrap, text=cat,
                bg=ACCENT if active else BG_CARD,
                fg="#000000" if active else TEXT_SEC,
                activebackground=ACCENT, activeforeground="#000000",
                relief="flat", bd=0, cursor="hand2",
                font=("Consolas", 9, "bold"),
                padx=10, pady=4,
                command=lambda c=cat: self._pick(c)
            )
            b.pack(side=LEFT, padx=3)
            self._pill_btns[cat] = b

    def _pick(self, cat):
        for c, b in self._pill_btns.items():
            b.config(bg=ACCENT if c == cat else BG_CARD,
                     fg="#000000" if c == cat else TEXT_SEC)
        self._on_filter(cat)

    def _focus_in(self, _=None):
        if self._entry.get() == "Search clips…":
            self._entry.delete(0, END)
            self._entry.config(fg=TEXT_PRI)

    def _focus_out(self, _=None):
        if not self._entry.get().strip():
            self._entry.insert(0, "Search clips…")
            self._entry.config(fg=TEXT_SEC)

    def _query(self):
        q = self._entry.get()
        return "" if q in ("Search clips…", "") else q


# ─── STATUS BAR ──────────────────────────────────────────────────
class StatusBar(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG_DEEP, **kwargs)
        self._count = tk.StringVar(value="0 clips")
        self._status = tk.StringVar(value="● MONITORING")
        tk.Label(self, textvariable=self._count,
                 bg=BG_DEEP, fg=TEXT_SEC,
                 font=("Consolas", 9)).pack(side=LEFT, padx=12)
        tk.Label(self, textvariable=self._status,
                 bg=BG_DEEP, fg=ACCENT3,
                 font=("Consolas", 9)).pack(side=RIGHT, padx=12)
        self._blink()

    def set_count(self, n):
        self._count.set(f"{n} clip{'s' if n != 1 else ''} stored")

    def _blink(self):
        v = self._status.get()
        self._status.set("○ MONITORING" if v.startswith("●") else "● MONITORING")
        self.after(900, self._blink)


# ─── MAIN APP ────────────────────────────────────────────────────
class App:
    def __init__(self, stop_event: threading.Event):
        self.stop_event = stop_event
        self.search_query = ""
        self.category_filter = "All"

        # Tell Windows this is its own app so the taskbar shows
        # the ClipCore icon instead of the Python logo
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "ClipCore.App")
        except Exception:
            pass

        self.root = tk.Tk()
        self.root.title("ClipCore")
        self.root.geometry("1280x800")
        self.root.minsize(900, 580)
        self.root.configure(bg=BG_DEEP)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)

        try:
            png_path = resource_path("images/ClipCore.png")
            # Store the .ico in %APPDATA%\ClipCore — always writable,
            # never cleaned up, works whether running from source or as EXE
            ico_path = app_data_path("ClipCore.ico")
            if not os.path.exists(ico_path):
                img = Image.open(png_path)
                img.save(ico_path, format="ICO",
                         sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
            photo = ImageTk.PhotoImage(Image.open(png_path).resize((32, 32)))
            self.root.iconphoto(True, photo)
            self._ico = photo
            self.root.after(0, lambda: self.root.iconbitmap(ico_path))
        except Exception:
            pass

        self._build()
        self.get_info()
        self.update_content()
        self.tray_icon = None
        self._start_tray()

    # ── Layout ──────────────────────────────────────────────────
    def _build(self):
        # Title bar
        tbar = tk.Frame(self.root, bg=BG_DEEP, height=50)
        tbar.pack(fill=X)
        tbar.pack_propagate(False)
        try:
            li = ImageTk.PhotoImage(
                Image.open(resource_path("images/ClipCore.png")).resize((26, 26)))
            self._li = li
            tk.Label(tbar, image=li, bg=BG_DEEP).pack(
                side=LEFT, padx=(14, 8), pady=10)
        except Exception:
            pass
        tk.Label(tbar, text="CLIPCORE", bg=BG_DEEP, fg=ACCENT,
                 font=("Consolas", 15, "bold")).pack(side=LEFT)
        tk.Label(tbar, text="  clipboard manager",
                 bg=BG_DEEP, fg=TEXT_DIM,
                 font=("Consolas", 9)).pack(side=LEFT, pady=(7, 0))
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill=X)

        # Navbar
        nav = tk.Frame(self.root, bg=BG_DEEP, pady=9)
        nav.pack(fill=X, padx=14)
        self._sbar = FancySearchBar(
            nav,
            on_search=self._do_search,
            on_filter=self._do_filter
        )
        self._sbar.pack(side=LEFT)
        tk.Button(nav, text="⌫  CLEAR ALL",
                  bg=BG_CARD, fg=DANGER,
                  activebackground=DANGER, activeforeground="#000",
                  relief="flat", bd=0, cursor="hand2",
                  font=("Consolas", 9, "bold"),
                  padx=10, pady=4,
                  command=self._clear_all).pack(side=RIGHT, padx=4)
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill=X)

        # Body
        body = tk.Frame(self.root, bg=BG_DEEP)
        body.pack(fill=BOTH, expand=True)

        # Left — clip list
        left = tk.Frame(body, bg=BG_DEEP)
        left.pack(side=LEFT, fill=BOTH, expand=True)
        col_hdr = tk.Frame(left, bg=BG_PANEL, height=28)
        col_hdr.pack(fill=X)
        col_hdr.pack_propagate(False)
        tk.Label(col_hdr, text="  CLIPBOARD HISTORY",
                 bg=BG_PANEL, fg=TEXT_DIM,
                 font=("Consolas", 8, "bold"), anchor="w").pack(
                     side=LEFT, padx=8)

        self._canvas = tk.Canvas(left, bg=BG_DEEP, highlightthickness=0)
        sb = tk.Scrollbar(left, orient=VERTICAL,
                          command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=RIGHT, fill=Y)
        self._canvas.pack(side=LEFT, fill=BOTH, expand=True)
        self._inner = tk.Frame(self._canvas, bg=BG_DEEP)
        self._cwin = self._canvas.create_window(
            (0, 0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>",
            lambda _: self._canvas.configure(
                scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
            lambda e: self._canvas.itemconfig(self._cwin, width=e.width))

        # Bind scroll globally on the root so it works no matter which
        # child widget the mouse is hovering over
        self.root.bind_all("<MouseWheel>", self._on_scroll)

        # Divider
        tk.Frame(body, bg=BORDER, width=1).pack(side=LEFT, fill=Y)

        # Right — detail panel
        self._detail = DetailPanel(body, width=310)
        self._detail.pack(side=LEFT, fill=Y)
        self._detail.pack_propagate(False)
        self._detail.show_welcome()

        # Status bar
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill=X)
        self._status = StatusBar(self.root, height=26)
        self._status.pack(fill=X)
        self._status.pack_propagate(False)

    def _on_scroll(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ── Event handlers ───────────────────────────────────────────
    def _do_search(self, q):
        self.search_query = q
        self.update_content()

    def _do_filter(self, cat):
        self.category_filter = cat
        self.update_content()

    def _clear_all(self):
        if tk.messagebox.askyesno(
                "Clear All", "Delete ALL clipboard history?",
                icon="warning"):
            for row in db.fetch_all():
                db.delete_clip(row[1])
            self.update_content()

    def copy_image_to_clipboard(self, image_bytes):
        img = Image.open(BytesIO(image_bytes))
        out = BytesIO()
        img.convert("RGB").save(out, format="BMP")
        bmp = out.getvalue()[14:]
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, bmp)
        win32clipboard.CloseClipboard()

    # ── Render ───────────────────────────────────────────────────
    def update_content(self):
        global organized_info
        self.get_info()

        for w in self._inner.winfo_children():
            w.destroy()

        filtered = (
            [i for i in organized_info
             if i[1] == self.category_filter.lower()]
            if self.category_filter != "All"
            else list(organized_info)
        )

        if self.search_query:
            texts = [
                "[Image]" if i[1] == "image" else str(i[0])
                for i in filtered
            ]
            hits = process.extract(
                self.search_query, texts,
                scorer=fuzz.WRatio, limit=50, score_cutoff=40)
            filtered = [filtered[idx] for _, _, idx in hits]

        self._status.set_count(len(organized_info))

        if not filtered:
            tk.Label(self._inner,
                     text="No clips found",
                     bg=BG_DEEP, fg=TEXT_DIM,
                     font=("Consolas", 12)).pack(pady=40)
            return

        for data in filtered:
            content, category, is_fav, timestamp = data
            if category == "image":
                display = "⟨ image attachment ⟩"
            else:
                flat = "".join(str(content).split())
                display = (flat[:55] + "...") if len(flat) > 55 else flat or "⟨ empty ⟩"

            ClipCard(
                self._inner,
                text=display,
                category=category,
                is_fav=is_fav,
                on_select=lambda c=content, cat=category,
                                  f=is_fav, t=timestamp:
                    self._detail.show_clip(c, cat, f, t),
                on_delete=lambda c=content: (
                    db.delete_clip(c), self.update_content()),
                on_fav=lambda c=content, f=is_fav: (
                    db.toggle_favourite(c, 0 if f else 1),
                    self.update_content()),
                on_copy=(
                    (lambda c=content: self.copy_image_to_clipboard(c))
                    if category == "image"
                    else (lambda c=content: pyperclip.copy(c))
                ),
            ).pack(fill=X)

    def get_info(self):
        global organized_info
        organized_info.clear()
        for row in db.fetch_all():
            _, content, category, fav, timestamp = row
            if fav == 1:
                organized_info.insert(0, [content, category, fav, timestamp])
            else:
                organized_info.append([content, category, fav, timestamp])

    # kept for compatibility with monitor.py
    def update_info(self, content, category, favourite, timestamp):
        self._detail.show_clip(content, category, favourite, timestamp)

    # ── Tray ────────────────────────────────────────────────────
    def _start_tray(self):
        menu = pystray.Menu(
            item("Show", self.show_window, default=True),
            item("Quit", self.quit_app),
        )
        self.tray_icon = pystray.Icon(
            "ClipCore", create_tray_icon_image(), "ClipCore", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def hide_window(self):
        self.root.withdraw()

    def show_window(self, icon=None, item=None):
        self.root.after(0, self.root.deiconify)

    def quit_app(self, icon=None, item=None):
        self.stop_event.set()
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.after(0, self.root.destroy)

    def run(self):
        self.root.mainloop()


# ─── ENTRY POINT ──────────────────────────────────────────────────
def main():
    stop_event = threading.Event()
    app = App(stop_event)

    t1 = threading.Thread(
        target=check_clips, args=(stop_event, app), daemon=True)
    t1.start()

    app.run()

    print("Stopping threads…")
    stop_event.set()
    t1.join()
    print("All threads stopped.")


if __name__ == "__main__":
    main()