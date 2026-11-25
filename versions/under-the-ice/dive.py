"""Real-time swimming, fish, breath, the lookout, and Deepfin."""

from math import dist, sin

from pygame.math import Vector2

from cave import AIR, BODY, EXIT_Y, GOAL, LEFT, RIGHT, SWIM_SPEED, VENTS, WATERLINE, Cave, infer_exit


PATROL = ((873, 512), (584, 543), (384, 504), (657, 475), (972, 484))


def clamp(value, low=0., high=1.):
    return max(low, min(high, value))


def current(y):
    if y < 521:
        return 48 * clamp((y-341)/60) * clamp((521-y)/45)
    return -38 * clamp((y-531)/65)


class Dive:
    def __init__(self, seed, *, cave=None):
        self.cave = Cave(seed) if cave is None else cave
        self.position = Vector2(VENTS[0], WATERLINE-16)
        self.velocity = Vector2()
        self.facing = 1
        self.lookout = VENTS[0]+94
        self.vent = 0
        self.seal = Vector2(964, 525)
        self.seal_facing = -1
        self.patrol = 0
        self.threat = 0.
        self.air = AIR
        self.lives = 3
        self.banked = 0
        self.haul = set()
        self.available = set(range(len(self.cave.fish)))
        self.underwater = False
        self.paused = False
        self.finished = None
        self.seconds = 0.
        self.route_delay = 0.
        self.greedy = False
        self.show_route = False
        self.route = None
        self.hint = "Press S or Down at a vent to dive."
        self.notice = ""
        self.notice_until = 0.
        self.dive_ready = 0.
        self.events = []

    def cycle_search(self):
        self.greedy = not self.greedy
        self.route_delay = 0.

    def fish_position(self, index):
        x, y = self.cave.fish[index]
        return x+sin(self.seconds*1.7+index*1.9)*6, y+sin(self.seconds*2.3+index)*4

    def step(self, dt, direction):
        if self.finished or self.paused:
            return
        self.seconds += dt
        if direction.x:
            self.facing = 1 if direction.x > 0 else -1
        if self.underwater:
            self.swim(dt, direction)
        else:
            self.walk(dt, direction)
        if not self.finished:
            self.move_seal(dt)
        target = VENTS[self.vent] + (92 if self.vent == 0 else -92)
        self.lookout += clamp(target-self.lookout, -209*dt, 209*dt)

    def walk(self, dt, direction):
        self.air = min(AIR, self.air+6.8*dt)
        self.position.x = clamp(self.position.x+direction.x*214*dt, LEFT+BODY, RIGHT-BODY)
        opening = self.cave.opening(self.position.x)
        floor = WATERLINE-(17 if opening is not None else 47)
        self.position.y += (floor-self.position.y)*min(1, dt*14)
        if opening is not None:
            self.vent = opening
            self.hint = "Press S or Down at the opening to dive."
            if direction.y > .2 and self.seconds >= self.dive_ready:
                self.position.y = EXIT_Y+11
                self.velocity = Vector2(0, 75)
                self.underwater = True
                self.route_delay = 0.
                self.events.append("dive")
        else:
            self.hint = "Walk to an air opening, then press Down to dive."

    def move_in_water(self, position, change, radius=BODY):
        x, y = position
        if self.cave.clear(x+change.x, y, radius):
            x += change.x
        if self.cave.clear(x, y+change.y, radius):
            y += change.y
        return Vector2(x, y)

    def swim(self, dt, direction):
        goal = direction * SWIM_SPEED
        goal.x += current(self.position.y)
        self.velocity = self.velocity.lerp(goal, min(1., dt*8))
        opening = self.cave.opening(self.position.x)
        if opening is not None and direction.y < -.2 and self.position.y+self.velocity.y*dt <= EXIT_Y+2:
            self.surface(opening)
            return
        self.position = self.move_in_water(self.position, self.velocity*dt)
        self.air = max(0., self.air-dt)
        if not self.air:
            self.lose_dive("Out of air")
            return
        collected = {index for index in self.available if dist(self.position, self.fish_position(index)) <= 23}
        if collected:
            self.available -= collected
            self.haul |= collected
            self.events.append("catch")
        self.route_delay -= dt
        if self.route_delay <= 0:
            routes = tuple(self.cave.route(self.position, index, self.greedy) for index in range(len(VENTS)))
            exit_index, self.hint = infer_exit(routes, self.seal, self.air)
            if exit_index is not None:
                self.vent, self.route = exit_index, routes[exit_index]
            else:
                self.route = None
            self.route_delay = .32

    def surface(self, opening):
        landed = len(self.haul)
        self.banked += landed
        self.haul.clear()
        self.underwater = False
        self.vent = opening
        self.position.y = WATERLINE-17
        self.velocity.update(0, 0)
        self.route = None
        if landed:
            self.announce(f"{landed} fish brought to the surface")
            self.events.append("bank")
        if self.banked >= GOAL:
            self.finished = "win"
            self.events.append("win")

    def move_seal(self, dt):
        distance = self.seal.distance_to(self.position)
        near = clamp((300-distance)/228)
        exposed = 1. if self.underwater and self.cave.visible(self.seal, self.position) else 0.
        slow = clamp((.5-self.air/AIR)/.5)
        strength = exposed*min(1., near*(.82+.18*slow)+.08*bool(self.haul))
        self.threat += (strength-self.threat)*min(1., dt*2.9)
        patrol_target = Vector2(PATROL[self.patrol])
        if self.seal.distance_to(patrol_target) < 20:
            self.patrol = (self.patrol+1) % len(PATROL)
            patrol_target = Vector2(PATROL[self.patrol])
        target = patrol_target.lerp(self.position, min(1., self.threat*1.65)) if self.underwater else patrol_target
        direction = target-self.seal
        if direction.length_squared() > 1:
            step = direction.normalize()*(94+115*self.threat)*dt
            if abs(step.x) > .2:
                self.seal_facing = 1 if step.x > 0 else -1
            self.seal = self.move_in_water(self.seal, step, BODY+3)
        if self.underwater and self.position.distance_to(self.seal) < 32:
            self.lose_dive("Deepfin caught you")

    def lose_dive(self, cause):
        self.lives -= 1
        self.available |= self.haul
        self.haul.clear()
        self.announce(cause)
        self.events.append("lost")
        self.air = AIR
        self.route = None
        self.underwater = False
        self.threat = 0.
        self.dive_ready = self.seconds+.65
        self.seal.update(964, 525)
        self.position.update(VENTS[self.vent], WATERLINE-17)
        self.velocity.update(0, 0)
        if self.lives <= 0:
            self.finished = "lost"

    def announce(self, message):
        self.notice = message
        self.notice_until = self.seconds+2.8
