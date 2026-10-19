"""Тесты графического интерфейса.

Модуль пропускается, если в текущем Python нет ``tkinter`` или нет дисплея
(например, тесты идут под Python 3.14 без пакета ``python-tk``).
"""

import unittest

try:
    import tkinter as tk
except Exception:                                    # pragma: no cover
    tk = None

from game import X


def _make_root():
    if tk is None:
        return None
    try:
        root = tk.Tk()
    except Exception:                                # pragma: no cover
        return None
    root.withdraw()          # окно не мешает и не мигает
    return root


@unittest.skipIf(_make_root() is None, "tkinter или графический дисплей недоступны")
class TestUi(unittest.TestCase):
    def setUp(self):
        import ui

        self.ui = ui
        self.root = _make_root()
        self.app = ui.TicTacToeApp(self.root)
        self.root.update()

    def tearDown(self):
        self.app._cancel_ai()
        self.root.destroy()

    # -------------------------------------------------------------- геометрия
    def test_screen_board_roundtrip(self):
        for coord in ((0, 0), (5, -3), (-12, 7)):
            sx, sy = self.app.to_screen(*coord)
            self.assertEqual(self.app.to_board(sx, sy), coord)

    def test_zoom_keeps_point_under_cursor(self):
        app = self.app
        sx, sy = app.to_screen(0, 0)
        app._zoom_at(1.5, sx, sy)
        self.assertAlmostEqual(app.cell, self.ui.DEFAULT_CELL * 1.5, places=6)
        self.assertEqual(app.to_board(*app.to_screen(0, 0)), (0, 0))
        for _ in range(50):
            app._zoom_at(2.0, 10, 10)
        self.assertLessEqual(app.cell, self.ui.MAX_CELL)
        for _ in range(50):
            app._zoom_at(0.5, 10, 10)
        self.assertGreaterEqual(app.cell, self.ui.MIN_CELL)

    def test_center_view_puts_origin_in_the_middle(self):
        app = self.app
        app.new_game()
        self.root.update()
        middle = (self.root.winfo_width() or 0) / 2
        if middle > 1:                               # проверяем только с реальным размером
            coord = app.to_board(middle, middle)
            self.assertLessEqual(max(abs(coord[0]), abs(coord[1])), 1)

    # -------------------------------------------------------------- ходы
    def test_click_places_mark_human_vs_human(self):
        app = self.app
        app.mode_var.set("Человек – человек")
        app.new_game()
        app._handle_click(*app.to_screen(2, 3))
        self.assertEqual(app.board.get((2, 3)), X)
        self.assertEqual(app.board.move_count, 1)

    def test_click_on_occupied_cell_is_ignored(self):
        app = self.app
        app.mode_var.set("Человек – человек")
        app.new_game()
        app._handle_click(*app.to_screen(0, 0))
        app._handle_click(*app.to_screen(0, 0))
        self.assertEqual(app.board.move_count, 1)

    def test_ai_replies_after_human_move(self):
        app = self.app
        app.mode_var.set("Человек – ИИ")
        app.ai_side_var.set("O")
        app.new_game()
        self.assertTrue(app.is_human_turn())
        self.assertFalse(app.is_ai_turn())
        app._handle_click(*app.to_screen(0, 0))
        self.assertTrue(app.is_ai_turn())
        app._ai_move()
        self.assertEqual(app.board.move_count, 2)
        self.assertIsNotNone(app.last_ai_ms)
        self.assertTrue(app.is_human_turn())

    def test_ai_plays_first_when_it_is_x(self):
        app = self.app
        app.mode_var.set("Человек – ИИ")
        app.ai_side_var.set("X")
        app.new_game()
        self.assertTrue(app.is_ai_turn())
        app._ai_move()
        self.assertEqual(app.board.get((0, 0)), X)

    def test_ai_does_not_move_for_human_in_human_mode(self):
        app = self.app
        app.mode_var.set("Человек – человек")
        app.new_game()
        self.assertFalse(app.is_ai_turn())
        self.assertIsNone(app._ai_job)

    def test_undo_rolls_back_the_pair(self):
        app = self.app
        app.mode_var.set("Человек – ИИ")
        app.ai_side_var.set("O")
        app.new_game()
        app._handle_click(*app.to_screen(0, 0))
        app._ai_move()
        app._handle_click(*app.to_screen(3, 3))
        app._ai_move()
        self.assertEqual(app.board.move_count, 4)
        app.undo()
        self.assertEqual(app.board.move_count, 2)
        self.assertTrue(app.is_human_turn())

    def test_pause_stops_autoplay(self):
        app = self.app
        app.mode_var.set("ИИ – ИИ")
        app.new_game()
        app._cancel_ai()
        app.toggle_pause()
        self.assertTrue(app.paused)
        app.schedule_ai()
        self.assertIsNone(app._ai_job)
        app.toggle_pause()
        self.assertFalse(app.paused)

    # -------------------------------------------------------------- отрисовка
    def test_win_is_detected_and_drawn(self):
        app = self.app
        app.mode_var.set("Человек – человек")
        app.win_len_var.set(3)
        app.new_game()
        for coord in ((0, 0), (0, 5), (1, 0), (1, 5), (2, 0)):
            app._handle_click(*app.to_screen(*coord))
        self.assertEqual(app.board.winner, X)
        self.assertEqual(len(app.board.winning_line), 3)
        app.redraw()
        self.assertIn("Победили X", app.status_var.get())

    def test_eval_overlay_scores(self):
        app = self.app
        app.mode_var.set("Человек – человек")
        app.new_game()
        app._handle_click(*app.to_screen(0, 0))
        scores = app.eval_scores()
        self.assertTrue(scores)
        self.assertNotIn((0, 0), scores)             # занятые клетки не оцениваются
        app.show_eval_var.set(True)
        app.redraw()

    def test_draw_by_move_limit(self):
        app = self.app
        app.mode_var.set("Человек – человек")
        app.max_moves_var.set(2)
        app.new_game()
        app._handle_click(*app.to_screen(0, 0))
        app._handle_click(*app.to_screen(1, 1))
        self.assertTrue(app.board.is_draw)
        self.assertIn("Ничья", app.status_var.get())
        app.redraw()


if __name__ == "__main__":                           # pragma: no cover
    unittest.main()
