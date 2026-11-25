from importlib.util import find_spec
from unittest import TestCase, skipUnless


@skipUnless(find_spec("panda3d"), "3D tests require Panda3D")
class GuardClientTests(TestCase):
    @classmethod
    def setUpClass(cls):
        from panda3d.core import ConfigPageManager, loadPrcFileData
        from frostfall.guard3d import GuardZone3D

        config = loadPrcFileData("Guard tests", "win-size 1100 720\nwindow-type offscreen\n"
                                               "audio-library-name null\nnotify-level error")
        cls.addClassCleanup(ConfigPageManager.getGlobalPtr().deleteExplicitPage, config)
        cls.game = GuardZone3D("offscreen", audio_enabled=False)
        cls.addClassCleanup(cls.game.destroy)

    def setUp(self):
        self.game.local = True
        self.game.arena_mode = False
        self.game.motion = True
        self.game.launch(610830, 0)
        self.game.update(.2)

    def test_choosing_defender_updates_preview_without_committing(self):
        game = self.game
        before = game.state
        target = next(iter(game.current_actions()))
        game.pick(target)
        self.assertIs(game.state, before)
        self.assertEqual(game.phase, "attacker")
        self.assertEqual(game.draft_board.positions[1], target)
        game.update(0)
        self.assertFalse(game.arena.guard_markers[target][3].isHidden())
        game.undo_order()
        self.assertEqual(game.phase, "defender")
        self.assertIs(game.state, before)
        game.hold()
        self.assertEqual(game.phase, "attacker")
        self.assertIs(game.draft_board, before)

    def test_attacker_click_commits_and_shows_the_crack_after_arrival(self):
        game = self.game
        target = next(iter(game.current_actions()))
        game.pick(target)
        game.pick(18)
        self.assertEqual(game.state.active, 1)
        self.assertEqual(game.board_state().positions[1], target)
        self.assertIn(18, game.state.cracked)
        game.update(game.delay+.03)
        self.assertTrue(game.arena.guard_markers[18][2].isHidden())
        game.update(game.delay+.03)
        self.assertEqual(game.phase, "defender")
        self.assertFalse(game.arena.guard_markers[18][2].isHidden())
        self.assertFalse(game.arena.tiles[17].root.isHidden())

    def test_menu_runs_the_minimax_opponent_through_a_reply(self):
        game = self.game
        game.home()
        game.update(0)
        x, y, width, height = game.hud.buttons[0].area
        self.assertTrue(game.hud.handle_click((x+width/2, y+height/2)))
        self.assertEqual(game.controllers, ("Human", "Minimax"))
        game.motion = False
        game.update(.2)
        game.hold()
        game.pick(next(iter(game.current_actions())))
        game.update(.2)
        game.future.result(timeout=8)
        game.update(.2)
        self.assertEqual(game.stats[1][0], 1)
        self.assertEqual(game.team, 0)
