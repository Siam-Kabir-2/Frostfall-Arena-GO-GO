"""Rules and AI regression coverage for Fish Heist."""

from dataclasses import replace
from unittest import TestCase

from frostfall.heist import CAPACITY, DOCKS, GOAL, Move, advance, board_cell, display_cell, legal, new_heist
from frostfall.heist_ai import search_heist


class HeistTests(TestCase):
    def setUp(self):
        self.state = new_heist(610830)

    def test_schools_are_mirrored_and_display_coordinates_round_trip(self):
        self.assertEqual(self.state.fish, self.state.fish[::-1])
        self.assertEqual(tuple(board_cell(display_cell(cell)) for cell in range(36)), tuple(range(36)))
        self.assertIsNone(board_cell(0))

    def test_skate_picks_up_along_route_and_banks_only_on_dock(self):
        out, recap = advance(self.state, Move("skate", 15))
        self.assertEqual((recap.caught, out.carry[0], out.bank[0]), (CAPACITY, CAPACITY, 0))
        other, _ = advance(out, Move("skate", 21))
        banked, recap = advance(other, Move("skate", DOCKS[0]))
        self.assertEqual((recap.banked, banked.carry[0], banked.bank[0]), (CAPACITY, 0, CAPACITY))
        self.assertEqual(banked.fish[15], self.state.fish[15])
        self.assertEqual(sum(banked.fish) + sum(banked.carry) + sum(banked.bank), sum(self.state.fish))

    def test_bump_spills_fish_and_next_player_can_recover_it(self):
        first, _ = advance(self.state, Move("skate", 15))
        second, _ = advance(first, Move("skate", 21))
        after, recap = advance(second, Move("bump", 27))
        self.assertEqual((after.positions, recap.spilled, after.carry[1]), ((15, 27), 1, 3))
        self.assertEqual(after.fish[21], second.fish[21] + 1)
        recovered, recap = advance(after, Move("skate", 21))
        self.assertEqual((recap.caught, recovered.carry[1]), (1, 4))

    def test_docks_protect_occupant_and_block_rival_entry(self):
        position = replace(self.state, positions=(17, 23), active=0)
        self.assertNotIn(Move("skate", DOCKS[1]), legal(position))
        self.assertFalse(any(move.kind == "bump" for move in legal(position)))
        position = replace(self.state, positions=(14, 13), active=0)
        self.assertNotIn(Move("bump", DOCKS[0]), legal(position))

    def test_eight_banked_or_the_round_limit_ends_the_match(self):
        at_dock = replace(self.state, positions=(13, DOCKS[1]), carry=(4, 0), bank=(4, 5))
        after, _ = advance(at_dock, Move("skate", DOCKS[0]))
        self.assertEqual((after.bank[0], after.over, after.winner), (GOAL, True, 0))
        for scores, winner in (((5, 6), 1), ((5, 5), -1)):
            at_limit = replace(self.state, bank=scores, ply=23)
            after, _ = advance(at_limit, Move("skate", 13))
            self.assertEqual((after.over, after.round, after.winner), (True, 12, winner))

    def test_both_search_algorithms_choose_the_available_winning_bank(self):
        position = replace(self.state, positions=(14, DOCKS[1]), carry=(3, 0), bank=(5, 7))
        for name in ("Minimax", "MCTS"):
            decision = search_heist(position, name)
            self.assertEqual(decision.action, Move("skate", DOCKS[0]))

