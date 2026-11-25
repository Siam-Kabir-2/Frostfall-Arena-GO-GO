"""Alpha-beta Minimax and UCT MCTS for paired slides."""

from time import perf_counter

from .ai import Decision, SearchGame, mcts
from .docks import (DOCK_INDEX, LINKS, Turn, advance, attacker_moves, defender_moves,
                    legal_turns, open_routes, slide)
from .rules import destinations


BUDGETS = {"Quick": (1, .3, 75), "Standard": (2, .9, 180), "Deep": (3, 2.1, 360)}


def evaluate(state, team):
    if state.over:
        if state.winner < 0:
            return 0.0
        return 300.0 if state.winner == team else -300.0
    value = [state.scores[side] * 1.35 + state.owners.count(side) * 25 for side in range(2)]
    for side in range(2):
        moves = tuple(destinations(state, side * 2))
        reachable_docks = {DOCK_INDEX[cell] for cell in moves if cell in DOCK_INDEX}
        value[side] += 4 * sum(state.owners[dock] != side for dock in reachable_docks)
        value[side] += .21 * len(moves) + .14 * sum(1 for _ in destinations(state, side * 2 + 1))
        value[side] += 1.5 * (not state.brace_used[side])
    for a, b, routes in LINKS:
        available = len(open_routes(state, routes))
        if available and state.owners[a] >= 0 and state.owners[a] == state.owners[b]:
            value[state.owners[a]] += 11 * available
    if state.pending >= 0:
        value[state.pending] += 48
    return max(-295., min(295., value[team] - value[1-team]))


def slide_priority(state, action):
    if action is None:
        return 0
    score = state.fish[action.target] * 1.6
    dock = DOCK_INDEX.get(action.target)
    if action.penguin % 2 == 0 and dock is not None and state.owners[dock] != state.active:
        score += 12 if state.owners[dock] < 0 else 17
        if state.owners[dock] >= 0 and state.owners[dock] == state.pending:
            score += 35
    origin = state.positions[action.penguin]
    if action.kind == "move" and origin not in DOCK_INDEX:
        for a, b, routes in LINKS:
            owner = state.owners[a]
            if owner >= 0 and state.owners[b] == owner:
                live = open_routes(state, routes)
                if live and all(origin in route for route in live):
                    score += -18 if owner == state.active else 29
    return score - (1.6 if action.kind == "brace" else 0)


def priority(state, turn):
    return slide_priority(state, turn.defender) + slide_priority(state, turn.attacker)


def rollout(state, rng):
    defenders = defender_moves(state) or (None,)
    defender = max(rng.choices(defenders, k=3), key=lambda action: slide_priority(state, action))
    middle = slide(state, defender)
    attackers = attacker_moves(middle) or (None,)
    attacker = max(rng.choices(attackers, k=4), key=lambda action: slide_priority(middle, action))
    return Turn(defender, attacker)


def mcts_actions(state):
    turns = legal_turns(state)
    if state.pending < 0:
        return turns
    # A reply that immediately loses is dominated whenever a surviving reply exists.
    survivors = []
    for turn in turns:
        result, _ = advance(state, turn, validate=False)
        if not result.over or result.winner != state.pending:
            survivors.append(turn)
    return survivors or turns


DOCK_SEARCH = SearchGame(mcts_actions, advance, lambda state: state.active, evaluate, None,
                         lambda state: state.seed * 97 + state.round * 43 + state.turn,
                         rollout_choice=rollout, expansion_priority=priority)


class SearchBudgetReached(Exception):
    pass


def alpha_beta(state, depth, seconds, cancelled):
    started = perf_counter()
    team = state.active
    visited = 0
    roots = sorted(legal_turns(state), key=lambda turn: priority(state, turn), reverse=True)
    best = roots[0]

    def visit(position, remaining, alpha, beta):
        nonlocal visited
        visited += 1
        if visited % 32 == 0:
            if cancelled():
                raise InterruptedError
            if perf_counter() - started >= seconds:
                raise SearchBudgetReached
        if position.over or remaining == 0:
            return evaluate(position, team)
        turns = sorted(legal_turns(position), key=lambda turn: priority(position, turn), reverse=True)
        maximize = position.active == team
        value = -float("inf") if maximize else float("inf")
        for turn in turns:
            child, _ = advance(position, turn, validate=False)
            rating = visit(child, remaining - 1, alpha, beta)
            if maximize:
                value = max(value, rating)
                alpha = max(alpha, value)
            else:
                value = min(value, rating)
                beta = min(beta, value)
            if alpha >= beta:
                break
        return value

    for horizon in range(1, depth + 1):
        try:
            rating = -float("inf")
            for turn in roots:
                if cancelled():
                    raise InterruptedError
                child, _ = advance(state, turn, validate=False)
                value = visit(child, horizon - 1, rating, float("inf"))
                if value > rating:
                    rating, best_at_depth = value, turn
            best = best_at_depth
            if abs(rating) == 300:
                break
            roots.remove(best)
            roots.insert(0, best)
        except SearchBudgetReached:
            break
    return Decision(best, visited, perf_counter() - started)


def search(state, algorithm, difficulty, cancelled=lambda: False):
    depth, seconds, simulations = BUDGETS[difficulty]
    if algorithm == "Minimax":
        return alpha_beta(state, depth, seconds, cancelled)
    return mcts(state, simulations, cancelled, game=DOCK_SEARCH)
