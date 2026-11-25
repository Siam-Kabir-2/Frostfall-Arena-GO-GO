"""Rules for paired moves, contested guard zones, and fishing through ice."""

from dataclasses import dataclass, replace

from .rules import (ADJACENT, ADVENTURE_GOAL, ROLES, TEAMS, Action, Event, State,
                    destinations, label, land, new_match as arena_match, safe_neighbors)


FISH_GOAL = ADVENTURE_GOAL
ROUND_LIMIT = 24


@dataclass(frozen=True, slots=True)
class GuardState(State):
    cracked: frozenset[int] = frozenset()


@dataclass(frozen=True, slots=True)
class Turn:
    defender: Action | None = None
    attacker: Action | None = None


def new_match(seed, first=0):
    base = arena_match(seed, adventure=False, first=first)
    return GuardState(seed, False, first, base.fish, active=first, empty_ice=base.empty_ice)


def zones(state):
    """Return exclusive Coral, exclusive Azure, and contested tiles."""
    coral, azure = (frozenset(cell for cell in ADJACENT[state.positions[piece]] if state.has_ice(cell))
                    for piece in (1, 3))
    return coral - azure, azure - coral, coral & azure


def defender_moves(state):
    piece = state.active * 2 + 1
    # Every adjacent floe is already in this Defender's own guard.
    return tuple(Action("move", piece, cell) for cell in safe_neighbors(state, piece))


def attacker_moves(state):
    piece = state.active * 2
    denied = zones(state)[1 - state.active]
    # A guard forbids landing. Physical obstacles still stop the whole glide.
    return tuple(Action("move", piece, cell) for cell in destinations(state, piece) if cell not in denied)


def slide(state, action):
    if action is None:
        return state
    piece, target = action.penguin, action.target
    if piece % 2:
        positions = state.positions[:piece] + (target,) + state.positions[piece+1:]
        return replace(state, positions=positions)
    origin = state.positions[piece]
    result = land(state, piece, target)
    if origin in state.cracked:
        result = replace(result, empty_ice=result.empty_ice - {origin})
    cracked = state.cracked - {origin}
    if state.fish[target]:
        cracked |= {target}
    return replace(result, cracked=cracked)


def legal_turns(state):
    if state.over:
        return ()
    return tuple(Turn(defender, attacker)
                 for defender in (*defender_moves(state), None)
                 for attacker in attacker_moves(slide(state, defender)) or (None,))


def physical_moves(state, team):
    return bool(safe_neighbors(state, team * 2 + 1) or next(destinations(state, team * 2), None) is not None)


def final_score(state, reason):
    a, b = state.scores
    return replace(state, over=True, winner=-1 if a == b else int(b > a), reason=reason)


def advance(state, turn, *, validate=True):
    if validate and (state.over or (turn.defender is not None and turn.defender not in defender_moves(state))):
        raise ValueError(f"Illegal Defender move in {turn}")
    middle = slide(state, turn.defender)
    if validate and turn.attacker not in (attacker_moves(middle) or (None,)):
        raise ValueError(f"Illegal Attacker move in {turn}")
    result = slide(middle, turn.attacker)
    team, rival = state.active, 1 - state.active
    if result.scores[team] >= FISH_GOAL:
        result = replace(result, over=True, winner=team, reason=f"Reached {FISH_GOAL} fish")
    elif not physical_moves(result, rival):
        if physical_moves(result, team):
            result = replace(result, over=True, winner=team, reason=f"{TEAMS[rival]} is trapped")
        else:
            result = final_score(result, "Both teams trapped. Fish decide.")
    elif not any(result.fish):
        result = final_score(result, "All fish collected. Fish decide.")
    elif state.round == ROUND_LIMIT and state.turn:
        result = final_score(result, "Round limit reached. Fish decide.")
    else:
        result = replace(result, active=rival, round=state.round + state.turn, turn=1 - state.turn)
    if not validate:
        return result, ()

    events = []
    if turn.defender is not None:
        target = turn.defender.target
        events.append(Event("move", f"{TEAMS[team]} Defender guards from {label(target)}.",
                            (state.positions[team*2+1], target), team))
    if turn.attacker is not None:
        start, target = state.positions[team*2], turn.attacker.target
        fish = middle.fish[target]
        catch = f" +{fish} fish. Ice cracked." if fish else ""
        events.append(Event("move", f"{TEAMS[team]} {ROLES[0]} slid to {label(target)}.{catch}", (start, target), team))
        if start in state.cracked:
            events.append(Event("strike", f"Cracked ice at {label(start)} sank.", (start,), team))
    if not events:
        events.append(Event("pass", f"{TEAMS[team]} holds position."))
    if result.over:
        events.append(Event("result", result.reason, team=result.winner))
    return result, tuple(events)
