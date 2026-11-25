"""Render the Go Go board, penguin sprites and combat effects."""

from dataclasses import dataclass
from math import cos, pi, sin, tau

from panda3d.core import LineSegs, Point2, Point3, TransparencyAttrib

from arena import COLS, DEFEAT_ANIMATION, DEFEAT_FADE, DEFEAT_VISIBLE, HURT_ANIMATION, ROSTER, ROWS, clamp
from gogo_runtime.geometry import FLOE, GOLD, TOP, circle, ease
from gogo_tiles import BoardTile, TileSkin, load_tile_skins
from sprites import ATTACK, DEFEAT, FRAMES_PER_POSE, HURT, IDLE, WALK, load_atlases, make_sprite, set_frame

VIOLET = (.71, .32, 1.)
VIOLET_CORE = (.94, .84, 1.)
UPGRADE_DURATION = .92
TILE_PATTERN = (
    (5, 0, 1, 3, 0, 4, 2, 5),
    (4, 2, 0, 1, 4, 0, 3, 1),
    (0, 1, 3, 0, 2, 1, 0, 4),
    (2, 0, 4, 2, 1, 3, 4, 0),
    (5, 3, 1, 0, 4, 0, 2, 5),
)


def action_frame(start, progress):
    return start+min(FRAMES_PER_POSE-1, int(max(0., progress)*FRAMES_PER_POSE))


def world(x, y, z=TOP):
    return Point3((x-COLS/2)*FLOE, (ROWS/2-y)*FLOE, z)


def hero_tint(index):
    return (*(component/255 for component in ROSTER[index].color), 1.)


@dataclass
class Actor:
    root: object
    sprite: object
    facing: int
    frame: int = -1


class GoGoStage:
    def __init__(self, render, loader):
        self.root = render.attachNewNode("Go Go 3D arena")
        self.overlay = self.root.attachNewNode("Go Go combat effects")
        self.sprite_root = self.root.attachNewNode("Go Go sprite penguins")
        self.world_clock = 0.
        self.atlases = load_atlases(loader)
        self.actors = {}
        self.effects = None
        self.blinks = {}
        self.tiles = {}
        self.labels = []
        self.upgrades = {}
        self.upgrade_labels = []
        board = self.root.attachNewNode("Go Go textured board")
        skins = load_tile_skins(loader)
        for index in range(COLS*ROWS):
            row, col = divmod(index, COLS)
            tile = BoardTile(board, skins, TILE_PATTERN[row][col])
            self.tiles[col, row] = tile
            tile.root.setPos(world(col+.5, row+.5, 0))
        self.last_options = None

    def selection(self, match, selected, hover):
        if match.phase != "prep":
            selected, hover = None, None
        key = selected, hover, tuple((team.ready, team.upgrades, tuple((cell, unit.upgraded_round)
                                         for cell, unit in team.field.items())) for team in match.sides)
        if key == self.last_options:
            return
        self.last_options = key
        for cell, tile in self.tiles.items():
            if not selected:
                tile.show_skin()
                continue
            side, kind, origin = selected
            if not match.legal_cell(side, cell) or not match.editable(side):
                tile.show_skin()
                continue
            if kind == "unit" and cell == origin:
                tile.show_skin(TileSkin.SELECTED)
                continue
            legal = match.can_upgrade(side, cell) if kind == "upgrade" else (
                cell not in match.sides[side].field if kind in ("card", "return") else True)
            if not legal:
                tile.show_skin()
            elif kind == "upgrade":
                tile.show_skin(TileSkin.UPGRADE)
            elif cell == hover:
                tile.show_skin(TileSkin.HOVER)
            else:
                tile.show_skin((TileSkin.CORAL, TileSkin.AZURE)[side])

    def create_actor(self, side, hero):
        root = self.sprite_root.attachNewNode("Penguin")
        sprite = make_sprite(root, self.atlases[side], hero)
        return Actor(root, sprite, -1 if side else 1)

    def animate_upgrade(self, side, recruit):
        self.upgrades[side, id(recruit)] = (recruit, 0.)

    def pose(self, unit, x, y, moving):
        if unit is not None:
            if unit.hp <= 0:
                return action_frame(DEFEAT, unit.fall/DEFEAT_ANIMATION)
            if unit.hurt_pose and (not unit.attack_pose or unit.hurt_pose > .18):
                return action_frame(HURT, 1-unit.hurt_pose/HURT_ANIMATION)
            if unit.attack_pose:
                return action_frame(ATTACK, 1-unit.attack_pose/unit.attack_span)
            if moving:
                return action_frame(WALK, 1-unit.glide_left/unit.glide_time)
        return IDLE+int(self.world_clock*8+x*.3+y*.2)%FRAMES_PER_POSE

    def sync_actors(self, match):
        fighters = match.phase != "prep"
        if fighters:
            units = [(unit.side, unit.recruit, *unit.visual_position, unit.hp/unit.maximum, unit.shield, unit.fall, unit)
                     for unit in match.fighters if unit.hp > 0 or unit.fall < DEFEAT_VISIBLE]
        else:
            units = [(side, recruit, col+.5, row+.5, 1., 0., 0., None)
                     for side, team in enumerate(match.sides) for (col, row), recruit in team.field.items()]
        alive = set()
        self.labels.clear()
        self.upgrade_labels.clear()
        for side, recruit, x, y, health, shield, fall, unit in units:
            standing = unit is None or unit.hp > 0
            key = side, id(recruit)
            alive.add(key)
            position = world(x, y, TOP + .022)
            actor = self.actors.get(key)
            if actor is None:
                actor = self.actors[key] = self.create_actor(side, recruit.hero)
                actor.root.setPos(position)
            node = actor.root
            blink = self.blinks.get(key) if standing else None
            progress = blink.blink_progress if blink else 1.
            fading = blink is not None and progress < .95
            if fading:
                if progress < .31:
                    position = world(*blink.origin, TOP+.022)
                    opacity = 1-ease(clamp(progress/.31, 0., 1.))
                else:
                    opacity = ease(clamp((progress-.50)/.32, 0., 1.))
                    position.z += .11*(1-opacity)
                node.setColorScale(1., .80+.20*opacity, 1., opacity)
                node.setScale(.54+.46*opacity)
            else:
                opacity = clamp((DEFEAT_VISIBLE-fall)/DEFEAT_FADE, 0., 1.) if not standing else 1.
                node.setColorScale(1., 1., 1., opacity)
                node.setScale(1.)
                if standing and key in self.upgrades:
                    progress = self.upgrades[key][1]/UPGRADE_DURATION
                    self.upgrade_labels.append((Point3(position), recruit.rank, progress))
                    pulse = sin(pi*min(1., progress*1.8))
                    node.setScale(1+.15*pulse)
                    node.setColorScale(1+.18*pulse, 1+.12*pulse, 1-.15*pulse, 1.)
                    position.z += .13*pulse
            moving = unit is not None and standing and unit.glide_left and not (fading or unit.knocked_back)
            if moving:
                direction = unit.x-unit.glide_from[0]
            elif unit is not None and unit.target is not None and standing:
                direction = unit.target.x-x
            else:
                direction = 0.
            if abs(direction) > .10:
                actor.facing = 1 if direction > 0 else -1
            actor.sprite.setSx(actor.facing)
            frame = self.pose(unit, x, y, moving)
            if frame != actor.frame:
                set_frame(actor.sprite, recruit.hero, frame)
                actor.frame = frame
            node.setPos(position)
            if standing and not fading:
                self.labels.append((position, side, recruit, health, shield))
        for key in self.actors.keys()-alive:
            actor = self.actors.pop(key)
            actor.root.removeNode()

    def draw_effects(self, match):
        if self.effects:
            self.effects.removeNode()
            self.effects = None
        if not match.effects and not self.upgrade_labels:
            return
        rays = LineSegs("Go Go arena effects")
        rays.setThickness(2.5)
        for origin, _, progress in self.upgrade_labels:
            self.draw_upgrade(rays, origin, progress)
        for effect in match.effects:
            if effect.blink_actor is not None:
                self.draw_night_slip(rays, effect)
                continue
            strength = min(1., effect.life/.14)
            tint = hero_tint(effect.hero) if effect.spell else (.94, .98, 1., 1.)
            rays.setColor(*tint[:3], .85*strength)
            origin = world(*effect.origin, TOP+.38)
            target = world(*effect.target, TOP+.37)
            rays.moveTo(origin)
            rays.drawTo(target)
            radius = (.38-effect.life) * (.85 if effect.spell else .48)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                rays.moveTo(target + Point3(dx*radius*.55, dy*radius*.55, .02))
                rays.drawTo(target + Point3(dx*radius, dy*radius, .10))
        self.effects = self.overlay.attachNewNode(rays.create())
        self.effects.setTransparency(TransparencyAttrib.MAlpha)
        self.effects.setDepthWrite(False)

    def draw_upgrade(self, rays, origin, progress):
        fade = min(1., progress*10)*(1-progress)**.75
        radius = .22+.35*ease(progress)
        rays.setColor(*GOLD[:3], fade)
        for index, (x, y) in enumerate(circle(radius, 24)+[(radius, 0)]):
            (rays.moveTo if index == 0 else rays.drawTo)(origin+Point3(x, y, .045))
        for index in range(7):
            angle = tau*index/7+progress*.65
            spread = radius*(.83+.20*(index % 2))
            spark = origin+Point3(cos(angle)*spread, sin(angle)*spread, .13+progress*(.7+.16*(index % 3)))
            rays.setColor(1, .92, .67, fade*.92)
            rays.moveTo(spark)
            rays.drawTo(spark+Point3(0, 0, .12*(1-progress)))

    def draw_night_slip(self, rays, effect):
        progress = effect.blink_progress
        origin, target = (world(*cell, TOP+.054) for cell in (effect.origin, effect.target))
        departure = clamp((.55-progress)/.45, 0., 1.)
        arrival = clamp((progress-.34)/.66, 0., 1.)
        for point, intensity, radius, spin in (
            (origin, departure, .31-.18*min(1., progress/.38), progress*tau),
            (target, sin(pi*arrival)**.65, .19+.24*arrival, -progress*tau),
        ):
            if intensity <= 0:
                continue
            rays.setColor(*VIOLET, intensity)
            for i, (x, y) in enumerate(circle(radius, 28)+[(radius, 0)]):
                (rays.moveTo if i == 0 else rays.drawTo)(point + Point3(x, y, 0.))
            rays.setColor(*VIOLET_CORE, intensity*.88)
            for index in range(8):
                a = spin+index*tau/8
                base = Point3(cos(a)*radius, sin(a)*radius, .021)
                rays.moveTo(point+base)
                rays.drawTo(point+base*1.37+Point3(0, 0, .09+.13*intensity))
        if .18 < progress < .72:
            travel = clamp((progress-.18)/.39, 0., 1.)
            tail = max(0., travel-.32)
            rays.setColor(*VIOLET, .96*(1-clamp((progress-.56)/.16, 0., 1.)))
            for i in range(13):
                t = tail+(travel-tail)*i/12
                point = origin+(target-origin)*t+Point3(0, 0, .53*sin(pi*t))
                (rays.moveTo if i == 0 else rays.drawTo)(point)

    def update(self, match, dt, *, selected=None, hover=None):
        self.world_clock += dt
        self.upgrades = {key: (recruit, elapsed+dt) for key, (recruit, elapsed) in self.upgrades.items()
                         if elapsed+dt < UPGRADE_DURATION}
        for (col, row), tile in self.tiles.items():
            lift = .028 if hover == (col, row) and selected else 0.
            tile.root.setZ(sin(self.world_clock*1.2 + (row*COLS+col)*.61)*.008 + lift)
        self.selection(match, selected, hover)
        self.blinks = {(effect.side, id(effect.blink_actor)): effect
                       for effect in match.effects if effect.blink_actor is not None}
        self.sync_actors(match)
        self.draw_effects(match)

    def pick(self, camera, lens, pointer):
        near, far = Point3(), Point3()
        if not pointer or not lens.extrude(Point2(*pointer), near, far):
            return None
        near = self.root.getRelativePoint(camera, near)
        far = self.root.getRelativePoint(camera, far)
        ray = far - near
        if abs(ray.z) < .0001:
            return None
        fraction = (TOP-near.z)/ray.z
        if not 0 <= fraction <= 1:
            return None
        point = near+ray*fraction
        col = int((point.x/FLOE+COLS/2)//1)
        row = int((ROWS/2-point.y/FLOE)//1)
        return (col, row) if (col, row) in self.tiles else None
