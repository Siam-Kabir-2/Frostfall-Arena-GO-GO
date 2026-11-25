"""Minimax with alpha-beta pruning and MCTS for Guard Zone turns."""

from time import perf_counter

from .ai import Decision, SearchGame, mcts
from .guard import FISH_GOAL, Turn, advance, attacker_moves, defender_moves, legal_turns, slide, zones
from .rules import destinations


BUDGETS = {"Quick": (1, .25, 70), "Standard": (2, .85, 150), "Deep": (3, 1.8, 280)}


def evaluate(state, team):
    if state.over:
        return 0. if state.winner < 0 else 300. if state.winner == team else -300.
    guarded = zones(state)
    scores = [score * 4.6 for score in state.scores]
    for side in range(2):
        reachable = tuple(destinations(state, side*2))
        allowed = [cell for cell in reachable if cell not in guarded[1-side]]
        denied = sum(state.fish[cell] for cell in reachable if cell in guarded[1-side])
        scores[side] += .42*len(allowed) - .34*denied + 2.3*max((state.fish[c] for c in allowed), default=0)
        if not allowed:
            scores[side] -= 7
    return scores[team] - scores[1-team]


def priority(state, turn):
    fish = state.fish[turn.attacker.target] if turn.attacker else 0
    return 60 if state.scores[state.active]+fish >= FISH_GOAL else 4*fish + (turn.defender is not None)*.15


def rollout(state, rng):
    defenders = (*defender_moves(state), None)
    defender = rng.choice(defenders)
    middle = slide(state, defender)
    attackers = attacker_moves(middle)
    attacker = max(rng.choices(attackers, k=4), key=lambda action: state.fish[action.target]) if attackers else None
    return Turn(defender, attacker)


GUARD_SEARCH = SearchGame(legal_turns, advance, lambda state: state.active, evaluate, None,
                          lambda state: state.seed * 97 + state.round * 43 + state.turn,
                          rollout_choice=rollout, expansion_priority=priority)


class SearchExpired(Exception):
    pass


def alpha_beta(state, depth, seconds, cancelled):
    started = perf_counter()
    team = state.active
    count = 0
    roots = ordered_turns(state)
    best = roots[0]

    def visit(position, remaining, alpha, beta):
        nonlocal count
        count += 1
        if count % 32 == 0:
            if cancelled():
                raise InterruptedError
            if perf_counter() - started >= seconds:
                raise SearchExpired
        if position.over or not remaining:
            return evaluate(position, team)
        maximizing = position.active == team
        rating = -float("inf") if maximizing else float("inf")
        for turn in ordered_turns(position):
            child, _ = advance(position, turn, validate=False)
            value = visit(child, remaining-1, alpha, beta)
            if maximizing:
                rating = max(rating, value)
                alpha = max(alpha, rating)
            else:
                rating = min(rating, value)
                beta = min(beta, rating)
            if alpha >= beta:
                break
        return rating

    for horizon in range(1, depth+1):
        rating = -float("inf")
        try:
            for turn in roots:
                if cancelled():
                    raise InterruptedError
                child, _ = advance(state, turn, validate=False)
                value = visit(child, horizon-1, rating, float("inf"))
                if value > rating:
                    rating, choice = value, turn
        except SearchExpired:
            break
        best = choice
        if abs(rating) == 300:
            break
        roots.remove(best)
        roots.insert(0, best)
    return Decision(best, count, perf_counter()-started)


def ordered_turns(state):
    return sorted(legal_turns(state), key=lambda turn: priority(state, turn), reverse=True)


def search(state, algorithm, difficulty, cancelled=lambda: False):
    depth, seconds, simulations = BUDGETS[difficulty]
    if algorithm == "Minimax":
        return alpha_beta(state, depth, seconds, cancelled)
    return mcts(state, simulations, cancelled, game=GUARD_SEARCH)
