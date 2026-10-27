import importlib
import itertools
import unittest

from engine import Game
from test_engine import ko_setup


class AITests(unittest.TestCase):
    def setUp(self):
        try:
            self.choose_move = importlib.import_module("ai").choose_move
        except ModuleNotFoundError:
            self.fail("The legal bounded AI is not implemented yet")

    def test_seeded_opening_is_legal_repeatable_and_does_not_mutate_game(self):
        game = Game(size=5)
        before = game.to_dict()
        move = self.choose_move(game, seed=1234)
        self.assertIsNotNone(move)
        self.assertEqual(move, self.choose_move(game, seed=1234))
        self.assertEqual(game.to_dict(), before)
        game.play(move)

    def test_ai_prioritizes_available_capture(self):
        game = Game(setup=ko_setup())
        before = game.to_dict()
        self.assertEqual(self.choose_move(game, seed=3), (1, 0, 0, 0))
        self.assertEqual(game.to_dict(), before)

    def test_ai_saves_own_group_in_atari(self):
        game = Game(setup={(0, 0, 0, 0): 1,
                           (0, 1, 0, 0): 2, (0, 0, 1, 0): 2, (0, 0, 0, 1): 2})
        self.assertEqual(self.choose_move(game, seed=1), (1, 0, 0, 0))

    def test_ai_respects_superko(self):
        game = Game(setup=ko_setup())
        game.play((1, 0, 0, 0))
        move = self.choose_move(game, seed=8)
        self.assertNotEqual(move, (0, 0, 0, 0))
        if move is not None:
            game.play(move)

    def test_ai_passes_instead_of_filling_own_eyes(self):
        holes = {(0, 0, 0, 0), (2, 2, 2, 2)}
        setup = {p: 1 for p in itertools.product(range(3), repeat=4) if p not in holes}
        game = Game(setup=setup)
        before = game.to_dict()
        self.assertIsNone(self.choose_move(game, seed=0))
        self.assertEqual(game.to_dict(), before)

    def test_ai_avoids_own_eye_when_other_moves_are_available(self):
        eye = (0, 0, 0, 0)
        game = Game(setup={(1, 0, 0, 0): 1, (0, 1, 0, 0): 1,
                           (0, 0, 1, 0): 1, (0, 0, 0, 1): 1})
        for seed in range(5):
            with self.subTest(seed=seed):
                move = self.choose_move(game, seed=seed)
                self.assertIsNotNone(move)
                self.assertNotEqual(move, eye)

    def test_ai_returns_pass_when_game_finished(self):
        game = Game()
        game.pass_turn()
        game.pass_turn()
        self.assertIsNone(self.choose_move(game, seed=1))

    def test_ai_returned_moves_remain_legal_through_a_sequence(self):
        game = Game()
        for number in range(40):
            move = self.choose_move(game, seed=number)
            if move is None:
                game.pass_turn()
            else:
                game.play(move)
            if game.finished:
                break


if __name__ == "__main__":
    unittest.main()
