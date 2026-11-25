from dataclasses import replace
from random import Random
from unittest import TestCase

from frostfall.guard import (Turn, advance, attacker_moves, defender_moves, legal_turns,
                             new_match, slide, zones)
from frostfall.guard_ai import search
from frostfall.rules import Action, destinations


def board(positions):
    bare = frozenset((positions[0], positions[2]))
    return replace(new_match(47), positions=positions, empty_ice=bare,
                   fish=tuple(0 if cell in bare else 2 for cell in range(64)))


class GuardRulesTests(TestCase):
    def test_center_and_corners_have_the_expected_eight_way_zones(self):
        state = board((0, 27, 7, 63))
        self.assertEqual(zones(state), (frozenset({18, 19, 20, 26, 28, 34, 35, 36}),
                                        frozenset({54, 55, 62}), frozenset()))

    def test_guard_forbids_landing_without_stopping_a_glide(self):
        state = replace(board((56, 27, 17, 63)), active=1)
        legal = {action.target for action in attacker_moves(state)}
        self.assertTrue({18, 19, 20}.isdisjoint(legal))
        self.assertIn(21, legal)
        blocked = replace(state, positions=(56, 27, 25, 63))
        self.assertNotIn(28, tuple(destinations(blocked, 2)))
        inside = replace(state, positions=(56, 27, 18, 63))
        self.assertIn(Action("move", 2, 16), attacker_moves(inside))

    def test_rival_defender_contests_a_rich_tile_in_time_for_its_attacker(self):
        state = replace(board((44, 27, 12, 30)), active=1)
        step = Action("move", 3, 29)
        catch = Action("move", 2, 28)
        self.assertNotIn(catch, attacker_moves(state))
        self.assertIn(step, defender_moves(state))
        middle = slide(state, step)
        self.assertIn(28, zones(middle)[2])
        self.assertIn(catch, attacker_moves(middle))
        self.assertIn(Action("move", 0, 28), attacker_moves(replace(middle, active=0)))
        after, _ = advance(state, Turn(step, catch))
        self.assertEqual(after.scores, (0, 2))
        self.assertEqual(after.cracked, frozenset({28}))

    def test_only_attacker_takes_fish_and_only_cracked_departure_sinks(self):
        state = board((17, 41, 22, 46))
        step = Action("move", 1, 42)
        catch = Action("move", 0, 18)
        after, _ = advance(state, Turn(step, catch))
        self.assertEqual(after.scores, (2, 0))
        self.assertEqual(after.fish[42], 2)
        self.assertTrue(after.has_ice(17))
        self.assertTrue(after.has_ice(18))
        self.assertEqual(after.cracked, frozenset({18}))
        moved, _ = advance(replace(after, active=0), Turn(None, Action("move", 0, 19)))
        self.assertFalse(moved.has_ice(18))
        self.assertTrue(moved.has_ice(41))
        self.assertEqual(moved.cracked, frozenset({19}))

    def test_defender_can_step_onto_a_contested_tile_but_never_an_occupied_one(self):
        state = board((17, 25, 22, 27))
        self.assertIn(26, zones(state)[2])
        self.assertIn(Action("move", 1, 26), defender_moves(state))
        self.assertNotIn(Action("move", 1, 27), defender_moves(slide(state, Action("move", 1, 26))))

    def test_ai_returns_a_legal_pair_and_random_games_finish(self):
        state = new_match(47)
        for algorithm in ("Minimax", "MCTS"):
            self.assertIn(search(state, algorithm, "Quick").action, legal_turns(state))
        rng = Random(883)
        for seed in range(10):
            state = new_match(seed)
            for _ in range(48):
                state, _ = advance(state, rng.choice(legal_turns(state)))
                if state.over:
                    break
            self.assertTrue(state.over)
