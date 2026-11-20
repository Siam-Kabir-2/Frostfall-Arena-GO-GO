"""Draft strategies for the shared combat engine."""

from dataclasses import dataclass, field, replace
from math import log, sqrt
from random import Random
from time import perf_counter

from arena import ASSASSIN, COLS, MAGE, MARKSMAN, ROSTER, SHELLS, TANK, Match

SEARCH_BUDGET = .65


@dataclass(frozen=True)
class Decision:
    action: object = None
    explored: int = 0
    depth: int = 0


def choose_greedy(match, side):
    actions = match.draft_actions(side, 1)
    return Decision(actions[0], 1, 1) if actions else Decision()


@dataclass(frozen=True)
class DraftPlanner:
    label: str
    choose: object
    effort: str
    description: str


DRAFT_PLANNERS = {
    "greedy": DraftPlanner("Greedy", choose_greedy, "", "Takes the best-rated move on each turn."),
}
