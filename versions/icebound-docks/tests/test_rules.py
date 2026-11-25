import unittest
from dataclasses import replace
from random import Random

from frostfall.ai import minimax, mcts
from frostfall.rules import ADVENTURE_GOAL, Action, OPENING, PASS, choices, destinations, new_match, shark_target, transition


def scenario(*, ice=None, adventure=True, **fields):
    state = new_match(709, adventure=adventure)
    fields.setdefault("empty_ice", frozenset())
    fields["fish"] = tuple(value or 1 for value in state.fish)
    if ice is not None:
        fields["fish"] = tuple(ice.get(cell, 0) for cell in range(64))
    return replace(state, **fields)


class MovementTests(unittest.TestCase):
    def test_seeded_gaps_preserve_starts_pickups_and_opening_routes(self):
        layouts=set()
        for seed in range(25):
            state=new_match(seed)
            gaps={cell for cell in range(64) if not state.has_ice(cell)}
            self.assertEqual(len(gaps),8)
            self.assertEqual(gaps,{cell//8*8+7-cell%8 for cell in gaps})
            self.assertFalse(gaps.intersection((*OPENING,*state.pickups)))
            self.assertEqual(state.scores, (0, 0))
            self.assertTrue(all(state.fish[cell] == 0 for cell in OPENING))
            self.assertTrue(all(len(tuple(destinations(state,piece)))>=7 for piece in range(4)))
            self.assertEqual(state,new_match(seed))
            layouts.add(tuple(sorted(gaps)))
        self.assertGreater(len(layouts),20)

    def test_slides_in_all_eight_directions(self):
        state = scenario(positions=(27, -1, -1, -1))
        self.assertTrue({18, 19, 20, 26, 28, 34, 35, 36, 0, 63} <= set(destinations(state, 0)))
        self.assertNotIn(12, destinations(state, 0))

    def test_water_occupied_and_frozen_stop_the_entire_ray(self):
        points = {23: 1, 24: 3, 25: 1, 26: 1, 27: 1, 32: 2, 40: 2, 33: 1, 42: 2}
        state = scenario(ice=points, positions=(24, 25, 23, 63), frozen=(33,))
        self.assertEqual(set(destinations(state, 0)), {32, 40})
        with self.assertRaises(ValueError):
            transition(state, Action("move", 0, 26))

    def test_slide_collects_only_landing_fish_and_sinks_departure_ice(self):
        state = scenario(ice={17: 3, 18: 1, 19: 2, 22: 1, 23: 1})
        moved, _ = transition(state, Action("move", 0, 19))
        self.assertEqual(moved.scores, (2, 0))
        self.assertEqual((moved.fish[17], moved.fish[18], moved.fish[19]), (0, 1, 0))
        self.assertFalse(moved.has_ice(17))
        self.assertTrue(moved.has_ice(19))
        self.assertEqual(moved.positions, (19,) + OPENING[1:])
        self.assertEqual(moved.active, 1)
        self.assertEqual(state.fish[17], 3)

    def test_only_mobile_team_wins_when_opponent_has_no_legal_action(self):
        state = scenario(ice={17: 2, 41: 2, 22: 1, 23: 3, 46: 2}, adventure=False, scores=(40, 0))
        self.assertEqual(choices(state), (PASS,))
        state, events = transition(state, PASS)
        self.assertTrue(state.over)
        self.assertEqual((state.winner, state.reason), (1, "Coral has no legal move"))
        self.assertEqual(events[0].kind, "result")

    def test_trapping_next_team_ends_match_on_the_move(self):
        state = scenario(ice={17: 2, 18: 2, 19: 1, 41: 2, 22: 1, 46: 2}, adventure=False)
        state, _ = transition(state, Action("move", 0, 18))
        self.assertTrue(state.over)
        self.assertEqual((state.winner, state.reason), (0, "Azure has no legal move"))

    def test_no_moves_finishes_with_score_win_or_draw(self):
        for score, winner in (((3, 2), 0), ((2, 3), 1), ((3, 3), -1)):
            with self.subTest(score=score):
                state = scenario(ice=dict.fromkeys(OPENING, 2), scores=score, turn=1, active=1)
                state, _ = transition(state, PASS)
                self.assertTrue(state.over)
                self.assertEqual(state.winner, winner)


class SharkTests(unittest.TestCase):
    def test_round_three_warning_stays_locked_for_both_turns(self):
        state = scenario(round=2, turn=1, active=1)
        warned, events = transition(state, Action("move", 2, 23))
        self.assertEqual(warned.round, 3)
        self.assertIn("shark", [event.kind for event in events])
        after_move, _ = transition(warned, choices(warned)[0])
        self.assertEqual(after_move.shark, warned.shark)

    def test_empty_tile_destroyed_and_melted_target_misses(self):
        for fish, empty_ice, event in ((2, frozenset(), "strike"), (0, frozenset({4}), "strike"),
                                     (0, frozenset(), "miss")):
            with self.subTest(fish=fish, empty_ice=empty_ice):
                state = scenario(ice={**dict.fromkeys(OPENING, 1), 4: fish}, empty_ice=empty_ice,
                                 round=3, turn=1, active=1, shark=4)
                state, events = transition(state, PASS)
                self.assertFalse(state.has_ice(4))
                self.assertIn(event, [item.kind for item in events])
                self.assertEqual(state.positions, OPENING)

    def test_rescue_has_eight_directions_but_only_safe_tiles(self):
        state = scenario(ice={17: 3, 18: 2, 24: 1, 22: 1, 46: 1, 41: 1},
                         round=3, turn=1, active=1, shark=17, frozen=(24,), scores=(1, 0), pickups=(18,))
        state, _ = transition(state, PASS)
        self.assertEqual(state.rescue, 0)
        self.assertEqual(choices(state), (Action("rescue", 0, 18),))
        moved, _ = transition(state, choices(state)[0])
        self.assertEqual((moved.round, moved.active), (4, 0))
        self.assertEqual(moved.positions[0], 18)
        self.assertEqual(moved.scores, (2, 0))
        self.assertEqual(moved.pickups, (18,))
        self.assertEqual(moved.fish[18], 0)
        self.assertTrue(moved.has_ice(18))

    def test_elimination_allows_survivor_and_the_last_loss_overrides_score(self):
        for survivor, over in ((41, False), (-1, True)):
            with self.subTest(survivor=survivor):
                state = scenario(ice={17: 3, 22: 1, 23: 1, 40: 1, 41: 1, 46: 1},
                                 round=3, turn=1, active=1, shark=17, positions=(17, survivor, 22, 46),
                                 scores=(24, 0))
                state, events = transition(state, Action("move", 2, 23))
                self.assertEqual(state.positions[0], -1)
                self.assertEqual(state.over, over)
                self.assertIn("eliminated", [event.kind for event in events])
                if over:
                    self.assertEqual((state.winner, state.reason), (1, "Elimination"))

    def test_normal_target_excludes_penguins_without_an_escape(self):
        state = scenario(ice={17: 3, 41: 3, 22: 3, 46: 3, 0: 1}, round=3)
        self.assertEqual(shark_target(state), 0)


class AdventureObjectiveTests(unittest.TestCase):
    def test_target_score_wins_immediately_even_during_shark_round(self):
        state = scenario(round=3, turn=1, active=1, shark=17, scores=(2, ADVENTURE_GOAL - 1))
        state, events = transition(state, Action("move", 2, 23))
        self.assertTrue(state.over)
        self.assertEqual((state.winner, state.reason), (1, f"Reached {ADVENTURE_GOAL} fish"))
        self.assertEqual([event.kind for event in events], ["move", "result"])

    def test_defender_brace_scores_and_keeps_empty_departure_ice_playable(self):
        state = scenario(ice={17: 1, 22: 1, 23: 1, 25: 1, 33: 1, 42: 3, 46: 1},
                         empty_ice=frozenset({41}), pickups=(41,), scores=(5, 6))
        self.assertNotIn(Action("brace", 0, 18), choices(state))
        used, events = transition(state, Action("brace", 1, 42))
        self.assertEqual((used.positions[1], used.scores, used.pickups), (42, (8, 6), state.pickups))
        self.assertEqual((used.fish[41], used.fish[42]), (0, 0))
        self.assertEqual(used.brace_used, (True, False))
        self.assertEqual(events[0].kind, "brace")
        self.assertFalse(any(action.kind == "brace" for action in choices(replace(used, active=0))))
        self.assertFalse(any(action.kind == "brace" for action in choices(replace(state, adventure=False))))
        returned, _ = transition(replace(used, active=0), Action("move", 0, 41))
        self.assertEqual(returned.scores, used.scores)
        self.assertTrue(returned.has_ice(41))


class BaitAndWardenTests(unittest.TestCase):
    def test_bait_pickup_is_on_departure_and_cannot_exceed_capacity(self):
        for already_held in (False, True):
            state = scenario(pickups=(17, 18), inventory=(already_held, False))
            moved, events = transition(state, Action("move", 0, 18))
            self.assertTrue(moved.inventory[0])
            self.assertEqual(moved.pickups, (18,))
            self.assertEqual(any(event.kind == "pickup" for event in events), not already_held)

    def test_bait_costs_the_turn_and_redirects_next_shark(self):
        state = scenario(round=2, inventory=(True, False), frozen=(19,))
        self.assertNotIn(Action("bait", 0, 19), choices(state))
        self.assertNotIn(Action("bait", 0, 63), choices(state))
        baited, _ = transition(state, Action("bait", 0, 20))
        self.assertEqual((baited.active, baited.positions, baited.scores), (1, OPENING, (0, 0)))
        self.assertEqual((baited.deployed, baited.inventory), ((True, False), (False, False)))
        warned, _ = transition(baited, Action("move", 2, 23))
        self.assertEqual(warned.shark, 20)
        self.assertFalse(any(action.kind == "bait" for action in choices(warned)))
        self.assertFalse(any(action.kind == "bait" for action in choices(replace(warned, round=8, inventory=(True, False)))))

    def test_competing_baits_prioritize_occupied_and_are_order_independent(self):
        state = scenario(round=3, markers=(17, 2))
        self.assertEqual(shark_target(state), 17)
        self.assertEqual(shark_target(replace(state, markers=(2, 17))), 17)
        tie = replace(state, markers=(14, 15))
        self.assertEqual(shark_target(tie), shark_target(replace(tie, markers=(15, 14))))

    def test_warden_skips_occupied_mark_and_thaws_after_one_round(self):
        state = scenario(round=6, turn=1, active=1, marks=(21, 23))
        frozen, _ = transition(state, Action("move", 2, 23))
        self.assertEqual((frozen.round, frozen.frozen), (7, (21,)))
        self.assertNotIn(21, destinations(frozen, 0))
        frozen, _ = transition(frozen, Action("move", 0, 18))
        thawed, events = transition(frozen, Action("move", 2, 15))
        self.assertEqual((thawed.round, thawed.frozen), (8, ()))
        self.assertIn("thaw", [event.kind for event in events])
        self.assertEqual(thawed.fish[21], state.fish[21])

    def test_temporary_obstacles_do_not_end_the_match(self):
        state = scenario(ice={17: 1, 18: 1, 22: 1, 41: 1, 46: 1}, round=7, frozen=(18,))
        state, _ = transition(state, PASS)
        state, _ = transition(state, PASS)
        self.assertFalse(state.over)
        self.assertIn(Action("move", 0, 18), choices(state))


class AITests(unittest.TestCase):
    def test_both_searches_use_the_underused_defender_when_safe(self):
        board = new_match(610830, adventure=False)
        fish = tuple(int(bool(value)) for value in board.fish)
        state = replace(board, fish=fish, move_counts=(5, 0, 0, 0))
        for decision in (minimax(state, 2), mcts(state, 200)):
            self.assertEqual(decision.action.penguin, 1)

    def test_search_returns_legal_actions_without_mutating_state(self):
        state = scenario(round=3, shark=17)
        start = replace(state)
        for decision in (minimax(state, 2), mcts(state, 75)):
            self.assertIn(decision.action, choices(state))
            self.assertEqual(transition(state, decision.action), transition(state, decision.action, validate=False))
            self.assertGreater(decision.effort, 0)
            self.assertEqual(state, start)

    def test_classic_and_adventure_pass_loops_terminate(self):
        for seed in range(14):
            rng = Random(seed)
            for adventure in (False, True):
                state = new_match(seed, adventure, first=seed % 2)
                for _ in range(160):
                    if state.over:
                        break
                    state, _ = transition(state, rng.choice(choices(state)))
                self.assertTrue(state.over, (seed, adventure, state))
                self.assertGreaterEqual(min(state.scores), 0)
                self.assertTrue(all(state.fish[cell] == 0 for cell in state.positions if cell >= 0))
                self.assertEqual(len({cell for cell in state.positions if cell >= 0}),
                                 sum(cell >= 0 for cell in state.positions))


if __name__ == "__main__":
    unittest.main()
