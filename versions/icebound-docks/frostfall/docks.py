"""Rules for a two-penguin turn on the Icebound Docks board."""

from dataclasses import dataclass, replace
from random import Random

from .rules import CELLS, ROLES, TEAMS, Action, Event, State, destinations, label, land, set_item


DOCK_NAMES = ("West", "Harbor", "East")
DOCKS = ((25,), (51, 52), (30,))
DOCK_INDEX = {cell: dock for dock, cells in enumerate(DOCKS) for cell in cells}
OPENING = (9, 32, 14, 39)
GAPS = frozenset({0, 7, 11, 12, 40, 47, 56, 63})
ROUND_LIMIT = 12

# Each pair has two marked routes. The middle dock has two entrances but one flag.
LINKS = (
    (0, 1, ((25, 33, 41, 49, 50, 51), (25, 26, 34, 35, 43, 51))),
    (0, 2, ((25, 26, 27, 28, 29, 30), (25, 17, 18, 19, 20, 21, 22, 30))),
    (1, 2, ((52, 53, 54, 46, 38, 30), (52, 44, 36, 37, 29, 30))),
)


@dataclass(frozen=True, slots=True)
class DockState(State):
    owners: tuple[int, int, int] = (-1, -1, -1)
    pending: int = -1
    passes: int = 0


@dataclass(frozen=True, slots=True)
class Turn:
    defender: Action | None = None
    attacker: Action | None = None


def new_match(seed, first=0):
    rng = Random(seed)
    fish = [0] * len(CELLS)
    bare = frozenset((*OPENING, *DOCK_INDEX))
    for row in range(8):
        for col in range(4):
            cell, mirror = row * 8 + col, row * 8 + 7 - col
            if cell not in GAPS and cell not in bare:
                fish[cell] = fish[mirror] = rng.choices((1, 2, 3), (5, 3, 2))[0]
    return DockState(seed, False, first, tuple(fish), positions=OPENING, active=first, empty_ice=bare)


def open_routes(state, routes):
    return tuple(route for route in routes if all(map(state.has_ice, route)))


def linked_pair(state, team):
    return next(((a, b) for a, b, routes in LINKS
                 if state.owners[a] == state.owners[b] == team and open_routes(state, routes)), None)


def defender_moves(state):
    piece = state.active * 2 + 1
    targets = tuple(destinations(state, piece))
    slides = tuple(Action("move", piece, cell) for cell in targets)
    if state.brace_used[state.active] or state.positions[piece] in DOCK_INDEX:
        return slides
    return slides + tuple(Action("brace", piece, cell) for cell in targets)


def attacker_moves(state):
    piece = state.active * 2
    return tuple(Action("move", piece, cell) for cell in destinations(state, piece))


def slide(state, action):
    if action is None:
        return state
    origin = state.positions[action.penguin]
    if action.kind == "brace":
        state = replace(state, brace_used=set_item(state.brace_used, state.active, True))
    elif origin not in DOCK_INDEX:
        state = replace(state, fish=set_item(state.fish, origin, 0), empty_ice=state.empty_ice - {origin})
    state = land(state, action.penguin, action.target)
    if action.penguin % 2 == 0 and action.target in DOCK_INDEX:
        state = replace(state, owners=set_item(state.owners, DOCK_INDEX[action.target], state.active))
    return state


def legal_turns(state):
    if state.over:
        return ()
    turns = []
    for defender in defender_moves(state) or (None,):
        shifted = slide(state, defender)
        turns.extend(Turn(defender, attacker) for attacker in attacker_moves(shifted) or (None,))
    return tuple(turns)


def score_result(state, reason):
    coral, azure = state.scores
    winner = -1 if coral == azure else int(azure > coral)
    return replace(state, over=True, winner=winner, reason=reason, pending=-1)


def advance(state, turn, *, validate=True):
    if validate and (state.over or turn.defender not in (defender_moves(state) or (None,))):
        raise ValueError(f"Illegal Defender move in {turn}")
    middle = slide(state, turn.defender)
    if validate and turn.attacker not in (attacker_moves(middle) or (None,)):
        raise ValueError(f"Illegal Attacker move in {turn}")
    result = slide(middle, turn.attacker)
    passes = state.passes + 1 if turn == Turn() else 0
    if state.pending >= 0 and linked_pair(result, state.pending):
        result = replace(result, over=True, winner=state.pending, pending=-1,
                         reason="Held two linked docks through the reply")
    elif passes == 2:
        result = score_result(result, "Both teams trapped. Fish decide.")
    elif not any(open_routes(result, routes) for _, _, routes in LINKS):
        result = score_result(result, "All links broken. Fish decide.")
    else:
        pending = state.active if linked_pair(result, state.active) else -1
        if state.round > ROUND_LIMIT or (state.round == ROUND_LIMIT and state.turn and pending < 0):
            result = score_result(result, "Round limit reached. Fish decide.")
        else:
            result = replace(result, active=1 - state.active, pending=pending, passes=passes,
                             round=state.round + state.turn, turn=1 - state.turn)
    if not validate:
        return result, ()

    events = []
    for before, after, action in ((state, middle, turn.defender), (middle, result, turn.attacker)):
        if action is None:
            continue
        origin = before.positions[action.penguin]
        fish = before.fish[action.target]
        catch = f" +{fish} fish" if fish else ""
        role = ROLES[action.penguin % 2]
        verb = "braced and slid" if action.kind == "brace" else "slid"
        events.append(Event(action.kind, f"{role} {verb} to {label(action.target)}.{catch}",
                            (origin, action.target), state.active))
        if before.owners != after.owners:
            dock = DOCK_NAMES[DOCK_INDEX[action.target]]
            events.append(Event("dock", f"{TEAMS[state.active]} claimed {dock}.", (action.target,), state.active))
    if turn == Turn():
        events.append(Event("pass", f"{TEAMS[state.active]} has no legal slide."))
    if result.over:
        events.append(Event("result", result.reason, team=result.winner))
    elif result.pending >= 0:
        events.append(Event("hold", f"{TEAMS[result.pending]} must hold through the next turn.", team=result.pending))
    return result, tuple(events)
