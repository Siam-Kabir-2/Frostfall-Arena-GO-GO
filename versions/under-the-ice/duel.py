"""Shared rules for a two-player dive in one cave."""

from collections import deque
from dataclasses import dataclass, replace
from functools import lru_cache


GOAL, AIR, LIVES, ROUND_LIMIT = 8, 10, 2, 24
TEAMS = ("Coral", "Azure")
AIR_VENTS = (0, 1)
PASS = -1

# World coordinates lie on the dive plane. Edges are swim lanes, not ice tiles.
POINTS = ((-10.65, 3.38), (10.65, 3.38), (-10.65, 1.05), (10.65, 1.05),
          (-7.1, .65), (7.1, .65), (-10.05, -2.16), (10.05, -2.16),
          (-6.55, -2.7), (6.55, -2.7), (-9.1, -5.25), (9.1, -5.25),
          (-4.7, -5.63), (4.7, -5.63), (-3.4, .88), (3.4, .88),
          (-3.05, -2.45), (3.05, -2.45), (0, .88), (0, -2.28), (0, -5.22))
NAMES = ("West air", "East air", "West mouth", "East mouth", "West shelf", "East shelf",
         "West pocket", "East pocket", "West channel", "East channel", "West basin", "East basin",
         "West trench", "East trench", "West ledge", "East ledge", "West arch", "East arch",
         "Crown", "Deepfin bend", "Deep seam")
EDGES = ((0, 1), (0, 2), (1, 3), (2, 4), (3, 5), (2, 6), (3, 7), (4, 6), (5, 7),
         (4, 8), (5, 9), (4, 14), (5, 15), (6, 8), (7, 9), (6, 10), (7, 11),
         (8, 10), (9, 11), (8, 12), (9, 13), (8, 16), (9, 17), (10, 12), (11, 13),
         (12, 16), (13, 17), (12, 20), (13, 20), (14, 16), (15, 17), (14, 18), (15, 18),
         (16, 19), (17, 19), (18, 19), (19, 20))
NEIGHBORS = tuple(tuple(b if a == cell else a for a, b in EDGES if cell in (a, b))
                  for cell in range(len(POINTS)))
FISH = (0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 2, 2, 1, 1, 1, 1, 2, 2, 2, 0, 3)
START_FISH = sum(1 << cell for cell, amount in enumerate(FISH) if amount)
PATROL = (19, 16, 12, 20, 13, 17, 18, 8, 9)


def distances(start):
    costs = {start: 0}
    queue = deque([start])
    while queue:
        cell = queue.popleft()
        for target in NEIGHBORS[cell]:
            if target not in costs:
                costs[target] = costs[cell]+1
                queue.append(target)
    return tuple(costs[cell] for cell in range(len(POINTS)))


DISTANCE = tuple(distances(cell) for cell in range(len(POINTS)))
TO_AIR = tuple(min(DISTANCE[cell][vent] for vent in AIR_VENTS) for cell in range(len(POINTS)))


@dataclass(frozen=True, slots=True)
class State:
    seed: int = 0
    positions: tuple[int, int] = AIR_VENTS
    air: tuple[int, int] = (AIR, AIR)
    lives: tuple[int, int] = (LIVES, LIVES)
    cargo: tuple[int, int] = (0, 0)
    scores: tuple[int, int] = (0, 0)
    fish: int = START_FISH
    active: int = 0
    round: int = 1
    turn: int = 0
    over: bool = False
    winner: int = -1
    reason: str = ""

    @property
    def warning(self):
        return PATROL[(self.seed + self.round - 1) % len(PATROL)]

    @property
    def seal(self):
        return PATROL[(self.seed + self.round - 2) % len(PATROL)]


@lru_cache(maxsize=8192)
def count_fish(mask):
    return sum(amount for cell, amount in enumerate(FISH) if mask & (1 << cell))


def change(pair, team, value):
    return (value, pair[1]) if team == 0 else (pair[0], value)


def choices(state):
    if state.over:
        return ()
    pawn, rival = state.positions[state.active], state.positions[1-state.active]
    return tuple(cell for cell in NEIGHBORS[pawn] if cell in AIR_VENTS or cell != rival) or (PASS,)


def rescue(state, team):
    return replace(state, positions=change(state.positions, team, AIR_VENTS[team]),
                   air=change(state.air, team, AIR), lives=change(state.lives, team, state.lives[team]-1),
                   cargo=change(state.cargo, team, 0), fish=state.fish | state.cargo[team])


def finish_on_fish(state, reason):
    coral, azure = state.scores
    return replace(state, over=True, winner=-1 if coral == azure else int(azure > coral), reason=reason)


def advance(state, action, *, validate=True):
    if validate and action not in choices(state):
        raise ValueError(f"Illegal destination {action}")
    team = state.active
    result = state
    events = []
    if action != PASS:
        result = replace(result, positions=change(result.positions, team, action))
        if action in AIR_VENTS:
            score = count_fish(result.cargo[team])
            result = replace(result, scores=change(result.scores, team, result.scores[team]+score),
                             cargo=change(result.cargo, team, 0), air=change(result.air, team, AIR))
            if score and validate:
                events.append(f"{TEAMS[team]} banked {score} fish")
        else:
            catch = result.fish & (1 << action)
            result = replace(result, air=change(result.air, team, result.air[team]-1),
                             cargo=change(result.cargo, team, result.cargo[team] | catch), fish=result.fish ^ catch)
            if catch and validate:
                events.append(f"{TEAMS[team]} caught {FISH[action]} fish at {NAMES[action]}")
    elif result.positions[team] not in AIR_VENTS:
        result = replace(result, air=change(result.air, team, result.air[team]-1))

    if result.scores[team] >= GOAL:
        return replace(result, over=True, winner=team, reason=f"Banked {GOAL} fish"), tuple(events)
    if result.air[team] == 0 and result.positions[team] not in AIR_VENTS:
        result = rescue(result, team)
        if validate:
            events.append(f"{TEAMS[team]} ran out of air and dropped the catch")

    if state.turn:
        for side, position in enumerate(result.positions):
            if position == state.warning:
                result = rescue(result, side)
                if validate:
                    events.append(f"Deepfin caught {TEAMS[side]} at {NAMES[position]}")
    if min(result.lives) <= 0:
        result = (finish_on_fish(result, "Both divers ran out of lives") if max(result.lives) <= 0 else
                  replace(result, over=True, winner=int(result.lives[1] > 0), reason="Rival ran out of lives"))
    elif result.fish == 0 and not any(result.cargo):
        result = finish_on_fish(result, "All fish banked")
    elif state.round >= ROUND_LIMIT and state.turn:
        result = finish_on_fish(result, "Round limit reached")
    else:
        result = replace(result, active=1-team, turn=1-state.turn, round=state.round+state.turn)
    return result, tuple(events)
