"""Guard markings, cracked ice, and fish visible beneath a frosted layer."""

from panda3d.core import LineSegs, TransparencyAttrib

from .stage3d import Arena, GOLD, TEAM, TOP, VIOLET, circle, flat_shape, outline


class GuardArena(Arena):
    def __init__(self, render, font):
        super().__init__(render, font)
        self.guard_markers = [self.make_guard_markers(tile) for tile in self.tiles]
        self.overlay_key = None

    @staticmethod
    def make_guard_markers(tile):
        parent = tile.root.attachNewNode("Guard markings")
        parent.setShaderOff(1)
        parent.setZ(TOP+.023)
        sides = []
        for team, color in enumerate(TEAM):
            side = parent.attachNewNode("Guard corners")
            for x, y in ((-.405, -.400), (.405, .400)) if team == 0 else ((.405, -.400), (-.405, .400)):
                dx, dy = (-.11 if x > 0 else .11), (-.10 if y > 0 else .10)
                for height, thickness, tone in ((0., 5, (.09, .20, .31, 1)), (.003, 3, color)):
                    lines = LineSegs("Shield corners")
                    lines.setThickness(thickness)
                    lines.setColor(*tone)
                    lines.moveTo(x+dx, y, height)
                    lines.drawTo(x, y, height)
                    lines.drawTo(x, y+dy, height)
                    side.attachNewNode(lines.create())
            sides.append(side)
            side.hide()
        contested = outline("Contested ice", parent, circle(.084, 6), .70, GOLD)
        contested.setPos(.278, .286, .003)
        contested.hide()

        fractures = parent.attachNewNode("Fishing cracks")
        lines = LineSegs("Fracture lines")
        lines.setThickness(2.2)
        lines.setColor(.08, .28, .42, 1)
        for points in (((-.34, -.24), (-.18, -.13), (-.11, .025), (0, .09), (.09, .30)),
                       ((-.11, .025), (.05, -.035), (.18, -.045), (.35, -.23)),
                       ((.05, -.035), (.03, -.18), (.10, -.33)),
                       ((0, .09), (.19, .14), (.31, .25))):
            lines.moveTo(*points[0], .004)
            for point in points[1:]:
                lines.drawTo(*point, .004)
        fractures.attachNewNode(lines.create())
        fractures.hide()
        plan = outline("Planned Defender position", parent, circle(.29), .88, VIOLET)
        plan.setZ(.010)
        plan.hide()
        return sides, contested, fractures, plan

    def draw_fish(self, tile, value, cell):
        changed = tile.value != value
        super().draw_fish(tile, value, cell)
        if not changed or value < 1:
            return
        for prop in tile.fish.getChildren():
            if prop.getName() == self.fish_model.getName():
                prop.setColorScale(.69, .87, 1., 1.)
        profile = tuple((x*.375, y*.172) for x, y in circle(1, 18))
        frost = flat_shape("Clear ice over fish", tile.fish, profile, (.40, .77, .95, .29), .128)
        frost.setShaderOff(1)
        frost.setTransparency(TransparencyAttrib.MAlpha)
        frost.setDepthWrite(False)

    def show_guards(self, guarded, cracked, planned):
        key = guarded, cracked, planned
        if self.overlay_key == key:
            return
        self.overlay_key = key
        coral, azure, overlap = guarded
        for cell, (sides, contested, fractures, plan) in enumerate(self.guard_markers):
            for side, cells in zip(sides, (coral, azure)):
                side.show() if cell in cells or cell in overlap else side.hide()
            contested.show() if cell in overlap else contested.hide()
            fractures.show() if cell in cracked else fractures.hide()
            plan.show() if cell == planned else plan.hide()
