"""Fish Heist rules on a public, deterministic 6×6 board."""

from dataclasses import dataclass, replace
from random import Random

SIZE = 6
GOAL = 8
CAPACITY = 4
ROUNDS = 12
DOCKS = (12, 23)
DIRECTIONS = ((-1, 0), (0, -1), (0, 1), (1, 0))


@dataclass(frozen=True, slots=True)
class Move:
    kind: str
    target: int


@dataclass(frozen=True, slots=True)
class Heist:
    seed: int
    fish: tuple[int, ...]
    positions: tuple[int, int] = DOCKS
    carry: tuple[int, int] = (0, 0)
    bank: tuple[int, int] = (0, 0)
    active: int = 0
    ply: int = 0
    over: bool = False
    winner: int = -1

    @property
    def round(self):
        return min(ROUNDS, self.ply // 2 + 1)


@dataclass(frozen=True, slots=True)
class Recap:
    caught: int = 0
    banked: int = 0
    spilled: int = 0
    rival_banked: int = 0


def new_heist(seed, first=0):
    rng = Random(seed)
    fish = [0] * (SIZE * SIZE)
    # Mirror once across the center. The six rich schools sit in contested water.
    for cell, amount in ((14, 3), (15, 2), (8, 2), (7, 1), (10, 1), (13, 1), (2, 1)):
        fish[cell] = fish[35 - cell] = amount
    for cell in rng.sample((0, 1, 3, 4, 5, 6, 9, 11, 16, 17), 3):
        fish[cell] = fish[35 - cell] = 1
    return Heist(seed, tuple(fish), active=first)


def cell_label(cell):
    row, col = divmod(cell, SIZE)
    return f"{'ABCDEF'[col]}{row + 1}"


def distance(first, second):
    row, col = divmod(first, SIZE)
    other_row, other_col = divmod(second, SIZE)
    return abs(row - other_row) + abs(col - other_col)


def display_cell(cell):
    row, col = divmod(cell, SIZE)
    return (row + 1) * 8 + col + 1


def board_cell(cell):
    if cell is None:
        return None
    row, col = divmod(cell, 8)
    if 1 <= row <= 6 and 1 <= col <= 6:
        return (row - 1) * SIZE + col - 1
    return None


def on_board(row, col):
    return 0 <= row < SIZE and 0 <= col < SIZE


def legal(state):
    if state.over:
        return ()
    team = state.active
    rival = 1 - team
    start, other = state.positions[team], state.positions[rival]
    row, col = divmod(start, SIZE)
    moves = []
    for dy, dx in DIRECTIONS:
        for step in range(1, 4):
            y, x = row + dy * step, col + dx * step
            if not on_board(y, x):
                break
            cell = y * SIZE + x
            if cell == other or cell == DOCKS[rival]:
                if step == 1 and cell == other and cell != DOCKS[rival] and on_board(y + dy, x + dx):
                    pushed = (y + dy) * SIZE + x + dx
                    if pushed != DOCKS[team]:
                        moves.append(Move("bump", pushed))
                break
            moves.append(Move("skate", cell))
    return tuple(moves)


def path(first, last):
    row, col = divmod(first, SIZE)
    y, x = divmod(last, SIZE)
    step_y, step_x = (y > row) - (y < row), (x > col) - (x < col)
    for step in range(1, abs(y - row) + abs(x - col) + 1):
        yield (row + step_y * step) * SIZE + col + step_x * step


def advance(state, action, *, validate=True):
    """Play one legal action and return the new position plus scoring details."""
    if validate and action not in legal(state):
        raise ValueError(f"Illegal Heist action {action}")
    team, rival = state.active, 1 - state.active
    positions, carry, bank, fish = map(list, (state.positions, state.carry, state.bank, state.fish))
    caught = banked = spilled = rival_banked = 0
    if action.kind == "skate":
        for cell in path(positions[team], action.target):
            grab = min(CAPACITY - carry[team], fish[cell])
            carry[team] += grab
            fish[cell] -= grab
            caught += grab
        positions[team] = action.target
        if action.target == DOCKS[team]:
            banked = carry[team]
            bank[team] += banked
            carry[team] = 0
    else:
        if carry[rival]:
            carry[rival] -= 1
            fish[positions[rival]] += 1
            spilled = 1
        positions[rival] = action.target
        if action.target == DOCKS[rival]:
            rival_banked = carry[rival]
            bank[rival] += rival_banked
            carry[rival] = 0
    ply = state.ply + 1
    over = max(bank) >= GOAL or ply >= ROUNDS * 2
    winner = (int(bank[1] > bank[0]) if bank[0] != bank[1] else -1) if over else -1
    position = replace(state, fish=tuple(fish), positions=tuple(positions), carry=tuple(carry),
                       bank=tuple(bank), active=rival, ply=ply, over=over, winner=winner)
    return position, Recap(caught, banked, spilled, rival_banked)

