"""Модель игры «крестики-нолики» на бесконечном поле.

Поле не является матрицей: занятые клетки хранятся в словаре
``{(x, y): "X" | "O"}``, поэтому координаты могут быть любыми
(в том числе отрицательными и очень большими).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

Coord = Tuple[int, int]

X = "X"
O = "O"
PLAYERS = (X, O)

#: Четыре оси, по которым ищутся линии: горизонталь, вертикаль, две диагонали.
DIRECTIONS: Tuple[Coord, ...] = ((1, 0), (0, 1), (1, 1), (1, -1))


def other(player: str) -> str:
    """Вернуть знак соперника."""
    return O if player == X else X


class Board:
    """Бесконечное игровое поле.

    :param win_len: сколько знаков подряд нужно для победы (>= 3).
    :param max_moves: лимит ходов; по достижении — ничья (``None`` — без лимита).
    """

    def __init__(self, win_len: int = 5, max_moves: Optional[int] = None) -> None:
        if win_len < 3:
            raise ValueError("win_len должен быть не меньше 3")
        self.win_len = win_len
        self.max_moves = max_moves
        self.cells: Dict[Coord, str] = {}
        self.history: List[Coord] = []
        self.winner: Optional[str] = None
        self.winning_line: List[Coord] = []

    # ------------------------------------------------------------------ состояние
    @property
    def move_count(self) -> int:
        return len(self.history)

    @property
    def last_move(self) -> Optional[Coord]:
        return self.history[-1] if self.history else None

    @property
    def next_player(self) -> str:
        return X if self.move_count % 2 == 0 else O

    @property
    def is_draw(self) -> bool:
        """Ничья: лимит ходов исчерпан, но никто не выиграл."""
        return (
            self.winner is None
            and self.max_moves is not None
            and self.move_count >= self.max_moves
        )

    @property
    def is_over(self) -> bool:
        return self.winner is not None or self.is_draw

    def get(self, coord: Coord) -> Optional[str]:
        """Знак в клетке или ``None``, если клетка пуста."""
        return self.cells.get(coord)

    def is_empty(self, coord: Coord) -> bool:
        return coord not in self.cells

    # ------------------------------------------------------------------ ходы
    def place(self, coord: Coord, player: Optional[str] = None) -> str:
        """Поставить знак. Возвращает фактически поставленный знак."""
        if self.is_over:
            raise ValueError("Игра уже завершена")
        if coord in self.cells:
            raise ValueError(f"Клетка {coord} уже занята")
        player = player or self.next_player
        if player not in PLAYERS:
            raise ValueError(f"Неизвестный игрок: {player!r}")

        self.cells[coord] = player
        self.history.append(coord)

        if self.is_winning_move(coord, player):
            self.winner = player
            self.winning_line = self.line_through(coord, player)
        return player

    def undo(self) -> Optional[Coord]:
        """Отменить последний ход. Возвращает координату или ``None``."""
        if not self.history:
            return None
        coord = self.history.pop()
        del self.cells[coord]
        self.winner = None
        self.winning_line = []
        return coord

    def reset(self) -> None:
        self.cells.clear()
        self.history.clear()
        self.winner = None
        self.winning_line = []

    # ------------------------------------------------------------------ победа
    def count_run(self, coord: Coord, player: str, direction: Coord) -> int:
        """Длина непрерывной линии знаков ``player`` через ``coord`` по оси."""
        dx, dy = direction
        x, y = coord
        total = 1
        for sign in (1, -1):
            step = 1
            while self.cells.get((x + sign * step * dx, y + sign * step * dy)) == player:
                step += 1
            total += step - 1
        return total

    def is_winning_move(self, coord: Coord, player: str) -> bool:
        """Победит ли ``player``, поставив знак в ``coord`` (клетка пустая или его же)?"""
        return any(
            self.count_run(coord, player, direction) >= self.win_len
            for direction in DIRECTIONS
        )

    def line_through(self, coord: Coord, player: str) -> List[Coord]:
        """Выигрышная линия через ``coord`` (пустой список, если победы нет)."""
        for direction in DIRECTIONS:
            if self.count_run(coord, player, direction) < self.win_len:
                continue
            dx, dy = direction
            x, y = coord
            line = [coord]
            for sign in (1, -1):
                step = 1
                while self.cells.get((x + sign * step * dx, y + sign * step * dy)) == player:
                    line.append((x + sign * step * dx, y + sign * step * dy))
                    step += 1
            line.sort()
            return line
        return []

    def winning_cells_for(self, player: str) -> Set[Coord]:
        """Все пустые клетки, поставив в которые ``player`` немедленно побеждает."""
        return {c for c in self.candidates(1) if self.is_winning_move(c, player)}

    # ------------------------------------------------------------------ кандидаты
    def candidates(self, radius: int = 2) -> Set[Coord]:
        """Пустые клетки в радиусе ``radius`` (по Чебышёву) от занятых.

        Бесконечное поле становится конечным именно так: рассматриваются
        только окрестности уже поставленных знаков.
        """
        if not self.cells:
            return {(0, 0)}
        out: Set[Coord] = set()
        for (x, y) in self.cells:
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if dx == 0 and dy == 0:
                        continue
                    coord = (x + dx, y + dy)
                    if coord not in self.cells:
                        out.add(coord)
        return out

    def neighbor_count(self, coord: Coord, radius: int = 1) -> int:
        """Сколько занятых клеток вокруг (используется как тай-брейк)."""
        x, y = coord
        return sum(
            1
            for dx in range(-radius, radius + 1)
            for dy in range(-radius, radius + 1)
            if (dx or dy) and (x + dx, y + dy) in self.cells
        )

    def center_of_mass(self, player: Optional[str] = None) -> Optional[Tuple[float, float]]:
        """Центр масс знаков игрока (или всех знаков, если ``player`` не задан)."""
        coords = (
            [c for c, p in self.cells.items() if p == player]
            if player
            else list(self.cells)
        )
        if not coords:
            return None
        return (
            sum(c[0] for c in coords) / len(coords),
            sum(c[1] for c in coords) / len(coords),
        )

    # ------------------------------------------------------------------ отладка
    def __str__(self) -> str:  # pragma: no cover - только для отладки
        if not self.cells:
            return "<пустое поле>"
        xs = [c[0] for c in self.cells]
        ys = [c[1] for c in self.cells]
        rows = []
        for y in range(max(ys), min(ys) - 1, -1):
            rows.append(
                "".join(self.cells.get((x, y), ".") for x in range(min(xs), max(xs) + 1))
            )
        return "\n".join(rows)
