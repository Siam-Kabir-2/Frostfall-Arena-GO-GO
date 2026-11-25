from math import dist
from unittest import TestCase

from pygame.math import Vector2

from cave import AIR, EXIT_Y, VENTS, Cave, Route, infer_exit
from dive import Dive


class DiveTests(TestCase):
    def test_seeded_layouts_have_clear_routes_to_both_vents(self):
        for seed in (0, 13, 42, 610830):
            cave = Cave(seed)
            for fish in cave.fish:
                for opening in range(2):
                    route = cave.route(fish, opening)
                    self.assertIsNotNone(route)
                    self.assertTrue(all(cave.visible(a, b) for a, b in zip(route.points, route.points[1:])))

    def test_a_star_and_greedy_produce_visible_paths_around_ice(self):
        cave = Cave(610830)
        start = (625, 386)
        self.assertFalse(cave.visible(start, cave.ends[0]))
        shortest = cave.route(start, 0)
        greedy = cave.route(start, 0, greedy=True)
        self.assertIsNotNone(shortest)
        self.assertIsNotNone(greedy)
        self.assertLessEqual(shortest.length, greedy.length+1e-6)
        self.assertEqual(shortest.points[-1], (VENTS[0], EXIT_Y))
        self.assertAlmostEqual(shortest.length, sum(dist(a, b) for a, b in zip(shortest.points, shortest.points[1:])))

    def test_lookout_can_route_away_from_deepfin_in_middle_of_shorter_lane(self):
        west = Route(((100, 500), (100, 300)), 200, 1)
        east = Route(((100, 500), (430, 500), (510, 300)), 550, 4)
        self.assertEqual(infer_exit((west, east), (100, 398), AIR)[0], 1)
        self.assertEqual(infer_exit((west, east), (100, 398), .4)[0], 0)

    def test_swim_catch_and_surface_in_one_real_dive(self):
        game = Dive(610830)
        for direction, frames in (((0, 1), 44), ((0, -1), 76)):
            for _ in range(frames):
                game.step(1/60, Vector2(direction))
        self.assertFalse(game.underwater)
        self.assertGreater(game.banked, 0)
        self.assertFalse(game.haul)
        self.assertEqual(game.lives, 3)

    def test_out_of_air_returns_fish_and_preserves_banked_score(self):
        game = Dive(610830)
        for _ in range(44):
            game.step(1/60, Vector2(0, 1))
        caught = set(game.haul)
        self.assertTrue(caught)
        self.assertTrue(caught.isdisjoint(game.available))
        game.air = .001
        game.banked = 2
        game.step(1/60, Vector2())
        self.assertFalse(game.underwater)
        self.assertTrue(caught <= game.available)
        self.assertEqual(game.lives, 2)
        self.assertEqual(game.banked, 2)
