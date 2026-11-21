"""Pack the supplied RGBA character sheets into the Go Go atlases."""

from argparse import ArgumentParser
from json import dumps
from pathlib import Path
from statistics import median

import pygame as pg

from arena import ROSTER
from sprites import (ANCHOR_X, ANCHOR_Y, ASSETS, ATLAS_COLS, FRAME_HEIGHT,
                     FRAME_WIDTH, FRAMES_PER_POSE, FRAMES_PER_ROLE)

# Each sheet has a portrait, a column of labels, and six frames in each action row.
# The sheets have different margins and row spacing.
SHEETS = (
    {
        "tank": (709, (0, 148, 289, 430, 573, 724), (0, 73, 447, 512)),
        "mage": (690, (0, 149, 285, 433, 584, 724), (0, 110, 434, 500)),
        "marksman": (720, (0, 149, 298, 444, 588, 724), (0, 111, 466, 478)),
        "assassin": (713, (0, 147, 288, 434, 582, 724), (0, 90, 454, 479)),
        "fighter": (721, (0, 155, 300, 444, 585, 724), (0, 110, 472, 498)),
    },
    {
        "tank": (592, (0, 157, 301, 444, 591, 776), (0, 115, 351, 443)),
        "mage": (592, (0, 154, 300, 450, 600, 776), (0, 137, 336, 466)),
        "marksman": (607, (0, 168, 298, 443, 596, 774), (0, 145, 341, 445)),
        "assassin": (593, (0, 171, 309, 451, 599, 776), (0, 155, 334, 453)),
        "fighter": (612, (0, 173, 314, 456, 603, 777), (0, 174, 372, 480)),
    },
)


def trim_alpha(image, floor, *, portrait=False):
    """Drop nearly transparent matte pixels while retaining soft sprite edges."""
    rgba = bytearray(pg.image.tobytes(image, "RGBA"))
    remap = bytes(round(255 * min(1, max(0, (alpha-floor)/(246-floor)))) for alpha in range(256))
    rgba[3::4] = rgba[3::4].translate(remap)
    result = pg.image.frombytes(bytes(rgba), image.get_size(), "RGBA")
    mask = pg.mask.from_surface(result, 0)
    cleaned = pg.mask.Mask(result.get_size())
    parts = [mask.connected_component()] if portrait else mask.connected_components(14)
    for part in parts:
        cleaned.draw(part, (0, 0))
    result.blit(cleaned.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(255, 255, 255, 0)),
                (0, 0), special_flags=pg.BLEND_RGBA_MULT)
    return result


def frame_bounds(row, name):
    cores = sorted((part.get_bounding_rects()[0] for part in
                    pg.mask.from_surface(row, 180).connected_components(4500)), key=lambda rect: rect.x)
    if len(cores) != FRAMES_PER_POSE:
        raise ValueError(f"{name} has {len(cores)} opaque sprites in this row. Expected {FRAMES_PER_POSE}.")

    width, height = row.get_size()
    alpha = pg.image.tobytes(row, "RGBA")[3::4]
    splits = [0]
    for left, right in zip(cores, cores[1:]):
        # Find the least visible seam between two bodies, including semi-transparent effects.
        middle = (left.right+right.left)/2
        cut = min(range(left.right, right.left+1),
                  key=lambda x: sum(a*a for a in alpha[x::width]) + abs(x-middle)*500)
        splits.append(cut)
    splits.append(width)
    return cores, [pg.Rect(x, 0, right-x, height) for x, right in zip(splits, splits[1:])]


def pack(sheet, side, role, atlas, cards):
    name = ROSTER[role].role.lower()
    left, rows, portrait = SHEETS[side][name]
    pale_matte = side == 1 and name == "tank"
    floor = 159 if pale_matte else 24
    for action, (top, bottom) in enumerate(zip(rows, rows[1:])):
        row = sheet.subsurface((left, top, sheet.get_width()-left, bottom-top))
        cores, bounds = frame_bounds(row, f"{side}-{name}, action {action}")
        ground = median(core.bottom for core in cores)-4
        if action == 0:
            standing_width = median(core.w for core in cores)
            standing_height = median(core.h for core in cores)
        for frame, (core, rect) in enumerate(zip(cores, bounds)):
            center = core.x+min(core.w, standing_width)*(.62 if side == 0 and name == "mage" and action == 0 else .52)
            sprite = trim_alpha(row.subsurface(rect), floor)
            ink = sprite.get_bounding_rect()
            sprite = sprite.subsurface(ink)
            x = round(ANCHOR_X+rect.x+ink.x-center)
            y = round(ANCHOR_Y+ink.y-ground)
            if not pg.Rect(0, 0, FRAME_WIDTH, FRAME_HEIGHT).contains(pg.Rect(x, y, ink.w, ink.h)):
                raise ValueError(f"{side}-{name}, action {action}, frame {frame} exceeds its atlas cell.")
            index = role*FRAMES_PER_ROLE+action*FRAMES_PER_POSE+frame
            atlas.blit(sprite, (index%ATLAS_COLS*FRAME_WIDTH+x, index//ATLAS_COLS*FRAME_HEIGHT+y))

    l, t, r, b = portrait
    art = trim_alpha(sheet.subsurface((l, t, r-l, b-t)), floor, portrait=True)
    art = art.subsurface(art.get_bounding_rect())
    pg.image.save(art, cards/f"{side}-{role}.png")
    return standing_height


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ASSETS/"sprite-sheets")
    parser.add_argument("--output", type=Path, default=ASSETS)
    args = parser.parse_args()
    cards = args.output/"cards"
    cards.mkdir(parents=True, exist_ok=True)
    rows = (len(ROSTER)*FRAMES_PER_ROLE + ATLAS_COLS-1)//ATLAS_COLS
    heights = []
    for side in range(2):
        atlas = pg.Surface((ATLAS_COLS*FRAME_WIDTH, rows*FRAME_HEIGHT), pg.SRCALPHA)
        standing_pixels = []
        for role, hero in enumerate(ROSTER):
            sheet = pg.image.load(args.source/f"{side}-{hero.role.lower()}.png")
            standing_pixels.append(pack(sheet, side, role, atlas, cards))
        pg.image.save(atlas, args.output/f"squad-{side}.png")
        heights.append(standing_pixels)
    (args.output/"sprite-heights.json").write_text(dumps(heights)+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
