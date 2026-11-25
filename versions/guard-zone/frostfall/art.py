"""Artwork, typography and audio for the Pygame client."""

import math
import os
from array import array
from functools import lru_cache
from pathlib import Path
from random import Random

import pygame as pg

ASSETS = Path(__file__).resolve().parents[1] / "assets"
INK = (238, 249, 255)
MUTED = (155, 187, 203)
DIM = (109, 151, 173)
NIGHT = (8, 23, 35)
PANEL = (12, 32, 46)
BORDER = (38, 74, 90)
MINT = (121, 230, 211)
CORAL = (255, 139, 133)
AZURE = (110, 198, 255)
TEAM = (CORAL, AZURE)
GOLD = (250, 207, 134)


def shade(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def rect(surface, color, bounds, radius=12, width=0):
    pg.draw.rect(surface, color, bounds, width, border_radius=radius)


@lru_cache(maxsize=128)
def font(size, style="body"):
    files = {"body": "segoeui.ttf", "strong": "segoeuib.ttf", "label": "bahnschrift.ttf",
             "display": "georgia.ttf", "italic": "georgiai.ttf", "mono": "consola.ttf"}
    windows_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / files[style]
    return pg.font.Font(str(windows_path) if windows_path.is_file() else
                        pg.font.match_font({"display": "dejavuserif", "italic": "dejavuserif",
                                            "mono": "dejavusansmono"}.get(style, "dejavusans"),
                                           bold=style in ("strong", "label"), italic=style == "italic"), size)


@lru_cache(maxsize=1024)
def rendered(value, size, color, style):
    return font(size, style).render(value, True, color)


def text(surface, value, x, y, size=20, color=INK, style="body", anchor="topleft"):
    content = rendered(str(value), size, color, style)
    bounds = content.get_rect(**{anchor: (round(x), round(y))})
    surface.blit(content, bounds)
    return bounds


def wrap(surface, value, x, y, width, size=18, color=MUTED, style="body", step=None, limit=10):
    lines = []
    current = ""
    for word in value.split():
        candidate = f"{current} {word}" if current else word
        if current and font(size, style).size(candidate)[0] > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) > limit:
        lines = lines[:limit]
        while font(size, style).size(lines[-1] + "…")[0] > width:
            lines[-1] = lines[-1][:-1]
        lines[-1] += "…"
    for line in lines:
        text(surface, line, x, y, size, color, style)
        y += step or size + 5
    return y


def icon(surface, name, center, color=INK, size=24):
    x, y = center
    unit = size / 24
    def point(a, b):
        return round(x + a * unit), round(y + b * unit)
    def points(*coords):
        return [point(a, b) for a, b in coords]
    def line(*coords, closed=False):
        pg.draw.lines(surface, color, closed, points(*coords), max(1, round(2 * unit)))

    if name == "peak":
        line((-11, 9), (-5, 0), (-2, 4), (4, -9), (12, 9), (-11, 9))
        line((1, -3), (4, -9), (7, -3), (4, -4), (2, -1))
    elif name == "fish":
        pg.draw.ellipse(surface, color, (*point(-7, -5), max(2, round(15 * unit)), max(2, round(10 * unit))))
        pg.draw.polygon(surface, color, points((-5, 0), (-12, -5), (-12, 5)))
        pg.draw.circle(surface, NIGHT if color != NIGHT else (209, 240, 250), point(4, -1), max(1, round(unit)))
    elif name == "shield":
        line((0, -9), (8, -6), (7, 3), (0, 9), (-7, 3), (-8, -6), closed=True)
        line((-3, 0), (-1, 2), (4, -3))
    elif name == "diamond":
        line((0, -10), (8, 0), (0, 10), (-8, 0), closed=True)
        pg.draw.circle(surface, color, point(0, 0), max(1, round(2 * unit)))
    elif name == "play":
        pg.draw.polygon(surface, color, points((-4, -8), (8, 0), (-4, 8)))
    elif name == "pause":
        line((-4, -7), (-4, 7))
        line((4, -7), (4, 7))
    elif name == "arrow":
        line((-8, 0), (8, 0), (3, -5))
        line((8, 0), (3, 5))
    elif name == "back":
        line((8, 0), (-8, 0), (-3, -5))
        line((-8, 0), (-3, 5))
    elif name == "shark":
        pg.draw.polygon(surface, color, points((-11, 7), (-7, 4), (-3, -6), (0, -9), (4, 3), (11, 7)))
    elif name == "snow":
        for n in range(3):
            angle = n * math.pi / 3
            dx, dy = 9 * math.cos(angle), 9 * math.sin(angle)
            line((-dx, -dy), (dx, dy))
        pg.draw.circle(surface, color, point(0, 0), max(1, round(3 * unit)), max(1, round(unit)))
    elif name == "bait":
        line((0, -10), (6, -4), (5, 4), (0, 9), (-5, 4), (-6, -4), closed=True)
        line((-5, 1), (5, -2))
    elif name in ("sound", "mute"):
        line((-10, -3), (-6, -3), (0, -8), (0, 8), (-6, 3), (-10, 3), closed=True)
        if name == "mute":
            line((4, -3), (10, 3))
            line((4, 3), (10, -3))
        else:
            line((4, -4), (6, 0), (4, 4))
            line((7, -7), (10, -3), (10, 3), (7, 7))
    elif name == "gear":
        pg.draw.circle(surface, color, point(0, 0), round(7 * unit), max(1, round(2 * unit)))
        pg.draw.circle(surface, color, point(0, 0), round(2 * unit), max(1, round(unit)))
        for n in range(8):
            a = math.pi * n / 4
            line((6 * math.cos(a), 6 * math.sin(a)), (10 * math.cos(a), 10 * math.sin(a)))
    elif name == "close":
        line((-6, -6), (6, 6))
        line((-6, 6), (6, -6))
    elif name == "restart":
        cx, cy = point(0, 0)
        radius = round(8 * unit)
        pg.draw.arc(surface, color, (cx - radius, cy - radius, radius * 2, radius * 2),
                    .45, math.tau - .9, max(1, round(2 * unit)))
        line((4, -8), (8, -5), (3, -4))
    elif name == "spark":
        line((-8, 0), (8, 0))
        line((0, -8), (0, 8))
        line((-5, -5), (5, 5))
        line((-5, 5), (5, -5))


def panel(surface, bounds, *, color=PANEL, border=BORDER, radius=14):
    rect(surface, color, bounds, radius)
    rect(surface, border, bounds, radius, 1)


def pill(surface, value, x, y, color=MINT, fill=(17, 53, 61), icon_name=None):
    width = font(14, "label").size(value)[0] + 24 + (23 if icon_name else 0)
    rect(surface, fill, (x, y, width, 28), 14)
    if icon_name:
        icon(surface, icon_name, (x + 15, y + 14), color, 14)
    text(surface, value, x + (32 if icon_name else 12), y + 14, 14, color, "label", "midleft")
    return width


@lru_cache(maxsize=2)
def landscape():
    return pg.image.load(str(ASSETS / "ice-background.png")).convert()


@lru_cache(maxsize=6)
def backdrop(size, menu):
    w, h = size
    photo = landscape()
    scale = max(w / photo.get_width(), h / photo.get_height())
    photo = pg.transform.smoothscale(photo, (round(photo.get_width() * scale), round(photo.get_height() * scale)))
    result = pg.Surface(size)
    result.blit(photo, (w - photo.get_width(), (h - photo.get_height()) // 2))
    # Blue color grade, then an opaque gradient over the text area.
    grade = pg.Surface(size)
    grade.fill((101, 164, 197) if menu else (31, 64, 83))
    result.blit(grade, (0, 0), special_flags=pg.BLEND_RGB_MULT)
    veil = pg.Surface(size, pg.SRCALPHA)
    for x in range(w):
        ratio = x / w
        opacity = 242 - round(221 * min(1, max(0, (ratio - .16) / .78)) ** 1.35) if menu else 188
        pg.draw.line(veil, (4, 15, 25, opacity), (x, 0), (x, h))
    result.blit(veil, (0, 0))
    for y in range(h):
        t = y / h
        alpha = round(max(0, (t - .52) / .48) ** 1.6 * (210 if menu else 110))
        pg.draw.line(veil, (5, 18, 28, alpha), (0, y), (w, y))
    result.blit(veil, (0, 0))
    return result.convert()


@lru_cache(maxsize=80)
def ice_tile(size, variant):
    rng = Random(14893 + variant)
    base = pg.Surface((84, 84), pg.SRCALPHA)
    points = [(6, 7), (13, 3), (60, 3), (75, 6), (80, 15), (80, 65),
              (74, 76), (62, 79), (13, 79), (4, 72), (2, 57), (2, 16)]
    top = [(x, min(69, y - max(0, (y - 35) // 4))) for x, y in points]
    pg.draw.polygon(base, (2, 14, 28, 140), [(x + 1, min(83, y + 5)) for x, y in points])
    pg.draw.polygon(base, (68, 134, 169), points)
    pg.draw.polygon(base, (105, 177, 202), [points[6], points[7], (47, 74), (63, 66), (77, 62)])
    pg.draw.polygon(base, (40, 99, 143), [(5, 67), (14, 79), (34, 79), (25, 69)])
    pg.draw.polygon(base, (128, 192, 214), top)
    plate = pg.Surface((84, 84), pg.SRCALPHA)
    pg.draw.polygon(plate, (255, 255, 255, 255), top)
    tint = pg.Surface((84, 84), pg.SRCALPHA)
    for y in range(84):
        tone = shade((216, 244, 248), (119, 183, 215), y / 84)
        pg.draw.line(tint, (*tone, 255), (0, y), (83, y))
    tint.blit(plate, (0, 0), special_flags=pg.BLEND_RGBA_MULT)
    base.blit(tint, (0, 0))
    frost = pg.Surface((84, 84), pg.SRCALPHA)
    for _ in range(13):
        x, y = rng.randint(8, 73), rng.randint(8, 65)
        pg.draw.polygon(frost, (239, 255, 255, rng.randrange(12, 44)), ((x, y), (x+8, y-2), (x+4, y+6)))
    for _ in range(46):
        x, y = rng.randint(9, 73), rng.randint(8, 63)
        pg.draw.circle(frost, (236, 255, 255, rng.randrange(15, 90)), (x, y), rng.choice((1, 1, 2)))
    x, y = rng.randrange(16, 43), rng.randrange(20, 49)
    pg.draw.lines(frost, (237, 255, 255, 110), False, ((8, y-8), (19, y-4), (x, y), (x+6, y+7), (x+14, y+10)))
    pg.draw.lines(frost, (102, 157, 189, 85), False, ((x, y), (x + 7, y - 7), (x + 14, y - 8)))
    base.blit(frost, (0, 0))
    pg.draw.lines(base, (231, 252, 255), False, top[:5], 2)
    pg.draw.lines(base, (174, 221, 236), False, top[5:] + [top[0]], 1)
    return pg.transform.smoothscale(base, (size, size))


@lru_cache(maxsize=64)
def penguin(size, team, role):
    cape = TEAM[team]
    art = pg.Surface((120, 128), pg.SRCALPHA)
    pg.draw.ellipse(art, (11, 26, 49, 55), (9, 109, 104, 16))
    pg.draw.ellipse(art, (10, 22, 34, 95), (23, 110, 76, 12))
    pg.draw.ellipse(art, (140, 60, 42), (30, 100, 28, 17))
    pg.draw.ellipse(art, (140, 60, 42), (62, 100, 28, 17))
    pg.draw.ellipse(art, (245, 158, 81), (31, 100, 25, 13))
    pg.draw.ellipse(art, (248, 168, 87), (63, 100, 25, 13))
    pg.draw.ellipse(art, (16, 29, 52), (22, 32, 78, 75))
    pg.draw.ellipse(art, (28, 49, 76), (25, 35, 65, 64))
    pg.draw.ellipse(art, (10, 28, 50), (15, 55, 24, 40))
    pg.draw.ellipse(art, (19, 39, 66), (82, 52, 23, 43))
    pg.draw.ellipse(art, (200, 224, 236), (34, 53, 57, 52))
    pg.draw.ellipse(art, (245, 251, 252), (38, 52, 48, 46))
    pg.draw.ellipse(art, (15, 28, 48), (23, 10, 76, 64))
    pg.draw.ellipse(art, (34, 57, 82), (27, 13, 64, 52))
    pg.draw.ellipse(art, (72, 105, 124), (36, 17, 36, 11))
    pg.draw.ellipse(art, (39, 62, 87), (33, 22, 50, 25))
    pg.draw.ellipse(art, (230, 245, 250), (35, 31, 30, 34))
    pg.draw.ellipse(art, (235, 248, 249), (59, 33, 27, 31))
    pg.draw.ellipse(art, (248, 254, 253), (38, 34, 25, 27))
    pg.draw.ellipse(art, (248, 254, 253), (60, 36, 23, 25))
    for x, y in ((53, 38), (71, 40)):
        pg.draw.ellipse(art, (12, 25, 37), (x, y, 9, 13))
        pg.draw.circle(art, (255, 255, 255), (x + 3, y + 3), 2)
    pg.draw.polygon(art, (170, 76, 45), [(57, 49), (73, 47), (86, 53), (71, 62), (60, 59)])
    pg.draw.polygon(art, (255, 177, 85), [(57, 49), (73, 47), (86, 53), (69, 56), (60, 55)])
    shade_color = shade(cape, (36, 34, 69), .52)
    pg.draw.polygon(art, shade_color, [(34, 61), (19, 69), (10, 90), (29, 87), (42, 73)])
    pg.draw.polygon(art, cape, [(34, 61), (19, 69), (13, 85), (29, 81), (42, 72)])
    pg.draw.polygon(art, shade_color, [(23, 56), (39, 62), (73, 64), (96, 57), (95, 73), (74, 80), (40, 78), (25, 69)])
    pg.draw.polygon(art, cape, [(24, 54), (42, 62), (74, 63), (95, 56), (93, 68), (73, 75), (40, 73), (25, 66)])
    pg.draw.lines(art, shade(cape, INK, .5), False, [(25, 56), (42, 63), (74, 64), (93, 58)], 2)
    icon(art, "diamond" if role == 0 else "shield", (50, 68), (21, 42, 57), 14)
    return pg.transform.smoothscale(art, (size, round(size * 128 / 120)))


class Audio:
    def __init__(self, enabled):
        self.enabled = enabled
        self.sounds = {}
        if pg.mixer.get_init() is None:
            return
        effects = {"click": (570, .065), "move": (420, .14), "pickup": (840, .2),
                   "shark": (108, .38), "strike": (63, .32), "rescue": (485, .26),
                   "freeze": (880, .3), "result": (260, .6), "bait": (705, .16)}
        rate, _, channels = pg.mixer.get_init()
        rng = Random(325)
        for name, (hz, duration) in effects.items():
            samples = array("h")
            for frame in range(round(rate * duration)):
                t = frame / rate
                progress = t / duration
                volume = min(1, t * 260) * (1 - progress) ** 2
                frequency = hz * (1 - .25 * progress if name in ("shark", "strike") else 1 + .45 * progress)
                harmonic = math.sin(math.tau * frequency * t) + .23 * math.sin(math.tau * frequency * 1.5 * t)
                noise = .5 * rng.uniform(-1, 1) if name in ("move", "strike", "freeze") else 0
                samples.extend([int(6300 * volume * (harmonic + noise))] * channels)
            self.sounds[name] = pg.mixer.Sound(buffer=samples)

    def play(self, key):
        if self.enabled and key in self.sounds:
            self.sounds[key].play()

