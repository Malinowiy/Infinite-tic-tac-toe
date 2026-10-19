"""Эвристика выбора хода.

Идея ровно такая: для каждой вероятной клетки считаем

* ``my``  — насколько сильную линию эта клетка создаёт для нас;
* ``opp`` — насколько сильную линию она создала бы сопернику (ценность блокировки);

и ходим туда, где ``ATTACK * my + DEFENSE * opp`` максимальна.
Отдельно обрабатываются мгновенная победа и вынужденная блокировка —
они получают вес ``WIN_SCORE``.
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

from game import Board, Coord, DIRECTIONS, other

# --- настраиваемые «ручки» ---------------------------------------------------
WIN_SCORE = 10 ** 9            # вес мгновенной победы / вынужденной блокировки
ATTACK = 1.0                   # вес собственной угрозы
DEFENSE = 0.9                  # вес блокировки чужой угрозы (чуть меньше своего выигрыша)
CENTRALITY_SCALE = 0.5         # микро-бонус за близость к своим знакам (тай-брейк)

#: Вес окна в зависимости от того, сколько наших знаков там окажется
#: после нашего хода (``potential`` = знаков в окне + 1).
POTENTIAL_SCORE: Dict[int, float] = {2: 10.0, 3: 100.0, 4: 10_000.0}

#: Множитель «свободы» окна: чем больше в окне пустых клеток,
#: тем меньше оно значит (закрытая четвёрка страшнее открытой тройки).
OPEN_WEIGHT: Dict[int, float] = {1: 1.0, 2: 0.5, 3: 0.25, 4: 0.1, 5: 0.05, 6: 0.03}

#: Профили сложности.
DIFFICULTY: Dict[str, Dict[str, object]] = {
    # строго лучший ход, но выбирает случайно из пяти лучших — «ошибается по-человечески»
    "easy": {"radius": 1, "top_k": 5, "lookahead": False},
    "normal": {"radius": 2, "top_k": 1, "lookahead": False},
    # шире смотрим + страховка: не оставляем сопернику немедленную победу
    "hard": {"radius": 3, "top_k": 1, "lookahead": True},
}

LOOKAHEAD_TOP = 10             # сколько лучших ходов проверяет страховка режима hard
LOOKAHEAD_PENALTY = 0.05       # во столько раз дешевеет ход, оставляющий сопернику победу


# --- оценка одной клетки -----------------------------------------------------
def line_strength(board: Board, coord: Coord, player: str, win_len: Optional[int] = None) -> float:
    """Сила линии, которую создаст знак ``player`` в клетке ``coord``.

    По каждой из четырёх осей рассматриваются все окна длиной ``win_len``,
    содержащие ``coord``. Если в окне есть чужой знак — окно бесполезно.
    Иначе считаем, сколько наших знаков там окажется (``potential``), и
    сколько в окне пустых клеток (свобода окна).

    Силы разных осей складываются (это естественно награждает «вилки» —
    двойные угрозы), но сумма ограничена, чтобы не перебить мгновенную победу.

    Клетка ``coord`` должна быть пустой; если в ней уже стоит чужой знак,
    сила равна нулю.
    """
    win_len = win_len or board.win_len
    occupant = board.cells.get(coord)
    if occupant is not None and occupant != player:
        return 0.0

    x, y = coord
    total = 0.0

    for dx, dy in DIRECTIONS:
        best_for_axis = 0.0
        for start in range(-(win_len - 1), 1):
            empties = 0
            blocked = False
            for i in range(win_len):
                cx = x + (start + i) * dx
                cy = y + (start + i) * dy
                if (cx, cy) == coord:
                    empties += 1          # наша будущая клетка пока пуста
                    continue
                cell = board.cells.get((cx, cy))
                if cell is None:
                    empties += 1
                elif cell != player:
                    blocked = True
                    break
            if blocked:
                continue
            potential = win_len - empties + 1     # знаков станет после нашего хода
            if potential >= win_len:              # ход закрывает линию — победа
                return WIN_SCORE
            value = POTENTIAL_SCORE.get(potential, 0.0) * OPEN_WEIGHT.get(empties, 0.03)
            if value > best_for_axis:
                best_for_axis = value
        total += best_for_axis

    # Ограничиваем сумму, чтобы «вилка» не перебила мгновенную победу.
    return min(total, WIN_SCORE // 2)


def centrality_bonus(board: Board, coord: Coord, player: str) -> float:
    """Микро-бонус: ближе к своим знакам — чуть предпочтительнее (снимает ничьи)."""
    center = board.center_of_mass(player)
    if center is None:
        return 0.0
    cx, cy = center
    distance = max(abs(coord[0] - cx), abs(coord[1] - cy))
    return CENTRALITY_SCALE / (1.0 + distance)


def evaluate_move(
    board: Board,
    coord: Coord,
    me: str,
    opp: Optional[str] = None,
    win_len: Optional[int] = None,
) -> float:
    """Итоговая «сила» хода ``me`` в клетку ``coord``."""
    opp = opp or other(me)
    if board.is_winning_move(coord, me):
        return WIN_SCORE

    mine = line_strength(board, coord, me, win_len)
    enemy = line_strength(board, coord, opp, win_len)
    return ATTACK * mine + DEFENSE * enemy + centrality_bonus(board, coord, me)


def move_scores(board: Board, me: str, radius: int = 2) -> Dict[Coord, float]:
    """Оценки всех клеток-кандидатов (используется ИИ и оверлеем в интерфейсе)."""
    opp = other(me)
    return {
        coord: evaluate_move(board, coord, me, opp)
        for coord in board.candidates(radius)
    }


# --- выбор хода --------------------------------------------------------------
def _apply_lookahead(
    board: Board, scores: Dict[Coord, float], me: str, radius: int
) -> Dict[Coord, float]:
    """Режим hard: страховка от зевка.

    Проверяем лучшие ходы на один полуход вперёд: если после нашего хода
    соперник побеждает немедленно (а мы сами не выиграли), оценка хода
    умножается на ``LOOKAHEAD_PENALTY`` — такой ход почти всегда проигрывает
    более безопасному, но порядок остальных ходов не ломается.
    """
    opp = other(me)
    adjusted = dict(scores)
    leaders = sorted(scores.items(), key=lambda kv: -kv[1])[:LOOKAHEAD_TOP]
    for coord, score in leaders:
        if score >= WIN_SCORE:      # это наша мгновенная победа — она всегда лучшая
            continue
        board.place(coord, me)
        try:
            loses = not board.is_over and any(
                board.is_winning_move(c, opp) for c in board.candidates(radius)
            )
        finally:
            board.undo()
        if loses:
            adjusted[coord] = score * LOOKAHEAD_PENALTY
    return adjusted


def _rank_key(board: Board, coord: Coord, score: float) -> Tuple[float, int, int, int]:
    """Детерминированный тай-брейк: сила, затем «густота» вокруг, затем порядок."""
    return (-score, -board.neighbor_count(coord), coord[1], coord[0])


def rank_moves(
    board: Board,
    me: str,
    radius: int = 2,
    difficulty: str = "normal",
) -> List[Tuple[Coord, float]]:
    """Отсортированный список ``(клетка, сила хода)`` — от лучшей к худшей."""
    config = _config(difficulty)
    scores = move_scores(board, me, radius)
    if config["lookahead"]:
        scores = _apply_lookahead(board, scores, me, radius)
    return sorted(
        scores.items(), key=lambda kv: _rank_key(board, kv[0], kv[1])
    )


def _config(difficulty: str) -> Dict[str, object]:
    if difficulty not in DIFFICULTY:
        raise ValueError(
            f"Неизвестная сложность {difficulty!r}; доступно: {sorted(DIFFICULTY)}"
        )
    return DIFFICULTY[difficulty]


def choose_move(
    board: Board,
    me: Optional[str] = None,
    difficulty: str = "normal",
    radius: Optional[int] = None,
    rng: Optional[random.Random] = None,
) -> Coord:
    """Выбрать клетку с наибольшей силой хода.

    :param radius: переопределить радиус поиска кандидатов (по умолчанию из режима).
    :param rng: генератор случайных чисел — нужен только режиму ``easy`` и тестам.
    """
    if board.is_over:
        raise ValueError("Игра уже завершена")
    me = me or board.next_player
    if not board.cells:
        return (0, 0)                      # первый ход — в центр

    config = _config(difficulty)
    search_radius = radius if radius is not None else int(config["radius"])
    ranked = rank_moves(board, me, search_radius, difficulty)
    if not ranked:
        return (0, 0)

    top_k = min(int(config["top_k"]), len(ranked))
    if top_k > 1:
        picker = rng or random
        return picker.choice([coord for coord, _ in ranked[:top_k]])
    return ranked[0][0]
