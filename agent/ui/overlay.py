"""
Premium transparent overlay for PokemonAI bot.
Clean, professional HUD showing bot thoughts in real-time.
"""

import ctypes
import ctypes.wintypes
import logging
import queue
import threading
import tkinter as tk
import time

logger = logging.getLogger(__name__)

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000

user32 = ctypes.windll.user32

# ── Color palette ────────────────────────────────────────────
BG = "#0a0a12"
BG_CARD = "#10101c"
BG_SURFACE = "#181828"
ACCENT = "#ff2d55"
TEXT = "#d8dce6"
TEXT_SEC = "#717b96"
TEXT_DIM = "#3a4058"
WHITE = "#f0f2f8"
GREEN = "#00e676"
YELLOW = "#ffd600"
RED = "#ff1744"
BLUE = "#448aff"
PURPLE = "#bb86fc"
CYAN = "#00d4ff"

PHASE_COLORS = {
    "overworld": GREEN, "battle": RED, "dialogue": YELLOW,
    "menu": BLUE, "transition": TEXT_DIM, "title": PURPLE,
}
PHASE_LABELS = {
    "overworld": "EXPLORING", "battle": "BATTLE", "dialogue": "DIALOGUE",
    "menu": "MENU", "transition": "LOADING", "title": "TITLE",
}


class Overlay:
    def __init__(self, hwnd=None, width=340):
        self._hwnd_mgba = hwnd
        self._width = width
        self._height = 400
        self._queue = queue.Queue()
        self._root = None
        self._start_time = time.time()
        self._pulse_on = True

        self._thread = threading.Thread(
            target=self._run_tk, daemon=True, name="OverlayThread",
        )
        self._thread.start()
        logger.info("Overlay thread started")

    # ── Tk thread ────────────────────────────────────────────

    def _run_tk(self):
        try:
            self._root = tk.Tk()
            self._root.title("PokemonAI")
            self._root.overrideredirect(True)
            self._root.attributes("-topmost", True)
            self._root.attributes("-alpha", 0.92)
            self._root.configure(bg=BG)
            self._position_window()
            self._build_ui()
            self._root.after(200, self._apply_win32_flags)
            self._root.after(150, self._poll_queue)
            self._root.after(700, self._pulse)
            self._root.mainloop()
        except Exception as e:
            logger.error(f"Overlay thread error: {e}")

    def _position_window(self):
        x, y = 100, 100
        if self._hwnd_mgba:
            r = ctypes.wintypes.RECT()
            user32.GetWindowRect(self._hwnd_mgba, ctypes.byref(r))
            x = r.right - self._width - 10
            y = r.top + 40
        if self._root:
            x = max(0, min(x, self._root.winfo_screenwidth() - self._width - 10))
            y = max(0, min(y, self._root.winfo_screenheight() - self._height - 10))
            self._root.geometry(f"{self._width}x{self._height}+{x}+{y}")

    # ── Build UI ─────────────────────────────────────────────

    def _build_ui(self):
        w = self._width

        # Outer accent border
        border = tk.Frame(self._root, bg=ACCENT)
        border.pack(fill="both", expand=True)
        main = tk.Frame(border, bg=BG)
        main.pack(fill="both", expand=True, padx=1, pady=1)

        # ── Header row ───────────────────────────────────────
        hdr = tk.Frame(main, bg=BG_CARD)
        hdr.pack(fill="x")

        hdr_inner = tk.Frame(hdr, bg=BG_CARD)
        hdr_inner.pack(fill="x", padx=12, pady=8)

        tk.Label(
            hdr_inner, text="POKEMONAI", font=("Segoe UI", 12, "bold"),
            fg=WHITE, bg=BG_CARD,
        ).pack(side="left")

        # Live dot
        self._live_dot = tk.Label(
            hdr_inner, text="\u25CF", font=("Segoe UI", 6),
            fg=GREEN, bg=BG_CARD,
        )
        self._live_dot.pack(side="right", padx=2)
        tk.Label(
            hdr_inner, text="LIVE", font=("Consolas", 7, "bold"),
            fg=GREEN, bg=BG_CARD,
        ).pack(side="right", padx=0)

        # Accent line
        tk.Frame(main, height=2, bg=ACCENT).pack(fill="x")

        # ── Status row: tick + phase + uptime ────────────────
        status = tk.Frame(main, bg=BG)
        status.pack(fill="x", padx=12, pady=6)

        self._lbl_tick = tk.Label(
            status, text="#0", font=("Consolas", 8, "bold"),
            fg=CYAN, bg=BG,
        )
        self._lbl_tick.pack(side="left")

        self._lbl_phase_dot = tk.Label(
            status, text="\u25CF", font=("Segoe UI", 6),
            fg=GREEN, bg=BG,
        )
        self._lbl_phase_dot.pack(side="left", padx=6)

        self._lbl_phase = tk.Label(
            status, text="EXPLORING", font=("Segoe UI", 8, "bold"),
            fg=GREEN, bg=BG,
        )
        self._lbl_phase.pack(side="left")

        self._lbl_uptime = tk.Label(
            status, text="00:00:00", font=("Consolas", 8),
            fg=TEXT_DIM, bg=BG,
        )
        self._lbl_uptime.pack(side="right")

        # Separator
        tk.Frame(main, height=1, bg=BG_SURFACE).pack(fill="x", padx=12)

        # ── Observation ──────────────────────────────────────
        tk.Label(
            main, text="AI SEES:", font=("Consolas", 7, "bold"),
            fg=PURPLE, bg=BG, anchor="w",
        ).pack(fill="x", padx=14, pady=(6, 0))

        self._lbl_obs = tk.Label(
            main, text="Waiting for first tick...",
            font=("Segoe UI", 9), fg=TEXT, bg=BG,
            anchor="nw", justify="left", wraplength=w - 30,
        )
        self._lbl_obs.pack(fill="x", padx=14, pady=(2, 6))

        # ── Reasoning ────────────────────────────────────────
        tk.Label(
            main, text="AI THINKS:", font=("Consolas", 7, "bold"),
            fg=PURPLE, bg=BG, anchor="w",
        ).pack(fill="x", padx=14, pady=(0, 0))

        self._lbl_reasoning = tk.Label(
            main, text="--",
            font=("Segoe UI", 9), fg=CYAN, bg=BG,
            anchor="nw", justify="left", wraplength=w - 30,
        )
        self._lbl_reasoning.pack(fill="x", padx=14, pady=(2, 0))

        # Small gap
        tk.Frame(main, height=6, bg=BG).pack(fill="x")

        # ── Action (compact inline) ──────────────────────────
        act_row = tk.Frame(main, bg=BG_CARD)
        act_row.pack(fill="x", padx=12, pady=4)

        # Left accent stripe
        tk.Frame(act_row, width=3, bg=ACCENT).pack(side="left", fill="y")

        act_inner = tk.Frame(act_row, bg=BG_CARD)
        act_inner.pack(side="left", fill="x", expand=True, padx=8, pady=6)

        self._lbl_action_key = tk.Label(
            act_inner, text="--", font=("Consolas", 10, "bold"),
            fg=ACCENT, bg=BG_CARD,
        )
        self._lbl_action_key.pack(side="left")

        self._lbl_action_detail = tk.Label(
            act_inner, text="", font=("Segoe UI", 8),
            fg=TEXT_SEC, bg=BG_CARD, anchor="w",
        )
        self._lbl_action_detail.pack(side="left", padx=8)

        # ── Next plan ────────────────────────────────────────
        plan_row = tk.Frame(main, bg=BG)
        plan_row.pack(fill="x", padx=14, pady=4)

        tk.Label(
            plan_row, text="NEXT", font=("Consolas", 7),
            fg=TEXT_DIM, bg=BG,
        ).pack(side="left")

        self._lbl_plan = tk.Label(
            plan_row, text="--", font=("Segoe UI", 8),
            fg=TEXT_SEC, bg=BG, anchor="w",
        )
        self._lbl_plan.pack(side="left", padx=6)

        # ── HP section ────────────────────────────────────────
        hp_frame = tk.Frame(main, bg=BG)
        hp_frame.pack(fill="x", padx=12, pady=8)

        # Separator above HP
        tk.Frame(hp_frame, height=1, bg=BG_SURFACE).pack(fill="x", pady=4)

        hp_info = tk.Frame(hp_frame, bg=BG)
        hp_info.pack(fill="x")

        self._lbl_hp_name = tk.Label(
            hp_info, text="--", font=("Segoe UI", 9, "bold"),
            fg=TEXT, bg=BG,
        )
        self._lbl_hp_name.pack(side="left")

        self._lbl_hp_nums = tk.Label(
            hp_info, text="", font=("Consolas", 9, "bold"),
            fg=GREEN, bg=BG,
        )
        self._lbl_hp_nums.pack(side="right")

        # HP bar
        self._hp_canvas = tk.Canvas(
            hp_frame, height=10, bg=BG, highlightthickness=0,
        )
        self._hp_canvas.pack(fill="x", pady=4)
        self._hp_bar_w = w - 28
        self._draw_hp_bar(0, 1)

    # ── HP bar drawing ───────────────────────────────────────

    def _draw_hp_bar(self, current, maximum):
        c = self._hp_canvas
        c.delete("all")
        bw = self._hp_bar_w
        bh = 8

        c.create_rectangle(0, 0, bw, bh, fill=BG_CARD, outline=BG_SURFACE, width=1)

        if maximum <= 0:
            return
        ratio = max(0, min(current / maximum, 1.0))
        fw = int(bw * ratio)
        if fw <= 0:
            return

        if ratio > 0.5:
            color, shine = GREEN, "#69f0ae"
        elif ratio > 0.2:
            color, shine = YELLOW, "#ffff8d"
        else:
            color, shine = RED, "#ff8a80"

        c.create_rectangle(1, 1, fw, bh - 1, fill=color, outline="")
        c.create_rectangle(2, 2, fw - 1, bh // 2, fill=shine, outline="")
        if fw > 4:
            c.create_line(2, 1, fw - 1, 1, fill="#ffffff", width=1)

    # ── Animations ───────────────────────────────────────────

    def _pulse(self):
        try:
            self._pulse_on = not self._pulse_on
            self._live_dot.config(fg=GREEN if self._pulse_on else "#0a2e1a")
        except Exception:
            pass
        if self._root:
            self._root.after(700, self._pulse)

    # ── Win32 click-through ──────────────────────────────────

    def _apply_win32_flags(self):
        try:
            fid = self._root.wm_frame()
            if fid:
                hwnd = int(fid, 16)
                if hwnd:
                    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                    ex |= WS_EX_NOACTIVATE | WS_EX_TRANSPARENT | WS_EX_LAYERED
                    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)
                    logger.info("Overlay Win32 flags applied")
                    return
            self._root.after(200, self._apply_win32_flags)
        except Exception as e:
            logger.warning(f"Win32 flags failed: {e}")

    # ── Queue polling ────────────────────────────────────────

    def _poll_queue(self):
        try:
            while not self._queue.empty():
                self._render(self._queue.get_nowait())
        except queue.Empty:
            pass
        except Exception as e:
            logger.debug(f"Poll error: {e}")
        if self._root:
            self._root.after(150, self._poll_queue)

    # ── Render data ──────────────────────────────────────────

    def _render(self, data):
        try:
            tick = data.get("tick", 0)

            # Uptime
            el = int(time.time() - self._start_time)
            self._lbl_tick.config(text=f"#{tick}")
            self._lbl_uptime.config(text=f"{el//3600:02d}:{(el%3600)//60:02d}:{el%60:02d}")

            # Phase
            phase = data.get("game_phase", "unknown")
            color = PHASE_COLORS.get(phase, TEXT_DIM)
            label = PHASE_LABELS.get(phase, phase.upper())
            self._lbl_phase.config(text=label, fg=color)
            self._lbl_phase_dot.config(fg=color)

            # Observation (full text, no truncation - label wraps)
            self._lbl_obs.config(text=data.get("observation", "--"))

            # Reasoning
            self._lbl_reasoning.config(text=data.get("reasoning", "--"))

            # Action
            self._lbl_action_key.config(text=data.get("action", "--"))
            detail = data.get("action_detail", "")
            self._lbl_action_detail.config(text=detail if detail else "")

            # Plan
            plan = data.get("next_plan", "--")
            if len(plan) > 60:
                plan = plan[:57] + "..."
            self._lbl_plan.config(text=plan)

            # HP
            hp_str = data.get("hp_status", "--")
            hp_c, hp_m = 0, 1
            name = "--"
            if ":" in hp_str and "/" in hp_str:
                try:
                    name = hp_str.split(":")[0].strip()
                    nums = hp_str.split(":")[1].strip()
                    parts = nums.split("/")
                    hp_c = int(parts[0].strip())
                    hp_m = int(parts[1].strip())
                except (ValueError, IndexError):
                    pass

            self._lbl_hp_name.config(text=name)
            self._lbl_hp_nums.config(text=f"{hp_c}/{hp_m}" if hp_m > 0 else "--")

            self._draw_hp_bar(hp_c, hp_m)

            if hp_m > 0:
                r = hp_c / hp_m
                self._lbl_hp_nums.config(
                    fg=GREEN if r > 0.5 else YELLOW if r > 0.2 else RED
                )

            self._position_window()

        except Exception as e:
            logger.debug(f"Render error: {e}")

    # ── Public API ───────────────────────────────────────────

    def update(self, data):
        try:
            while self._queue.qsize() > 2:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
            self._queue.put_nowait(data)
        except Exception:
            pass

    def shutdown(self):
        if self._root:
            try:
                self._root.after(0, self._root.destroy)
            except Exception:
                pass
