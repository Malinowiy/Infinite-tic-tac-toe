"""Тесты эвристики ИИ (``ai.py``)."""

import random
import unittest

import ai
from game import O, X, Board


def build(win_len=5, x_moves=(), o_moves=()):
    """Собрать позицию: все знаки X, затем все знаки O."""
    board = Board(win_len=win_len)
    for coord in x_moves:
        board.place(coord, X)
    for coord in o_moves:
        board.place(coord, O)
    return board


class TestLineStrength(unittest.TestCase):
    def test_empty_board_is_zero(self):
        board = Board(win_len=5)
        self.assertEqual(ai.line_strength(board, (3, 4), X), 0.0)

    def test_open_two_scores(self):
        # X: (0,0), (1,0). Ход в (2,0) даёт окно из трёх знаков с 3 пустыми
        # → potential 3, weight 0.25 → 100 * 0.25 = 25.
        board = build(win_len=5, x_moves=[(0, 0), (1, 0)])
        self.assertAlmostEqual(ai.line_strength(board, (2, 0), X), 25.0, places=6)

    def test_four_in_window_is_stronger_than_three(self):
        two = build(win_len=5, x_moves=[(0, 0), (1, 0)])
        three = build(win_len=5, x_moves=[(0, 0), (1, 0), (2, 0)])
        near_three = ai.line_strength(two, (2, 0), X)
        near_four = ai.line_strength(three, (3, 0), X)
        self.assertGreater(near_four, near_three)

    def test_opponent_marks_block_the_line(self):
        open_board = build(win_len=5, x_moves=[(0, 0), (1, 0)])
        closed_board = build(
            win_len=5, x_moves=[(0, 0), (1, 0)], o_moves=[(-1, 0), (3, 0)]
        )
        self.assertGreater(
            ai.line_strength(open_board, (2, 0), X),
            ai.line_strength(closed_board, (2, 0), X),
        )

    def test_occupied_foreign_cell_is_zero(self):
        board = build(win_len=5, x_moves=[(0, 0)], o_moves=[(1, 0)])
        self.assertEqual(ai.line_strength(board, (1, 0), X), 0.0)

    def test_cross_point_adds_directions(self):
        # Две открытые двойки, пересекающиеся в (0,0):
        # ход в (0,0) получает силу сразу по двум осям.
        board = build(win_len=5, x_moves=[(-2, 0), (-1, 0), (0, -2), (0, -1)])
        cross = ai.line_strength(board, (0, 0), X)
        single = ai.line_strength(board, (1, 0), X)
        self.assertGreater(cross, single)
        self.assertAlmostEqual(cross, 50.0, places=6)

    def test_gap_pattern_counts(self):
        # X: (0,0) и (2,0) — ход в (1,0) закрывает разрыв и даёт окно из трёх.
        board = build(win_len=5, x_moves=[(0, 0), (2, 0)])
        self.assertGreater(ai.line_strength(board, (1, 0), X), 0.0)


class TestEvaluateMove(unittest.TestCase):
    def test_winning_move_is_top_score(self):
        board = build(win_len=5, x_moves=[(0, 0), (1, 0), (2, 0), (3, 0)])
        self.assertEqual(ai.evaluate_move(board, (4, 0), X), ai.WIN_SCORE)

    def test_blocking_is_valuable(self):
        board = build(
            win_len=5, x_moves=[(10, 10)], o_moves=[(0, 0), (1, 0), (2, 0)]
        )
        blocking = ai.evaluate_move(board, (3, 0), X)
        neutral = ai.evaluate_move(board, (5, 5), X)
        self.assertGreater(blocking, neutral)
        # Соперник закрыл бы этим ходом открытую тройку: potential 4 → 10_000 * 0.5
        self.assertAlmostEqual(blocking, ai.DEFENSE * 5_000, delta=1.0)

    def test_immediate_threat_worth_a_full_win(self):
        # У O четыре в ряд: любой конец линии весит DEFENSE * WIN_SCORE.
        board = build(win_len=5, x_moves=[(10, 10)], o_moves=[(0, 0), (1, 0), (2, 0), (3, 0)])
        self.assertAlmostEqual(
            ai.evaluate_move(board, (4, 0), X), ai.DEFENSE * ai.WIN_SCORE, delta=1.0
        )

    def test_move_scores_cover_only_empty_candidates(self):
        board = build(win_len=5, x_moves=[(0, 0)], o_moves=[(1, 0)])
        scores = ai.move_scores(board, X, radius=1)
        self.assertEqual(set(scores), board.candidates(1))
        for coord in scores:
            self.assertNotIn(coord, board.cells)


class TestChooseMove(unittest.TestCase):
    def test_first_move_is_center(self):
        for difficulty in ai.DIFFICULTY:
            board = Board(win_len=5)
            self.assertEqual(ai.choose_move(board, X, difficulty=difficulty), (0, 0))

    def test_takes_immediate_win(self):
        board = build(
            win_len=5,
            x_moves=[(0, 0), (1, 0), (2, 0), (3, 0)],
            o_moves=[(0, 5), (1, 5), (2, 5), (3, 5)],
        )
        self.assertIn(ai.choose_move(board, X, difficulty="normal"), {(4, 0), (-1, 0)})

    def test_blocks_immediate_loss(self):
        board = build(
            win_len=5, x_moves=[(10, 10)], o_moves=[(0, 0), (1, 0), (2, 0), (3, 0)]
        )
        self.assertIn(ai.choose_move(board, X, difficulty="normal"), {(4, 0), (-1, 0)})

    def test_blocks_open_three(self):
        board = build(win_len=5, x_moves=[(10, 10)], o_moves=[(0, 0), (1, 0), (2, 0)])
        self.assertIn(ai.choose_move(board, X, difficulty="normal"), {(3, 0), (-1, 0)})

    def test_prefers_cross_point(self):
        board = build(
            win_len=5,
            x_moves=[(-2, 0), (-1, 0), (0, -2), (0, -1)],
            o_moves=[(10, 0), (0, 10), (10, 10), (20, 20)],
        )
        self.assertEqual(ai.choose_move(board, X, difficulty="normal"), (0, 0))

    def test_hard_takes_forced_win(self):
        # Открытая тройка X: любой её конец даёт открытую четвёрку,
        # то есть сразу две выигрышные клетки — такую угрозу не отбить.
        board = build(
            win_len=5,
            x_moves=[(0, 10), (1, 10), (2, 10)],
            o_moves=[(0, 0), (1, 0), (2, 0)],
        )
        self.assertIn(ai.choose_move(board, X, "hard"), {(-1, 10), (3, 10)})

    def test_hard_blocks_immediate_loss(self):
        board = build(
            win_len=5, x_moves=[(10, 10)], o_moves=[(0, 0), (1, 0), (2, 0), (3, 0)]
        )
        self.assertIn(ai.choose_move(board, X, "hard"), {(4, 0), (-1, 0)})

    def test_hard_move_is_empty_candidate(self):
        board = build(win_len=5, x_moves=[(0, 0), (1, 1)], o_moves=[(2, 2), (0, 1)])
        move = ai.choose_move(board, X, "hard")
        self.assertIn(move, board.candidates(3))

    def test_easy_mode_varies_its_choice(self):
        board = build(win_len=5, x_moves=[(10, 10)], o_moves=[(0, 0), (1, 0), (2, 0)])
        moves = {
            ai.choose_move(board, X, "easy", rng=random.Random(seed))
            for seed in range(20)
        }
        self.assertGreater(len(moves), 1)

    def test_unknown_difficulty_raises(self):
        board = build(win_len=5, x_moves=[(0, 0)])
        with self.assertRaises(ValueError):
            ai.choose_move(board, X, difficulty="impossible")

    def test_finished_game_raises(self):
        board = Board(win_len=3)
        board.place((0, 0), X)
        board.place((5, 5), O)
        board.place((1, 0), X)
        board.place((6, 5), O)
        board.place((2, 0), X)
        with self.assertRaises(ValueError):
            ai.choose_move(board, O)

    def test_far_coordinates(self):
        board = build(
            win_len=5, x_moves=[(10 ** 5, -10 ** 5)], o_moves=[(10 ** 5 + 1, -10 ** 5)]
        )
        move = ai.choose_move(board, X, difficulty="normal")
        self.assertIsInstance(move, tuple)
        self.assertLessEqual(max(abs(move[0] - 10 ** 5), abs(move[1] + 10 ** 5)), 3)

    def test_easy_mode_is_random_but_sane(self):
        board = build(
            win_len=5, x_moves=[(10, 10)], o_moves=[(0, 0), (1, 0), (2, 0)]
        )
        # даже «лёгкий» режим остаётся в пределах разумных клеток
        for seed in range(10):
            move = ai.choose_move(board, X, "easy", rng=random.Random(seed))
            self.assertIn(move, board.candidates(1) | board.candidates(2))

    def test_never_loses_to_random_player(self):
        """Свойство: против случайного игрока ИИ не проигрывает ни разу."""
        wins = 0
        for seed in range(12):
            rng = random.Random(seed)
            board = Board(win_len=3)
            while not board.is_over and board.move_count < 60:
                if board.next_player == X:
                    coord = ai.choose_move(board, X, "normal")
                else:
                    coord = rng.choice(sorted(board.candidates(2)))
                board.place(coord)
            self.assertNotEqual(board.winner, O, f"ИИ проиграл, seed={seed}\n{board}")
            if board.winner == X:
                wins += 1
        self.assertGreaterEqual(wins, 8, "ИИ должен побеждать случайного игрока почти всегда")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
