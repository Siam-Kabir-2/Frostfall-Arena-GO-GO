"""Autonomous diver that uses the same movement and air limits as a player."""

from math import dist

from pygame.math import Vector2

from cave import AIR, GOAL, SWIM_SPEED, VENTS, infer_exit, segment_distance
from dive import current


class Pilot:
    def __init__(self):
        self.returning = False
        self.target = None
        self.route = None
        self.route_age = 0.
        self.waypoint = 1
        self.exit_index = 0
        self.explored = 0
        self.return_distances = {}

    def direction(self, game, dt):
        if not game.underwater:
            self.returning = False
            self.target = self.route = None
            self.route_age = 0.
            return self.on_surface(game)

        self.route_age -= dt
        if self.route_age <= 0 or (self.target is not None and self.target not in game.available):
            self.plan(game)
            self.waypoint = 1
            self.route_age = .28
        if self.route is None:
            delta = Vector2(VENTS[game.vent], game.cave.ends[game.vent][1])-game.position
        else:
            points = self.route.points
            while self.waypoint < len(points)-1 and game.position.distance_to(points[self.waypoint]) <= 15:
                self.waypoint += 1
            delta = Vector2(points[self.waypoint])-game.position
        if self.returning and game.cave.opening(game.position.x) == self.exit_index and game.position.y < 322:
            delta.y = min(delta.y, -30)
        steer = delta / max(22, delta.length())
        steer.x -= current(game.position.y)/SWIM_SPEED
        return steer.normalize() if steer.length_squared() > 1 else steer

    @staticmethod
    def on_surface(game):
        if not game.available:
            return Vector2()
        def opening_cost(index):
            spot = game.cave.ends[index]
            fish = sorted(dist(game.cave.fish[i], spot) for i in game.available)
            return sum(fish[:3])/min(3, len(fish)) + .45*abs(game.position.x-spot[0])

        opening = min(range(len(VENTS)), key=opening_cost)
        dx = VENTS[opening]-game.position.x
        if abs(dx) > 6:
            return Vector2(max(-1., min(1., dx/19)), 0)
        return Vector2(0, 1) if game.air >= AIR-.2 else Vector2()

    def swim_home(self, game, routes):
        self.returning = True
        self.target = None
        exit_index, _ = infer_exit(routes, game.seal, game.air)
        if exit_index is not None:
            self.exit_index = exit_index
            game.vent = exit_index
            self.route = routes[exit_index]
        else:
            self.route = None

    def plan(self, game):
        cave = game.cave
        exits = tuple(cave.route(game.position, index, game.greedy) for index in range(len(VENTS)))
        self.explored += sum(route.expanded for route in exits if route)
        home = min((route.length for route in exits if route), default=800)
        worth_banking = game.banked+len(game.haul) >= GOAL or len(game.haul) >= 5
        if self.returning or worth_banking or game.air < home/(SWIM_SPEED*.75)+1.45:
            self.swim_home(game, exits)
            return

        candidates = sorted(game.available, key=lambda index: dist(game.position, cave.fish[index]))[:7]
        best = None
        for index in candidates:
            target = cave.fish[index]
            route = cave.route_to(game.position, target, greedy=game.greedy)
            if route is None:
                continue
            self.explored += route.expanded
            key = index, game.greedy
            if key not in self.return_distances:
                home_routes = [cave.route(target, opening, game.greedy) for opening in range(len(VENTS))]
                self.explored += sum(path.expanded for path in home_routes if path)
                self.return_distances[key] = min((path.length for path in home_routes if path), default=800)
            if (route.length+self.return_distances[key])/(SWIM_SPEED*.75)+1.30 >= game.air:
                continue
            nearest_seal = min(segment_distance(game.seal, start, end)
                               for start, end in zip(route.points, route.points[1:]))
            danger = max(0, 153-nearest_seal)*2.1
            cost = route.length + danger - (20 if index == self.target else 0)
            if best is None or cost < best[0]:
                best = cost, index, route
        if best is None or (game.haul and best[0] > 310):
            self.swim_home(game, exits)
        else:
            _, self.target, self.route = best
