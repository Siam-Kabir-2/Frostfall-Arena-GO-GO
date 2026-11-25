"""Immutable match state and the rules shared by the game and both AIs."""

from dataclasses import dataclass, replace
from random import Random

SIZE = 8
CELLS = tuple(range(SIZE * SIZE))
TEAMS = ("Coral", "Azure")
ROLES = ("Attacker", "Defender")
DIRECTIONS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
OPENING = (17, 41, 22, 46)
RESCUE_COST = 2
ADVENTURE_GOAL = 30


def coordinates(cell):
    return divmod(cell, SIZE)


def label(cell):
    row, col = coordinates(cell)
    return f"{'ABCDEFGH'[col]}{row + 1}"


def rays(cell):
    row, col = coordinates(cell)
    result = []
    for dr, dc in DIRECTIONS:
        line = []
        r, c = row + dr, col + dc
        while 0 <= r < SIZE and 0 <= c < SIZE:
            line.append(r * SIZE + c)
            r, c = r + dr, c + dc
        if line:
            result.append(tuple(line))
    return tuple(result)


RAYS = tuple(rays(cell) for cell in CELLS)
ADJACENT = tuple(tuple(ray[0] for ray in group) for group in RAYS)
BAIT_RANGE = tuple(tuple(other for other in CELLS if max(
    abs(cell // SIZE - other // SIZE), abs(cell % SIZE - other % SIZE)) <= 3) for cell in CELLS)


@dataclass(frozen=True, slots=True)
class Action:
    kind: str
    penguin: int = -1
    target: int = -1


PASS = Action("pass")


@dataclass(frozen=True, slots=True)
class Event:
    kind: str
    text: str
    cells: tuple[int, ...] = ()
    team: int = -1


@dataclass(frozen=True, slots=True)
class State:
    seed: int
    adventure: bool
    first: int
    fish: tuple[int, ...]
    positions: tuple[int, int, int, int] = OPENING
    scores: tuple[int, int] = (0, 0)
    move_counts: tuple[int, int, int, int] = (0, 0, 0, 0)
    brace_used: tuple[bool, bool] = (False, False)
    pickups: tuple[int, ...] = ()
    inventory: tuple[bool, bool] = (False, False)
    deployed: tuple[bool, bool] = (False, False)
    markers: tuple[int, int] = (-1, -1)
    active: int = 0
    round: int = 1
    turn: int = 0
    shark: int = -1
    marks: tuple[int, ...] = ()
    frozen: tuple[int, ...] = ()
    rescue: int = -1
    over: bool = False
    winner: int = -1
    reason: str = ""
    empty_ice: frozenset[int] = frozenset()

    def has_ice(self, cell):
        return bool(self.fish[cell]) or cell in self.empty_ice


def set_item(values, index, value):
    return values[:index] + (value,) + values[index + 1:]


def land(state, piece, target, *, penalty=0):
    team = piece // 2
    score = state.scores[team] - penalty + state.fish[target]
    return replace(state, positions=set_item(state.positions, piece, target),
                   fish=set_item(state.fish, target, 0), empty_ice=state.empty_ice | {target},
                   scores=set_item(state.scores, team, score))


def new_match(seed, adventure=True, first=0):
    rng = Random(seed)
    fish = rng.choices((1, 2, 3), (5, 3, 2), k=64)
    pickups = rng.choice(((26, 29), (34, 37), (25, 30), (33, 38))) if adventure else ()
    protected = set(OPENING) | set(pickups)
    for start in OPENING:
        protected.update(ray[0] for ray in RAYS[start] if len(ray) and (
            ray[0] // SIZE == start // SIZE or ray[0] % SIZE == start % SIZE))
    mirror = lambda cell: cell // SIZE * SIZE + (SIZE - 1 - cell % SIZE)
    candidates = [cell for cell in CELLS if cell % SIZE < SIZE // 2
                  and cell not in protected and mirror(cell) not in protected]
    gaps_rng = Random(seed ^ 0xF2057)
    for _ in range(128):
        chosen = gaps_rng.sample(candidates, 4)
        gaps = set(chosen) | {mirror(cell) for cell in chosen}
        ice = set(CELLS) - gaps
        reachable, frontier = {OPENING[0]}, [OPENING[0]]
        while frontier:
            for cell in ADJACENT[frontier.pop()]:
                if cell in ice and cell not in reachable:
                    reachable.add(cell)
                    frontier.append(cell)
        board = tuple(value if cell in ice and cell not in OPENING else 0 for cell, value in enumerate(fish))
        state = State(seed, adventure, first, board, active=first, pickups=pickups,
                      empty_ice=frozenset(OPENING))
        if reachable == ice and all(len(tuple(destinations(state, piece))) >= 7 for piece in range(4)):
            return state
    raise RuntimeError("Could not generate a playable opening for this seed")


def destinations(state, penguin, blocked=None):
    start = state.positions[penguin]
    if start < 0:
        return
    if blocked is None:
        blocked = set(state.positions) | set(state.frozen)
    for ray in RAYS[start]:
        for cell in ray:
            if cell in blocked or not state.has_ice(cell):
                break
            yield cell


def safe_neighbors(state, penguin):
    start = state.positions[penguin]
    blocked = set(state.positions) | set(state.frozen)
    return tuple(cell for cell in ADJACENT[start] if cell not in blocked and state.has_ice(cell))


def bait_round(round_number):
    return round_number % 6 == 2


def moves_for_team(state, team):
    blocked = set(state.positions) | set(state.frozen)
    return tuple(Action("move", piece, cell)
                 for piece in range(team * 2, team * 2 + 2)
                 for cell in destinations(state, piece, blocked))


def bait_actions(state, team):
    if not (state.adventure and bait_round(state.round)
            and state.inventory[team] and not state.deployed[team]):
        return ()
    friendly = state.positions[team * 2:team * 2 + 2]
    blocked = set(friendly) | set(state.frozen)
    return tuple(Action("bait", piece, cell)
                 for piece, start in enumerate(friendly, team * 2) if start >= 0
                 for cell in BAIT_RANGE[start] if cell not in blocked and state.has_ice(cell))


def choices(state):
    if state.over:
        return ()
    if state.rescue >= 0:
        return tuple(Action("rescue", state.rescue, cell) for cell in safe_neighbors(state, state.rescue))
    team = state.active
    moves = moves_for_team(state, team)
    braces = ()
    if state.adventure and not state.brace_used[team]:
        braces = tuple(Action("brace", action.penguin, action.target) for action in moves if action.penguin % 2)
    return moves + bait_actions(state, team) + braces or (PASS,)


def decide_team(state):
    return state.rescue // 2 if state.rescue >= 0 else state.active


def route_traffic(state):
    counts = [0] * 64
    blocked = set(state.positions) | set(state.frozen)
    for piece in range(4):
        for cell in destinations(state, piece, blocked):
            counts[cell] += 1
    return counts


def tie_break(state, cell):
    return ((state.seed + 1) * 2654435761 ^ (state.round * 40503 + cell) * 2246822519) % 4294967291


def shark_target(state):
    occupied = {cell: piece for piece, cell in enumerate(state.positions) if cell >= 0}
    candidates = [cell for cell in CELLS if state.has_ice(cell) and cell not in state.frozen]
    markers = [cell for cell in state.markers if cell in candidates]
    traffic = route_traffic(state)

    def priority(cell):
        near = any(cell in ADJACENT[pos] for pos in occupied)
        # Paths from at least two penguins approximate tactically important ice.
        return (10 * (cell in occupied) + 4 * (traffic[cell] >= 2) + state.fish[cell] + near,
                tie_break(state, cell))

    if not markers:
        candidates = [cell for cell in candidates if cell not in occupied
                      or next(destinations(state, occupied[cell]), None) is not None
                      or safe_neighbors(state, occupied[cell])]
    return max(markers or candidates, key=priority, default=-1)


def next_round(state, events):
    if state.frozen:
        events.append(Event("thaw", "The frozen lanes thawed.", state.frozen))
    state = replace(state, round=state.round + 1, turn=0, active=state.first, frozen=())
    if not state.adventure:
        return state
    if state.round % 6 == 3:
        target = shark_target(state)
        if target >= 0:
            events.append(Event("shark", f"Deepfin marked {label(target)}.", (target,)))
            return replace(state, shark=target)
    if state.round % 6 == 0:
        traffic = route_traffic(state)
        empty = [cell for cell in CELLS if state.has_ice(cell) and cell not in state.positions]
        marks = tuple(sorted(empty, key=lambda cell: (traffic[cell], tie_break(state, cell)), reverse=True)[:2])
        if marks:
            events.append(Event("warden", "The Warden marked " + " and ".join(map(label, marks)) + ".", marks))
            return replace(state, marks=marks)
    return state


def check_end(state, events, *, active_turn=True):
    living = (any(cell >= 0 for cell in state.positions[:2]), any(cell >= 0 for cell in state.positions[2:]))
    winner = -1 if state.scores[0] == state.scores[1] else int(state.scores[1] > state.scores[0])
    if state.adventure and not all(living):
        if any(living):
            winner = living.index(True)
        reason = "Elimination"
    elif state.adventure and max(state.scores) >= ADVENTURE_GOAL:
        reason = f"Reached {ADVENTURE_GOAL} fish"
    elif state.rescue >= 0 or state.shark >= 0 or state.marks or state.frozen or any(
            cell >= 0 for cell in state.markers):
        return state
    else:
        blocked = set(state.positions)
        available = tuple(any(next(destinations(state, piece, blocked), None) is not None
                              for piece in range(team * 2, team * 2 + 2))
                          or bool(bait_actions(state, team)) for team in range(2))
        if not any(available):
            reason = "Final fish count"
        elif active_turn and not available[state.active]:
            winner = 1 - state.active
            reason = f"{TEAMS[state.active]} has no legal move"
        else:
            return state
    title = f"{TEAMS[winner]} wins" if winner >= 0 else "Draw"
    events.append(Event("result", f"{title} · {reason}", team=winner))
    return replace(state, over=True, winner=winner, reason=reason)


def finish_round(state, events, newly_frozen=()):
    # New blocks belong to next round. Old blocks are still in force until then.
    if newly_frozen:
        state = replace(state, frozen=newly_frozen)
        state = check_end(state, events)
        if state.over:
            return state
        return replace(state, round=state.round + 1, turn=0, active=state.first)
    state = check_end(state, events, active_turn=False)
    if state.over:
        return state
    return check_end(next_round(state, events), events)


def transition(state, action, *, validate=True):
    """Return the next position and presentation events for a legal action."""
    if validate and action not in choices(state):
        raise ValueError(f"Illegal action {action}")
    events = []
    team = decide_team(state)
    piece, target = action.penguin, action.target
    name = TEAMS[team]

    if action.kind == "rescue":
        origin = state.positions[piece]
        penalty = min(RESCUE_COST, state.scores[team])
        catch = f" · +{state.fish[target]} fish" if state.fish[target] else ""
        events.append(Event("rescue", f"{name} jumped to {label(target)} · −{penalty} fish{catch}.",
                            (origin, target), team))
        state = replace(land(state, piece, target, penalty=penalty), rescue=-1)
        return finish_round(state, events), tuple(events)

    if action.kind in ("move", "brace"):
        origin = state.positions[piece]
        catch = f" · +{state.fish[target]} fish" if state.fish[target] else ""
        if action.kind == "brace":
            events.append(Event("brace", f"{name}'s Defender braced {label(origin)} and slid to {label(target)}{catch}.",
                                (origin, target), team))
            state = replace(state, brace_used=set_item(state.brace_used, team, True))
        else:
            events.append(Event("move", f"{name} {ROLES[piece % 2].lower()} slid to {label(target)}{catch}.",
                                (origin, target), team))
            pickups, inventory = state.pickups, state.inventory
            if origin in pickups:
                pickups = tuple(cell for cell in pickups if cell != origin)
                if not inventory[team]:
                    inventory = set_item(inventory, team, True)
                    events.append(Event("pickup", f"{name} collected bait.", (origin,), team))
            state = replace(state, pickups=pickups, inventory=inventory,
                            fish=set_item(state.fish, origin, 0), empty_ice=state.empty_ice - {origin})
        state = replace(land(state, piece, target),
                        move_counts=set_item(state.move_counts, piece, state.move_counts[piece] + 1))
        if state.adventure and state.scores[team] >= ADVENTURE_GOAL:
            return check_end(state, events), tuple(events)

    elif action.kind == "bait":
        events.append(Event("bait", f"{name} deployed bait at {label(target)}.", (target,), team))
        state = replace(state, inventory=set_item(state.inventory, team, False),
                        deployed=set_item(state.deployed, team, True),
                        markers=set_item(state.markers, team, target))
    else:
        stalled = check_end(state, events)
        if stalled.over:
            return stalled, tuple(events)
        events.append(Event("pass", f"{name} waits for the field to clear.", team=team))

    if not state.turn:
        upcoming = replace(state, turn=1, active=1 - state.first)
        return check_end(upcoming, events), tuple(events)

    if state.round % 6 == 3 and state.adventure:
        target = state.shark
        state = replace(state, shark=-1, markers=(-1, -1))
        if target >= 0 and state.has_ice(target):
            events.append(Event("strike", f"Deepfin shattered {label(target)}.", (target,)))
            state = replace(state, fish=set_item(state.fish, target, 0), empty_ice=state.empty_ice - {target},
                            pickups=tuple(cell for cell in state.pickups if cell != target))
            if target in state.positions:
                piece = state.positions.index(target)
                if safe_neighbors(state, piece):
                    events.append(Event("danger", f"{TEAMS[piece // 2]} must jump to safe ice.", (target,), piece // 2))
                    return replace(state, rescue=piece), tuple(events)
                events.append(Event("eliminated", f"{TEAMS[piece // 2]} {ROLES[piece % 2].lower()} fell through the ice.",
                                    (target,), piece // 2))
                state = replace(state, positions=set_item(state.positions, piece, -1))
        elif target >= 0:
            events.append(Event("miss", "Deepfin struck open water.", (target,)))

    newly_frozen = tuple(cell for cell in state.marks if state.has_ice(cell) and cell not in state.positions)
    if newly_frozen:
        events.append(Event("freeze", "The marked lanes froze for one round.", newly_frozen))
    state = replace(state, marks=())
    return finish_round(state, events, newly_frozen), tuple(events)
