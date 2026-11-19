"""Pathfinding to open attack positions on the arena's visible tile grid."""

from functools import lru_cache
from heapq import heappop, heappush
from math import floor, hypot, sqrt

DIAGONAL = sqrt(2)
NEIGHBORS = ((1, 0), (0, -1), (0, 1), (-1, 0), (1, -1), (1, 1), (-1, -1), (-1, 1))


def tile_at(x, y):
    return floor(x), floor(y)


def tile_center(cell):
    return cell[0]+.5, cell[1]+.5


def on_board(cell, columns, rows):
    return 0 <= cell[0] < columns and 0 <= cell[1] < rows


def adjacent(cell):
    return ((cell[0]+dx, cell[1]+dy) for dx, dy in NEIGHBORS)


@lru_cache(maxsize=16384)
def astar(start, target, reach, columns, rows, occupied, previous=None):
    """Return the first step to a free tile in range of target, or None."""
    def estimate(cell):
        return max(0., hypot(cell[0]-target[0], cell[1]-target[1])-reach)

    remaining = estimate(start)
    frontier = [(remaining, remaining, 0., start)]
    costs = {start: 0.}
    first_steps = {start: None}
    while frontier:
        _, remaining, cost, cell = heappop(frontier)
        if cost != costs[cell]:
            continue
        if remaining == 0:
            return first_steps[cell]
        for neighbor in adjacent(cell):
            if neighbor in occupied or not on_board(neighbor, columns, rows):
                continue
            diagonal = neighbor[0] != cell[0] and neighbor[1] != cell[1]
            if diagonal and ((neighbor[0], cell[1]) in occupied or (cell[0], neighbor[1]) in occupied):
                continue
            travel = cost + (DIAGONAL if diagonal else 1.)
            if cell == start and neighbor == previous:
                travel += 1.25
            if travel < costs.get(neighbor, float("inf")):
                costs[neighbor] = travel
                first_steps[neighbor] = first_steps[cell] or neighbor
                remaining = estimate(neighbor)
                heappush(frontier, (travel+remaining, remaining, travel, neighbor))
    return None


def combat_destination(unit, target, occupied, columns, rows):
    # Normalize both teams to left-to-right so mirror matches get the same tie-breaking.
    def local(cell):
        return (columns-1-cell[0], cell[1]) if unit.side else cell

    start = tile_at(unit.x, unit.y)
    blocked = {local(cell) for cell in occupied if cell != start}
    if unit.avoid is not None:
        blocked.add(local(unit.avoid))
    previous = local(unit.previous_tile) if unit.previous_tile is not None else None
    step = astar(local(start), local(tile_at(target.x, target.y)), unit.reach,
                 columns, rows, frozenset(blocked), previous)
    return local(step) if step is not None else None
