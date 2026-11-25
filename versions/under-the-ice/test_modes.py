from unittest import TestCase

from pygame.math import Vector2

from modes import Run


class ModeTests(TestCase):
    def test_solo_moves_only_with_player_input(self):
        run = Run("solo", 610830)
        run.step(1/60, Vector2())
        self.assertFalse(run.games[0].underwater)
        run.step(1/60, Vector2(0, 1))
        self.assertTrue(run.games[0].underwater)

    def test_watch_diver_banks_fish_without_player_input(self):
        run = Run("watch", 610830)
        for _ in range(2000):
            run.step(1/60, Vector2())
            if run.finished:
                break
        self.assertEqual(run.games[0].finished, "win")
        self.assertGreater(run.pilots[0].explored, 0)

    def test_race_has_equal_cave_geometry_and_independent_divers(self):
        run = Run("race", 610830)
        a_star, greedy = run.games
        self.assertIs(a_star.cave, greedy.cave)
        self.assertIsNot(a_star.available, greedy.available)
        run.switch_search()
        self.assertFalse(a_star.greedy)
        self.assertTrue(greedy.greedy)
        for _ in range(2400):
            run.step(1/60, Vector2())
            if run.finished:
                break
        self.assertTrue(run.finished)
        self.assertTrue(a_star.finished == "win" or greedy.finished == "win")
        self.assertTrue(all(pilot.explored > 0 for pilot in run.pilots))
