"""Plain minimax and UCT Monte Carlo tree search."""

from dataclasses import dataclass, field
from math import log, sqrt, tanh
from random import Random
from time import perf_counter
from typing import Callable

from .rules import ADJACENT, choices, decide_team, destinations, transition


@dataclass(frozen=True, slots=True)
class Decision:
    action: object
    effort: int
    seconds: float


@dataclass(frozen=True, slots=True)
class SearchGame:
    actions: Callable
    advance: Callable
    team: Callable
    evaluate: Callable
    rollout: Callable
    seed: Callable
    costs_ply: Callable = lambda state: True
    final_bonus: Callable = lambda state, action: 0.0
    rollout_choice: Callable | None = None
    expansion_priority: Callable | None = None


PRESETS = {
    "Quick": (1, 80),
    "Standard": (2, 200),
    "Deep": (3, 500),
}


def evaluate(state, team):
    if state.over:
        return 0.0 if state.winner < 0 else (300.0 if state.winner == team else -300.0)
    values = [score * 4.5 for score in state.scores]
    blocked = set(state.positions) | set(state.frozen)
    mobile = [False] * 4
    for piece, cell in enumerate(state.positions):
        if cell < 0:
            continue
        moves = tuple(destinations(state, piece, blocked))
        mobile[piece] = bool(moves)
        value = 10 + len(moves) * (0.24 if piece % 2 == 0 else 0.42)
        if moves:
            best = max(state.fish[dest] for dest in moves)
            value += best * (1.4 if piece % 2 == 0 else 0.75)
            if piece % 2:
                value += sum(neighbor in moves for neighbor in ADJACENT[cell]) * 0.45
        if cell == state.shark or piece == state.rescue:
            value -= 4 + (4 if len(moves) <= 2 else 0)
        values[piece // 2] += value
    for team_id in range(2):
        first = team_id * 2
        if mobile[first] and mobile[first + 1]:
            # A modest tempo cost keeps a safe second piece involved in tight decisions.
            values[team_id] -= min(9, abs(state.move_counts[first] - state.move_counts[first + 1]) * 1.75)
        if state.adventure:
            values[team_id] += 1.0 * (state.inventory[team_id] and not state.deployed[team_id])
            if mobile[first + 1] and not state.brace_used[team_id]:
                values[team_id] += 1.9
    return values[team] - values[1 - team]


def minimax(state, depth, cancelled=lambda: False, *, game=None):
    game = game or FROSTFALL
    started = perf_counter()
    root_team, visited = game.team(state), 0

    def visit(position, remaining):
        nonlocal visited
        visited += 1
        if cancelled():
            raise InterruptedError
        normal = game.costs_ply(position)
        if position.over or (remaining <= 0 and normal):
            return game.evaluate(position, root_team)
        pick = max if game.team(position) == root_team else min
        next_depth = remaining - normal
        return pick(visit(game.advance(position, action, validate=False)[0], next_depth)
                    for action in game.actions(position))

    decision = max(game.actions(state), key=lambda action: visit(
        game.advance(state, action, validate=False)[0], depth - game.costs_ply(state)))
    return Decision(decision, visited, perf_counter() - started)


@dataclass(slots=True)
class Node:
    state: object
    untried: list
    action: object = None
    children: list = field(default_factory=list)
    visits: int = 0
    reward: float = 0.0


def rollout_action(state, actions, rng):
    if state.rescue >= 0:
        team = decide_team(state)
        return max(actions, key=lambda action: evaluate(transition(state, action, validate=False)[0], team))
    if len(actions) == 1 or rng.random() < 0.25:
        return rng.choice(actions)

    def priority(action):
        if action.kind == "bait":
            return 2.0 + (2.5 if action.target in state.positions else 0)
        start = state.positions[action.penguin]
        if action.kind == "brace":
            return 1.0 + 1.8 * state.fish[action.target] - (6 if action.target == state.shark else 0)
        use_gap = state.move_counts[action.penguin ^ 1] - state.move_counts[action.penguin]
        tempo = min(2, max(-2, use_gap)) * .42
        return (state.fish[action.target] * 1.8
                + (6 if start == state.shark else 0) - (8 if action.target == state.shark else 0)
                + (1 if start in state.pickups else 0) + tempo)

    return max(rng.choices(actions, k=4), key=priority)


def role_bonus(state, action):
    if action.kind != "move":
        return 0.0
    role = action.penguin
    return max(-3, min(3, state.move_counts[role ^ 1] - state.move_counts[role])) * .021


FROSTFALL = SearchGame(choices, transition, decide_team, evaluate, rollout_action,
                       lambda state: state.seed * 17191 + state.round * 303 + state.turn * 29 + decide_team(state),
                       lambda state: state.rescue < 0, role_bonus)


def mcts(state, simulations, cancelled=lambda: False, *, game=None):
    game = game or FROSTFALL
    started = perf_counter()
    team = game.team(state)
    def make_node(position, action=None):
        actions = list(game.actions(position))
        if game.expansion_priority:
            actions.sort(key=lambda candidate: game.expansion_priority(position, candidate), reverse=True)
        return Node(position, actions, action)

    root = make_node(state)
    rng = Random(game.seed(state))
    for _ in range(simulations):
        if cancelled():
            raise InterruptedError
        node, path = root, [root]
        while node.children and not node.untried:
            sign = 1 if game.team(node.state) == team else -1
            exploration = 2 * log(node.visits)
            node = max(node.children, key=lambda child: sign * child.reward / child.visits
                       + sqrt(exploration / child.visits))
            path.append(node)
        if node.untried:
            count = len(node.untried)
            if game.expansion_priority and rng.random() < .85:
                count = min(count, 6)
            action = node.untried.pop(rng.randrange(count))
            position = game.advance(node.state, action, validate=False)[0]
            child = make_node(position, action)
            node.children.append(child)
            node = child
            path.append(node)

        position = node.state
        for _ in range(28):
            if position.over:
                break
            action = (game.rollout_choice(position, rng) if game.rollout_choice else
                      game.rollout(position, game.actions(position), rng))
            position = game.advance(position, action, validate=False)[0]
        value = game.evaluate(position, team)
        reward = value / 300 if position.over else 0.85 * tanh(value / 55)
        for node in path:
            node.visits += 1
            node.reward += reward

    def final_priority(child):
        return child.visits, child.reward / child.visits + game.final_bonus(state, child.action)

    champion = max(root.children, key=final_priority)
    return Decision(champion.action, simulations, perf_counter() - started)


def search(state, algorithm, difficulty, cancelled=lambda: False):
    depth, simulations = PRESETS[difficulty]
    if algorithm == "Minimax":
        return minimax(state, depth, cancelled)
    return mcts(state, simulations, cancelled)
