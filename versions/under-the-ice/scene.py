"""Side-view artwork and the diving display."""

from functools import lru_cache
from math import atan2, degrees, sin, tau
from pathlib import Path
from random import Random

import pygame as pg

from cave import AIR, FLOOR, GOAL, HEIGHT, LEFT, RIGHT, VENT_HALF, VENTS, WATERLINE, WIDTH


ASSETS = Path(__file__).with_name("assets")
INK = (229, 247, 248)
MUTED = (142, 189, 200)
MINT = (110, 237, 212)
GOLD = (255, 203, 121)
CORAL = (255, 136, 126)
NIGHT = (10, 31, 43)
EDGE = (39, 86, 99)


def mix(a, b, t):
    return tuple(round(x+(y-x)*t) for x, y in zip(a, b))


@lru_cache(maxsize=60)
def font(size, kind):
    filename = {"display": "BarlowCondensed-Black.ttf", "bold": "BarlowSemiCondensed-ExtraBold.ttf",
                "body": "Barlow-SemiBold.ttf"}[kind]
    return pg.font.Font(str(ASSETS / "fonts" / filename), size)


def label(canvas, words, x, y, size=18, color=INK, kind="body", anchor="topleft"):
    text = font(size, kind).render(str(words), True, color)
    canvas.blit(text, text.get_rect(**{anchor: (round(x), round(y))}))


def card(canvas, bounds):
    pg.draw.rect(canvas, NIGHT, bounds, border_radius=12)
    pg.draw.rect(canvas, EDGE, bounds, width=1, border_radius=12)


def dot_path(canvas, points):
    for start, end in zip(points, points[1:]):
        a, b = pg.Vector2(start), pg.Vector2(end)
        steps = max(1, int(a.distance_to(b)/12))
        for step in range(steps):
            dot = a.lerp(b, step/steps)
            pg.draw.circle(canvas, (207, 250, 221), dot, 2)


class Scene:
    def __init__(self, cave):
        self.background = self.paint_cave(cave)
        self.diver = pg.image.load(str(ASSETS / "diver.png")).convert_alpha()
        self.lookout = pg.image.load(str(ASSETS / "lookout.png")).convert_alpha()
        self.diver = pg.transform.smoothscale(self.diver, (50, 53))
        self.lookout = pg.transform.smoothscale(self.lookout, (45, 48))
        self.seal = self.paint_seal()

    @staticmethod
    def paint_cave(cave):
        layer = pg.Surface((WIDTH, HEIGHT)).convert()
        for y in range(HEIGHT):
            if y < WATERLINE:
                rgb = mix((9, 28, 47), (34, 78, 90), y/WATERLINE)
            else:
                progress = min(1, (y-WATERLINE)/(FLOOR-WATERLINE))
                rgb = mix((17, 94, 111), (5, 23, 40), progress**.82)
            pg.draw.line(layer, rgb, (0, y), (WIDTH, y))

        rng = Random(cave.seed ^ 5449)
        for _ in range(58):
            x, y = rng.randrange(16, WIDTH-16), rng.randrange(100, WATERLINE-27)
            pg.draw.circle(layer, rng.choice(((67, 114, 126), (113, 157, 163), (85, 128, 141))), (x, y), rng.choice((1, 1, 2)))
        for depth, (base, high, color) in enumerate(((238, 80, (25, 52, 75)), (256, 69, (31, 72, 91)), (269, 38, (42, 94, 107)))):
            points = [(0, base)]
            for x in range(-16, WIDTH+95, 58):
                points.append((x, base-rng.randint(9, high)))
            points += [(WIDTH, WATERLINE+4), (0, WATERLINE+4)]
            pg.draw.polygon(layer, color, points)
            if depth != 2:
                pg.draw.lines(layer, mix(color, (98, 152, 166), .23), False, points[:-2], 1)

        glints = pg.Surface((WIDTH, HEIGHT), pg.SRCALPHA)
        for x in VENTS:
            for offset, width, opacity in ((-28, 118, 17), (3, 163, 17), (33, 215, 11)):
                pg.draw.polygon(glints, (151, 243, 234, opacity),
                                ((x+offset-18, WATERLINE), (x+offset+14, WATERLINE),
                                 (x+offset+width, 675), (x+offset-width, 675)))
            pg.draw.line(layer, (144, 217, 222), (x-VENT_HALF+2, WATERLINE), (x+VENT_HALF-2, WATERLINE), 2)
        layer.blit(glints, (0, 0))

        for _ in range(150):
            x, y = rng.randrange(15, WIDTH-15), rng.randrange(WATERLINE+12, FLOOR)
            tone = mix((39, 130, 146), (25, 59, 79), (y-WATERLINE)/(FLOOR-WATERLINE))
            pg.draw.circle(layer, tone, (x, y), rng.choice((1, 1, 1, 2)))
        for x in range(10, WIDTH+45, 16):
            base = rng.randint(FLOOR-36, FLOOR-2)
            pg.draw.polygon(layer, (11, 36, 51), ((x-16, FLOOR+8), (x, base), (x+25, FLOOR+8)))
        pg.draw.rect(layer, (9, 28, 43), (0, FLOOR, WIDTH, HEIGHT-FLOOR))

        for rock in cave.rocks:
            Scene.ice_formation(layer, rock, rng, rock.top == WATERLINE)
        bars = ((0, VENTS[0]-VENT_HALF), (VENTS[0]+VENT_HALF, VENTS[1]-VENT_HALF),
                (VENTS[1]+VENT_HALF, WIDTH))
        for left, right in bars:
            Scene.ice_formation(layer, pg.Rect(left, WATERLINE-32, right-left, 35), rng, True)
            snow = [(left, WATERLINE-33), (right, WATERLINE-33)]
            snow.extend((x, WATERLINE-rng.randint(34, 41)) for x in range(right-6, left, -31))
            pg.draw.polygon(layer, (198, 232, 235), snow)
            pg.draw.line(layer, (227, 249, 249), (left+2, WATERLINE-32), (right-2, WATERLINE-32), 2)
        for x in (65, 115, 280, 334, 556, 588, 688, 954, 1149, 1225):
            for index in range(4):
                y = FLOOR-rng.randrange(4, 24)
                points = [(x+index*4, FLOOR), (x+index*7+8, y-12), (x+index*9, y-31), (x+index*7-3, y-40)]
                pg.draw.lines(layer, (30, 77, 80), False, points, 2)
        return layer

    @staticmethod
    def ice_formation(layer, rect, rng, bright):
        x, y, w, h = rect
        cut = min(22, w//5, h//3)
        outline = ((x, y+cut), (x+cut, y), (x+w-cut, y), (x+w, y+cut),
                   (x+w, y+h-cut), (x+w-cut, y+h), (x+cut, y+h), (x, y+h-cut))
        face = (111, 176, 190) if bright else (40, 97, 123)
        pg.draw.polygon(layer, face, outline)
        for xx in range(x+cut, x+w-cut, 43):
            angle = rng.randint(11, 32)
            tone = mix(face, (211, 242, 240), rng.uniform(.11, .34))
            pg.draw.polygon(layer, tone, ((xx, y+2), (min(xx+37, x+w-cut), y+2),
                                          (min(x+w-2, xx+angle), y+h-2)))
        pg.draw.lines(layer, mix(face, (211, 245, 240), .49), False, outline[:4], 2)
        pg.draw.lines(layer, mix(face, (6, 34, 54), .55), False, outline[3:], 2)

    @staticmethod
    def paint_seal():
        art = pg.Surface((222, 100), pg.SRCALPHA)
        pg.draw.polygon(art, (69, 115, 137), ((51, 42), (7, 28), (21, 46), (5, 60), (72, 62)))
        pg.draw.ellipse(art, (41, 77, 111), (34, 22, 151, 56))
        pg.draw.ellipse(art, (84, 134, 153), (41, 24, 150, 52))
        pg.draw.ellipse(art, (122, 165, 173), (62, 45, 125, 33))
        pg.draw.polygon(art, (58, 99, 125), ((120, 62), (93, 91), (132, 78), (153, 57)))
        pg.draw.ellipse(art, (100, 145, 160), (152, 21, 58, 51))
        pg.draw.ellipse(art, (147, 176, 179), (171, 49, 40, 21))
        rng = Random(744)
        for _ in range(21):
            x, y = rng.randrange(57, 165), rng.randrange(33, 60)
            pg.draw.ellipse(art, (62, 102, 123), (x, y, rng.randrange(4, 9), rng.randrange(3, 6)))
        pg.draw.circle(art, (16, 40, 51), (193, 41), 6)
        pg.draw.circle(art, (216, 246, 241), (194, 39), 2)
        pg.draw.line(art, (53, 81, 95), (179, 61), (208, 61), 2)
        pg.draw.ellipse(art, (44, 64, 73), (203, 50, 10, 8))
        return pg.transform.smoothscale(art, (109, 49))

    def draw(self, canvas, game, *, chrome=True, pilot_route=None, automated=False):
        canvas.blit(self.background, (0, 0))
        self.draw_current(canvas, game.seconds)
        for index, x in enumerate(VENTS):
            color = MINT if index == game.vent else MUTED
            name = "WEST AIR" if index == 0 else "EAST AIR"
            pg.draw.line(canvas, color, (x, 217), (x, 243), 1)
            pg.draw.circle(canvas, color, (x, 245), 3)
            label(canvas, name, x, 193, 18, color, "bold", "midtop")
        route = pilot_route or game.route
        if game.underwater and route is not None and (game.show_route or game.air < 5):
            dot_path(canvas, route.points)

        for index in sorted(game.available):
            x, y = game.fish_position(index)
            direction = -1 if index % 3 == 0 else 1
            self.draw_fish(canvas, x, y, direction)

        seal = self.seal if game.seal_facing > 0 else pg.transform.flip(self.seal, True, False)
        canvas.blit(seal, seal.get_rect(center=game.seal))
        if game.threat > .32:
            label(canvas, "DEEPFIN", game.seal.x, game.seal.y-40, 14, CORAL, "bold", "midtop")
        bob = sin(game.seconds*3.2)*1.8
        canvas.blit(self.lookout, self.lookout.get_rect(center=(game.lookout, WATERLINE-55+bob)))
        label(canvas, "LOOKOUT", game.lookout, WATERLINE-88, 12, MINT, "bold", "midtop")
        self.draw_diver(canvas, game)
        if chrome:
            self.hud(canvas, game, automated)
            if game.paused or game.finished:
                self.dialog(canvas, game)

    @staticmethod
    def draw_current(canvas, seconds):
        for direction, y, color in ((1, 455, (36, 104, 122)), (-1, 582, (29, 82, 106))):
            for index in range(10):
                x = 65+(index*126+direction*seconds*22) % 1148
                dy = 13*sin(index*3.8)
                pg.draw.line(canvas, color, (x, y+dy), (x+38, y+dy), 1)
                end = x+38 if direction == 1 else x
                pg.draw.lines(canvas, color, False, ((end-6*direction, y+dy-3), (end, y+dy),
                                                    (end-6*direction, y+dy+3)), 1)

    @staticmethod
    def draw_fish(canvas, x, y, direction):
        trail = (x-11*direction, y)
        pg.draw.polygon(canvas, (205, 147, 81), (trail, (x-20*direction, y-6), (x-19*direction, y+5)))
        pg.draw.ellipse(canvas, (239, 182, 102), (x-12, y-5, 24, 11))
        pg.draw.ellipse(canvas, (255, 223, 155), (x-9, y-5, 16, 4))
        pg.draw.circle(canvas, (69, 55, 58), (x+7*direction, y-1), 2)

    def draw_diver(self, canvas, game):
        figure = self.diver if game.facing >= 0 else pg.transform.flip(self.diver, True, False)
        x, y = game.position
        if game.underwater:
            forward = max(85, abs(game.velocity.x))
            roll = -game.facing*(51+min(31, degrees(atan2(abs(game.velocity.y), forward))*.5))
            figure = pg.transform.rotozoom(figure, roll, 1)
            for offset in range(4):
                fraction = (game.seconds*.74+offset*.22) % 1
                bx = x-game.facing*(23+fraction*30)+sin(fraction*tau+offset)*4
                by = y-18-fraction*36
                pg.draw.circle(canvas, mix((80, 157, 180), (160, 221, 226), 1-fraction), (bx, by), 2+round(fraction*2), 1)
        pg.draw.circle(canvas, (143, 227, 216), (x, y), 28, 1)
        canvas.blit(figure, figure.get_rect(center=(x, y)))

    @staticmethod
    def hud(canvas, game, automated):
        pg.draw.rect(canvas, (8, 27, 40), (0, 0, WIDTH, 117))
        pg.draw.line(canvas, (40, 83, 100), (0, 116), (WIDTH, 116), 1)
        label(canvas, "FROSTFALL", 34, 19, 14, MINT, "bold")
        label(canvas, "UNDER THE ICE", 31, 30, 63, INK, "display")
        label(canvas, "Bring fish back to either air opening.", 34, 92, 14, MUTED)

        card(canvas, (498, 24, 177, 67))
        label(canvas, "AT THE SURFACE", 514, 32, 13, MUTED, "bold")
        label(canvas, f"{game.banked} / {GOAL}", 514, 46, 35, GOLD, "display")
        card(canvas, (686, 24, 115, 67))
        label(canvas, "CARRYING", 702, 32, 13, MUTED, "bold")
        label(canvas, len(game.haul), 702, 46, 35, INK, "display")
        card(canvas, (812, 24, 105, 67))
        label(canvas, "LIVES", 828, 32, 13, MUTED, "bold")
        for index in range(3):
            pg.draw.circle(canvas, CORAL if index < game.lives else EDGE, (835+19*index, 67), 6)
        card(canvas, (928, 24, 319, 67))
        air_color = CORAL if game.air < 4.5 else MINT
        label(canvas, "AIR", 944, 31, 13, MUTED, "bold")
        label(canvas, f"{game.air:04.1f} s", 1231, 29, 17, air_color, "bold", "topright")
        pg.draw.rect(canvas, (29, 62, 76), (944, 64, 287, 9), border_radius=4)
        fill = round(287*game.air/AIR)
        if fill:
            pg.draw.rect(canvas, air_color, (944, 64, fill, 9), border_radius=4)

        footer = (24, 726, 1232, 58)
        card(canvas, footer)
        notice = game.notice if game.seconds < game.notice_until else game.hint
        label(canvas, notice, 42, 737, 18, CORAL if game.air < 4.5 else INK, "bold")
        algorithm = "Greedy Best-First" if game.greedy else "A*"
        routing = f"Lookout  {algorithm}"
        if game.route is not None and game.show_route:
            count = game.route.expanded
            routing += f"  /  {count} {'node' if count == 1 else 'nodes'} searched"
        label(canvas, routing, 42, 761, 13, MUTED)
        actions = (("G", "Route"), ("TAB", "Search"), ("P", "Pause"), ("ESC", "Modes"))
        if not automated:
            actions = (("WASD", "Move"), *actions)
        x = 1237
        for key, action in reversed(actions):
            text = font(16, "body").size(action)[0]
            width = font(13, "bold").size(key)[0]+16
            label(canvas, action, x, 750, 16, MUTED, anchor="topright")
            left = x-text-width-7
            pg.draw.rect(canvas, (25, 53, 66), (left, 748, width, 24), border_radius=5)
            label(canvas, key, left+width/2, 751, 13, INK, "bold", "midtop")
            x = left-19

    @staticmethod
    def dialog(canvas, game):
        veil = pg.Surface((WIDTH, HEIGHT), pg.SRCALPHA)
        veil.fill((1, 15, 25, 164))
        canvas.blit(veil, (0, 0))
        card(canvas, (400, 271, 480, 210))
        if game.paused:
            title, detail, control = "Dive paused", "Your dive is on hold.", "P  Resume"
        elif game.finished == "win":
            title, detail, control = "Catch secured", f"You brought {game.banked} fish to the surface.", "R  Same cave    /    N  New cave"
        else:
            title, detail, control = "Dive over", f"{game.banked} / {GOAL} fish brought back.", "R  Try again    /    N  New cave"
        label(canvas, title, 640, 306, 47, GOLD if game.finished else INK, "display", "midtop")
        label(canvas, detail, 640, 369, 20, MUTED, anchor="midtop")
        label(canvas, control, 640, 418, 16, MINT, "bold", "midtop")
