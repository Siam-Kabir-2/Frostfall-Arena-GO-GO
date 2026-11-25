"""Deterministic downhill racing simulation. Distances are in metres."""

from bisect import bisect_right
from dataclasses import dataclass, replace
from math import cos, pi, sin

HZ = 60
DT = 1 / HZ
LENGTH = 1280
LIMIT = 94
CHECKPOINTS = (0, 152, 389, 473, 727, 861, 1104)
SECTIONS = ((0, "Powder Basin"), (402, "Blue Hollow"), (814, "Knife Edge"))
CURVES = ((0, 0), (105, 1), (215, 30), (339, 12), (463, -38),
          (611, -16), (737, 17), (863, -10), (999, 16), (1116, -11), (1280, 0))
CURVE_STARTS = tuple(point[0] for point in CURVES)


def clamp(value, low=0., high=1.):
    return min(high, max(low, value))


def ease(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


@dataclass(frozen=True)
class Fork:
    name: str
    start: int
    end: int
    side: int
    offset: int
    speed: float
    skill: float
    shutter: int = 0
    deadline: float = 0.

    def spread(self, s):
        return ease((s - self.start) / 48) * ease((self.end - s) / 58)


FORKS = (
    Fork("Powder Cut", 185, 353, 1, 23, 3.8, 4.7),
    Fork("Blue Tunnel", 522, 709, -1, 25, 5.4, 5.3, 588, 34.5),
    Fork("Ridge Drop", 908, 1090, 1, 22, 6.3, 4.1),
)


@dataclass(frozen=True)
class RoughIce:
    start: int
    length: int
    lane: float
    half_width: float

    @property
    def end(self):
        return self.start + self.length


ROUGH_ICE = (RoughIce(113, 16, -3.6, 1.9), RoughIce(394, 17, 2.8, 2.2),
             RoughIce(455, 18, -.9, 2.5), RoughIce(776, 22, -2.4, 2.4),
             RoughIce(855, 15, 2.1, 1.8), RoughIce(1142, 21, .1, 2.5))


def rough_ahead(s, route, distance=0):
    if route < 0:
        return next((patch for patch in ROUGH_ICE if patch.start-distance <= s < patch.end), None)
    return None


def center(s):
    index = min(max(0, bisect_right(CURVE_STARTS, s) - 1), len(CURVES) - 2)
    a, x = CURVES[index]
    b, y = CURVES[index + 1]
    return x + (y - x) * ease((s - a) / (b - a))


def road_x(s, route=-1):
    if route < 0:
        return center(s)
    fork = FORKS[route]
    return center(s) + fork.side * fork.offset * fork.spread(s)


def height(s, route=-1):
    drop = 7 * ease((s - 1000) / 100)
    base = 90 - .054 * s + 1.8 * sin(s / 69) - drop
    if route >= 0:
        fork = FORKS[route]
        clearance = fork.offset * fork.spread(s) - width(s) - width(s, route)
        base -= (1.2, 2.9, 4.1)[route] * ease(clearance / 5)
    return base


def width(s, route=-1):
    main = 12.3 - 3.7 * ease((s - 795) / 115) + 3.7 * ease((s - 1110) / 130)
    if route < 0:
        return main
    fork = FORKS[route]
    return main + (fork.skill - main) * fork.spread(s)


def section(s):
    return next(name for start, name in reversed(SECTIONS) if s >= start)


def avalanche(t):
    return -119 + 17.40 * t + .056 * t * t


@dataclass(frozen=True)
class Control:
    steer: float = 0.
    boost: bool = False
    brake: bool = False


@dataclass(frozen=True)
class Trail:
    owner: int
    s: float
    x: float
    route: int
    tick: int


@dataclass
class Racer:
    name: str
    s: float
    lane: float
    speed: float = 14.
    lateral: float = 0.
    energy: float = .68
    route: int = -1
    next_fork: int = 0
    draft: bool = False
    boosting: bool = False
    rough: bool = False
    recovery: int = 0
    crashes: int = 0
    finished: int = 0
    eliminated: str = ""
    event: str = ""
    event_tick: int = -400

    @property
    def active(self):
        return not self.finished and not self.eliminated

    @property
    def x(self):
        return road_x(self.s, self.route) + self.lane


class Race:
    def __init__(self, names):
        count = len(names)
        self.racers = [Racer(name, -((index // 4) * 4.0) if count > 2 else 0.,
                             ((index % 4) - 1.5) * 4.4 if count > 2 else (-3.3, 3.3)[index])
                       for index, name in enumerate(names)]
        self.tick = 0
        self.trails = {}

    @property
    def time(self):
        return self.tick * DT

    @property
    def danger(self):
        return avalanche(self.time)

    @property
    def done(self):
        return all(not racer.active for racer in self.racers)

    def order(self):
        return sorted(range(len(self.racers)), key=self.rank_key)

    def rank_key(self, index):
        racer = self.racers[index]
        if racer.finished:
            return 0, racer.finished, index
        return (2 if racer.eliminated else 1), -racer.s, index

    def copy(self):
        child = object.__new__(Race)
        child.racers = [replace(racer) for racer in self.racers]
        child.tick = self.tick
        child.trails = {key: values.copy() for key, values in self.trails.items()}
        return child

    def has_draft(self, index, racer):
        cell = int(racer.s // 4)
        x = racer.x
        return any(sample.owner != index and 0 <= self.tick - sample.tick <= 156
                   and abs(sample.s - racer.s) < 3.2 and abs(sample.x - x) < 1.45
                   and sample.route == racer.route
                   for key in (cell - 1, cell, cell + 1) for sample in self.trails.get(key, ()))

    def fail(self, racer, reason):
        index = bisect_right(CHECKPOINTS, racer.s) - 1
        racer.s = CHECKPOINTS[max(0, index)]
        racer.route = -1
        racer.next_fork = bisect_right(tuple(fork.start for fork in FORKS), racer.s)
        if racer.s <= self.danger:
            racer.eliminated = "Caught by the avalanche"
        racer.lane = racer.lateral = 0.
        racer.speed = 8.
        racer.energy *= .66
        racer.recovery = 65
        racer.crashes += 1
        racer.event, racer.event_tick = reason, self.tick

    def step(self, controls):
        if self.done:
            return
        self.tick += 1
        snowfall = self.danger
        elapsed = self.time
        for index, (racer, control) in enumerate(zip(self.racers, controls, strict=True)):
            if not racer.active:
                continue
            self.move(index, racer, control)
            if racer.s >= LENGTH:
                racer.s = LENGTH
                racer.finished = self.tick
            elif racer.s <= snowfall:
                racer.eliminated = "Caught by the avalanche"
            elif elapsed >= LIMIT:
                racer.eliminated = "Out of time"
        if self.tick % 9 == 0:
            for index, racer in enumerate(self.racers):
                if racer.active and racer.recovery == 0:
                    sample = Trail(index, racer.s, racer.x, racer.route, self.tick)
                    self.trails.setdefault(int(racer.s // 4), []).append(sample)
        if self.tick % 36 == 0:
            self.trails = {bucket: fresh for bucket, samples in self.trails.items()
                           if (fresh := [trail for trail in samples if self.tick - trail.tick <= 156])}

    def move(self, index, racer, control):
        racer.draft = racer.boosting = False
        if racer.recovery:
            racer.recovery -= 1
            return
        steer = clamp(control.steer, -1., 1.)
        racer.draft = self.tick > 50 and self.has_draft(index, racer)
        boosting = control.boost and not control.brake and racer.energy >= .013
        racer.boosting = boosting
        charge = (.038 if racer.draft else .010) + (.011 if control.brake else 0)
        racer.energy = clamp(racer.energy + DT * (-.175 if boosting else charge))
        route_speed = FORKS[racer.route].speed * FORKS[racer.route].spread(racer.s) if racer.route >= 0 else 0.
        corner = road_x(racer.s + 17, racer.route) - 2 * road_x(racer.s + 8.5, racer.route) + road_x(racer.s, racer.route)
        grip = (.82 if 462 < racer.s < 720 else 1.) * (1.20 if control.brake else 1.)
        target_lateral = steer * (6.8 if boosting else 7.7) * grip - corner * (.66 if boosting else .42)
        racer.lateral += (target_lateral - racer.lateral) * DT * (4.3 if grip < 1 else 5.8)
        racer.lane += racer.lateral * DT
        patch = rough_ahead(racer.s, racer.route)
        rough = bool(patch and abs(racer.lane - patch.lane) < patch.half_width)
        if rough and not racer.rough:
            racer.event, racer.event_tick = "Rough ice / Speed reduced", self.tick
        racer.rough = rough
        off_center = max(0., abs(racer.lane) / width(racer.s, racer.route) - .64)
        target_speed = (19.8 + route_speed + (3.8 if racer.draft else 0.) + (8.5 if boosting else 0.)
                        - (7.6 if control.brake else 0.) - 1.30 * abs(steer) - off_center * 8 - (7.0 if rough else 0.))
        racer.speed += (target_speed - racer.speed) * DT * (1.5 if control.brake else .94)
        previous = racer.s
        racer.s += racer.speed * DT
        if racer.next_fork < len(FORKS):
            fork = FORKS[racer.next_fork]
            if previous < fork.start <= racer.s:
                if racer.lane * fork.side >= width(fork.start) * .31:
                    racer.route = racer.next_fork
                    racer.event, racer.event_tick = fork.name, self.tick
                racer.next_fork += 1
        if racer.route >= 0:
            fork = FORKS[racer.route]
            if fork.shutter and previous < fork.shutter <= racer.s and self.time >= fork.deadline:
                self.fail(racer, "Tunnel shutter closed")
                return
            if racer.s >= fork.end:
                racer.route = -1
        if abs(racer.lane) > width(racer.s, racer.route) + .95:
            self.fail(racer, "Off the ridge" if racer.s > 814 else "Off the course")
