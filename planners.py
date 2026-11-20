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


def draft_snapshot(match, seed=0):
    snapshot = Match(seed, public_draft=match.public_draft, effects=False)
    snapshot.round_number = match.round_number
    snapshot.round_wins = match.round_wins.copy()
    snapshot.sides = [replace(team, hand=team.hand.copy(),
                              field={cell: replace(unit) for cell, unit in team.field.items()},
                              returning=[replace(unit) if unit is not None else None for unit in team.returning])
                      for team in match.sides]
    return snapshot


def sample_opponent(state, side, rng):
    rival = 1-side
    opponent = state.sides[rival]
    if state.public_draft or opponent.ready:
        return
    opponent.hand = state.start_hand(rival) if opponent.shells == SHELLS and not opponent.field else (
        rng.choices(range(len(ROSTER)), k=len(opponent.hand)))
    opponent.next_card = rng.randrange(len(ROSTER))


def battlefield_value(match, side):
    match.fight()
    while match.phase == "fight":
        match.step()
    winner = match.round_winner
    if winner == -1:
        return 0.
    surviving = sum(unit.hp for unit in match.fighters if unit.side == winner)
    original = sum(unit.maximum for unit in match.fighters if unit.side == winner)
    score = .76 + .24*surviving/original if original else .76
    return score if winner == side else -score


def recruit_value(recruit):
    hero = ROSTER[recruit.hero]
    return (hero.hp*.018+hero.attack/hero.interval*.17+hero.cost*.85)*(1+.27*(recruit.rank-1))


def lineup_value(match, side):
    team, enemies = match.sides[side], match.sides[1-side]
    score = (.70 if not team.ready else .20)*team.shells
    score += .78*sum(recruit_value(unit) for unit in team.returning if unit is not None)
    for (x, y), recruit in team.field.items():
        hero = ROSTER[recruit.hero]
        depth = x if side == 0 else COLS-1-x
        score += recruit_value(recruit)
        score -= abs(depth-hero.column)*.55
        score -= min(abs(lane-y) for lane in hero.lanes)*.28
        if recruit.hero in (MARKSMAN, MAGE):
            covered = any(ally.hero == TANK and abs(ally_y-y) <= 1 and abs(ally_x-x) > 0
                          for (ally_x, ally_y), ally in team.field.items()
                          if (ally_x-x)*(1 if side == 0 else -1) > 0)
            if covered:
                score += 1.8
            elif any(enemy.hero == ASSASSIN for enemy in enemies.field.values()):
                score -= 2.7
        if recruit.hero == MAGE:
            score += .60*sum((x+dx, y+dy) in enemies.field
                             for x, y in enemies.field for dx, dy in ((1, 0), (0, 1)))
    score += 1.35*len({unit.hero for unit in team.field.values()})
    return score


def choose_minimax(match, side, budget=SEARCH_BUDGET, max_depth=4):
    """Alpha-beta over visible drafts or a sampled opponent hand in private drafts."""
    if not match.public_draft:
        # Search a plausible hidden hand without using or modifying the real one.
        seed = match.round_number*31+match.sides[1-side].draws
        match = draft_snapshot(match, seed)
        sample_opponent(match, side, Random(seed))
    start_actions = match.draft_actions(side, 5)
    if not start_actions:
        return Decision()
    end = perf_counter()+budget
    explored = 0

    def search(state, turn, depth, alpha, beta):
        nonlocal explored
        explored += 1
        if perf_counter() >= end:
            raise TimeoutError
        if all(team.ready for team in state.sides):
            return 100*battlefield_value(draft_snapshot(state), side), None
        if not depth:
            return lineup_value(state, side)-lineup_value(state, 1-side), None
        best_action = None
        maximize = turn == side
        best = -float("inf") if maximize else float("inf")
        options = state.draft_actions(turn, 5) or [None]
        for action in options:
            child = draft_snapshot(state)
            child.apply_draft(turn, action)
            value, _ = search(child, 1-turn, depth-1, alpha, beta)
            if (maximize and value > best) or (not maximize and value < best):
                best, best_action = value, action
            if maximize:
                alpha = max(alpha, best)
            else:
                beta = min(beta, best)
            if beta <= alpha:
                break
        return best, best_action

    action, depth = start_actions[0], 0
    for horizon in range(1, max_depth+1):
        try:
            _, action = search(match, side, horizon, -float("inf"), float("inf"))
        except TimeoutError:
            break
        depth = horizon
    return Decision(action, explored, depth)


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
    "minimax": DraftPlanner("Minimax", choose_minimax, "nodes", "Looks ahead at draft moves and counterpicks."),
    "greedy": DraftPlanner("Greedy", choose_greedy, "", "Takes the best-rated move on each turn."),
}
