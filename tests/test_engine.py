import copy
import importlib
import json
import unittest


def adjacent(point, size=3):
    result = []
    for axis in range(4):
        for step in (-1, 1):
            candidate = list(point)
            candidate[axis] += step
            if 0 <= candidate[axis] < size:
                result.append(tuple(candidate))
    return result


def ko_setup():
    return {
        (0, 0, 0, 0): 2,
        (0, 1, 0, 0): 1,
        (0, 0, 1, 0): 1,
        (0, 0, 0, 1): 1,
        (2, 0, 0, 0): 2,
        (1, 1, 0, 0): 2,
        (1, 0, 1, 0): 2,
        (1, 0, 0, 1): 2,
    }


class EngineTests(unittest.TestCase):
    def setUp(self):
        try:
            engine = importlib.import_module("engine")
        except ModuleNotFoundError:
            self.fail("The four-dimensional rule engine is not implemented yet")
        self.Game = engine.Game
        self.IllegalMove = engine.IllegalMove

    def test_neighbors_use_all_four_axes_without_wrap_or_diagonals(self):
        game = self.Game()
        self.assertEqual(set(game.neighbors((1, 1, 1, 1))), {
            (0, 1, 1, 1), (2, 1, 1, 1),
            (1, 0, 1, 1), (1, 2, 1, 1),
            (1, 1, 0, 1), (1, 1, 2, 1),
            (1, 1, 1, 0), (1, 1, 1, 2),
        })
        self.assertEqual(set(game.neighbors((0, 0, 0, 0))), {
            (1, 0, 0, 0), (0, 1, 0, 0),
            (0, 0, 1, 0), (0, 0, 0, 1),
        })

    def test_flat_board_x_is_fastest_coordinate(self):
        for point, index in [((1, 0, 0, 0), 1), ((0, 1, 0, 0), 3),
                             ((0, 0, 1, 0), 9), ((0, 0, 0, 1), 27)]:
            with self.subTest(point=point):
                game = self.Game(setup={point: 1})
                self.assertEqual(game.to_dict()["board"][index], 1)

    def test_group_connects_across_w_and_counts_unique_liberties(self):
        game = self.Game(setup={(0, 0, 0, 0): 1, (0, 0, 0, 1): 1})
        stones, liberties = game.group((0, 0, 0, 0))
        self.assertEqual(stones, {(0, 0, 0, 0), (0, 0, 0, 1)})
        self.assertEqual(liberties, {
            (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0),
            (1, 0, 0, 1), (0, 1, 0, 1), (0, 0, 1, 1), (0, 0, 0, 2),
        })
        self.assertEqual(game.group((2, 2, 2, 2)), (set(), set()))

    def test_shared_liberty_is_counted_only_once(self):
        game = self.Game(setup={(0, 0, 0, 0): 1, (1, 0, 0, 0): 1, (1, 1, 0, 0): 1})
        stones, liberties = game.group((0, 0, 0, 0))
        self.assertEqual(len(stones), 3)
        self.assertEqual(len(liberties), 10)
        self.assertIn((0, 1, 0, 0), liberties)

    def test_cross_slice_connected_block_is_captured_as_one_group(self):
        victims = {(1, 1, 1, 1), (1, 1, 2, 1)}
        final_liberty = (1, 1, 2, 2)
        surround = {p for stone in victims for p in adjacent(stone)} - victims - {final_liberty}
        setup = {p: 1 for p in surround}
        setup.update({p: 2 for p in victims})
        game = self.Game(setup=setup)
        self.assertEqual(set(game.play(final_liberty)), victims)
        self.assertEqual(game.to_dict()["captures"], {"black": 2, "white": 0})
        for point in victims:
            self.assertEqual(game.group(point), (set(), set()))

    def test_suicide_rejection_has_no_side_effects(self):
        game = self.Game(setup={p: 2 for p in adjacent((0, 0, 0, 0))})
        before = game.to_dict()
        with self.assertRaises(self.IllegalMove):
            game.play((0, 0, 0, 0))
        self.assertEqual(game.to_dict(), before)
        self.assertFalse(game.undo())

    def test_enemy_capture_happens_before_own_liberty_check(self):
        target = (0, 0, 0, 0)
        victim = (1, 0, 0, 0)
        setup = {p: 2 for p in adjacent(target)}
        setup.update({p: 1 for p in adjacent(victim) if p != target})
        game = self.Game(setup=setup)
        self.assertEqual(game.play(target), [victim])
        self.assertEqual(game.group(target)[1], {victim})

    def test_occupied_and_out_of_bounds_moves_do_not_change_game(self):
        game = self.Game(setup={(0, 0, 0, 0): 1})
        before = game.to_dict()
        for point in [(0, 0, 0, 0), (-1, 0, 0, 0), (3, 0, 0, 0),
                      (0, 0, 0), (True, 0, 0, 0), "0000", None]:
            with self.subTest(point=point), self.assertRaises(self.IllegalMove):
                game.play(point)
            self.assertEqual(game.to_dict(), before)

    def test_position_superko_rejects_recapture_even_after_passes(self):
        game = self.Game(setup=ko_setup())
        game.play((1, 0, 0, 0))
        with self.assertRaises(self.IllegalMove):
            game.play((0, 0, 0, 0))
        game.pass_turn()
        game.pass_turn()
        game.resume()
        before = game.to_dict()
        with self.assertRaises(self.IllegalMove):
            game.play((0, 0, 0, 0))
        self.assertEqual(game.to_dict(), before)

    def test_superko_remembers_positions_beyond_immediate_previous_move(self):
        corners = [(0, 0, 0, 0), (0, 4, 4, 0), (4, 4, 4, 4)]
        vacancies = [(1, 0, 0, 0), (1, 4, 4, 0), (3, 4, 4, 4)]
        setup = {}
        for corner, vacancy, color in zip(corners, vacancies, (2, 1, 2)):
            setup[corner] = color
            setup.update({p: 3 - color for p in adjacent(corner, 5) if p != vacancy})
            setup.update({p: color for p in adjacent(vacancy, 5) if p != corner})
        game = self.Game(size=5, setup=setup)
        for point in [vacancies[0], vacancies[1], vacancies[2], corners[0], corners[1]]:
            game.play(point)
        before = game.to_dict()
        with self.assertRaises(self.IllegalMove):
            game.play(corners[2])
        self.assertEqual(game.to_dict(), before)

    def test_undo_restores_capture_turn_and_allows_replaying_move(self):
        game = self.Game(setup=ko_setup())
        before = game.to_dict()
        game.play((1, 0, 0, 0))
        self.assertTrue(game.undo())
        self.assertEqual(game.to_dict(), before)
        self.assertEqual(game.play((1, 0, 0, 0)), [(0, 0, 0, 0)])

    def test_two_passes_finish_and_undo_reopens_game(self):
        game = self.Game()
        game.pass_turn()
        self.assertFalse(game.to_dict()["finished"])
        game.pass_turn()
        self.assertTrue(game.to_dict()["finished"])
        for operation in [lambda: game.play((0, 0, 0, 0)), game.pass_turn, game.resign]:
            with self.assertRaises(self.IllegalMove):
                operation()
        self.assertTrue(game.undo())
        self.assertFalse(game.to_dict()["finished"])
        self.assertEqual(game.to_dict()["pass_count"], 1)

    def test_move_breaks_consecutive_passes(self):
        game = self.Game()
        game.pass_turn()
        game.play((0, 0, 0, 0))
        game.pass_turn()
        self.assertFalse(game.to_dict()["finished"])
        self.assertEqual(game.to_dict()["pass_count"], 1)

    def test_score_flood_fill_uses_4d_area_and_neutral_empty_regions(self):
        game = self.Game()
        self.assertEqual(game.to_dict()["score"]["neutral"], 81)
        self.assertEqual(game.to_dict()["score"]["white"], 0.5)
        black = self.Game(setup={(0, 0, 0, 0): 1})
        score = black.to_dict()["score"]
        self.assertEqual((score["black"], score["black_stones"], score["black_territory"]), (81, 1, 80))
        mixed = self.Game(setup={(0, 0, 0, 0): 1, (2, 2, 2, 2): 2})
        score = mixed.to_dict()["score"]
        self.assertEqual((score["black"], score["white"], score["neutral"]), (1, 1.5, 79))
        self.assertEqual(len(score["territory"]), 81)

    def test_dead_selection_toggles_whole_4d_group_and_recalculates_score(self):
        group = {(0, 0, 0, 0), (0, 0, 0, 1)}
        game = self.Game(setup={p: 1 for p in group})
        with self.assertRaises(self.IllegalMove):
            game.toggle_dead((0, 0, 0, 0))
        game.pass_turn()
        game.pass_turn()
        game.toggle_dead((0, 0, 0, 0))
        self.assertEqual({tuple(p) for p in game.to_dict()["dead"]}, group)
        self.assertEqual(game.to_dict()["score"]["neutral"], 81)
        game.toggle_dead((0, 0, 0, 1))
        self.assertEqual(game.to_dict()["dead"], [])
        with self.assertRaises(self.IllegalMove):
            game.toggle_dead((2, 2, 2, 2))

    def test_resume_clears_dead_marks_and_is_undoable(self):
        game = self.Game(setup={(0, 0, 0, 0): 1})
        game.pass_turn()
        game.pass_turn()
        game.toggle_dead((0, 0, 0, 0))
        before = game.to_dict()
        game.resume()
        self.assertFalse(game.to_dict()["finished"])
        self.assertEqual(game.to_dict()["dead"], [])
        self.assertEqual(game.to_dict()["pass_count"], 0)
        self.assertTrue(game.undo())
        self.assertEqual(game.to_dict(), before)

    def test_resignation_remembers_losing_color_and_forbids_dead_marks(self):
        game = self.Game(turn=2)
        before = game.to_dict()
        game.resign()
        self.assertTrue(game.to_dict()["finished"])
        self.assertEqual(game.to_dict()["resigned"], 2)
        for operation in [game.resume, lambda: game.toggle_dead((0, 0, 0, 0))]:
            with self.assertRaises(self.IllegalMove):
                operation()
        self.assertTrue(game.undo())
        self.assertEqual(game.to_dict(), before)

    def test_setup_validates_types_bounds_and_surrounded_groups(self):
        invalid = [dict(size=True), dict(size=2), dict(size=6), dict(size=3.0),
                   dict(komi=True), dict(komi=float("nan")), dict(komi=float("inf")),
                   dict(komi=51), dict(komi=10 ** 1000), dict(turn=True), dict(turn=0),
                   dict(setup=[]), dict(setup={(3, 0, 0, 0): 1}),
                   dict(setup={(0, 0, 0, 0): True}), dict(setup={(0, 0, 0, 0): 0})]
        setup = {p: 2 for p in adjacent((0, 0, 0, 0))}
        setup[(0, 0, 0, 0)] = 1
        invalid.append(dict(setup=setup))
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.Game(**kwargs)

    def test_json_save_replay_preserves_state_and_undo_history(self):
        game = self.Game(setup=ko_setup(), komi=-2)
        game.play((1, 0, 0, 0))
        game.pass_turn()
        game.pass_turn()
        game.toggle_dead((2, 0, 0, 0))
        restored = self.Game.from_data(json.loads(json.dumps(game.export_data())))
        self.assertEqual(restored.to_dict(), game.to_dict())
        while game.undo():
            self.assertTrue(restored.undo())
            self.assertEqual(restored.to_dict(), game.to_dict())
        self.assertFalse(restored.undo())

    def test_export_after_undo_contains_only_surviving_actions(self):
        game = self.Game()
        game.play((0, 0, 0, 0))
        game.play((2, 2, 2, 2))
        game.undo()
        restored = self.Game.from_data(game.export_data())
        self.assertEqual(restored.to_dict(), game.to_dict())
        self.assertEqual(len(restored.to_dict()["moves"]), 1)

    def test_import_preserves_dead_marks_before_undoing_resume(self):
        game = self.Game(setup={(0, 0, 0, 0): 1})
        game.pass_turn()
        game.pass_turn()
        game.toggle_dead((0, 0, 0, 0))
        before = game.to_dict()
        game.resume()
        restored = self.Game.from_data(game.export_data())
        self.assertTrue(restored.undo())
        self.assertEqual(restored.to_dict(), before)

    def test_save_validation_rejects_bad_root_fields_and_illegal_replay(self):
        valid = self.Game().export_data()
        invalid = [None, [], {}, {**valid, "size": True}, {**valid, "version": True},
                   {**valid, "komi": "0.5"}, {**valid, "turn": 0},
                   {**valid, "unexpected": 1}, {**valid, "moves": [None]},
                   {**valid, "moves": [{"color": 2, "action": "pass", "point": None}]},
                   {**valid, "moves": [{"color": 1, "action": "move", "point": [True, 0, 0, 0]}]},
                   {**valid, "moves": [{"color": 1, "action": "pass", "point": [0, 0, 0, 0]}]},
                   {**valid, "dead": [[0, 0, 0, 0]]},
                   {**valid, "setup": [{"color": 1, "point": [0, 0, 0, 0]}, {"color": 2, "point": [0, 0, 0, 0]}]},
                   {**valid, "moves": [{"color": 1, "action": "pass", "point": None}] * 3001}]
        duplicate = copy.deepcopy(valid)
        duplicate["moves"] = [{"color": 1, "action": "move", "point": [0, 0, 0, 0]},
                              {"color": 2, "action": "move", "point": [0, 0, 0, 0]}]
        invalid.append(duplicate)
        for data in invalid:
            if type(data) is dict and type(data.get("moves")) is list:
                data["dead_history"] = [[] for _ in data["moves"]]
            with self.subTest(data=str(data)[:160]), self.assertRaises(ValueError):
                self.Game.from_data(data)

    def test_save_dead_marks_must_contain_complete_groups(self):
        game = self.Game(setup={(0, 0, 0, 0): 1, (0, 0, 0, 1): 1})
        game.pass_turn()
        game.pass_turn()
        data = game.export_data()
        data["dead"] = [[0, 0, 0, 0]]
        with self.assertRaises(ValueError):
            self.Game.from_data(data)

    def test_save_requires_json_array_coordinates(self):
        game = self.Game(setup={(0, 0, 0, 0): 1})
        setup_data = game.export_data()
        setup_data["setup"][0]["point"] = (0, 0, 0, 0)
        move_data = self.Game().export_data()
        move_data["moves"] = [{"color": 1, "action": "move", "point": (0, 0, 0, 0)}]
        move_data["dead_history"] = [[]]
        game.pass_turn()
        game.pass_turn()
        dead_data = game.export_data()
        dead_data["dead"] = [(0, 0, 0, 0)]
        for data in [setup_data, move_data, dead_data]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.Game.from_data(data)

    def test_invalid_dead_history_and_tampered_superko_replay_are_rejected(self):
        game = self.Game(setup=ko_setup())
        game.play((1, 0, 0, 0))
        data = game.export_data()
        tampered = copy.deepcopy(data)
        tampered["moves"].append({"color": 2, "action": "move", "point": [0, 0, 0, 0]})
        tampered["dead_history"].append([])
        wrong_count = copy.deepcopy(data)
        wrong_count["dead_history"] = []
        active_dead = copy.deepcopy(data)
        active_dead["dead_history"][0] = [[0, 0, 0, 0]]
        for invalid in [tampered, wrong_count, active_dead]:
            with self.subTest(data=invalid), self.assertRaises(ValueError):
                self.Game.from_data(invalid)


if __name__ == "__main__":
    unittest.main()
