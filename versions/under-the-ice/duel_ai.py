"""Competitive alpha-beta Minimax and UCT MCTS for the 3D duel."""

from functools import lru_cache
from time import perf_counter

from duel import AIR_VENTS, DISTANCE, FISH, PASS, TO_AIR, advance, choices, count_fish
from frostfall.ai import Decision, SearchGame, mcts


@lru_cache(maxsize=16384)
def evaluate(state, team):
    if state.over:
        return 0. if state.winner < 0 else (300. if state.winner == team else -300.)
    scores = []
    for side, position in enumerate(state.positions):
        banked = state.scores[side]*10.0
        carry = count_fish(state.cargo[side])
        room = state.air[side]-TO_AIR[position]
        catch = carry*(8.0-.42*TO_AIR[position] if room >= 0 else 1.4)
        lives = 15*state.lives[side]
        risk = 7*(position == state.warning) + 3*max(0, 1-room)
        fish = max((amount*4.8/(1+.69*DISTANCE[position][cell]) for cell, amount in enumerate(FISH)
                    if state.fish & (1 << cell) and DISTANCE[position][cell]+TO_AIR[cell]-1 <= state.air[side]),
                   default=0.)
        scores.append(banked+catch+lives+fish-risk)
    return scores[team]-scores[1-team]


def priority(state, action):
    if action == PASS:
        return -20.
    side = state.active
    carried = count_fish(state.cargo[side])
    if action in AIR_VENTS:
        return 2.6*carried if carried else -1.1
    threat = 22. if action == state.warning else 0.
    room = state.air[side]-1-TO_AIR[action]
    fish = FISH[action] if state.fish & (1 << action) else 0
    return 2.7*fish + .20*room - 8*max(0, -room) - threat - .34*carried*TO_AIR[action]


def rollout(state, actions, rng):
    if len(actions) == 1 or rng.random() < .08:
        return rng.choice(actions)
    def rating(action):
        child, _ = advance(state, action, validate=False)
        return evaluate(child, state.active) + priority(state, action)
    return max(rng.sample(actions, min(3, len(actions))), key=rating)


SEARCH_GAME = SearchGame(choices, advance, lambda state: state.active, evaluate, rollout,
                         lambda state: state.seed*193 + state.round*31 + state.turn)


def minimax(state, depth, cancelled):
    started = perf_counter()
    team = state.active
    visited = 0

    def visit(position, remaining, alpha, beta):
        nonlocal visited
        if cancelled():
            raise InterruptedError
        visited += 1
        if position.over or not remaining:
            return evaluate(position, team)
        maximizing = position.active == team
        score = -float("inf") if maximizing else float("inf")
        for action in ordered(position):
            child, _ = advance(position, action, validate=False)
            value = visit(child, remaining-1, alpha, beta)
            if maximizing:
                score = max(score, value)
                alpha = max(alpha, score)
            else:
                score = min(score, value)
                beta = min(beta, score)
            if alpha >= beta:
                break
        return score

    highest = -float("inf")
    for action in ordered(state):
        result, _ = advance(state, action, validate=False)
        score = visit(result, depth-1, highest, float("inf"))
        if score > highest:
            highest, best = score, action
    return Decision(best, visited, perf_counter()-started)


def ordered(state):
    return sorted(choices(state), key=lambda action: priority(state, action), reverse=True)


def search(state, algorithm, cancelled=lambda: False):
    if algorithm == "Minimax":
        return minimax(state, 6, cancelled)
    if algorithm == "MCTS":
        return mcts(state, 260, cancelled, game=SEARCH_GAME)
    raise ValueError(f"Unknown algorithm {algorithm}")
