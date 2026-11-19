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
