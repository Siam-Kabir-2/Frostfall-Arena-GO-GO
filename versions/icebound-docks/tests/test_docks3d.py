from importlib.util import find_spec
from unittest import TestCase, skipUnless


@skipUnless(find_spec("panda3d"), "3D tests require Panda3D")
class DocksClientTests(TestCase):
    @classmethod
    def setUpClass(cls):
        from panda3d.core import ConfigPageManager, loadPrcFileData
        from frostfall.docks3d import IceboundDocks3D

        config = loadPrcFileData("Docks tests", "win-size 1100 720\nwindow-type offscreen\n"
                                               "audio-library-name null\nnotify-level error")
        cls.addClassCleanup(ConfigPageManager.getGlobalPtr().deleteExplicitPage, config)
        cls.game = IceboundDocks3D("offscreen", audio_enabled=False)
        cls.addClassCleanup(cls.game.destroy)

    def setUp(self):
        self.game.local = True
        self.game.arena_mode = False
        self.game.motion = True
        self.game.launch(42, 0)
        self.game.update(.2)

    def test_preview_undo_confirmation_and_ordered_animation(self):
        game = self.game
        before = game.state
        game.pick(33)
        self.assertEqual(game.phase, "attacker")
        self.assertIs(game.state, before)
        game.pick(25)
        self.assertEqual(game.phase, "ready")
        game.undo_order()
        self.assertEqual(game.phase, "attacker")
        game.pick(25)
        game.confirm()
        self.assertEqual(game.state.owners, (0, -1, -1))
        self.assertEqual(game.state.positions[:2], (25, 33))
        self.assertEqual(game.board_state().positions[:2], (9, 33))
        game.update(game.delay+.03)
        self.assertEqual(game.board_state().positions[:2], (25, 33))
        game.update(game.delay+.03)
        self.assertEqual(game.phase, "defender")
        self.assertEqual(game.team, 1)
        self.assertIsNone(game.animation_board)

    def test_menu_human_vs_ai_plays_a_paired_reply(self):
        game = self.game
        game.home()
        game.update(0)
        x, y, width, height = game.hud.buttons[0].area
        self.assertTrue(game.hud.handle_click((x+width/2, y+height/2)))
        self.assertEqual(game.controllers, ("Human", "Minimax"))
        game.motion = False
        game.update(.2)
        game.pick(33)
        game.pick(25)
        game.commit()
        game.update(.2)
        game.future.result(timeout=8)
        game.update(.2)
        self.assertEqual(game.stats[1][0], 1)
        self.assertEqual(game.team, 0)
