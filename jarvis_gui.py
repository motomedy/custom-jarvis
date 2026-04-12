"""
Jarvis GUI — Dark Sci-Fi Interface
Drop-in wrapper for llm-guy/jarvis (main.py logic)

Requirements (add to your existing requirements.txt):
    psutil

Usage:
    python jarvis_gui.py
    
This file replaces running main.py directly. It starts the Jarvis
voice loop in a background thread and provides a full GUI overlay.
"""

import tkinter as tk
from tkinter import font as tkfont
import threading
import queue
import time
import psutil
import datetime
import os
import json
import sys

# ─── Try to import Jarvis internals ───────────────────────────────────────────
# We'll monkey-patch the speak / transcript functions so GUI can intercept them.
# If main.py isn't importable yet, we run in DEMO mode.
DEMO_MODE = False
try:
    # Suppress stdout from jarvis startup
    import importlib.util, io, contextlib
    # We don't import main directly to avoid auto-running it.
    # Instead we import the tools and re-wire speech below.
    pass
except Exception:
    DEMO_MODE = True

# ─── Colour Palette ───────────────────────────────────────────────────────────
BG        = "#0a0d12"
PANEL     = "#0f1318"
BORDER    = "#1c2a3a"
ACCENT    = "#00d4ff"
ACCENT2   = "#0077aa"
GREEN     = "#00ff9d"
RED       = "#ff4560"
YELLOW    = "#ffd166"
TEXT      = "#cde4f5"
DIM       = "#4a6070"
WHITE     = "#e8f4fb"

# ─── Shared event queue (background thread → GUI) ─────────────────────────────
gui_queue = queue.Queue()

def post(event, data=None):
    if data is None:
        data = ""
    gui_queue.put((event, data))

# ─────────────────────────────────────────────────────────────────────────────
# JARVIS VOICE LOOP  (runs in daemon thread)
# Replace the body of `run_jarvis()` with your actual main.py logic.
# The only requirement: call post() to push state updates to the GUI.
# ─────────────────────────────────────────────────────────────────────────────
def run_jarvis():
    """
    Paste / import your main.py logic here.
    We provide stub hooks so you can wire GUI events easily.
    """
    if DEMO_MODE:
        # Demo loop — simulates Jarvis activity so you can see the GUI
        time.sleep(1.5)
        post("status", "idle")
        post("log", ("jarvis", "Hello! I'm Jarvis. Say my name to wake me up."))
        while True:
            time.sleep(8)
    
    # ── Real Jarvis integration ───────────────────────────────────────────────
    # Example wiring. Adapt to match your main.py structure:
    #
    # from langchain_ollama import ChatOllama
    # from tools.get_time import get_time
    # import speech_recognition as sr
    #
    # def speak(text):
    #     post("log", ("jarvis", text))
    #     post("status", "speaking")
    #     # TTS handled in main.py using subprocess+say
    #     post("status", "idle")
    #
    # def listen():
    #     post("status", "listening")
    #     ... your recognition code ...
    #     post("status", "thinking")
    #     ... your LLM call ...
    #
    # Then call your main loop here.
    pass


# ─────────────────────────────────────────────────────────────────────────────
#  TODO STORE  (persisted to jarvis_todos.json next to this file)
# ─────────────────────────────────────────────────────────────────────────────
TODO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_todos.json")

def load_todos():
    if os.path.exists(TODO_FILE):
        try:
            with open(TODO_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_todos(todos):
    with open(TODO_FILE, "w") as f:
        json.dump(todos, f, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
#  ANIMATED PULSE RING  (canvas widget)
# ─────────────────────────────────────────────────────────────────────────────
class PulseRing(tk.Canvas):
    STATES = {
        "idle":      {"color": ACCENT2,  "rings": 1, "speed": 60},
        "listening": {"color": GREEN,    "rings": 3, "speed": 20},
        "thinking":  {"color": YELLOW,   "rings": 2, "speed": 30},
        "speaking":  {"color": ACCENT,   "rings": 2, "speed": 25},
        "error":     {"color": RED,      "rings": 2, "speed": 40},
    }

    def __init__(self, parent, size=120, **kw):
        super().__init__(parent, width=size, height=size,
                         bg=BG, highlightthickness=0, **kw)
        self.size = size
        self.cx = size // 2
        self.cy = size // 2
        self.state = "idle"
        self._rings = []   # list of (canvas_id, radius, alpha_fraction)
        self._phase = 0
        self._after_id = None
        self._draw_static()
        self._animate()

    def _hex_blend(self, color, alpha):
        """Blend color toward BG by alpha (0=BG, 1=color)."""
        def parse(h): return tuple(int(h[i:i+2], 16) for i in (1,3,5))
        bg = parse(BG)
        c  = parse(color)
        r = tuple(int(bg[i] + (c[i]-bg[i])*alpha) for i in range(3))
        return "#{:02x}{:02x}{:02x}".format(*r)

    def _draw_static(self):
        """Draw the inner core circle."""
        pad = 10
        self._core = self.create_oval(
            pad, pad, self.size-pad, self.size-pad,
            outline=ACCENT, width=2, fill=PANEL
        )
        # J letter
        self._label = self.create_text(
            self.cx, self.cy,
            text="J", fill=ACCENT,
            font=("Courier", int(self.size*0.28), "bold")
        )

    def set_state(self, state):
        if state not in self.STATES:
            state = "idle"
        self.state = state
        cfg = self.STATES[state]
        self.itemconfig(self._core, outline=cfg["color"])
        self.itemconfig(self._label, fill=cfg["color"])

    def _animate(self):
        cfg = self.STATES[self.state]
        self._phase = (self._phase + 2) % 100

        # Delete old rings
        for oid in self._rings:
            self.delete(oid)
        self._rings = []

        if self.state != "idle":
            n = cfg["rings"]
            for i in range(n):
                # Each ring offset by equal phase
                phase = (self._phase + i * (100 // n)) % 100
                frac  = phase / 100.0
                r = (self.cx - 12) * (0.5 + 0.5 * frac)
                alpha = 1.0 - frac
                color = self._hex_blend(cfg["color"], alpha)
                x0, y0 = self.cx - r, self.cy - r
                x1, y1 = self.cx + r, self.cy + r
                oid = self.create_oval(x0, y0, x1, y1,
                                       outline=color, width=1)
                self._rings.append(oid)

        self._after_id = self.after(cfg["speed"], self._animate)


# ─────────────────────────────────────────────────────────────────────────────
#  RAM / CPU BAR
# ─────────────────────────────────────────────────────────────────────────────
class ResourceBar(tk.Frame):
    def __init__(self, parent, label, get_val_fn, **kw):
        super().__init__(parent, bg=PANEL, **kw)
        self._get = get_val_fn
        tk.Label(self, text=label, bg=PANEL, fg=DIM,
                 font=("Courier", 8)).pack(anchor="w")
        self._bar_bg = tk.Frame(self, bg=BORDER, height=6)
        self._bar_bg.pack(fill="x", pady=(1,0))
        self._bar_fg = tk.Frame(self._bar_bg, bg=ACCENT, height=6)
        self._bar_fg.place(x=0, y=0, relheight=1.0, relwidth=0)
        self._pct_lbl = tk.Label(self, bg=PANEL, fg=TEXT, font=("Courier", 8))
        self._pct_lbl.pack(anchor="e")
        self._update()

    def _update(self):
        v = self._get()           # 0–100
        color = GREEN if v < 60 else YELLOW if v < 85 else RED
        self._bar_fg.config(bg=color)
        self._bar_fg.place(relwidth=v/100)
        self._pct_lbl.config(text=f"{v:.0f}%")
        self.after(1500, self._update)


# ─────────────────────────────────────────────────────────────────────────────
#  CONVERSATION LOG
# ─────────────────────────────────────────────────────────────────────────────
class ConvoLog(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=PANEL, **kw)
        self._text = tk.Text(
            self, bg=PANEL, fg=TEXT, bd=0, relief="flat",
            wrap="word", state="disabled", cursor="arrow",
            font=("Courier", 9), padx=8, pady=6,
            selectbackground=ACCENT2
        )
        sb = tk.Scrollbar(self, orient="vertical", command=self._text.yview,
                          bg=BORDER, troughcolor=PANEL, width=6)
        self._text.config(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._text.pack(side="left", fill="both", expand=True)

        self._text.tag_config("user",   foreground=GREEN,  font=("Courier", 9, "bold"))
        self._text.tag_config("jarvis", foreground=ACCENT, font=("Courier", 9, "bold"))
        self._text.tag_config("body",   foreground=TEXT,   font=("Courier", 9))
        self._text.tag_config("ts",     foreground=DIM,    font=("Courier", 8))

    def append(self, speaker, message):
        ts   = datetime.datetime.now().strftime("%H:%M")
        name = "YOU" if speaker == "user" else "JARVIS"
        tag  = "user" if speaker == "user" else "jarvis"

        self._text.config(state="normal")
        self._text.insert("end", f"\n[{ts}] ", "ts")
        self._text.insert("end", f"{name}: ", tag)
        self._text.insert("end", message + "\n", "body")
        self._text.config(state="disabled")
        self._text.see("end")


# ─────────────────────────────────────────────────────────────────────────────
#  TODO LIST PANEL
# ─────────────────────────────────────────────────────────────────────────────
class TodoPanel(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=PANEL, **kw)
        self._todos = load_todos()   # list of {"text":..., "done": bool}
        self._vars  = []

        hdr = tk.Frame(self, bg=PANEL)
        hdr.pack(fill="x", padx=8, pady=(8,4))
        tk.Label(hdr, text="◈  TASKS", bg=PANEL, fg=ACCENT,
                 font=("Courier", 9, "bold")).pack(side="left")
        tk.Button(hdr, text="+", bg=BORDER, fg=GREEN, relief="flat",
                  font=("Courier", 10, "bold"), cursor="hand2",
                  command=self._add_dialog, padx=6).pack(side="right")

        self._list_frame = tk.Frame(self, bg=PANEL)
        self._list_frame.pack(fill="both", expand=True, padx=8)

        self._rebuild()

    def _rebuild(self):
        for w in self._list_frame.winfo_children():
            w.destroy()
        self._vars = []
        for i, todo in enumerate(self._todos):
            row = tk.Frame(self._list_frame, bg=PANEL)
            row.pack(fill="x", pady=1)
            var = tk.BooleanVar(value=todo["done"])
            self._vars.append(var)

            def _toggle(idx=i, v=var):
                self._todos[idx]["done"] = v.get()
                save_todos(self._todos)
                self._rebuild()

            cb = tk.Checkbutton(
                row, variable=var, bg=PANEL,
                activebackground=PANEL, fg=ACCENT,
                selectcolor=PANEL, relief="flat",
                command=_toggle
            )
            cb.pack(side="left")
            style = "overstrike" if todo["done"] else ""
            color = DIM if todo["done"] else TEXT
            tk.Label(row, text=todo["text"], bg=PANEL, fg=color,
                     font=("Courier", 9, style),
                     anchor="w").pack(side="left", fill="x", expand=True)
            tk.Button(row, text="✕", bg=PANEL, fg=RED, relief="flat",
                      font=("Courier", 8), cursor="hand2",
                      command=lambda idx=i: self._delete(idx)).pack(side="right")

    def _delete(self, idx):
        self._todos.pop(idx)
        save_todos(self._todos)
        self._rebuild()

    def _add_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("New Task")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.geometry("340x110")
        dlg.grab_set()

        tk.Label(dlg, text="Task:", bg=BG, fg=TEXT,
                 font=("Courier", 9)).pack(anchor="w", padx=14, pady=(14,2))
        entry = tk.Entry(dlg, bg=PANEL, fg=WHITE, insertbackground=ACCENT,
                         relief="flat", font=("Courier", 10), bd=6)
        entry.pack(fill="x", padx=14)
        entry.focus()

        def _save(e=None):
            txt = entry.get().strip()
            if txt:
                self._todos.append({"text": txt, "done": False})
                save_todos(self._todos)
                self._rebuild()
            dlg.destroy()

        entry.bind("<Return>", _save)
        tk.Button(dlg, text="ADD", bg=ACCENT2, fg=WHITE, relief="flat",
                  font=("Courier", 9, "bold"), command=_save,
                  cursor="hand2", padx=10, pady=4).pack(pady=8)

    def add_task_from_voice(self, text):
        """Called by Jarvis voice logic to add tasks programmatically."""
        self._todos.append({"text": text, "done": False})
        save_todos(self._todos)
        self._rebuild()

    def remove_from_voice(self, text):
        """Called by Jarvis voice logic to remove a task by name."""
        text_lower = text.lower()
        # Reload from disk to stay in sync with tool
        self._todos = load_todos()
        self._rebuild()

    def complete_from_voice(self, text):
        """Called by Jarvis voice logic to mark a task done by name."""
        # Reload from disk — the tool already saved the change
        self._todos = load_todos()
        self._rebuild()


# ─────────────────────────────────────────────────────────────────────────────
#  STATUS BAR  (bottom strip)
# ─────────────────────────────────────────────────────────────────────────────
class StatusBar(tk.Frame):
    LABELS = {
        "idle":      ("● IDLE",      DIM),
        "listening": ("◉ LISTENING", GREEN),
        "thinking":  ("◈ THINKING",  YELLOW),
        "speaking":  ("▶ SPEAKING",  ACCENT),
        "error":     ("✖ ERROR",     RED),
    }

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=BORDER, height=28, **kw)
        self._state_lbl = tk.Label(self, text="● IDLE", bg=BORDER, fg=DIM,
                                   font=("Courier", 9, "bold"))
        self._state_lbl.pack(side="left", padx=12)

        self._time_lbl = tk.Label(self, bg=BORDER, fg=DIM, font=("Courier", 9))
        self._time_lbl.pack(side="right", padx=12)
        self._tick()

        self._model_lbl = tk.Label(self, text="MODEL: qwen3:1.7b",
                                   bg=BORDER, fg=DIM, font=("Courier", 9))
        self._model_lbl.pack(side="right", padx=12)

    def set_state(self, state):
        txt, color = self.LABELS.get(state, ("● IDLE", DIM))
        self._state_lbl.config(text=txt, fg=color)

    def set_model(self, name):
        self._model_lbl.config(text=f"MODEL: {name}")

    def _tick(self):
        now = datetime.datetime.now().strftime("%a %d %b  %H:%M:%S")
        self._time_lbl.config(text=now)
        self.after(1000, self._tick)


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN WINDOW
# ─────────────────────────────────────────────────────────────────────────────
class JarvisApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("JARVIS  //  Local AI Assistant")
        self.configure(bg=BG)
        self.geometry("900x620")
        self.minsize(760, 520)

        # Custom window chrome
        self._build_titlebar()
        self._build_body()
        self._build_statusbar()

        # Start polling the event queue
        self._poll_queue()

        # Start Jarvis voice loop in daemon thread
        t = threading.Thread(target=run_jarvis, daemon=True)
        t.start()

        # Boot message
        self.after(600, lambda: self._convo.append(
            "jarvis",
            "System online. Say 'Jarvis' to begin."
        ))

    # ── Title bar ─────────────────────────────────────────────────────────────
    def _build_titlebar(self):
        bar = tk.Frame(self, bg=PANEL, height=42)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        # Drag support
        bar.bind("<ButtonPress-1>",   self._drag_start)
        bar.bind("<B1-Motion>",       self._drag_move)

        tk.Label(bar, text="◈ JARVIS", bg=PANEL, fg=ACCENT,
                 font=("Courier", 13, "bold")).pack(side="left", padx=14)
        tk.Label(bar, text="LOCAL AI ASSISTANT", bg=PANEL, fg=DIM,
                 font=("Courier", 8)).pack(side="left", padx=4)

        # Window buttons
        for sym, cmd, col in [
            ("✕", self.destroy, RED),
            ("▭", self._toggle_max, DIM),
            ("─", self.iconify, DIM),
        ]:
            tk.Button(bar, text=sym, bg=PANEL, fg=col, relief="flat",
                      font=("Courier", 10), cursor="hand2",
                      activebackground=BORDER, command=cmd,
                      padx=8).pack(side="right")

    def _drag_start(self, e):
        self._dx, self._dy = e.x, e.y

    def _drag_move(self, e):
        x = self.winfo_x() + e.x - self._dx
        y = self.winfo_y() + e.y - self._dy
        self.geometry(f"+{x}+{y}")

    def _toggle_max(self):
        self.state("zoomed" if self.state() != "zoomed" else "normal")

    # ── Main body ─────────────────────────────────────────────────────────────
    def _build_body(self):
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=0, pady=0)

        # LEFT SIDEBAR
        sidebar = tk.Frame(body, bg=PANEL, width=200)
        sidebar.pack(side="left", fill="y", padx=(8,4), pady=8)
        sidebar.pack_propagate(False)

        # Pulse ring
        self._pulse = PulseRing(sidebar, size=110)
        self._pulse.pack(pady=(18, 8))

        tk.Frame(sidebar, bg=BORDER, height=1).pack(fill="x", padx=10)

        # Resource bars
        res_frame = tk.Frame(sidebar, bg=PANEL)
        res_frame.pack(fill="x", padx=12, pady=10)
        tk.Label(res_frame, text="SYSTEM", bg=PANEL, fg=DIM,
                 font=("Courier", 8, "bold")).pack(anchor="w", pady=(0,4))
        ResourceBar(res_frame, "RAM",
                    lambda: psutil.virtual_memory().percent
                    ).pack(fill="x", pady=2)
        ResourceBar(res_frame, "CPU",
                    lambda: psutil.cpu_percent(interval=None)
                    ).pack(fill="x", pady=2)

        tk.Frame(sidebar, bg=BORDER, height=1).pack(fill="x", padx=10)

        # Todo list
        self._todo = TodoPanel(sidebar)
        self._todo.pack(fill="both", expand=True, pady=4)

        # RIGHT — Conversation log
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(4,8), pady=8)

        hdr = tk.Frame(right, bg=BG)
        hdr.pack(fill="x", pady=(0,4))
        tk.Label(hdr, text="◈  CONVERSATION", bg=BG, fg=ACCENT,
                 font=("Courier", 9, "bold")).pack(side="left")
        tk.Button(hdr, text="CLEAR", bg=BORDER, fg=DIM, relief="flat",
                  font=("Courier", 8), cursor="hand2",
                  command=self._clear_log, padx=6).pack(side="right")

        self._convo = ConvoLog(right)
        self._convo.pack(fill="both", expand=True)

        # Manual input row (type to Jarvis when voice isn't convenient)
        inp_row = tk.Frame(right, bg=PANEL)
        inp_row.pack(fill="x", pady=(6,0))
        self._entry = tk.Entry(
            inp_row, bg=BORDER, fg=WHITE, insertbackground=ACCENT,
            relief="flat", font=("Courier", 10), bd=8
        )
        self._entry.pack(side="left", fill="x", expand=True, padx=(6,4), pady=6)
        self._entry.bind("<Return>", self._send_text)
        tk.Button(inp_row, text="SEND ▶", bg=ACCENT2, fg=WHITE, relief="flat",
                  font=("Courier", 9, "bold"), cursor="hand2",
                  command=self._send_text, padx=10).pack(side="right", padx=6)

    def _build_statusbar(self):
        self._statusbar = StatusBar(self)
        self._statusbar.pack(fill="x", side="bottom")

    # ── Event queue polling ────────────────────────────────────────────────────
    def _poll_queue(self):
        try:
            while True:
                event, data = gui_queue.get_nowait()
                if event == "status":
                    self._pulse.set_state(data)
                    self._statusbar.set_state(data)
                elif event == "log":
                    speaker, msg = data
                    self._convo.append(speaker, msg)
                elif event == "todo_add":
                    self._todo.add_task_from_voice(data)
                elif event == "todo_remove":
                    self._todo.remove_from_voice(data)
                elif event == "todo_complete":
                    self._todo.complete_from_voice(data)
                elif event == "model":
                    self._statusbar.set_model(data)
        except queue.Empty:
            pass
        self.after(80, self._poll_queue)

    # ── Text input ────────────────────────────────────────────────────────────
    def _send_text(self, _=None):
        txt = self._entry.get().strip()
        if not txt:
            return
        self._entry.delete(0, "end")
        self._convo.append("user", txt)
        # Route to Jarvis logic via queue or direct call
        # For now, echo with a placeholder response
        post("status", "thinking")
        def _respond():
            time.sleep(0.8)
            post("log", ("jarvis", f"(Text input received: '{txt}')"))
            post("status", "idle")
        threading.Thread(target=_respond, daemon=True).start()

    def _clear_log(self):
        self._convo._text.config(state="normal")
        self._convo._text.delete("1.0", "end")
        self._convo._text.config(state="disabled")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = JarvisApp()
    app.mainloop()