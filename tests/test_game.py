"""Тесты модели поля (``game.py``)."""

import unittest

from game import O, X, Board, other


class TestBoardBasics(unittest.TestCase):
    def test_empty_board(self):
        board = Board(win_len=5)
        self.assertEqual(board.move_count, 0)
        self.assertEqual(board.next_player, X)
        self.assertIsNone(board.last_move)
        self.assertFalse(board.is_over)
        self.assertEqual(board.candidates(2), {(0, 0)})

    def test_other(self):
        self.assertEqual(other(X), O)
        self.assertEqual(other(O), X)

    def test_place_and_turn_order(self):
        board = Board(win_len=5)
        self.assertEqual(board.place((0, 0)), X)
        self.assertEqual(board.place((1, 0)), O)
        self.assertEqual(board.next_player, X)
        self.assertEqual(board.get((0, 0)), X)
        self.assertEqual(board.last_move, (1, 0))

    def test_place_on_occupied_raises(self):
        board = Board(win_len=5)
        board.place((0, 0), X)
        with self.assertRaises(ValueError):
            board.place((0, 0), O)

    def test_invalid_win_len(self):
        with self.assertRaises(ValueError):
            Board(win_len=2)

    def test_undo(self):
        board = Board(win_len=5)
        board.place((0, 0), X)
        board.place((1, 0), O)
        self.assertEqual(board.undo(), (1, 0))
        self.assertIsNone(board.get((1, 0)))
        self.assertEqual(board.next_player, O)
        self.assertEqual(board.undo(), (0, 0))
        self.assertIsNone(board.undo())

    def test_undo_clears_winner(self):
        board = Board(win_len=3)
        board.place((0, 0), X)
        board.place((5, 5), O)
        board.place((1, 0), X)
        board.place((6, 5), O)
        board.place((2, 0), X)
        self.assertEqual(board.winner, X)
        board.undo()
        self.assertIsNone(board.winner)
        self.assertEqual(board.winning_line, [])
        self.assertFalse(board.is_over)

    def test_move_limit_is_draw(self):
        board = Board(win_len=5, max_moves=2)
        board.place((0, 0), X)
        self.assertFalse(board.is_draw)
        board.place((1, 0), O)
        self.assertTrue(board.is_draw)
        self.assertTrue(board.is_over)
        with self.assertRaises(ValueError):
            board.place((2, 0), X)


class TestWinDetection(unittest.TestCase):
    def test_diagonal_win_on_negative_coordinates(self):
        board = Board(win_len=3)
        board.place((-7, -7), X)
        board.place((0, 0), O)
        board.place((-6, -6), X)
        board.place((0, 1), O)
        self.assertFalse(board.is_over)
        board.place((-5, -5), X)
        self.assertEqual(board.winner, X)
        self.assertEqual(board.winning_line, [(-7, -7), (-6, -6), (-5, -5)])

    def test_win_len_five_diagonal(self):
        board = Board(win_len=5)
        for i in range(4):
            board.place((i, -i), X)
            board.place((100 + i, 100), O)
        self.assertFalse(board.is_over)
        board.place((4, -4), X)
        self.assertEqual(board.winner, X)
        self.assertEqual(len(board.winning_line), 5)

    def test_is_winning_move_does_not_mutate(self):
        board = Board(win_len=5)
        for i in range(4):
            board.place((i, 0), X)
        self.assertTrue(board.is_winning_move((4, 0), X))
        self.assertTrue(board.is_winning_move((-1, 0), X))
        self.assertFalse(board.is_winning_move((5, 0), X))
        self.assertEqual(board.move_count, 4)
        self.assertIsNone(board.winner)

    def test_winning_cells_for(self):
        board = Board(win_len=5)
        for i in range(4):
            board.place((i, 0), X)
        self.assertEqual(board.winning_cells_for(X), {(4, 0), (-1, 0)})


class TestCandidates(unittest.TestCase):
    def test_radius_bounds(self):
        board = Board(win_len=5)
        board.place((0, 0), X)
        self.assertEqual(len(board.candidates(1)), 8)
        self.assertEqual(len(board.candidates(2)), 24)
        for coord in board.candidates(2):
            self.assertLessEqual(max(abs(coord[0]), abs(coord[1])), 2)
            self.assertNotIn(coord, board.cells)

    def test_far_coordinates(self):
        board = Board(win_len=5)
        board.place((10 ** 6, -10 ** 6), X)
        candidates = board.candidates(1)
        self.assertIn((10 ** 6 + 1, -10 ** 6), candidates)
        self.assertEqual(len(candidates), 8)

    def test_neighbor_count(self):
        board = Board(win_len=5)
        board.place((0, 0), X)
        board.place((1, 0), O)
        board.place((0, 1), X)
        self.assertEqual(board.neighbor_count((0, 0)), 2)
        self.assertEqual(board.neighbor_count((5, 5)), 0)

    def test_center_of_mass(self):
        board = Board(win_len=5)
        self.assertIsNone(board.center_of_mass(X))
        board.place((0, 0), X)
        board.place((4, 0), X)
        self.assertEqual(board.center_of_mass(X), (2.0, 0.0))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
