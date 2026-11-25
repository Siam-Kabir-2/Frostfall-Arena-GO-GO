"""Roster, draft, and fixed-step auto-battle rules."""

from dataclasses import dataclass, field
from math import fsum, hypot
from random import Random

from navigation import combat_destination

COLS, ROWS = 8, 5
PREP, LIMIT = 32, 23
STEP = 1 / 60
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


@dataclass
class Side:
    hand: list
    next_card: int
    field: dict
    shells: int = SHELLS
    ready: bool = False
    draws: int = 0
    upgrades: int = 1


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

    @property
    def hero(self):
        return ROSTER[self.recruit.hero]


@dataclass
class Effect:
    side: int
    hero: int
    origin: tuple
    target: tuple
    spell: bool
    life: float = .34


@dataclass
class Changes:
    damage: list = field(default_factory=list)
    heal: float = 0.
    shield: float = 0.
    stun: float = 0.
    slow: float = 0.
    destination: tuple | None = None
    push: float = 0.


def distance(a, b):
    return round(hypot(a.x-b.x, a.y-b.y), 8)


def clamp(value, low, high):
    return min(high, max(low, value))


class Match:
    def __init__(self, seed=None, *, public_draft=False, effects=True):
        random = Random(seed)
        self.random = (Random(random.getrandbits(64)), Random(random.getrandbits(64)))
        self.public_draft = public_draft
        self.draw_effects = effects
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

    def legal_cell(self, side, cell):
        col, row = cell
        return 0 <= row < ROWS and (0 <= col <= 2 if side == 0 else 5 <= col <= 7)

    def editable(self, side):
        return self.phase == "prep" and not self.sides[side].ready

    def buy(self, side, slot, cell):
        if not self.editable(side) or not 0 <= slot < HAND or not self.legal_cell(side, cell):
            return "Choose a tile on your side."
        team = self.sides[side]
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
        if self.phase == "prep":
            self.sides[side].ready = not self.sides[side].ready
            if all(team.ready for team in self.sides):
                self.fight()

    def fight(self):
        if self.phase != "prep":
            return
        self.phase, self.time = "fight", 0.
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
            if self.time >= PREP:
                self.fight()
        elif self.phase == "fight":
            self.time += STEP
            self.advance_fight()
        elif self.phase in ("round_end", "end"):
            if self.phase == "round_end":
                self.time += STEP
            self.age_effects()

    def next_round(self):
        if self.phase != "round_end":
            return False
        self.round_number += 1
        self.round_winner = None
        self.reason = ""
        self.phase, self.time = "prep", 0.
        self.fighters.clear()
        self.effects.clear()
        for team in self.sides:
            team.ready = False
            team.upgrades = self.round_number
        return True

    def age_effects(self):
        for effect in self.effects:
            effect.life -= STEP
        self.effects = [effect for effect in self.effects if effect.life > 0.]
        for unit in self.fighters:
            if unit.hp <= 0:
                unit.fall += STEP

    def effect(self, unit, destination, *, spell, origin=None):
        if self.draw_effects:
            self.effects.append(Effect(unit.side, unit.recruit.hero, origin or (unit.x, unit.y), destination, spell))

    def impact(self, unit, target, amount, pending, *, spell=False, origin=None):
        pending[target].damage.append(amount)
        self.effect(unit, (target.x, target.y), spell=spell, origin=origin)

    def cast(self, unit, target, teams, pending):
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
            destination = (clamp(target.x+forward*.65, .28, COLS-.28), target.y)
            pending[unit].destination = destination
            self.effect(unit, destination, spell=True)
            self.impact(unit, target, 67*strength, pending, spell=True, origin=destination)
        else:
            reach = distance(unit, target)
            if reach > .94:
                gap = max(.0, reach-.74)
                pending[unit].destination = (unit.x+(target.x-unit.x)*gap/reach, unit.y+(target.y-unit.y)*gap/reach)
            self.impact(unit, target, 48*strength, pending, spell=True)
            pending[target].push += forward*.54
            pending[target].stun = max(pending[target].stun, .46)
            pending[unit].heal += 27*strength

    def advance_fight(self):
        self.age_effects()
        actors = [unit for unit in self.fighters if unit.hp > 0]
        teams = tuple([unit for unit in actors if unit.side == side] for side in (0, 1))
        pending = {unit: Changes() for unit in actors}
        # Choose actions from the same positions and health, then apply them together.
        for unit in actors:
            rivals = teams[1-unit.side]
            if not rivals:
                continue
            target = min(rivals, key=lambda other: distance(unit, other))
            unit.attack_timer -= STEP
            unit.spell_timer -= STEP
            unit.slow = max(0., unit.slow-STEP)
            unit.shield = max(0., unit.shield-STEP*8)
            if unit.stun > 0:
                unit.stun -= STEP
                continue
            reach = distance(unit, target)
            ability_range = 1.65 if unit.recruit.hero == FIGHTER else unit.hero.reach+.12
            if unit.spell_timer <= 0 and (unit.recruit.hero == ASSASSIN or reach <= ability_range):
                self.cast(unit, target, teams, pending)
                unit.spell_timer = unit.hero.cooldown
            elif reach <= unit.hero.reach and unit.attack_timer <= 0:
                damage = unit.hero.attack * (1+.27*(unit.recruit.rank-1))
                self.impact(unit, target, damage, pending)
                unit.attack_timer = unit.hero.interval
            elif reach > unit.hero.reach:
                speed = unit.hero.speed * STEP * (.52 if unit.slow else 1)
                pending[unit].destination = combat_destination(unit, target, teams[unit.side], speed, COLS, ROWS)
        for unit, change in pending.items():
            shield = max(unit.shield, change.shield)
            damage = fsum(change.damage)
            unit.shield = max(0., shield-damage)
            unit.hp = clamp(unit.hp + change.heal - max(0., damage-shield), 0., unit.maximum)
            unit.stun = max(unit.stun, change.stun)
            unit.slow = max(unit.slow, change.slow)
            x, y = change.destination or (unit.x, unit.y)
            unit.x = round(clamp(x+change.push, .28, COLS-.28), 8)
            unit.y = round(clamp(y, .28, ROWS-.28), 8)
        living = [unit for unit in actors if unit.hp > 0]
        self.separate(living)
        self.check_result(living)

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
        if self.round_winner != -1:
            self.round_wins[self.round_winner] += 1
        if max(self.round_wins) >= WINS_NEEDED or self.round_number == MAX_ROUNDS:
            a, b = self.round_wins
            self.winner = -1 if a == b else int(b > a)
            self.phase = "end"
        else:
            self.phase, self.time = "round_end", 0.

    def separate(self, living):
        offsets = {unit: [0., 0.] for unit in living}
        for i, first in enumerate(living):
            for second in living[i+1:]:
                dx, dy = second.x-first.x, second.y-first.y
                reach = round(hypot(dx, dy), 8)
                if reach >= .49:
                    continue
                if reach < .001:
                    dx, dy = (.12 if first.side == 0 else -.12, 0.) if first.side != second.side else (0., .12)
                else:
                    scale = (.49-reach)*.25/reach
                    dx, dy = dx*scale, dy*scale
                offsets[first][0] -= dx
                offsets[first][1] -= dy
                offsets[second][0] += dx
                offsets[second][1] += dy
        for unit, (dx, dy) in offsets.items():
            unit.x = round(clamp(unit.x+dx, .28, COLS-.28), 8)
            unit.y = round(clamp(unit.y+dy, .28, ROWS-.28), 8)

    def cpu_prepare(self, side=1):
        while options := self.draft_actions(side, limit=1):
            self.apply_draft(side, options[0])

    def apply_draft(self, side, action):
        if action is None:
            self.sides[side].ready = True
            return ""
        if isinstance(action, UpgradeAction):
            return self.upgrade(side, action.cell)
        hand = self.sides[side].hand
        return self.buy(side, hand.index(action.hero), action.cell) if action.hero in hand else "Card unavailable."

    def draft_actions(self, side, limit):
        if not self.editable(side):
            return []
        team = self.sides[side]
        used = {unit.hero for unit in team.field.values()}
        cols = (2, 1, 0) if side == 0 else (5, 6, 7)
        best, variants = [], []
        for index in dict.fromkeys(team.hand):
            hero = ROSTER[index]
            if hero.cost > team.shells:
                continue
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
                        choices.append((base-offset, DraftAction(index, cell)))
            if choices:
                choices.sort(key=lambda choice: -choice[0])
                best.append(choices[0])
                variants.extend(choices[1:3])
        for cell, recruit in team.field.items():
            if self.can_upgrade(side, cell):
                hero = ROSTER[recruit.hero]
                priority = 9.4 + .06*hero.attack/hero.interval + .002*hero.hp
                best.append((priority, UpgradeAction(cell)))
        best.sort(key=lambda choice: -choice[0])
        variants.sort(key=lambda choice: -choice[0])
        return [action for _, action in (best+variants)[:limit]]
