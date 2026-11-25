import os
from random import Random
from unittest import TestCase

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import pygame as pg

from frostfall.app import Game, OPTIONS
class ClientTests(TestCase):
    def setUp(self):
        self.game = Game(preferences=OPTIONS, initial_size=(1440, 900))
        self.addCleanup(self.game.close)

    def click(self, logical):
        game = self.game
        x, y = logical
        point = (round(game.viewport.left + x * game.viewport.width / game.width),
                 round(game.viewport.top + y * game.viewport.height / game.height))
        game.event(pg.event.Event(pg.MOUSEBUTTONDOWN, pos=point, button=1))

    def button(self, label):
        self.game.render()
        bounds = next(button.bounds for button in self.game.buttons if button.label == label)
        self.click(bounds.center)

    def key(self, key):
        self.game.event(pg.event.Event(pg.KEYDOWN, key=key, mod=0, unicode=""))

    def test_keyboard_selection_after_resize_and_rematch(self):
        game = self.game
        self.button("Play")
        self.button("Human vs AI")
        game.launch(610830, 0)
        self.assertEqual(game.controls, ("Human", "Human"))
        game.screen = pg.display.set_mode((760, 920), pg.RESIZABLE)
        game.event(pg.event.Event(pg.VIDEORESIZE, w=760, h=920))
        game.time = 1
        game.render()
        self.assertTrue(game.compact)
        self.key(pg.K_1)
        self.key(pg.K_RIGHT)
        fish = game.state.fish[18]
        self.assertGreater(fish, 0)
        self.key(pg.K_RETURN)
        self.assertEqual(game.state.positions[0], 18)
        self.assertEqual(game.state.scores[0], fish)
        self.assertEqual(game.state.fish[18], 0)
        self.key(pg.K_p)
        self.assertEqual(game.modal, "pause")
        self.button("Restart this board")
        self.assertIsNone(game.modal)
        self.assertEqual((game.state.seed, game.state.round, game.state.positions[0]), (610830, 1, 17))

    def test_local_adventure_reaches_results_through_board_input(self):
        game = self.game
        game.setup_seed = 610830
        self.button("Play")
        self.button("Human vs AI")
        self.button("Start match")
        game.time = 1
        rng = Random(60)
        for _ in range(155):
            if game.state.over:
                game.update()
                break
            action = rng.choice(game.available())
            if action.kind == "pass":
                game.update()
            else:
                if action.kind != "rescue":
                    piece = game.state.positions[action.penguin]
                    self.click(game.cell_rect(piece).center)
                    if action.kind == "bait":
                        self.key(pg.K_b)
                    elif action.kind == "brace":
                        self.key(pg.K_r)
                before = game.state
                self.click(game.cell_rect(action.target).center)
                self.assertIsNot(before, game.state, action)
            game.time = game.ready_at + .1
        self.assertEqual(game.modal, "result")
        self.assertTrue(game.state.over)
        self.button("Main menu")
        self.assertEqual(game.page, "home")

    def test_ai_worker_commits_only_after_resume(self):
        game = self.game
        self.button("AI Arena")
        game.difficulty = "Quick"
        game.launch(610830, 1)
        game.time = 1
        before = game.state
        game.update()
        self.assertIsNotNone(game.future)
        self.key(pg.K_p)
        self.assertEqual(game.modal, "pause")
        game.future.result(timeout=5)
        game.update()
        self.assertIs(game.state, before)
        self.key(pg.K_p)
        game.update()
        self.assertIsNot(game.state, before)
        self.assertEqual(game.stats[1][0], 1)
