from dataclasses import replace
from random import Random
from unittest import TestCase

from frostfall.docks import (DOCK_INDEX, GAPS, LINKS, ROUND_LIMIT, Turn, advance, attacker_moves,
                            legal_turns, linked_pair, new_match, open_routes, slide)
from frostfall.docks_ai import search
from frostfall.rules import Action


class DocksTests(TestCase):
    def test_all_marked_routes_start_playable_on_symmetric_ice(self):
        state = new_match(1729)
        self.assertEqual({cell for cell in range(64) if not state.has_ice(cell)}, GAPS)
        self.assertTrue(all(len(open_routes(state, paths)) == 2 for _, _, paths in LINKS))
        for _, _, paths in LINKS:
            for path in paths:
                for a, b in zip(path, path[1:]):
                    self.assertEqual(abs(a//8-b//8) + abs(a%8-b%8), 1)
        for cell in range(64):
            self.assertEqual(state.fish[cell], state.fish[cell//8*8+7-cell%8])

    def test_attacker_can_follow_a_brace_but_cannot_slide_through_water(self):
        state = replace(new_match(42), positions=(8, 32, 14, 39))
        normal = Action("move", 1, 33)
        brace = Action("brace", 1, 33)
        follow = Action("move", 0, 32)
        self.assertNotIn(follow, attacker_moves(slide(state, normal)))
        self.assertIn(follow, attacker_moves(slide(state, brace)))
        with self.assertRaises(ValueError):
            advance(state, Turn(normal, follow))
        result, _ = advance(state, Turn(brace, follow))
        self.assertTrue(result.brace_used[0])
        self.assertTrue(result.has_ice(32))
        self.assertEqual(result.active, 1)

    def test_defender_blocks_the_attacker_and_attacker_alone_claims_docks(self):
        state = new_match(42)
        defend = Action("move", 1, 25)
        self.assertEqual(slide(state, defend).owners, (-1, -1, -1))
        self.assertNotIn(Action("move", 0, 25), attacker_moves(slide(state, defend)))
        defend = Action("move", 1, 33)
        attack = Action("move", 0, 25)
        result, _ = advance(state, Turn(defend, attack))
        self.assertEqual(result.owners, (0, -1, -1))
        self.assertEqual(result.scores[0], state.fish[33])
        departed = slide(result, Action("move", 0, 26))
        self.assertTrue(departed.has_ice(25))
        self.assertEqual(departed.owners, (0, -1, -1))
        self.assertEqual(DOCK_INDEX[51], DOCK_INDEX[52])

    def test_the_whole_reply_can_cut_both_routes_and_cancel_a_hold(self):
        state = replace(new_match(42, 1), owners=(0, -1, 0), pending=0, positions=(9, 32, 21, 27))
        defend = Action("move", 3, 35)
        attack = Action("move", 2, 29)
        self.assertEqual(linked_pair(slide(state, defend), 0), (0, 2))
        result, _ = advance(state, Turn(defend, attack))
        self.assertFalse(result.over)
        self.assertEqual(result.pending, -1)
        self.assertIsNone(linked_pair(result, 0))

    def test_final_turn_claim_gets_a_full_reply_and_can_win(self):
        state = replace(new_match(42), active=1, round=ROUND_LIMIT, turn=1, owners=(-1, 1, -1))
        turn = Turn(Action("move", 3, 38), Action("move", 2, 30))
        reply, _ = advance(state, turn)
        self.assertFalse(reply.over)
        self.assertEqual(reply.pending, 1)
        self.assertEqual(reply.active, 0)
        result, _ = advance(reply, Turn(Action("move", 1, 33), Action("move", 0, 10)))
        self.assertTrue(result.over)
        self.assertEqual(result.winner, 1)

    def test_two_passes_end_on_fish_with_docks_still_intact(self):
        state = new_match(42)
        # Keep the entire route network and put all pawns on isolated floes.
        ice = {cell for _, _, paths in LINKS for path in paths for cell in path}
        pawns = (0, 2, 5, 7)
        state = replace(state, positions=pawns, empty_ice=frozenset((*ice, *pawns)), fish=(0,)*64, scores=(4, 1))
        for side in range(2):
            self.assertEqual(legal_turns(state), (Turn(),))
            state, _ = advance(state, Turn())
        self.assertTrue(state.over)
        self.assertEqual(state.winner, 0)
        self.assertIn("trapped", state.reason)

    def test_sampled_matches_terminate_and_only_land_fish_once(self):
        rng = Random(173)
        for seed in range(8):
            state = new_match(seed, seed % 2)
            for _ in range(2*ROUND_LIMIT+1):
                plan = rng.choice(legal_turns(state))
                state, _ = advance(state, plan)
                self.assertTrue(all(state.fish[cell] == 0 for cell in state.positions))
                if state.over:
                    break
            self.assertTrue(state.over)

    def test_both_algorithms_choose_a_legal_paired_turn(self):
        state = new_match(42)
        for algorithm in ("Minimax", "MCTS"):
            with self.subTest(algorithm=algorithm):
                decision = search(state, algorithm, "Quick")
                self.assertIn(decision.action, legal_turns(state))
                self.assertIsNotNone(decision.action.defender)
                self.assertIsNotNone(decision.action.attacker)
