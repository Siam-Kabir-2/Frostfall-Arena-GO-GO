from dataclasses import replace
from importlib.util import find_spec
from random import Random
from unittest import TestCase, skipUnless

from duel import AIR, FISH, PATROL, ROUND_LIMIT, START_FISH, TO_AIR, State, advance, choices, count_fish


class DuelTests(TestCase):
    def test_every_school_is_within_round_trip_air_range(self):
        self.assertTrue(all(2*distance <= AIR for distance, fish in zip(TO_AIR,FISH) if fish))

    def test_both_penguins_draw_from_the_same_fish(self):
        state = replace(State(), positions=(2, 8))
        caught, _ = advance(state, 4)
        self.assertEqual(count_fish(caught.cargo[0]), 1)
        self.assertNotIn(4, choices(caught))
        moved = replace(caught, positions=(6, 8))
        visited, _ = advance(moved, 4)
        self.assertEqual(visited.cargo[1], 0)
        returned, _ = advance(replace(caught, positions=(2, 8), active=0), 0)
        self.assertEqual((returned.scores[0], returned.air[0], returned.cargo[0]), (1, AIR, 0))

    def test_deepfin_waits_for_both_moves_and_restores_lost_fish(self):
        target = PATROL[0]
        state = replace(State(), positions=(16, 3), cargo=(1<<4, 0), fish=START_FISH ^ (1<<4))
        first, _ = advance(state, target)
        self.assertEqual(first.positions[0], target)
        self.assertEqual(first.lives[0], 2)
        second, events = advance(first, 1)
        self.assertEqual((second.positions[0], second.lives[0], second.cargo[0]), (0,1,0))
        self.assertEqual(second.fish, START_FISH)
        self.assertTrue(any("Deepfin caught" in event for event in events))

    def test_out_of_air_restores_fish_but_can_bank_on_last_air(self):
        state = replace(State(), positions=(2,3), air=(1,AIR), cargo=(1<<4,0), fish=START_FISH ^ (1<<4))
        banked, _ = advance(state,0)
        self.assertEqual((banked.scores[0],banked.lives[0],banked.air[0]), (1,2,AIR))
        rescued, _ = advance(state,6)
        self.assertEqual((rescued.positions[0],rescued.lives[0],rescued.fish), (0,1,START_FISH))

    def test_random_games_end_and_never_duplicate_the_shared_fish(self):
        rng = Random(129)
        for seed in range(9):
            state = State(seed)
            for _ in range(2*ROUND_LIMIT):
                state, _ = advance(state,rng.choice(choices(state)))
                self.assertEqual(sum(state.scores)+count_fish(state.fish)+sum(map(count_fish,state.cargo)),sum(FISH))
                if state.over:
                    break
            self.assertTrue(state.over)

    def test_minimax_and_mcts_play_a_full_match(self):
        from duel_ai import search

        state = State()
        for _ in range(2*ROUND_LIMIT):
            move = search(state, ("Minimax", "MCTS")[state.active])
            self.assertGreater(move.effort,0)
            self.assertIn(move.action,choices(state))
            state, _ = advance(state,move.action)
            if state.over:
                break
        self.assertTrue(state.over)
        self.assertGreater(sum(state.scores),0)


@skipUnless(find_spec("panda3d"), "3D client needs Panda3D")
class SharedViewTests(TestCase):
    def test_projected_moves_and_computer_reply_share_one_scene(self):
        from panda3d.core import ConfigPageManager, loadPrcFileData
        from under_the_ice_3d import UnderIce3D

        config = loadPrcFileData("Duel test","win-size 1100 720\nwindow-type offscreen\naudio-library-name null\nnotify-level error")
        self.addCleanup(ConfigPageManager.getGlobalPtr().deleteExplicitPage,config)
        game = UnderIce3D("offscreen")
        self.addCleanup(game.destroy)
        game.number(2)
        game.update(.2)
        self.assertEqual(game.players,("Human","Minimax"))
        self.assertEqual(len(game.stage.swimmers),2)
        self.assertEqual(game.at(game.project(2)),2)
        game.mouse_pixels = lambda: game.project(2)
        game.click()
        self.assertEqual(game.state.positions[0],2)
        game.mouse_pixels = lambda: (-100,-100)
        game.update(.8)
        game.future.result(timeout=6)
        game.update(.1)
        self.assertEqual(game.state.active,0)
        self.assertGreater(game.effort[1],0)
