"""Графический интерфейс: окно Tkinter с бесконечной доской.

Доска рисуется только в пределах видимой области, поэтому «бесконечность»
ничего не стоит: панорама — перетаскиванием, масштаб — колесом мыши.
"""

from __future__ import annotations

import math
import time
import tkinter as tk
from tkinter import ttk
from typing import Dict, List, Optional, Tuple

import ai
from game import O, X, Board, other

# --- палитра и константы -----------------------------------------------------
BG = "#f7f4ed"            # фон доски («бумага»)
PANEL_BG = "#ece7dc"      # фон панели настроек
GRID = "#e2dbca"
GRID_MAJOR = "#cbc0a7"
AXIS = "#9c927c"
INK = "#3a352c"
MUTED = "#8b8171"
COLOR_X = "#c0392b"
COLOR_O = "#2c5aa0"
LAST_MOVE = "#f0b429"
WIN_LINE = "#8ed08e"
OVERLAY = "#e8622a"

MIN_CELL = 5.0
MAX_CELL = 110.0
DEFAULT_CELL = 40.0
CLICK_SLOP = 4            # px: меньше — это клик, больше — перетаскивание
AI_DELAY_MS = 40          # небольшая пауза, чтобы интерфейс успевал перерисоваться

MODE_LABELS = {
    "Человек – человек": "human_human",
    "Человек – ИИ": "human_ai",
    "ИИ – ИИ": "ai_ai",
}
DIFFICULTY_LABELS = {"Лёгкая": "easy", "Обычная": "normal", "Сложная": "hard"}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def blend(color_a: str, color_b: str, t: float) -> str:
    """Смешать два цвета ``#rrggbb`` (t = 0 → color_a, t = 1 → color_b)."""
    t = clamp(t, 0.0, 1.0)
    a = [int(color_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(color_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(
        int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3)
    )


def format_score(value: float) -> str:
    """Короткая подпись для силы хода."""
    if value >= ai.WIN_SCORE:
        return "победа"
    if value >= 1e8:
        return f"{value / 1e6:.0f}M"
    if value >= 1e6:
        return f"{value / 1e6:.1f}M"
    if value >= 1e3:
        return f"{value / 1e3:.1f}k"
    return f"{value:.0f}"


class TicTacToeApp:
    """Приложение целиком: состояние игры, отрисовка, настройки."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Крестики-нолики на бесконечном поле")
        root.geometry("1200x780")
        root.minsize(860, 580)
        root.configure(bg=PANEL_BG)

        # --- состояние вида ---
        self.cell = DEFAULT_CELL
        self.offset_x = 0.0
        self.offset_y = 0.0
        self._pan_origin: Optional[Tuple[float, float]] = None
        self._pan_offset: Tuple[float, float] = (0.0, 0.0)
        self._dragged = False

        # --- состояние игры ---
        self.board = Board(win_len=5)
        self.paused = False
        self.last_ai_ms: Optional[float] = None
        self._ai_job: Optional[str] = None
        self._eval_cache: Optional[Tuple[tuple, Dict[Tuple[int, int], float]]] = None

        self._build_vars()
        self._build_layout()
        self._bind_events()
        self.new_game()

    # ------------------------------------------------------------------ настройки
    def _build_vars(self) -> None:
        self.mode_var = tk.StringVar(value="Человек – ИИ")
        self.ai_side_var = tk.StringVar(value=O)
        self.difficulty_var = tk.StringVar(value="Обычная")
        self.win_len_var = tk.IntVar(value=5)
        self.max_moves_var = tk.IntVar(value=0)
        self.show_eval_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="")
        self.hint_var = tk.StringVar(
            value="Клик — поставить знак · перетаскивание — сдвинуть поле · "
                  "колесо мыши — масштаб · клавиша E — показать силу ходов"
        )

    @property
    def mode(self) -> str:
        return MODE_LABELS.get(self.mode_var.get(), "human_ai")

    @property
    def difficulty(self) -> str:
        return DIFFICULTY_LABELS.get(self.difficulty_var.get(), "normal")

    def _build_layout(self) -> None:
        style = ttk.Style(self.root)
        for theme in ("clam", "alt", "default"):
            try:
                style.theme_use(theme)
                break
            except tk.TclError:       # pragma: no cover - зависит от платформы
                continue
        style.configure("Panel.TFrame", background=PANEL_BG)
        style.configure("Panel.TLabel", background=PANEL_BG, foreground=INK)
        style.configure("Title.TLabel", background=PANEL_BG, foreground=INK,
                        font=("Helvetica", 15, "bold"))
        style.configure("Muted.TLabel", background=PANEL_BG, foreground=MUTED,
                        font=("Helvetica", 10))
        style.configure("Panel.TRadiobutton", background=PANEL_BG, foreground=INK)
        style.configure("Panel.TCheckbutton", background=PANEL_BG, foreground=INK)
        style.configure("Panel.TButton", padding=(6, 4))

        container = tk.Frame(self.root, bg=PANEL_BG)
        container.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(
            container, bg=BG, highlightthickness=0, cursor="crosshair"
        )
        self.canvas.pack(side="left", fill="both", expand=True)

        panel = ttk.Frame(container, style="Panel.TFrame", width=280)
        panel.pack(side="right", fill="y")
        panel.pack_propagate(False)
        self._build_panel(panel)

    # ------------------------------------------------------------------ панель
    @staticmethod
    def _section(parent: ttk.Frame, text: str) -> None:
        ttk.Label(parent, text=text.upper(), style="Muted.TLabel").pack(
            anchor="w", padx=14, pady=(12, 0)
        )

    def _build_panel(self, panel: ttk.Frame) -> None:
        pad = {"padx": 14, "pady": 2}

        ttk.Label(panel, text="Крестики-нолики", style="Title.TLabel").pack(
            anchor="w", padx=14, pady=(14, 0)
        )
        ttk.Label(panel, text="бесконечное поле", style="Muted.TLabel").pack(
            anchor="w", padx=14, pady=(0, 4)
        )

        self._section(panel, "Режим")
        for label in MODE_LABELS:
            ttk.Radiobutton(
                panel, text=label, value=label, variable=self.mode_var,
                style="Panel.TRadiobutton", command=self.on_settings_change,
            ).pack(anchor="w", **pad)

        self._section(panel, "ИИ играет за")
        side_row = ttk.Frame(panel, style="Panel.TFrame")
        side_row.pack(anchor="w", fill="x", **pad)
        for sign in (X, O):
            ttk.Radiobutton(
                side_row, text=sign, value=sign, variable=self.ai_side_var,
                style="Panel.TRadiobutton", command=self.on_settings_change,
            ).pack(side="left", padx=(0, 18))

        self._section(panel, "Сложность ИИ")
        difficulty = ttk.Combobox(
            panel, textvariable=self.difficulty_var, values=list(DIFFICULTY_LABELS),
            state="readonly", width=16,
        )
        difficulty.pack(anchor="w", **pad)
        difficulty.bind("<<ComboboxSelected>>", lambda _event: self.on_settings_change())

        self._section(panel, "Правила (новая игра)")
        self._spin(panel, "Знаков в линии", self.win_len_var, 3, 8)
        self._spin(panel, "Лимит ходов (0 — нет)", self.max_moves_var, 0, 999)

        self._section(panel, "Действия")
        ttk.Checkbutton(
            panel, text="Показывать силу ходов (E)", variable=self.show_eval_var,
            style="Panel.TCheckbutton", command=self.redraw,
        ).pack(anchor="w", **pad)

        buttons = ttk.Frame(panel, style="Panel.TFrame")
        buttons.pack(anchor="w", fill="x", padx=14, pady=(6, 2))
        ttk.Button(buttons, text="Новая игра", command=self.new_game).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(buttons, text="Отменить ход", command=self.undo).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(buttons, text="В центр", command=self.center_view).pack(side="left")

        self.pause_button = ttk.Button(panel, text="Пауза (ИИ–ИИ)", command=self.toggle_pause)
        self.pause_button.pack(anchor="w", padx=14, pady=(4, 0))

        self._section(panel, "Ход игры")
        ttk.Label(
            panel, textvariable=self.status_var, style="Panel.TLabel",
            wraplength=248, justify="left",
        ).pack(anchor="w", padx=14, pady=(0, 8))

        ttk.Label(
            panel, textvariable=self.hint_var, style="Muted.TLabel",
            wraplength=248, justify="left",
        ).pack(anchor="w", side="bottom", padx=14, pady=(0, 14))

    def _spin(self, panel: ttk.Frame, text: str, var: tk.IntVar, low: int, high: int) -> None:
        row = ttk.Frame(panel, style="Panel.TFrame")
        row.pack(anchor="w", fill="x", padx=14, pady=2)
        ttk.Label(row, text=text + ":", style="Panel.TLabel").pack(side="left")
        ttk.Spinbox(row, from_=low, to=high, textvariable=var, width=5).pack(
            side="right", padx=(6, 0)
        )

    # ------------------------------------------------------------------ события
    def _bind_events(self) -> None:
        canvas = self.canvas
        canvas.bind("<Configure>", lambda _event: self.redraw())
        canvas.bind("<ButtonPress-1>", self._on_press)
        canvas.bind("<B1-Motion>", self._on_drag)
        canvas.bind("<ButtonRelease-1>", self._on_release)
        for button in ("2", "3"):                     # средняя и правая — панорама
            canvas.bind(f"<ButtonPress-{button}>", self._on_press)
            canvas.bind(f"<B{button}-Motion>", self._on_drag)
        canvas.bind("<MouseWheel>", self._on_wheel)
        canvas.bind("<Button-4>", lambda event: self._zoom_at(1.15, event.x, event.y))
        canvas.bind("<Button-5>", lambda event: self._zoom_at(1 / 1.15, event.x, event.y))

        canvas.bind("<KeyPress-e>", lambda _event: self.toggle_eval())
        canvas.bind("<KeyPress-E>", lambda _event: self.toggle_eval())
        canvas.bind("<KeyPress-n>", lambda _event: self.new_game())
        canvas.bind("<KeyPress-c>", lambda _event: self.center_view())
        canvas.bind("<KeyPress-u>", lambda _event: self.undo())
        canvas.bind("<KeyPress-plus>", lambda _event: self._zoom_center(1.2))
        canvas.bind("<KeyPress-equal>", lambda _event: self._zoom_center(1.2))
        canvas.bind("<KeyPress-minus>", lambda _event: self._zoom_center(1 / 1.2))
        canvas.bind("<Left>", lambda _event: self._pan_by(60, 0))
        canvas.bind("<Right>", lambda _event: self._pan_by(-60, 0))
        canvas.bind("<Up>", lambda _event: self._pan_by(0, 60))
        canvas.bind("<Down>", lambda _event: self._pan_by(0, -60))

    def _on_press(self, event: tk.Event) -> None:
        self._pan_origin = (event.x, event.y)
        self._pan_offset = (self.offset_x, self.offset_y)
        self._dragged = False
        self.canvas.focus_set()

    def _on_drag(self, event: tk.Event) -> None:
        if self._pan_origin is None:
            return
        dx = event.x - self._pan_origin[0]
        dy = event.y - self._pan_origin[1]
        if abs(dx) > CLICK_SLOP or abs(dy) > CLICK_SLOP:
            self._dragged = True
        self.offset_x = self._pan_offset[0] + dx
        self.offset_y = self._pan_offset[1] + dy
        self.redraw()

    def _on_release(self, event: tk.Event) -> None:
        if self._pan_origin is None:
            return
        self._pan_origin = None
        if not self._dragged:
            self._handle_click(event.x, event.y)

    def _on_wheel(self, event: tk.Event) -> None:
        delta = getattr(event, "delta", 0)
        notches = delta / 120 if abs(delta) >= 120 else delta
        self._zoom_at(1.1 ** notches, event.x, event.y)

    # ------------------------------------------------------------------ вид
    def to_board(self, sx: float, sy: float) -> Tuple[int, int]:
        """Экранные пиксели → координаты клетки (ось Y смотрит вверх)."""
        return (
            math.floor((sx - self.offset_x) / self.cell),
            math.floor((self.offset_y - sy) / self.cell),
        )

    def to_screen(self, x: int, y: int) -> Tuple[float, float]:
        """Координаты клетки → центр её квадрата на экране."""
        return (
            self.offset_x + (x + 0.5) * self.cell,
            self.offset_y - (y + 0.5) * self.cell,
        )

    def _zoom_at(self, factor: float, sx: float, sy: float) -> None:
        new_cell = clamp(self.cell * factor, MIN_CELL, MAX_CELL)
        if abs(new_cell - self.cell) < 1e-9:
            return
        ratio = new_cell / self.cell
        self.offset_x = sx - (sx - self.offset_x) * ratio
        self.offset_y = sy - (sy - self.offset_y) * ratio
        self.cell = new_cell
        self.redraw()

    def _zoom_center(self, factor: float) -> None:
        self._zoom_at(
            factor,
            self.canvas.winfo_width() / 2,
            self.canvas.winfo_height() / 2,
        )

    def _pan_by(self, dx: float, dy: float) -> None:
        self.offset_x += dx
        self.offset_y += dy
        self.redraw()

    def center_view(self) -> None:
        width = self.canvas.winfo_width() or 800
        height = self.canvas.winfo_height() or 600
        cx, cy = self.board.center_of_mass() or (0.0, 0.0)
        self.offset_x = width / 2 - cx * self.cell
        self.offset_y = height / 2 + cy * self.cell
        self.redraw()

    def toggle_eval(self) -> None:
        self.show_eval_var.set(not self.show_eval_var.get())
        self.redraw()

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.pause_button.configure(
            text="Продолжить (ИИ–ИИ)" if self.paused else "Пауза (ИИ–ИИ)"
        )
        self.update_status()
        if not self.paused:
            self.schedule_ai()

    # ------------------------------------------------------------------ игра
    @staticmethod
    def _int_var(var: tk.IntVar, default: int) -> int:
        """Значение числового поля, устойчивое к пустому/некорректному вводу."""
        try:
            return int(var.get())
        except (tk.TclError, ValueError):
            return default

    def new_game(self) -> None:
        self._cancel_ai()
        win_len = int(clamp(self._int_var(self.win_len_var, 5), 3, 8))
        max_moves = self._int_var(self.max_moves_var, 0)
        self.board = Board(
            win_len=win_len, max_moves=max_moves if max_moves > 0 else None
        )
        self.paused = False
        self.last_ai_ms = None
        self._eval_cache = None
        self.pause_button.configure(text="Пауза (ИИ–ИИ)")
        self.center_view()
        self.update_status()
        self.schedule_ai()

    def on_settings_change(self) -> None:
        """Реакция на переключатели: режим и сложность применяются сразу."""
        self._cancel_ai()
        if self.board.move_count == 0:
            self.new_game()
            return
        if self.board.win_len != self._int_var(self.win_len_var, 5) or (
            self.board.max_moves or 0
        ) != self._int_var(self.max_moves_var, 0):
            self.hint_var.set(
                "Правила изменились — они применятся после «Новой игры» (клавиша N)."
            )
        self.update_status()
        self.schedule_ai()

    def undo(self) -> None:
        self._cancel_ai()
        if not self.board.history:
            return
        self.board.undo()
        human = self.human_side()
        # в игре с ИИ откатываем пару ходов — до хода человека
        if human is not None and self.board.history and self.board.next_player != human:
            self.board.undo()
        self.last_ai_ms = None
        self._eval_cache = None
        if self.mode == "ai_ai":     # автопартию после отката логично поставить на паузу
            self.paused = True
            self.pause_button.configure(text="Продолжить (ИИ–ИИ)")
        self.redraw()
        self.update_status()

    # ------------------------------------------------------------------ участники
    def human_side(self) -> Optional[str]:
        """За кого играет человек в режиме «человек – ИИ»."""
        if self.mode != "human_ai":
            return None
        return other(self.ai_side_var.get())

    def is_human_turn(self) -> bool:
        if self.board.is_over or self.mode == "ai_ai":
            return False
        if self.mode == "human_human":
            return True
        return self.board.next_player == self.human_side()

    def is_ai_turn(self) -> bool:
        if self.board.is_over or self.mode == "human_human":
            return False
        if self.mode == "ai_ai":
            return True
        return self.board.next_player == self.ai_side_var.get()

    def _handle_click(self, sx: float, sy: float) -> None:
        if not self.is_human_turn():
            return
        coord = self.to_board(sx, sy)
        if coord in self.board.cells:
            return
        self.board.place(coord, self.board.next_player)
        self.last_ai_ms = None
        self._eval_cache = None
        self.redraw()
        self.update_status()
        self.schedule_ai()

    # ------------------------------------------------------------------ ход ИИ
    def _cancel_ai(self) -> None:
        if self._ai_job is not None:
            self.root.after_cancel(self._ai_job)
            self._ai_job = None

    def schedule_ai(self) -> None:
        if self.paused or self._ai_job is not None:
            return
        if not self.is_ai_turn():
            return
        self._ai_job = self.root.after(AI_DELAY_MS, self._ai_move)

    def _ai_move(self) -> None:
        self._ai_job = None
        if not self.is_ai_turn():
            return
        player = self.board.next_player
        started = time.perf_counter()
        coord = ai.choose_move(self.board, player, difficulty=self.difficulty)
        self.last_ai_ms = (time.perf_counter() - started) * 1000.0
        self.board.place(coord, player)
        self._eval_cache = None
        self.redraw()
        self.update_status()
        self.schedule_ai()

    # ------------------------------------------------------------------ статус
    def update_status(self) -> None:
        board = self.board
        lines: List[str] = []
        if board.winner:
            lines.append(f"Победили {board.winner}!")
        elif board.is_draw:
            lines.append("Ничья: лимит ходов исчерпан.")
        else:
            who = board.next_player
            if self.mode == "ai_ai":
                role = "ИИ"
            elif self.mode == "human_human":
                role = None
            else:
                role = "вы" if who == self.human_side() else "ИИ"
            lines.append(f"Ход: {who}" + (f" ({role})" if role else ""))

        lines.append(f"Ходов: {board.move_count} · линия: {board.win_len}")
        if board.max_moves:
            lines.append(f"Лимит ходов: {board.max_moves}")
        if self.last_ai_ms is not None:
            lines.append(f"ИИ думал: {self.last_ai_ms:.0f} мс")
        if self.paused:
            lines.append("Пауза — нажмите «Продолжить».")
        self.status_var.set("\n".join(lines))

    def eval_scores(self) -> Dict[Tuple[int, int], float]:
        """Силы ходов для того, кто ходит следующим (с кэшем по позиции)."""
        if self.board.is_over:
            return {}
        signature = (
            self.board.win_len,
            self.board.next_player,
            tuple(sorted(self.board.cells.items())),
        )
        if self._eval_cache is not None and self._eval_cache[0] == signature:
            return self._eval_cache[1]
        scores = ai.move_scores(self.board, self.board.next_player, radius=2)
        self._eval_cache = (signature, scores)
        return scores

    # ------------------------------------------------------------------ отрисовка
    def redraw(self) -> None:
        canvas = self.canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        cell = self.cell

        # видимый диапазон клеток — только его и рисуем, поэтому поле «бесконечное»
        x0 = math.floor(-self.offset_x / cell)
        x1 = math.floor((width - self.offset_x) / cell)
        y0 = math.floor((self.offset_y - height) / cell)
        y1 = math.floor(self.offset_y / cell)

        self._draw_grid(x0, x1, y0, y1, width, height)
        self._draw_winning_line()
        if self.show_eval_var.get():
            self._draw_scores()
        self._draw_last_move()
        self._draw_marks(x0, x1, y0, y1)

    def _draw_grid(self, x0: int, x1: int, y0: int, y1: int,
                   width: int, height: int) -> None:
        canvas = self.canvas
        cell = self.cell
        label_step = 1 if cell >= 18 else (5 if cell >= 9 else 10)
        show_labels = cell >= 11
        font = ("Helvetica", 8)

        for gx in range(x0, x1 + 2):
            sx = self.offset_x + gx * cell
            if gx == 0:
                color = AXIS
            elif gx % 5 == 0:
                color = GRID_MAJOR
            else:
                color = GRID
            canvas.create_line(sx, 0, sx, height, fill=color)
            if show_labels and gx % label_step == 0:
                canvas.create_text(sx + 3, 4, anchor="nw", text=str(gx), fill=MUTED, font=font)

        for gy in range(y0, y1 + 2):
            sy = self.offset_y - gy * cell
            if gy == 0:
                color = AXIS
            elif gy % 5 == 0:
                color = GRID_MAJOR
            else:
                color = GRID
            canvas.create_line(0, sy, width, sy, fill=color)
            if show_labels and gy % label_step == 0:
                canvas.create_text(4, sy - 3, anchor="sw", text=str(gy), fill=MUTED, font=font)

    def _draw_marks(self, x0: int, x1: int, y0: int, y1: int) -> None:
        canvas = self.canvas
        cell = self.cell
        inset = cell * 0.2
        line_width = max(2.0, cell * 0.1)
        for (x, y), player in self.board.cells.items():
            if not (x0 - 1 <= x <= x1 + 1 and y0 - 1 <= y <= y1 + 1):
                continue
            cx, cy = self.to_screen(x, y)
            half = cell / 2 - inset
            if player == X:
                canvas.create_line(cx - half, cy - half, cx + half, cy + half,
                                   fill=COLOR_X, width=line_width, capstyle="round")
                canvas.create_line(cx - half, cy + half, cx + half, cy - half,
                                   fill=COLOR_X, width=line_width, capstyle="round")
            else:
                canvas.create_oval(cx - half, cy - half, cx + half, cy + half,
                                   outline=COLOR_O, width=line_width)

    def _draw_last_move(self) -> None:
        last = self.board.last_move
        if last is None or self.board.is_over:
            return
        sx, sy = self.to_screen(*last)
        half = self.cell / 2
        self.canvas.create_rectangle(
            sx - half + 2, sy - half + 2, sx + half - 2, sy + half - 2,
            outline=LAST_MOVE, width=3,
        )

    def _draw_winning_line(self) -> None:
        line = self.board.winning_line
        if not line:
            return
        canvas = self.canvas
        cell = self.cell
        for (x, y) in line:
            sx, sy = self.to_screen(x, y)
            canvas.create_rectangle(
                sx - cell / 2, sy - cell / 2, sx + cell / 2, sy + cell / 2,
                fill=WIN_LINE, outline="",
            )
        sx1, sy1 = self.to_screen(*line[0])
        sx2, sy2 = self.to_screen(*line[-1])
        canvas.create_line(sx1, sy1, sx2, sy2, fill="#3f9a3f",
                           width=max(3.0, cell * 0.1), capstyle="round")

    def _draw_scores(self) -> None:
        """Оверлей «сила хода»: чем ярче клетка, тем сильнее ход."""
        scores = self.eval_scores()
        if not scores:
            return
        best = max(scores.values())
        if best <= 0:
            return
        canvas = self.canvas
        cell = self.cell
        half = cell / 2
        denominator = math.log10(1.0 + best)
        font = ("Helvetica", max(7, int(cell * 0.2)))

        for (x, y), value in scores.items():
            if value <= 0:
                continue
            sx, sy = self.to_screen(x, y)
            ratio = math.log10(1.0 + value) / denominator
            color = blend(BG, OVERLAY, ratio ** 1.2)
            canvas.create_rectangle(
                sx - half + 1, sy - half + 1, sx + half - 1, sy + half - 1,
                fill=color, outline="",
            )
            if cell >= 30:
                canvas.create_text(sx, sy, text=format_score(value), fill=INK, font=font)


def main() -> None:
    root = tk.Tk()
    app = TicTacToeApp(root)
    app.canvas.focus_set()
    root.mainloop()


if __name__ == "__main__":
    main()
