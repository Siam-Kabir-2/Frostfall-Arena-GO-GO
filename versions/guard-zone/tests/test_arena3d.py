"""Exercise the 3D presentation when Panda3D is installed."""

from importlib.util import find_spec
from dataclasses import replace
from random import Random
from unittest import TestCase, skipUnless

from frostfall.rules import Action, OPENING, choices


@skipUnless(find_spec("panda3d"), "3D tests require Panda3D")
class Arena3DTests(TestCase):
    @classmethod
    def setUpClass(cls):
        from panda3d.core import loadPrcFileData
        from frostfall.client3d import Frostfall3D

        config = loadPrcFileData("3D tests", "win-size 1100 720\nwindow-type offscreen\n"
                                            "audio-library-name null\nnotify-level error")
        cls.addClassCleanup(cls.remove_config, config)
        cls.game = Frostfall3D("offscreen", audio_enabled=False)
        cls.addClassCleanup(cls.game.destroy)

    @staticmethod
    def remove_config(config):
        from panda3d.core import ConfigPageManager
        ConfigPageManager.getGlobalPtr().deleteExplicitPage(config)

    def setUp(self):
        self.game.home()
        self.game.local = True
        self.game.adventure = True
        self.game.arena_mode = False
        self.game.motion = False
        self.game.launch(610830, 0)
        self.game.update(.2)

    def test_projected_tile_centers_pick_correctly_in_each_view(self):
        from panda3d.core import Point2
        from frostfall.stage3d import TOP, center

        game = self.game
        for overhead in (False, True):
            game.overhead = overhead
            game.update(0)
            for cell in range(64):
                pointer = Point2()
                self.assertTrue(game.lens.project(game.cam.getRelativePoint(game.render, center(cell)), pointer))
                self.assertEqual(game.arena.pick(game.cam, game.lens, pointer), cell)
            cell = game.state.positions[0]
            pointer = Point2()
            game.lens.project(game.cam.getRelativePoint(game.render, center(cell, TOP + .68)), pointer)
            self.assertEqual(game.arena.pick(game.cam, game.lens, pointer, game.state.positions), cell)

    def test_match_hud_blocks_controls_without_covering_open_water(self):
        hud = self.game.hud
        self.assertFalse(hud.contains((5, 42*hud.s)))
        self.assertFalse(hud.contains((hud.w*.5, hud.h-5)))
        x, y, w, h = hud.blocked[-3]
        self.assertTrue(hud.contains((x+w*.5, y+h*.5)))
        self.assertFalse(hud.contains((x+w+5*hud.s, y+h*.5)))
        for button in hud.buttons:
            x, y, w, h = button.area
            self.assertTrue(hud.contains((x+w*.5, y+h*.5)))

    def test_human_move_animates_then_opens_the_next_turn(self):
        from frostfall.stage3d import BITE_LENGTH, FIRST_BITE, center

        game = self.game
        game.motion = True
        fish = list(game.state.fish)
        fish[18] = 3
        game.state = replace(game.state, fish=tuple(fish))
        game.arena.sync(game.state, restart=True)
        game.number(1)
        game.aim(0, 1)
        game.update(0)
        self.assertIn("+3 fish", game.move_hint()[0])
        game.confirm()
        self.assertEqual(game.state.positions[0], 18)
        self.assertFalse(game.actionable)
        self.assertIsNotNone(game.arena.moving)
        self.assertFalse(game.arena.tiles[17].root.isHidden())
        meal = game.arena.meal
        self.assertEqual(len(meal.fish), 3)
        self.assertEqual(game.state.scores[0], 3)
        first_fish, start, *_ = meal.fish[0]
        travel_time = game.arena.moving[5]
        game.update(travel_time / 2)
        self.assertLess(meal.age, 0)
        self.assertEqual(first_fish.getPos(), start)
        game.update(travel_time / 2)
        self.assertIsNone(game.arena.moving)
        game.update(FIRST_BITE + BITE_LENGTH * .5)
        self.assertAlmostEqual(game.arena.pieces[0].getX(), center(18).x)
        self.assertGreater(first_fish.getZ(), start.z + .2)
        self.assertGreater(game.arena.rigs[0].jaw.getP(), 0)
        game.update(BITE_LENGTH * .5 + .01)
        self.assertTrue(first_fish.isHidden())
        self.assertFalse(meal.fish[1][0].isHidden())
        game.update(game.delay + .15)
        self.assertIsNone(game.arena.meal)
        self.assertTrue(first_fish.isEmpty())
        self.assertEqual(game.arena.rigs[0].jaw.getP(), 0)
        self.assertIsNone(game.arena.moving)
        self.assertTrue(game.arena.tiles[17].root.isHidden())
        self.assertFalse(game.arena.tiles[18].root.isHidden())
        self.assertEqual(game.arena.tiles[18].value, 0)
        self.assertTrue(game.actionable)

    def test_no_move_shows_winner_screen(self):
        game = self.game
        ice = {*OPENING, 18, 19}
        game.state = replace(game.state, adventure=False, fish=tuple(int(cell in ice) for cell in range(64)))
        game.arena.sync(game.state, restart=True)
        game.apply(Action("move", 0, 18))
        game.update(.25)
        self.assertEqual((game.modal, game.state.winner), ("result", 0))
        self.assertEqual(game.state.reason, "Azure has no legal move")

    def test_deepfin_miss_breaches_and_dives_in_the_same_hole(self):
        from frostfall.stage3d import SEAL_DURATION, SEAL_IMPACT, center

        game = self.game
        game.motion = True
        game.state = replace(game.state, active=1, round=3, turn=1, shark=0,
                             fish=(0,) + game.state.fish[1:])
        game.arena.sync(game.state, restart=True)
        game.apply(Action("move", 2, 23))
        self.assertEqual(game.banner[0], "DEEPFIN MISSES")
        start = -game.arena.seal_strike.age
        game.update(start + .49)
        seal = game.arena.seal
        self.assertFalse(seal.isHidden())
        apex = seal.getPos()
        self.assertAlmostEqual(apex.x, center(0).x)
        self.assertAlmostEqual(apex.y, center(0).y)
        self.assertTrue(game.arena.tiles[0].root.isHidden())
        game.update(SEAL_IMPACT - .49 + .06)
        self.assertAlmostEqual(seal.getX(), apex.x)
        self.assertAlmostEqual(seal.getY(), apex.y)
        self.assertLess(seal.getZ(), apex.z)
        game.update(SEAL_DURATION - SEAL_IMPACT)
        self.assertTrue(seal.isHidden())

    def test_threatened_floe_shakes_and_breaks_at_seal_impact(self):
        from frostfall.stage3d import SEAL_IMPACT, center

        game = self.game
        cell = 27
        fish = list(game.state.fish)
        fish[cell] = 2
        game.state = replace(game.state, active=1, round=3, turn=1, shark=cell, fish=tuple(fish))
        game.arena.sync(game.state, restart=True)
        floe = game.arena.tiles[cell]
        game.update(.11)
        self.assertAlmostEqual(floe.root.getX(), center(cell).x)
        self.assertFalse(floe.warning.isHidden())
        game.motion = True
        game.update(.072)
        self.assertNotAlmostEqual(floe.root.getX(), center(cell).x)
        game.apply(Action("move", 2, 23))
        start = -game.arena.seal_strike.age
        game.update(start + SEAL_IMPACT - .05)
        self.assertFalse(floe.warning.isHidden())
        self.assertFalse(floe.root.isHidden())
        self.assertEqual(floe.value, 2)
        game.update(.11)
        self.assertTrue(floe.warning.isHidden())
        self.assertAlmostEqual(floe.root.getX(), center(cell).x)
        self.assertEqual(floe.value, 0)
        game.update(.80)
        self.assertTrue(floe.root.isHidden())

    def test_local_adventure_reaches_results_and_rematches(self):
        game = self.game
        rng = Random(60)
        for _ in range(220):
            if game.state.over:
                break
            if game.delay > 0:
                game.update(.5)
                continue
            available = game.current_actions()
            if game.state.rescue < 0:
                action = rng.choice(choices(game.state))
                if action.kind == "pass":
                    game.update(.4)
                    continue
                game.select(action.penguin)
                if action.kind == "bait":
                    game.toggle_bait()
                elif action.kind == "brace":
                    game.toggle_brace()
            else:
                action = rng.choice(tuple(available.values()))
            before = game.state
            game.pick(action.target)
            self.assertIsNot(game.state, before, action)
            game.update(.4)
        self.assertTrue(game.state.over)
        self.assertEqual(game.modal, "result")
        game.rematch()
        self.assertEqual((game.state.seed, game.state.round, game.modal), (610830, 1, None))

    def test_ai_worker_finishes_a_turn_after_resume(self):
        game = self.game
        game.arena_mode = True
        game.difficulty = "Quick"
        game.launch(610830, 1)
        game.update(.04)
        self.assertGreater(game.delay, 0)
        self.assertIsNotNone(game.future)
        old = game.state
        game.toggle_pause()
        game.future.result(timeout=5)
        game.update(.2)
        self.assertIs(game.state, old)
        game.toggle_pause()
        game.update(.2)
        self.assertIsNot(game.state, old)
        self.assertEqual(game.stats[1][0], 1)
