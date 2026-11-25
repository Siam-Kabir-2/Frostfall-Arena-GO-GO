"""Local two-player penguin auto-battler."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from math import ceil, cos, sin, tau
from os import environ
from random import Random

import pygame as pg

from arena import COLS, HAND, LIMIT, MAX_ROUNDS, PREP, ROWS, ROSTER, SHELLS, STEP, Match, UpgradeAction, recommended
from planners import choose_mcts, choose_minimax, draft_snapshot

SIZE = 1240, 790
FIELD = pg.Rect(150, 151, 936, 385)
CW, CH = FIELD.w // COLS, FIELD.h // ROWS
TEAM = ((106, 224, 249), (255, 153, 126))
NIGHT = (13, 25, 43)
PANEL = (22, 41, 66)
EDGE = (49, 75, 101)
TEXT = (236, 246, 252)
MUTED = (155, 180, 203)
GOLD = (255, 212, 113)
FIT_BUTTON = pg.Rect(945, 22, 128, 42)


def mix(a, b, factor):
    return tuple(round(x+(y-x)*factor) for x, y in zip(a, b))


def rect(x, y, width, height):
    return pg.Rect(x, y, width, height)


def desktop_work_area():
    if pg.display.get_driver() == "windows":
        from ctypes import byref, windll, wintypes

        area = wintypes.RECT()
        # SPI_GETWORKAREA excludes the Windows taskbar and desktop toolbars.
        if windll.user32.SystemParametersInfoW(0x0030, 0, byref(area), 0):
            return rect(area.left, area.top, area.right-area.left, area.bottom-area.top)
    return rect(0, 0, *pg.display.get_desktop_sizes()[0])


def fitted_scale(area):
    return min(1., max(1, area.w-32)/SIZE[0], max(1, area.h-64)/SIZE[1])


def scaled_size(scale):
    return tuple(max(1, round(length*scale)) for length in SIZE)


def game_viewport(size):
    width, height = scaled_size(min(size[0]/SIZE[0], size[1]/SIZE[1]))
    return rect((size[0]-width)//2, (size[1]-height)//2, width, height)


def center_window(area):
    if pg.display.get_driver() != "windows":
        return
    from ctypes import byref, windll, wintypes

    hwnd = wintypes.HWND(pg.display.get_wm_info()["window"])
    bounds = wintypes.RECT()
    if windll.user32.GetWindowRect(hwnd, byref(bounds)):
        x = area.left + (area.w-bounds.right+bounds.left)//2
        y = area.top + (area.h-bounds.bottom+bounds.top)//2
        # Move the framed window without changing its size, focus, or stacking order.
        windll.user32.SetWindowPos(hwnd, None, x, y, 0, 0, 0x0015)


def field_at(x, y):
    return round(FIELD.x+x*CW), round(FIELD.y+y*CH)


def cell_at(col, row):
    return rect(*field_at(col, row), CW, CH)


def ready_at(side):
    return rect((325, 765)[side], 82, 150, 42)


def penguin(surface, x, y, tone, face=1, size=1, faint=False, hero=None):
    x, y = int(x), int(y)

    def blob(color, a, b, w, h):
        pg.draw.ellipse(surface, color, (x+round(a*size), y+round(b*size), max(1, round(w*size)), max(1, round(h*size))))

    coat = (30, 45, 69) if not faint else (76, 96, 116)
    cream = (236, 250, 251) if not faint else (160, 180, 191)
    blob((58, 97, 124), -22, 10, 44, 13)
    for sign in (-1, 1):
        blob((241, 166, 87), sign*8-7, 11, 14, 7)
        blob(coat, sign*15-6, -5, 12, 18)
    blob(coat, -16, -15, 32, 30)
    blob(cream, face*2-10, -9, 20, 23)
    blob(coat, -15, -28, 30, 27)
    blob(cream, face*3-10, -22, 20, 17)
    blob((16, 30, 51), face*5-3, -19, 6, 8)
    blob((243, 178, 88), face*9-5, -11, 10, 6)
    blob(tone, -16, -7, 32, 6)
    blob(tone, face*-10-2, -3, 6, 9)
    blob(tone, -8, -29, 18, 5)
    if hero is not None:
        crests = (
            ((-12, -21), (-10, -32), (0, -36), (11, -31), (13, -21)),
            ((-10, -28), (-5, -39), (1, -32), (9, -41), (11, -27)),
            ((-8, -29), (0, -41), (8, -29), (0, -25)),
            ((-16, -25), (-12, -38), (0, -32), (12, -38), (16, -25)),
            ((-11, -28), (-11, -38), (1, -32), (11, -35), (11, -28)),
        )
        points = [(x+round(a*size*face), y+round(b*size)) for a, b in crests[hero]]
        pg.draw.polygon(surface, tone, points)


def card_art(hero_id):
    hero = ROSTER[hero_id]
    tone = hero.color
    art = pg.Surface((104, 106))
    for y in range(106):
        pg.draw.line(art, mix(mix(NIGHT, tone, .57), (14, 27, 45), y/118), (0, y), (104, y))
    glow = pg.Surface(art.get_size(), pg.SRCALPHA)
    for radius in range(48, 4, -4):
        pg.draw.circle(glow, (*tone, max(4, 120-radius*2)), (52, 48), radius, 4)
    art.blit(glow, (0, 0))
    rng = Random(514+hero_id*89)
    for i in range(9):
        angle = i*tau/9+hero_id*.2
        end = (52+cos(angle)*77, 48+sin(angle)*73)
        start = (52+cos(angle-.087)*24, 48+sin(angle-.087)*19)
        stop = (52+cos(angle+.19)*57, 48+sin(angle+.19)*58)
        pg.draw.polygon(art, mix(NIGHT, tone, rng.uniform(.27, .57)), (start, end, stop))
    for _ in range(24):
        x, y = rng.randrange(4, 101), rng.randrange(7, 97)
        pg.draw.circle(art, mix(tone, TEXT, rng.random()*.52), (x, y), rng.choice((1, 1, 1, 2)))
    pg.draw.ellipse(art, mix(NIGHT, tone, .31), (16, 80, 76, 25))
    penguin(art, 54, 68, tone, (-1, 1)[hero_id % 2], 1.71, hero=hero_id)
    pg.draw.line(art, mix(tone, TEXT, .17), (6, 102), (98, 102))
    return art


class Game:
    def __init__(self):
        environ.setdefault("SDL_VIDEO_CENTERED", "1")
        pg.init()
        pg.display.set_caption("Frostfall Go Go")
        area = desktop_work_area()
        self.window = pg.display.set_mode(scaled_size(fitted_scale(area)), pg.RESIZABLE)
        center_window(area)
        self.canvas = pg.Surface(SIZE)
        self.clock = pg.time.Clock()
        self.fonts = {}
        self.seed = None
        self.mode = "menu"
        self.match = Match()
        self.selected = None
        self.note = ""
        self.note_time = 0
        self.accumulator = 0.
        self.mouse = (0, 0)
        self.drag_start = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="draft-search")
        self.job = None
        self.ai_turn = 0
        self.ai_delay = 0.
        self.showdown_first = 1
        self.decisions = {}
        self.ai_moves = {}
        self.backdrop = self.make_backdrop()
        self.terrain = self.make_terrain()
        self.card_art = [card_art(i) for i in range(len(ROSTER))]
        self.next_art = [pg.transform.smoothscale(art, (51, 52)) for art in self.card_art]

    def dock_left(self, side):
        return 337 if self.mode == "cpu" else (28, 638)[side]

    def card_at(self, side, index):
        return rect(self.dock_left(side)+13+index*112, 610, 105, 125)

    def upgrade_at(self, side):
        return rect(self.dock_left(side)+229, 577, 141, 27)

    def make_backdrop(self):
        backdrop = pg.Surface(SIZE)
        for y in range(SIZE[1]):
            pg.draw.line(backdrop, mix((17, 37, 61), (11, 20, 36), y/SIZE[1]), (0, y), (SIZE[0], y))
        rng = Random(392)
        for _ in range(176):
            x, y = rng.randrange(SIZE[0]), rng.randrange(SIZE[1])
            pg.draw.circle(backdrop, mix(NIGHT, (107, 171, 193), rng.uniform(.16, .44)), (x, y), rng.choice((1, 1, 2)))
        for layer in range(2):
            ridge = [(0, 410)] + [(x, rng.randint(327, 533)+layer*57) for x in range(0, 1241, 68)] + [(1240, 790), (0, 790)]
            pg.draw.polygon(backdrop, mix((18, 39, 63), NIGHT, layer*.4), ridge)
        return backdrop

    def make_terrain(self):
        surface = self.backdrop.copy()
        rng = Random(208)
        water = FIELD.inflate(108, 96)
        pg.draw.ellipse(surface, (12, 37, 62), water)
        for _ in range(31):
            side = rng.choice((0, 1))
            x = rng.randint(19, 149) if side == 0 else rng.randint(1089, 1225)
            y = rng.randint(140, 558)
            scale = rng.randint(12, 52)
            points = [(x+cos(i*tau/6)*scale, y+sin(i*tau/6)*scale*.39) for i in range(6)]
            tone = mix((23, 62, 86), (79, 135, 154), rng.uniform(.08, .60))
            pg.draw.polygon(surface, tone, points)
            pg.draw.lines(surface, mix(tone, (121, 182, 198), .55), False, points[1:5], 1)
        x, y, w, h = FIELD.inflate(52, 32)
        rim = ((x+21, y), (x+w-21, y), (x+w, y+21), (x+w, y+h-15),
               (x+w-21, y+h+5), (x+21, y+h+5), (x, y+h-15), (x, y+21))
        pg.draw.polygon(surface, (18, 34, 57), [(px, py+14) for px, py in rim])
        pg.draw.polygon(surface, (51, 91, 118), rim)
        pg.draw.polygon(surface, (117, 170, 188), rim, 2)
        for row in range(ROWS):
            for col in range(COLS):
                tile = cell_at(col, row).inflate(-3, -3)
                base = (72, 136, 165) if col <= 2 else (139, 102, 120) if col >= 5 else (63, 102, 133)
                tone = mix(base, (177, 225, 230), .11 + rng.random()*.12)
                points = ((tile.x+5, tile.y), (tile.right-5, tile.y), (tile.right, tile.y+5),
                          (tile.right, tile.bottom-5), (tile.right-5, tile.bottom), (tile.x+5, tile.bottom),
                          (tile.x, tile.bottom-5), (tile.x, tile.y+5))
                pg.draw.polygon(surface, tone, points)
                pg.draw.lines(surface, mix(tone, TEXT, .23), False, points[:3], 2)
                pg.draw.lines(surface, mix(tone, NIGHT, .23), False, points[3:7], 3)
                for _ in range(2):
                    px, py = rng.randrange(tile.x+8, tile.right-35), rng.randrange(tile.y+14, tile.bottom-15)
                    tint = mix(tone, (198, 240, 247), rng.uniform(.08, .26))
                    pg.draw.polygon(surface, tint, ((px, py), (px+24, py-7), (px+10, py+5)))
                    pg.draw.line(surface, tint, (px+4, py+6), (px+32, py-2))
        self.paint_emblem(surface, (FIELD.left+174, FIELD.centery), TEAM[0])
        self.paint_emblem(surface, (FIELD.right-174, FIELD.centery), TEAM[1])
        return surface

    def paint_emblem(self, surface, center, tone):
        shield = pg.Surface((103, 103), pg.SRCALPHA)
        points = ((51, 10), (86, 30), (86, 69), (51, 94), (17, 69), (17, 30))
        pg.draw.polygon(shield, (*tone, 55), points, 3)
        pg.draw.lines(shield, (*tone, 69), False, ((31, 67), (51, 30), (71, 67)), 4)
        surface.blit(shield, shield.get_rect(center=center))

    def label(self, value, x, y, size=17, color=TEXT, *, bold=False, align="left"):
        key = size, bold
        if key not in self.fonts:
            self.fonts[key] = pg.font.SysFont("bahnschrift,aptos,arial", size, bold=bold)
        graphic = self.fonts[key].render(str(value), True, color)
        target = graphic.get_rect()
        setattr(target, {"left": "topleft", "center": "midtop", "right": "topright"}[align], (x, y))
        self.canvas.blit(graphic, target)

    def panel(self, bounds, color=PANEL, edge=EDGE, radius=11):
        pg.draw.rect(self.canvas, color, bounds, border_radius=radius)
        pg.draw.rect(self.canvas, edge, bounds, 1, border_radius=radius)

    def button(self, bounds, text, accent, active=True):
        color = mix(PANEL, accent, .25 if bounds.collidepoint(self.mouse) and active else .10)
        self.panel(bounds, color, accent if active else EDGE, 8)
        self.label(text, bounds.centerx, bounds.centery-8, 17, accent if active else MUTED, bold=True, align="center")

    def start(self, mode):
        self.cancel_ai()
        self.mode = mode
        self.match = Match(self.seed, public_draft=mode == "showdown")
        self.selected = None
        self.note = ""
        self.note_time = 0.
        self.accumulator = 0.
        self.ai_turn = 1 if mode == "cpu" else 0
        if mode == "showdown":
            self.showdown_first = 1-self.showdown_first
            self.ai_turn = self.showdown_first
        self.ai_delay = .35
        self.decisions.clear()
        self.ai_moves.clear()

    def cancel_ai(self):
        if self.job:
            self.job.cancel()
            self.job = None

    def next_round(self):
        if self.match.next_round():
            self.cancel_ai()
            self.selected = None
            self.decisions.clear()
            self.ai_moves.clear()
            self.ai_turn = 1 if self.mode == "cpu" else (self.showdown_first+self.match.round_number-1) % 2
            self.ai_delay = .30

    def to_menu(self):
        self.cancel_ai()
        self.mode = "menu"
        self.selected = None

    def tick_ai(self, dt):
        if self.mode not in ("cpu", "showdown") or self.match.phase != "prep":
            return
        if self.mode == "showdown" and self.match.sides[self.ai_turn].ready:
            self.ai_turn = 1-self.ai_turn
        side = self.ai_turn
        if self.match.sides[side].ready:
            return
        if self.job:
            if not self.job.done():
                return
            decision = self.job.result()
            self.decisions[side] = decision
            self.job = None
            if decision.action is None:
                self.match.lock(side)
            else:
                action = decision.action
                if self.match.apply_draft(side, action):
                    choices = self.match.draft_actions(side, 1)
                    if choices:
                        action = choices[0]
                        self.match.apply_draft(side, action)
                    else:
                        self.match.lock(side)
                        return
                if isinstance(action, UpgradeAction):
                    recruit = self.match.sides[side].field[action.cell]
                    self.ai_moves[side] = f"{ROSTER[recruit.hero].name} to rank {recruit.rank}"
                else:
                    self.ai_moves[side] = f"deployed {ROSTER[action.hero].name}"
            if self.mode == "showdown":
                self.ai_turn = 1-side
            self.ai_delay = .21
            return
        self.ai_delay -= dt
        if self.ai_delay <= 0:
            if not self.match.draft_actions(side, 1):
                self.match.lock(side)
                return
            algorithm = choose_minimax if self.mode == "showdown" and side == 0 else choose_mcts
            self.job = self.executor.submit(algorithm, draft_snapshot(self.match), side)

    def frame(self, dt):
        if self.mode == "menu":
            return
        self.tick_ai(dt)
        self.note_time = max(0., self.note_time-dt)
        self.accumulator += min(.08, dt)
        while self.accumulator >= STEP:
            self.accumulator -= STEP
            before = self.match.phase
            self.match.step()
            if self.match.phase != before:
                self.selected = None
                self.cancel_ai()
            if self.mode == "showdown" and self.match.phase == "round_end" and self.match.time >= 2.8:
                self.next_round()

    def team_name(self, side):
        if self.mode == "showdown":
            return ("MINIMAX", "MCTS")[side]
        return ("NORTH", "MCTS CPU" if self.mode == "cpu" else "SOUTH")[side]

    def ui_pos(self, point):
        viewport = game_viewport(self.window.get_size())
        if not viewport.collidepoint(point):
            return -1, -1
        return ((point[0]-viewport.x)*SIZE[0]//viewport.w, (point[1]-viewport.y)*SIZE[1]//viewport.h)

    def resize(self, factor=None):
        area = desktop_work_area()
        maximum = fitted_scale(area)
        scale = maximum
        if factor is not None:
            current = game_viewport(self.window.get_size()).w/SIZE[0]
            scale = min(maximum, max(min(.42, maximum), current*factor))
        self.window = pg.display.set_mode(scaled_size(scale), pg.RESIZABLE)
        center_window(area)

    def hit(self, point):
        for side in (0, 1):
            if side == 1 and self.mode == "cpu":
                continue
            for slot in range(HAND):
                if self.card_at(side, slot).collidepoint(point):
                    return side, "card", slot
        if FIELD.collidepoint(point):
            col = (point[0]-FIELD.x)//CW
            row = (point[1]-FIELD.y)//CH
            for side in (0, 1):
                if self.match.legal_cell(side, (col, row)):
                    return side, "field", (col, row)
        return None

    def click(self, point, button):
        if button == 1 and FIT_BUTTON.collidepoint(point):
            self.resize()
            return
        if self.mode == "menu":
            if rect(77, 369, 355, 48).collidepoint(point):
                self.start("cpu")
            if rect(77, 431, 355, 48).collidepoint(point):
                self.start("local")
            if rect(77, 493, 355, 48).collidepoint(point):
                self.start("showdown")
            return
        if rect(1085, 22, 128, 42).collidepoint(point):
            self.to_menu()
            return
        if self.match.phase == "end":
            if rect(500, 422, 240, 45).collidepoint(point):
                self.start(self.mode)
            return
        if self.match.phase == "round_end":
            if rect(500, 422, 240, 45).collidepoint(point):
                self.next_round()
            return
        if self.match.phase != "prep" or self.mode == "showdown":
            return
        for side in (0, 1):
            if side == 1 and self.mode != "local":
                continue
            if ready_at(side).collidepoint(point):
                self.ready(side)
                return
            if button == 1 and self.upgrade_at(side).collidepoint(point) and self.match.editable(side):
                if any(self.match.can_upgrade(side, cell) for cell in self.match.sides[side].field):
                    selection = (side, "upgrade", None)
                    self.selected = None if self.selected == selection else selection
                else:
                    self.note, self.note_time = "No penguin can upgrade this round.", 2.4
                return
        target = self.hit(point)
        if target is None:
            self.selected = None
            return
        side, kind, cell = target
        if (self.mode == "cpu" and side == 1) or not self.match.editable(side):
            return
        if button == 3:
            if kind == "field":
                self.match.sell(side, cell)
            self.selected = None
            return
        if kind != "card" and self.selected and self.selected[0] == side:
            self.commit(target)
        elif kind == "card" or cell in self.match.sides[side].field:
            self.selected = target
            self.drag_start = point

    def ready(self, side):
        if not self.match.sides[side].field:
            self.note, self.note_time = "Deploy a penguin to the battlefield first.", 2.4
            return
        self.selected = None
        self.match.lock(side)

    def commit(self, target):
        side, source, slot = self.selected
        _, _, cell = target
        if source == "card":
            message = self.match.buy(side, slot, cell)
        elif source == "upgrade":
            message = self.match.upgrade(side, cell)
        else:
            message = self.match.move(side, slot, cell)
        if message:
            self.note, self.note_time = message, 2.4
        else:
            self.selected = None

    def event(self, event):
        if event.type == pg.KEYDOWN:
            if event.key == pg.K_F10:
                self.resize()
                return
            if event.key in (pg.K_MINUS, pg.K_KP_MINUS, pg.K_EQUALS, pg.K_PLUS, pg.K_KP_PLUS):
                self.resize(.86 if event.key in (pg.K_MINUS, pg.K_KP_MINUS) else 1/.86)
                return
            if event.key == pg.K_ESCAPE:
                if self.selected:
                    self.selected = None
                else:
                    self.to_menu()
            if self.mode == "menu":
                if event.key == pg.K_1:
                    self.start("cpu")
                if event.key == pg.K_2:
                    self.start("local")
                if event.key == pg.K_3:
                    self.start("showdown")
            elif event.key == pg.K_SPACE:
                if self.match.phase == "round_end":
                    self.next_round()
                elif self.mode == "cpu" and self.match.phase == "prep":
                    self.ready(0)
                elif self.match.phase == "end":
                    self.start(self.mode)
            elif event.key == pg.K_u and self.mode in ("cpu", "local") and self.match.phase == "prep":
                self.click(self.upgrade_at(0).center, 1)
            elif self.mode != "showdown" and self.match.phase == "prep" and event.key in (pg.K_1, pg.K_2, pg.K_3, pg.K_4):
                if self.match.editable(0):
                    self.selected = (0, "card", event.key-pg.K_1)
        if event.type == pg.MOUSEBUTTONDOWN and event.button in (1, 3):
            self.drag_start = None
            self.click(self.ui_pos(event.pos), event.button)
        if event.type == pg.MOUSEBUTTONUP and event.button == 1 and self.selected and self.drag_start:
            point = self.ui_pos(event.pos)
            target = self.hit(point)
            if target and target[0] == self.selected[0] and target[1] != "card" and target != self.selected:
                if abs(point[0]-self.drag_start[0])+abs(point[1]-self.drag_start[1]) >= 9:
                    self.commit(target)
            self.drag_start = None

    def menu(self):
        self.label("FROSTFALL", 75, 120, 30, TEAM[0], bold=True)
        self.label("GO GO", 70, 149, 114, bold=True)
        self.label("Five classes. Best of three.", 77, 278, 27, MUTED)
        self.button(rect(77, 369, 355, 48), "1   PLAY VS MCTS", TEAM[0])
        self.button(rect(77, 431, 355, 48), "2   LOCAL TWO PLAYER", TEAM[1])
        self.button(rect(77, 493, 355, 48), "3   MINIMAX VS MCTS", GOLD)
        self.label("Drag cards to deploy. Right-click to sell.", 77, 583, 17, MUTED)
        for x, y, hero, size, face in ((775, 274, 0, 3.9, 1), (1003, 402, 1, 4.2, -1),
                                       (730, 508, 3, 2.4, 1), (1089, 182, 2, 2.25, -1)):
            pg.draw.ellipse(self.canvas, (40, 76, 104), (x-110, y-12, 220, 88))
            pg.draw.ellipse(self.canvas, (91, 173, 196), (x-108, y-16, 216, 74), 2)
            penguin(self.canvas, x, y, ROSTER[hero].color, face, size, hero=hero)

    def draw_team(self, side):
        team = self.match.sides[side]
        x = (27, 942)[side]
        accent = TEAM[side]
        self.panel(rect(x, 79, 271, 50), (17, 34, 56), mix(EDGE, accent, .38), 8)
        self.label(self.team_name(side), x+15, 95, 17, accent, bold=True)
        if self.match.phase == "prep":
            status = f"{len(team.field)} / {self.match.capacity} deployed"
        else:
            alive = sum(unit.hp > 0 for unit in self.match.fighters if unit.side == side)
            status = f"{alive} / {len(team.field)} standing"
        self.label(status, x+256, 97, 14, MUTED, align="right")
        ai_side = self.mode == "showdown" or (self.mode == "cpu" and side == 1)
        if ai_side:
            button_label = "READY" if team.ready else "PLANNING" if side == self.ai_turn else "WAITING"
        else:
            button_label = "UNLOCK" if team.ready else "READY"
        if self.match.phase != "prep":
            result = self.match.winner if self.match.phase == "end" else self.match.round_winner
            button_label = ("IN BATTLE" if self.match.phase == "fight" else "DRAW" if result == -1
                            else "WINNER" if result == side else "DEFEATED")
        self.button(ready_at(side), button_label, accent, self.match.phase == "prep" and not ai_side)

    def draw_field(self):
        if self.match.phase == "prep":
            hovered = self.hit(self.mouse)
            if self.selected:
                side, kind, origin = self.selected
                if kind == "field":
                    pg.draw.rect(self.canvas, TEAM[side], cell_at(*origin).inflate(-5, -5), 3, border_radius=7)
                if kind == "upgrade":
                    for cell in self.match.sides[side].field:
                        if self.match.can_upgrade(side, cell):
                            pg.draw.rect(self.canvas, GOLD, cell_at(*cell).inflate(-7, -7), 3, border_radius=7)
                if hovered and hovered[0] == side and hovered[1] == "field":
                    pg.draw.rect(self.canvas, TEXT, cell_at(*hovered[2]).inflate(-5, -5), 3, border_radius=7)
            self.range_preview()
            for side, team in enumerate(self.match.sides):
                for (col, row), recruit in team.field.items():
                    self.unit(side, recruit, col+.5, row+.5)
        else:
            for unit in sorted(self.match.fighters, key=lambda fighter: fighter.y):
                if unit.hp > 0 or unit.fall < .42:
                    self.unit(unit.side, unit.recruit, unit.x, unit.y, unit)
            for effect in self.match.effects:
                a, b = field_at(*effect.origin), field_at(*effect.target)
                tone = ROSTER[effect.hero].color if effect.spell else TEXT
                pg.draw.line(self.canvas, tone, a, b, 3 if effect.spell else 1)
                radius = round((.36-effect.life)*43)+5
                pg.draw.circle(self.canvas, tone, b, radius, 2)
                if effect.spell and effect.life > .13:
                    self.label(ROSTER[effect.hero].spell, b[0], b[1]-48, 12, (25, 39, 62), bold=True, align="center")

    def range_preview(self):
        target = self.hit(self.mouse)
        if not self.selected:
            return
        side, kind, origin = self.selected
        if kind == "upgrade":
            return
        if kind == "card":
            hero_id = self.match.sides[side].hand[origin]
        else:
            recruit = self.match.sides[side].field.get(origin)
            if recruit is None:
                return
            hero_id = recruit.hero
        hero = ROSTER[hero_id]
        for cell in recommended(hero, side):
            if cell not in self.match.sides[side].field:
                bounds = cell_at(*cell).inflate(-12, -12)
                pg.draw.rect(self.canvas, hero.color, bounds, 2, border_radius=6)
        if not target or target[1] != "field" or target[0] != side:
            return
        col, row = target[2]
        x, y = field_at(col+.5, row+.5)
        edge = pg.Surface(FIELD.size, pg.SRCALPHA)
        w, h = round(hero.reach*CW), round(hero.reach*CH)
        bounds = rect(x-FIELD.x-w, y-FIELD.y-h, w*2, h*2)
        pg.draw.ellipse(edge, (*hero.color, 34), bounds)
        pg.draw.ellipse(edge, (*hero.color, 175), bounds, 2)
        self.canvas.blit(edge, FIELD)
        team = self.match.sides[side]
        if kind == "card" and (col, row) not in team.field and len(team.field) < self.match.capacity and team.shells >= hero.cost:
            ghost = pg.Surface((68, 68), pg.SRCALPHA)
            penguin(ghost, 34, 38, hero.color, 1 if side == 0 else -1, hero=hero_id)
            ghost.set_alpha(175)
            self.canvas.blit(ghost, (x-34, y-38))

    def unit(self, side, recruit, x, y, fighter=None):
        px, py = field_at(x, y)
        accent = TEAM[side]
        shade = fighter is not None and fighter.hp <= 0
        pg.draw.ellipse(self.canvas, accent if not shade else EDGE, (px-24, py+4, 48, 20), 2)
        penguin(self.canvas, px, py, ROSTER[recruit.hero].color, 1 if side == 0 else -1, 1.0, shade, recruit.hero)
        if fighter:
            bar = rect(px-21, py-32, 42, 4)
            pg.draw.rect(self.canvas, NIGHT, bar, border_radius=2)
            pg.draw.rect(self.canvas, accent, (bar.x, bar.y, round(bar.w*fighter.hp/fighter.maximum), bar.h), border_radius=2)
            if fighter.shield > 0:
                pg.draw.circle(self.canvas, (223, 248, 255), (px, py-4), 24, 2)
        for i in range(recruit.rank):
            x = px+int((i-(recruit.rank-1)/2)*9)
            pg.draw.polygon(self.canvas, NIGHT, ((x, py+17), (x+4, py+21), (x, py+25), (x-4, py+21)))
            pg.draw.polygon(self.canvas, GOLD if recruit.rank > 1 else TEXT,
                            ((x, py+18), (x+3, py+21), (x, py+24), (x-3, py+21)))

    def draw_hand(self, side):
        left = self.dock_left(side)
        team = self.match.sides[side]
        self.panel(rect(left, 574, 566, 184), (17, 33, 56), mix(EDGE, TEAM[side], .42), 10)
        self.label(f"{self.team_name(side)} HAND", left+13, 584, 16, TEAM[side], bold=True)
        if self.match.phase == "prep":
            active = self.mode != "showdown" and any(self.match.can_upgrade(side, cell) for cell in team.field)
            color = TEXT if self.selected == (side, "upgrade", None) else GOLD
            self.button(self.upgrade_at(side), f"UPGRADE  {team.upgrades}", color, active)
        self.label(f"{team.shells} SHELLS", left+548, 585, 15, GOLD, bold=True, align="right")
        for shell in range(SHELLS):
            pg.draw.rect(self.canvas, GOLD if shell < team.shells else EDGE,
                         (left+13+shell*36, 743, 31, 5), border_radius=2)
        for slot, hero_id in enumerate(team.hand):
            hero = ROSTER[hero_id]
            bounds = self.card_at(side, slot)
            selected = self.selected == (side, "card", slot)
            hovered = bounds.collidepoint(self.mouse)
            if selected:
                bounds = bounds.move(0, -4)
            pg.draw.rect(self.canvas, (8, 17, 32), bounds.move(0, 3), border_radius=5)
            self.canvas.blit(self.card_art[hero_id], (bounds.x, bounds.y))
            pg.draw.rect(self.canvas, (14, 27, 45), rect(bounds.x, bounds.bottom-33, bounds.w, 33))
            pg.draw.rect(self.canvas, TEXT if selected else hero.color if hovered else mix(EDGE, hero.color, .66),
                         bounds, 2, border_radius=5)
            self.label(hero.name, bounds.centerx, bounds.bottom-32, 16, TEXT, bold=True, align="center")
            self.label(hero.role.upper(), bounds.centerx, bounds.bottom-15, 11, hero.color, bold=True, align="center")
            if self.match.phase == "prep" and team.shells < hero.cost:
                surface = pg.Surface((bounds.w-4, bounds.h-4), pg.SRCALPHA)
                surface.fill((9, 18, 32, 111))
                self.canvas.blit(surface, (bounds.x+2, bounds.y+2))
            center = (bounds.x+16, bounds.y+17)
            pg.draw.circle(self.canvas, (19, 39, 64), center, 12)
            pg.draw.circle(self.canvas, GOLD, center, 12, 2)
            self.label(hero.cost, center[0], center[1]-9, 15, GOLD, align="center", bold=True)
        x = left+485
        pg.draw.line(self.canvas, EDGE, (x-15, 615), (x-15, 729))
        self.label("NEXT", x+26, 616, 12, MUTED, bold=True, align="center")
        self.canvas.blit(self.next_art[team.next_card], (x, 637))
        pg.draw.rect(self.canvas, mix(EDGE, ROSTER[team.next_card].color, .6), rect(x, 637, 51, 52), 1, border_radius=4)
        self.label(ROSTER[team.next_card].name, x+26, 696, 13, TEXT, align="center")

    def match_view(self):
        phase = self.match.phase
        self.label("FROSTFALL", 29, 23, 16, TEAM[0], bold=True)
        self.label("GO GO", 26, 42, 39, bold=True)
        self.button(rect(1085, 22, 128, 42), "MENU", MUTED)
        title = "MINIMAX VS MCTS" if self.mode == "showdown" else f"BEST OF {MAX_ROUNDS}"
        self.label(title, 620, 24, 17, MUTED, bold=True, align="center")
        drafting = self.team_name(self.ai_turn) if self.mode == "showdown" else "DEPLOY"
        state = f"{drafting}  ·  {max(0, ceil(PREP-self.match.time)):02d}s" if phase == "prep" else (
            f"AUTO BATTLE  ·  {max(0, ceil(LIMIT-self.match.time)):02d}s" if phase == "fight" else
            "MATCH COMPLETE" if phase == "end" else "ROUND COMPLETE")
        self.label(state, 620, 47, 29, TEXT, bold=True, align="center")
        a, b = self.match.round_wins
        self.label(f"ROUND {self.match.round_number}/{MAX_ROUNDS}  ·  {a} – {b}", 620, 96, 15, MUTED, bold=True, align="center")
        self.draw_field()
        for side in (0, 1):
            self.draw_team(side)
            if side == 0 or self.mode != "cpu":
                self.draw_hand(side)
        tooltip = self.hit(self.mouse)
        if self.note_time and phase == "prep":
            hint, color = self.note, TEAM[1]
        elif self.selected and self.selected[1] == "upgrade":
            hint, color = "Choose a highlighted penguin to raise its rank by one.", GOLD
        elif hovered_card := (self.selected if self.selected and self.selected[1] == "card"
                              else tooltip if tooltip and tooltip[1] == "card" else None):
            side, _, slot = hovered_card
            hero = ROSTER[self.match.sides[side].hand[slot]]
            hint, color = f"{hero.role}  /  {hero.position}  ·  {hero.spell}: {hero.description}", hero.color
        elif self.mode == "showdown":
            minimax = self.decisions.get(0)
            mcts = self.decisions.get(1)
            mm_label = (f"Minimax: {self.ai_moves.get(0, 'ready')} ({minimax.explored} nodes)"
                        if minimax else "Minimax: waiting")
            mcts_label = (f"MCTS: {self.ai_moves.get(1, 'ready')} ({mcts.explored} rollouts)"
                          if mcts else "MCTS: waiting")
            hint, color = f"{mm_label}    ·    {mcts_label}", MUTED
        elif phase == "prep":
            hint, color = "Drag a card to deploy  ·  Use Upgrade to level a penguin  ·  Right-click to sell", MUTED
        else:
            hint, color = "Both teams use greedy targeting and A* movement.", MUTED
        self.label(hint, 620, 767, 16, color, align="center")
        if phase == "prep" and self.drag_start and self.selected and self.selected[1] == "card" and pg.mouse.get_pressed()[0]:
            x, y = self.mouse
            dx, dy = self.drag_start
            if abs(x-dx)+abs(y-dy) >= 9 and not FIELD.collidepoint(self.mouse):
                side, _, slot = self.selected
                hero_id = self.match.sides[side].hand[slot]
                self.canvas.blit(self.next_art[hero_id], (x+10, y-52))
        if phase in ("round_end", "end"):
            winner = self.match.winner if phase == "end" else self.match.round_winner
            layer = pg.Surface(SIZE, pg.SRCALPHA)
            layer.fill((9, 19, 35, 143))
            self.canvas.blit(layer, (0, 0))
            self.panel(rect(406, 275, 428, 222), NIGHT, EDGE)
            heading = "MATCH COMPLETE" if phase == "end" else f"ROUND {self.match.round_number} COMPLETE"
            self.label(heading, 620, 300, 17, MUTED, bold=True, align="center")
            self.label("DRAW" if winner == -1 else f"{self.team_name(winner)} WINS", 620, 339, 41,
                       GOLD if winner == -1 else TEAM[winner], bold=True, align="center")
            detail = f"Final score  {a} – {b}" if phase == "end" else (
                f"{a} – {b}   ·   Next round: {self.match.round_number + 1} upgrades each")
            self.label(detail, 620, 393, 16, MUTED, align="center")
            self.button(rect(500, 422, 240, 45), "REMATCH" if phase == "end" else "NEXT ROUND", GOLD)

    def draw(self):
        self.mouse = self.ui_pos(pg.mouse.get_pos())
        self.canvas.blit(self.backdrop if self.mode == "menu" else self.terrain, (0, 0))
        if self.mode == "menu":
            self.menu()
        else:
            self.match_view()
        self.button(FIT_BUTTON, "FIT WINDOW", MUTED)
        viewport = game_viewport(self.window.get_size())
        if self.window.get_size() == SIZE:
            self.window.blit(self.canvas, (0, 0))
        else:
            if viewport.size != self.window.get_size():
                self.window.fill(NIGHT)
            self.window.blit(pg.transform.smoothscale(self.canvas, viewport.size), viewport)
        pg.display.flip()

    def run(self):
        try:
            while True:
                dt = self.clock.tick(60)/1000
                for event in pg.event.get():
                    if event.type == pg.QUIT:
                        return
                    self.event(event)
                self.frame(dt)
                self.draw()
        finally:
            self.cancel_ai()
            self.executor.shutdown(cancel_futures=True)
            pg.quit()


def main():
    parser = argparse.ArgumentParser(description="Frostfall Go Go, a two-player penguin auto-battler")
    parser.add_argument("--mode", choices=("cpu", "local", "showdown"))
    parser.add_argument("--seed", type=int, help="repeat the opening card hands")
    args = parser.parse_args()
    game = Game()
    game.seed = args.seed
    if args.mode:
        game.start(args.mode)
    game.run()


if __name__ == "__main__":
    main()
