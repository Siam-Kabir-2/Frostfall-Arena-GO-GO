"""Roster, draft, and fixed-step auto-battle rules."""

from collections import Counter
from dataclasses import dataclass, field
from math import ceil, fsum, hypot
from random import Random

from navigation import adjacent, combat_destination, on_board, tile_at, tile_center

COLS, ROWS = 8, 5
PREP, LIMIT = 32, 25
COUNTDOWN = 3
STEP = 1 / 60
CLOCK_EPSILON = 1e-9
NIGHT_SLIP_DURATION = .48
ATTACK_ANIMATION, SPELL_ANIMATION, HURT_ANIMATION = .30, .48, .24
HAND, CAPACITY, SHELLS = 4, 5, 15
MAX_ROUNDS, WINS_NEEDED, MAX_RANK = 3, 2, 4
TANK, MAGE, MARKSMAN, ASSASSIN, FIGHTER = range(5)
PUBLIC_HAND = (TANK, MAGE, MARKSMAN, ASSASSIN)
PUBLIC_DECK = (FIGHTER, MARKSMAN, TANK, MAGE, ASSASSIN, FIGHTER, TANK, MARKSMAN)


@dataclass(frozen=True)
class Hero:
    name: str
    role: str
    spell: str
    description: str
    color: tuple
    cost: int
    hp: int
    attack: int
    reach: float
    speed: float
    cooldown: float
    interval: float
    position: str
    column: int
    lanes: tuple


ROSTER = (
    Hero("Glacier", "Tank", "Ice Dome", "Shields itself and nearby allies.",
         (104, 218, 248), 3, 350, 23, .77, 1.23, 5.4, 1.12, "Front center", 2, (2, 1, 3)),
    Hero("Cinder", "Mage", "Snowfire", "Bursts on a target and nearby enemies.",
         (255, 150, 98), 4, 170, 24, 2.64, 1.38, 4.65, 1.15, "Back offset", 0, (1, 3)),
    Hero("Rime", "Marksman", "Frost Volley", "Fires quickly and slows its target.",
         (142, 194, 255), 3, 158, 24, 3.27, 1.40, 4.9, .63, "Back center", 0, (2,)),
    Hero("Wisp", "Assassin", "Night Slip", "Blinks onto a Marksman or Mage in the back.",
         (190, 146, 251), 3, 178, 36, .70, 2.04, 5.9, .85, "Outer edge", 1, (0, 4)),
    Hero("Tide", "Fighter", "Tidal Rush", "Rushes a target, knocks it back and recovers health.",
         (117, 239, 233), 2, 240, 31, .87, 1.69, 4.8, .94, "Front flank", 2, (0, 4)),
)


def recommended(hero, side):
    col = hero.column if side == 0 else COLS-1-hero.column
    return tuple((col, row) for row in hero.lanes)


@dataclass
class Recruit:
    hero: int
    rank: int = 1
    paid: int = 0
    upgraded_round: int = 0


@dataclass(frozen=True)
class DraftAction:
    hero: int
    cell: tuple


@dataclass(frozen=True)
class UpgradeAction:
    cell: tuple


@dataclass(frozen=True)
class RedeployAction:
    slot: int
    cell: tuple


@dataclass
class Side:
    hand: list
    next_card: int
    field: dict
    shells: int = SHELLS
    ready: bool = False
    draws: int = 0
    upgrades: int = 1
    returning: list = field(default_factory=list)

    @property
    def to_deploy(self):
        return sum(recruit is not None for recruit in self.returning)


@dataclass(eq=False)
class Fighter:
    side: int
    recruit: Recruit
    x: float
    y: float
    hp: float
    maximum: float
    attack_timer: float = .4
    spell_timer: float = 2.6
    slow: float = 0.
    stun: float = 0.
    shield: float = 0.
    fall: float = 0.
    move_timer: float = 0.
    avoid: tuple | None = None
    previous_tile: tuple | None = None
    target: "Fighter | None" = None
    blocked_steps: int = 0
    glide_from: tuple | None = None
    glide_time: float = 0.
    glide_left: float = 0.
    knocked_back: bool = False
    attack_pose: float = 0.
    attack_span: float = ATTACK_ANIMATION
    hurt_pose: float = 0.

    @property
    def hero(self):
        return ROSTER[self.recruit.hero]

    @property
    def reach(self):
        return max(1., self.hero.reach)

    @property
    def visual_position(self):
        if not self.glide_left or not self.glide_from:
            return self.x, self.y
        progress = 1-self.glide_left/self.glide_time
        blend = progress*(2-progress) if self.knocked_back else progress
        x, y = self.glide_from
        return x+(self.x-x)*blend, y+(self.y-y)*blend


@dataclass
class Effect:
    side: int
    hero: int
    origin: tuple
    target: tuple
    spell: bool
    life: float = .34
    blink_actor: Recruit | None = None

    @property
    def blink_progress(self):
        return 1-self.life/NIGHT_SLIP_DURATION


@dataclass
class Changes:
    damage: list = field(default_factory=list)
    heal: float = 0.
    shield: float = 0.
    stun: float = 0.
    slow: float = 0.
    destination: tuple | None = None
    push: tuple = (0, 0)
    blink_target: Fighter | None = None


def distance(a, b):
    return round(hypot(a.x-b.x, a.y-b.y), 8)


def clamp(value, low, high):
    return min(high, max(low, value))


class Match:
    def __init__(self, seed=None, *, public_draft=False, effects=True, countdown=False):
        random = Random(seed)
        self.random = (Random(random.getrandbits(64)), Random(random.getrandbits(64)))
        self.public_draft = public_draft
        self.draw_effects = effects
        self.start_countdown = countdown
        self.sides = [Side(list(PUBLIC_HAND), PUBLIC_DECK[0], {}) if public_draft
                      else Side(self.start_hand(i), self.random[i].randrange(len(ROSTER)), {}) for i in range(2)]
        self.phase = "prep"
        self.time = 0.
        self.round_number = 1
        self.round_winner = None
        self.round_wins = [0, 0]
        self.winner = None
        self.reason = ""
        self.fighters = []
        self.effects = []

    def start_hand(self, side):
        rng = self.random[side]
        cards = [TANK, *rng.sample((MAGE, MARKSMAN, ASSASSIN, FIGHTER), 3)]
        rng.shuffle(cards)
        return cards

    @property
    def capacity(self):
        return CAPACITY

    @property
    def seconds_left(self):
        limit = {"prep": PREP if self.round_number == 1 else None,
                 "countdown": COUNTDOWN, "fight": LIMIT}.get(self.phase)
        return None if limit is None else max(0, ceil(limit-self.time-CLOCK_EPSILON))

    def legal_cell(self, side, cell):
        col, row = cell
        return 0 <= row < ROWS and (0 <= col <= 2 if side == 0 else 5 <= col <= 7)

    def editable(self, side):
        return self.phase == "prep" and not self.sides[side].ready

    def buy(self, side, slot, cell):
        if not self.editable(side) or not 0 <= slot < HAND or not self.legal_cell(side, cell):
            return "Choose a tile on your side."
        team = self.sides[side]
        if team.to_deploy:
            return "Place your returning penguins first."
        hero_id = team.hand[slot]
        hero = ROSTER[hero_id]
        target = team.field.get(cell)
        if target:
            return "Pick an empty tile. Use Upgrade to train a deployed penguin."
        if len(team.field) >= self.capacity:
            return "Lineup full. Sell a penguin to free a tile."
        if team.shells < hero.cost:
            return "You need more shells."
        team.shells -= hero.cost
        team.hand[slot] = team.next_card
        team.draws += 1
        if self.public_draft:
            team.next_card = PUBLIC_DECK[team.draws % len(PUBLIC_DECK)]
        else:
            team.next_card = self.random[side].choice([i for i in range(len(ROSTER)) if i != team.next_card])
        team.field[cell] = Recruit(hero_id, paid=hero.cost)
        return ""

    def redeploy(self, side, slot, cell):
        if not self.editable(side) or not self.legal_cell(side, cell):
            return "Choose a tile on your side."
        team = self.sides[side]
        if not 0 <= slot < len(team.returning) or team.returning[slot] is None:
            return "That penguin is already deployed."
        if cell in team.field:
            return "Pick an empty tile for your returning penguin."
        if len(team.field) >= self.capacity:
            return "Your lineup is full."
        team.field[cell] = team.returning[slot]
        team.returning[slot] = None
        return ""

    def move(self, side, source, destination):
        if not self.editable(side) or not all(self.legal_cell(side, cell) for cell in (source, destination)):
            return "Choose a tile on your side."
        field = self.sides[side].field
        recruit = field.get(source)
        target = field.get(destination)
        if not recruit or source == destination:
            return ""
        if target:
            field[source] = target
        else:
            del field[source]
        field[destination] = recruit
        return ""

    def sell(self, side, cell):
        if self.editable(side) and self.legal_cell(side, cell):
            team = self.sides[side]
            recruit = team.field.pop(cell, None)
            if recruit:
                team.shells = min(SHELLS, team.shells + max(1, recruit.paid // 2))

    def can_upgrade(self, side, cell):
        team = self.sides[side]
        recruit = team.field.get(cell)
        return (self.editable(side) and team.upgrades > 0 and recruit is not None
                and recruit.rank < MAX_RANK and recruit.upgraded_round != self.round_number)

    def upgrade(self, side, cell):
        if not self.can_upgrade(side, cell):
            return "Choose a deployed penguin that has not upgraded this round."
        team = self.sides[side]
        recruit = team.field[cell]
        recruit.rank += 1
        recruit.upgraded_round = self.round_number
        team.upgrades -= 1
        return ""

    def lock(self, side):
        if self.phase == "prep" and not self.sides[side].to_deploy:
            self.sides[side].ready = not self.sides[side].ready
            if all(team.ready for team in self.sides):
                self.fight()

    def fight(self):
        if self.phase != "prep" or any(team.to_deploy for team in self.sides):
            return
        self.phase, self.time = "countdown" if self.start_countdown else "fight", 0.
        self.effects = []
        self.fighters = []
        for side, team in enumerate(self.sides):
            cells = sorted(team.field, key=lambda cell: (cell[0] if side == 0 else COLS-1-cell[0], cell[1]))
            for x, y in cells:
                recruit = team.field[x, y]
                hp = ROSTER[recruit.hero].hp * (1 + .31*(recruit.rank-1))
                self.fighters.append(Fighter(side, recruit, x+.5, y+.5, hp, hp,
                                             spell_timer=1.02 if recruit.hero == ASSASSIN else 2.3 + .16*y))

    def step(self):
        if self.phase == "prep":
            self.time += STEP
            if self.round_number == 1 and self.time+CLOCK_EPSILON >= PREP:
                self.time = float(PREP)
                if not self.start_countdown or all(team.field for team in self.sides):
                    self.fight()
        elif self.phase == "countdown":
            self.time += STEP
            if self.time+CLOCK_EPSILON >= COUNTDOWN:
                self.phase, self.time = "fight", 0.
        elif self.phase == "fight":
            self.time += STEP
            if self.time+CLOCK_EPSILON >= LIMIT:
                self.time = float(LIMIT)
            self.advance_fight()
        elif self.phase in ("round_end", "end"):
            if self.phase == "round_end":
                self.time += STEP
            self.age_effects()


    def age_effects(self):
        for effect in self.effects:
            effect.life -= STEP
        self.effects = [effect for effect in self.effects if effect.life > 0.]
        for unit in self.fighters:
            if self.draw_effects:
                unit.attack_pose = max(0., unit.attack_pose-STEP)
                unit.hurt_pose = max(0., unit.hurt_pose-STEP)
            unit.glide_left = max(0., unit.glide_left-STEP)
            if not unit.glide_left:
                unit.knocked_back = False
            if unit.hp <= 0:
                unit.fall += STEP

    def effect(self, unit, destination, *, spell, origin=None):
        if self.draw_effects:
            self.effects.append(Effect(unit.side, unit.recruit.hero, origin or (unit.x, unit.y), destination, spell))

    def impact(self, unit, target, amount, pending, *, spell=False, origin=None):
        pending[target].damage.append(amount)
        self.effect(unit, (target.x, target.y), spell=spell, origin=origin)

    def cast(self, unit, target, teams, pending, occupied):
        strength = 1 + .30*(unit.recruit.rank-1)
        hero = unit.recruit.hero
        rivals = teams[1-unit.side]
        forward = 1 if unit.side == 0 else -1
        if hero == TANK:
            for ally in teams[unit.side]:
                if distance(unit, ally) <= 1.65:
                    pending[ally].shield = max(pending[ally].shield, 58*strength)
                    self.effect(unit, (ally.x, ally.y), spell=True)
        elif hero == MAGE:
            for rival in rivals:
                if distance(target, rival) <= 1.24:
                    self.impact(unit, rival, (79 if rival is target else 46)*strength, pending, spell=True)
        elif hero == MARKSMAN:
            self.impact(unit, target, 52*strength, pending, spell=True)
            pending[target].slow = max(pending[target].slow, 1.85)
        elif hero == ASSASSIN:
            target = max(rivals, key=lambda other: (other.recruit.hero in (MARKSMAN, MAGE),
                                                   round(forward*other.x, 8), -distance(unit, other)))
            cell = tile_at(target.x, target.y)
            open_cells = [candidate for candidate in adjacent(cell)
                          if on_board(candidate, COLS, ROWS) and candidate not in occupied]
            if not open_cells:
                return False
            destination = min(open_cells, key=lambda c: (abs(c[0]-cell[0]-forward)+abs(c[1]-cell[1]), c[1]))
            pending[unit].destination = destination
            pending[unit].blink_target = target
        else:
            if distance(unit, target) > unit.reach:
                pending[unit].destination = combat_destination(unit, target, occupied, COLS, ROWS)
            self.impact(unit, target, 48*strength, pending, spell=True)
            dx, dy = target.x-unit.x, target.y-unit.y
            push_x, push_y = pending[target].push
            if abs(dx) >= abs(dy):
                push_x += (dx > 0) - (dx < 0)
            else:
                push_y += (dy > 0) - (dy < 0)
            pending[target].push = push_x, push_y
            pending[target].stun = max(pending[target].stun, .54)
            pending[unit].heal += 27*strength
        return True

    def combat_target(self, unit, rivals):
        nearest = min(rivals, key=lambda other: distance(unit, other))
        previous = unit.target
        if previous is not None and previous.hp > 0:
            near = distance(unit, nearest)
            current = distance(unit, previous)
            if (current <= unit.reach or near > unit.reach) and current <= near+1.25:
                return previous
        unit.target = nearest
        unit.blocked_steps = 0
        return nearest

    def advance_toward(self, unit, target, rivals, occupied):
        step = combat_destination(unit, target, occupied, COLS, ROWS)
        can_retarget = unit.avoid is None and unit.blocked_steps >= 2
        unit.avoid = None
        if step is None and can_retarget:
            for rival in sorted(rivals, key=lambda other: distance(unit, other)):
                if rival is target:
                    continue
                step = combat_destination(unit, rival, occupied, COLS, ROWS)
                if step is not None:
                    unit.target = rival
                    break
        unit.blocked_steps = 0 if step is not None else unit.blocked_steps+1
        return step

    def advance_fight(self):
        self.age_effects()
        actors = [unit for unit in self.fighters if unit.hp > 0]
        teams = tuple([unit for unit in actors if unit.side == side] for side in (0, 1))
        pending = {unit: Changes() for unit in actors}
        occupied = frozenset(tile_at(unit.x, unit.y) for unit in actors) | frozenset(
            tile_at(*unit.glide_from) for unit in actors if unit.glide_left and unit.glide_from)
        # Choose actions from the same positions and health, then apply them together.
        for unit in actors:
            rivals = teams[1-unit.side]
            if not rivals:
                continue
            unit.attack_timer -= STEP
            unit.spell_timer -= STEP
            unit.move_timer -= STEP
            unit.slow = max(0., unit.slow-STEP)
            unit.shield = max(0., unit.shield-STEP*8)
            if unit.stun > 0:
                unit.stun -= STEP
                continue
            if unit.glide_left:
                continue
            target = self.combat_target(unit, rivals)
            reach = distance(unit, target)
            ability_range = 1.65 if unit.recruit.hero == FIGHTER else unit.reach+.12
            if (unit.spell_timer <= 0 and (unit.recruit.hero == ASSASSIN or reach <= ability_range)
                    and self.cast(unit, target, teams, pending, occupied)):
                unit.spell_timer = unit.hero.cooldown
                if self.draw_effects and pending[unit].blink_target is None:
                    unit.attack_pose = unit.attack_span = SPELL_ANIMATION
            elif reach <= unit.reach and unit.attack_timer <= 0:
                damage = unit.hero.attack * (1+.27*(unit.recruit.rank-1))
                self.impact(unit, target, damage, pending)
                unit.attack_timer = unit.hero.interval
                if self.draw_effects:
                    unit.attack_pose = unit.attack_span = ATTACK_ANIMATION
            elif reach > unit.reach and unit.move_timer <= 0:
                pending[unit].destination = self.advance_toward(unit, target, rivals, occupied)
                unit.move_timer = .16
        requests = self.movement_requests(actors, pending, occupied)
        contested = Counter(cell for cell, _ in requests.values())
        for unit, change in pending.items():
            target = change.blink_target
            if target is None:
                continue
            if requests.get(unit) != (change.destination, False) or contested[change.destination] > 1:
                unit.spell_timer = .24
                continue
            unit.target = target
            if self.draw_effects:
                unit.attack_pose = unit.attack_span = SPELL_ANIMATION
            damage = 67*(1 + .30*(unit.recruit.rank-1))
            self.impact(unit, target, damage, pending, spell=True, origin=(target.x, target.y))

        for unit, change in pending.items():
            shield = max(unit.shield, change.shield)
            damage = fsum(change.damage)
            unit.shield = max(0., shield-damage)
            previous_hp = unit.hp
            unit.hp = clamp(unit.hp + change.heal - max(0., damage-shield), 0., unit.maximum)
            if self.draw_effects and unit.hp < previous_hp:
                unit.hurt_pose = HURT_ANIMATION
            unit.stun = max(unit.stun, change.stun)
            unit.slow = max(unit.slow, change.slow)
        living = [unit for unit in actors if unit.hp > 0]
        self.resolve_movement(living, pending, requests, contested)
        self.check_result(living)

    def movement_requests(self, actors, pending, occupied):
        requests = {}
        for unit in actors:
            change = pending[unit]
            cell = change.destination
            push_x, push_y = change.push
            pushed = bool(push_x or push_y)
            if pushed:
                x, y = tile_at(unit.x, unit.y)
                if abs(push_x) >= abs(push_y):
                    cell = x+(push_x > 0)-(push_x < 0), y
                else:
                    cell = x, y+(push_y > 0)-(push_y < 0)
            if cell is not None and cell not in occupied and on_board(cell, COLS, ROWS):
                requests[unit] = cell, pushed
        return requests

    def resolve_movement(self, living, pending, requests, contested):
        for unit in living:
            if unit not in requests:
                continue
            cell, pushed = requests[unit]
            if contested[cell] > 1:
                unit.avoid = cell
                continue
            blink = pending[unit].blink_target is not None and not pushed
            origin = unit.visual_position
            x, y = tile_center(cell)
            travel = hypot(unit.x-x, unit.y-y)
            duration = travel / (unit.hero.speed * (.52 if unit.slow else 1.))
            unit.previous_tile = tile_at(*origin) if not (pushed or blink) else None
            unit.x, unit.y = x, y
            unit.knocked_back = pushed
            if blink:
                if self.draw_effects:
                    self.effects.append(Effect(unit.side, unit.recruit.hero, origin, (x, y), True,
                                               NIGHT_SLIP_DURATION, unit.recruit))
                unit.glide_left = 0.
                arrival = NIGHT_SLIP_DURATION*.82
                unit.attack_timer = max(unit.attack_timer, arrival)
                unit.move_timer = max(unit.move_timer, arrival)
            else:
                unit.glide_from = origin
                unit.glide_time = unit.glide_left = .18 if pushed else duration*.97
                unit.move_timer = max(unit.move_timer, unit.glide_time if pushed else duration)

    def check_result(self, living):
        remaining = {unit.side for unit in living}
        if len(remaining) == 1:
            self.round_winner = next(iter(remaining))
            self.reason = "Last squad standing"
        elif not remaining:
            self.round_winner = -1
            self.reason = "Both squads defeated" if self.fighters else "Neither side deployed"
        elif self.time >= LIMIT:
            scores = []
            for side in (0, 1):
                team = [unit for unit in self.fighters if unit.side == side]
                scores.append(fsum(unit.hp for unit in team)/fsum(unit.maximum for unit in team))
            self.round_winner = -1 if abs(scores[0]-scores[1]) < .0001 else int(scores[1] > scores[0])
            self.reason = "Time limit · Remaining health percentage"
        if self.round_winner is None:
            return
        self.phase, self.time = "round_end", 0.

    def cpu_prepare(self, side=1):
        while options := self.draft_actions(side, limit=1):
            self.apply_draft(side, options[0])

    def apply_draft(self, side, action):
        if action is None:
            if self.sides[side].to_deploy:
                return "Place your returning penguins first."
            self.sides[side].ready = True
            return ""
        if isinstance(action, UpgradeAction):
            return self.upgrade(side, action.cell)
        if isinstance(action, RedeployAction):
            return self.redeploy(side, action.slot, action.cell)
        hand = self.sides[side].hand
        return self.buy(side, hand.index(action.hero), action.cell) if action.hero in hand else "Card unavailable."

    def draft_actions(self, side, limit):
        if not self.editable(side):
            return []
        team = self.sides[side]
        used = {unit.hero for unit in team.field.values()}
        cols = (2, 1, 0) if side == 0 else (5, 6, 7)
        best, variants = [], []
        returning = team.to_deploy > 0
        if returning:
            entries = [(slot, unit.hero) for slot, unit in enumerate(team.returning) if unit is not None]
        else:
            entries = [(None, hero) for hero in dict.fromkeys(team.hand) if ROSTER[hero].cost <= team.shells]
        for slot, index in entries:
            hero = ROSTER[index]
            choices = []
            if len(team.field) < self.capacity:
                preferred = recommended(hero, side)
                base = 10. if index not in used else 7.3
                if index == TANK and TANK not in used:
                    base += 2.
                for col in cols:
                    for row in range(ROWS):
                        cell = col, row
                        if cell in team.field:
                            continue
                        offset = min(abs(col-x)*1.25+abs(row-y)*.45 for x, y in preferred)
                        action = RedeployAction(slot, cell) if returning else DraftAction(index, cell)
                        choices.append((base-offset, action))
            if choices:
                choices.sort(key=lambda choice: -choice[0])
                best.append(choices[0])
                variants.extend(choices[1:3])
        for cell, recruit in team.field.items():
            if not returning and self.can_upgrade(side, cell):
                hero = ROSTER[recruit.hero]
                priority = 9.4 + .06*hero.attack/hero.interval + .002*hero.hp
                best.append((priority, UpgradeAction(cell)))
        best.sort(key=lambda choice: -choice[0])
        variants.sort(key=lambda choice: -choice[0])
        return [action for _, action in (best+variants)[:limit]]
