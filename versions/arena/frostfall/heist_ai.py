"""Shared search algorithms with Fish Heist's scoring and movement model."""

from .ai import SearchGame, mcts, minimax
from .heist import CAPACITY, DOCKS, ROUNDS, SIZE, advance, distance, legal

DEPTH = 3
SIMULATIONS = 200


def turns_between(a, b):
    row, col = divmod(a, SIZE)
    y, x = divmod(b, SIZE)
    return (abs(row - y) + 2) // 3 + (abs(col - x) + 2) // 3


def evaluate(state, team):
    if state.over:
        if state.winner < 0:
            return 0
        value = 300 - state.ply * .75
        return value if state.winner == team else -value
    schools = [cell for cell, amount in enumerate(state.fish) if amount]
    values = list(state.bank)
    for player, cell in enumerate(state.positions):
        carry = state.carry[player]
        home = turns_between(cell, DOCKS[player])
        left = (ROUNDS * 2 - state.ply + int(state.active == player)) // 2
        value = 10.0 * state.bank[player]
        if carry and home <= left:
            value += carry * (3.6 + 3.1 / max(1, home))
        if carry < CAPACITY and schools:
            nearest = min(distance(cell, school) for school in schools)
            value += .79 * (6 - min(6, nearest))
        rival = 1 - player
        if carry and state.active == rival and distance(cell, state.positions[rival]) == 1:
            value -= 1.8
        values[player] = value
    return values[team] - values[1 - team]


def rollout(state, actions, rng):
    if len(actions) == 1 or rng.random() < .24:
        return rng.choice(actions)
    active = state.active
    dock = DOCKS[active]
    start = state.positions[active]
    carry = state.carry[active]

    def urgency(move):
        _, recap = advance(state, move, validate=False)
        if move.kind == "bump":
            return 2.9 * recap.spilled - 4 * recap.rival_banked
        homeward = turns_between(start, dock) - turns_between(move.target, dock)
        if carry >= 3 or state.ply >= 18:
            return 8 * recap.banked + 4 * homeward + recap.caught
        return 7 * recap.banked + 3.4 * recap.caught + homeward

    sample = rng.sample(actions, min(5, len(actions)))
    return max(sample, key=urgency)


HEIST = SearchGame(legal, advance, lambda state: state.active, evaluate, rollout,
                   lambda state: state.seed * 17911 + state.ply * 71 + state.active)


def search_heist(state, name, cancelled=lambda: False):
    if name == "Minimax":
        return minimax(state, DEPTH, cancelled, game=HEIST)
    if name == "MCTS":
        return mcts(state, SIMULATIONS, cancelled, game=HEIST)
    raise ValueError(f"Unknown Fish Heist opponent {name}")

