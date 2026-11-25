"""Constraint-generated cave geometry and graph searches for the lookout."""

from dataclasses import dataclass
from heapq import heappop, heappush
from math import ceil, dist
from random import Random

from pygame import Rect


WIDTH, HEIGHT = 1280, 800
LEFT, RIGHT, WATERLINE, FLOOR = 34, 1246, 278, 713
VENTS = (236, 1044)
VENT_HALF = 64
BODY = 16
GOAL = 11
AIR = 15.5
SWIM_SPEED = 238
EXIT_Y = WATERLINE + BODY + 1

OBSTACLES = {
    "roof": ((537, 278, 178, 106), (513, 278, 205, 83), (588, 278, 180, 92)),
    "west ridge": ((363, 626, 162, 87), (322, 654, 203, 59), (420, 603, 138, 110)),
    "east ridge": ((765, 590, 166, 123), (802, 608, 166, 105), (720, 625, 185, 88)),
}
RACE_REEFS = ((152, 351, 169, 58), (959, 360, 172, 45), (443, 520, 324, 36))
SHOALS = {
    "west": (((259, 390), (322, 409), (214, 461)), 3),
    "midwater": (((437, 504), (480, 458), (527, 527)), 3),
    "deep west": (((243, 602), (311, 570), (346, 601)), 4),
    "east": (((1011, 409), (965, 458), (1100, 396)), 3),
    "deep east": (((1026, 596), (1096, 551), (947, 626)), 4),
    "middle": (((638, 610), (702, 543), (661, 477)), 3),
}


def solve_layout(seed):
    rng = Random(seed)
    domains = {name: list(options) for name, options in OBSTACLES.items()}
    domains.update((name, list(options)) for name, (options, _) in SHOALS.items())
    for options in domains.values():
        rng.shuffle(options)
    examined = removed = 0

    def compatible(first, point, second, other):
        if first in OBSTACLES and second in OBSTACLES:
            return not Rect(point).inflate(73, 73).colliderect(Rect(other))
        if first in OBSTACLES:
            return not Rect(point).inflate(118, 100).collidepoint(other)
        if second in OBSTACLES:
            return not Rect(other).inflate(118, 100).collidepoint(point)
        return dist(point, other) >= 120

    def choose(remaining):
        nonlocal examined, removed
        if not remaining:
            return {}
        name = min(remaining, key=lambda key: len(remaining[key]))
        for point in remaining[name]:
            examined += 1
            next_domains = {}
            for other, values in remaining.items():
                if other != name:
                    viable = [value for value in values if compatible(name, point, other, value)]
                    removed += len(values)-len(viable)
                    if not viable:
                        break
                    next_domains[other] = viable
            else:
                found = choose(next_domains)
                if found is not None:
                    return {name: point, **found}
        return None

    result = choose(domains)
    if result is None:
        raise ValueError("The cave layout has no legal arrangement")
    return result, examined, removed


@dataclass(frozen=True, slots=True)
class Route:
    points: tuple
    length: float
    expanded: int


class Cave:
    def __init__(self, seed, *, race=False):
        self.seed = seed
        layout, self.examined, self.pruned = solve_layout(seed)
        self.rocks = tuple(Rect(layout[name]) for name in OBSTACLES)
        if race:
            self.rocks += tuple(Rect(reef) for reef in RACE_REEFS)
        offsets = ((-29, 5), (0, -14), (27, 10), (48, -16))
        self.fish = tuple((layout[name][0]+dx, layout[name][1]+dy)
                          for name, (_, number) in SHOALS.items() for dx, dy in offsets[:number])
        if race:
            fish = [point for point in self.fish if self.clear(*point)]
            # Reefs can cut into generated shoals. Keep enough fish for a finish.
            for x in (108, 1200):
                for y in (455, 509, 563, 617, 668):
                    if len(fish) < GOAL+2 and all(dist((x, y), point) >= 39 for point in fish):
                        fish.append((x, y))
            self.fish = tuple(fish)
        self.ends = tuple((x, EXIT_Y) for x in VENTS)
        columns = range(63, 1221, 57) if race else range(82, 1200, 73)
        rows = (308, 326, 396, 460, 524, 588, 652, 689) if race else range(328, 684, 64)
        self.nodes = self.ends + tuple((x, y) for y in rows for x in columns
                                       if self.clear(x, y, BODY+(3 if race else 2)))
        reach = 128 if race else 133
        self.links = tuple(tuple((other, dist(point, node)) for other, node in enumerate(self.nodes)
                                 if other != index and dist(point, node) <= reach and self.visible(point, node))
                           for index, point in enumerate(self.nodes))

    @staticmethod
    def opening(x):
        return next((i for i, vent in enumerate(VENTS) if abs(vent-x) <= VENT_HALF-BODY), None)

    def clear(self, x, y, radius=BODY):
        if not (LEFT+radius <= x <= RIGHT-radius and WATERLINE+radius <= y <= FLOOR-radius):
            return False
        return all(not (r.left-radius < x < r.right+radius and r.top-radius < y < r.bottom+radius)
                   for r in self.rocks)

    def visible(self, start, end, radius=BODY):
        steps = max(1, ceil(dist(start, end) / 13))
        sx, sy = start
        dx, dy = end[0]-sx, end[1]-sy
        return all(self.clear(sx+dx*step/steps, sy+dy*step/steps, radius) for step in range(steps+1))

    def route(self, start, exit_index, greedy=False):
        return self.search(start, self.ends[exit_index], exit_index, greedy)

    def route_to(self, start, goal, greedy=False):
        return self.search(start, goal, len(self.nodes), greedy)

    def search(self, start, goal, goal_index, greedy):
        if self.visible(start, goal):
            return Route((tuple(start), goal), dist(start, goal), 1)

        frontier, length, prev = [], {}, {}
        links = {} if goal_index < len(self.nodes) else dict(self.visible_nodes(goal))
        for index, cost in self.visible_nodes(start):
            length[index] = cost
            prev[index] = None
            estimate = dist(self.nodes[index], goal)
            heappush(frontier, (estimate if greedy else cost+estimate, cost, index))

        expanded, visited = 0, set()
        while frontier:
            _, cost, node = heappop(frontier)
            if node in visited or cost > length[node]:
                continue
            visited.add(node)
            expanded += 1
            if node == goal_index:
                path = [goal]
                while prev[node] is not None:
                    node = prev[node]
                    path.append(self.nodes[node])
                return Route((tuple(start), *reversed(path)), cost, expanded)
            options = self.links[node]
            if node in links:
                options += ((goal_index, links[node]),)
            for next_node, edge in options:
                candidate = cost+edge
                if next_node in visited or candidate >= length.get(next_node, float("inf")):
                    continue
                length[next_node], prev[next_node] = candidate, node
                estimate = 0. if next_node == goal_index else dist(self.nodes[next_node], goal)
                heappush(frontier, (estimate if greedy else candidate+estimate, candidate, next_node))
        return None

    def visible_nodes(self, point):
        closest = sorted((dist(point, node), index) for index, node in enumerate(self.nodes))[:22]
        return ((index, cost) for cost, index in closest if self.visible(point, self.nodes[index]))


def infer_exit(routes, seal, remaining):
    choices = [(index, route) for index, route in enumerate(routes) if route is not None]
    if not choices:
        return None, "Looking for a clear exit"
    shortest, route = min(choices, key=lambda item: item[1].length)
    safe = [(index, path) for index, path in choices
            if all(segment_distance(seal, start, end) >= 94 for start, end in zip(path.points, path.points[1:]))
            and path.length / (SWIM_SPEED*.82) < remaining]
    if safe:
        best, _ = min(safe, key=lambda item: item[1].length)
        if best != shortest:
            return best, "Deepfin is near the shorter route"
    if route.length / (SWIM_SPEED*.82) + .8 >= remaining:
        return shortest, "Low air. Take the shortest route"
    return shortest, "Lookout marks the nearest exit"


def segment_distance(point, start, end):
    x, y = start
    dx, dy = end[0]-x, end[1]-y
    squared = dx*dx+dy*dy
    if not squared:
        return dist(point, start)
    offset = max(0., min(1., ((point[0]-x)*dx+(point[1]-y)*dy)/squared))
    return dist(point, (x+dx*offset, y+dy*offset))
