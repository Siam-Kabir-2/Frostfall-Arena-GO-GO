"""Shared combat movement on a half-tile navigation grid."""

from functools import lru_cache
from heapq import heappop, heappush
from math import hypot, sqrt

DIAGONAL = sqrt(2)
NEIGHBORS = ((1, 0), (0, -1), (0, 1), (-1, 0), (1, -1), (1, 1), (-1, -1), (-1, 1))


def octile(a, b):
    x, y = abs(a[0]-b[0]), abs(a[1]-b[1])
    return max(x, y)+(DIAGONAL-1)*min(x, y)


@lru_cache(maxsize=4096)
def astar(start, goal, columns, rows, occupied):
    """Return the first waypoint of the lowest-cost route to the chosen position."""
    if start == goal:
        return goal
    frontier = [(octile(start, goal), 0., start)]
    costs = {start: 0.}
    parents = {}
    while frontier:
        _, cost, cell = heappop(frontier)
        if cost != costs[cell]:
            continue
        if cell == goal:
            while parents[cell] != start:
                cell = parents[cell]
            return cell
        for dx, dy in NEIGHBORS:
            next_cell = cell[0]+dx, cell[1]+dy
            if not (0 <= next_cell[0] < columns and 0 <= next_cell[1] < rows):
                continue
            # Occupied cells can be crossed, but there is usually a better route around a teammate.
            step = DIAGONAL if dx and dy else 1.
            travel = cost + step + (2.1 if next_cell in occupied and next_cell != goal else 0.)
            if travel < costs.get(next_cell, float("inf")):
                costs[next_cell] = travel
                parents[next_cell] = cell
                heappush(frontier, (travel+octile(next_cell, goal), travel, next_cell))
    return goal


def combat_destination(unit, target, friends, speed, columns, rows):
    """Pick a firing position in range and steer along its A* route."""
    def local(x):
        return round(x if unit.side == 0 else columns-x, 8)

    def cell(x, y):
        return (min(columns*2-1, max(0, int(x*2))), min(rows*2-1, max(0, int(y*2))))

    x, y = local(unit.x), unit.y
    tx, ty = local(target.x), target.y
    reach = hypot(tx-x, ty-y)
    gap = max(0., reach-unit.hero.reach*.87)
    destination = x+(tx-x)*gap/reach, y+(ty-y)*gap/reach
    start, goal = cell(x, y), cell(*destination)
    occupied = frozenset(cell(local(ally.x), ally.y) for ally in friends if ally is not unit)
    waypoint = astar(start, goal, columns*2, rows*2, occupied)
    if waypoint != goal:
        destination = (waypoint[0]+.5)/2, (waypoint[1]+.5)/2
    step_x, step_y = destination[0]-x, destination[1]-y
    length = hypot(step_x, step_y)
    scale = min(1., speed/length) if length else 0.
    result_x = x+step_x*scale
    return (result_x if unit.side == 0 else columns-result_x), y+step_y*scale
