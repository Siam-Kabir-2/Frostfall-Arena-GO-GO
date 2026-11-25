"""Procedural mountain course and chase camera."""

from math import atan2, cos, degrees, exp, pi, sin, tau
from random import Random

from panda3d.core import BillboardEffect, Fog, LineSegs, TextNode, Vec3

from frostfall.stage3d import Mesh, mix, oval, penguin, sphere
from whiteout_rules import FORKS, LENGTH, CHECKPOINTS, ROUGH_ICE, height, road_x, width

PALETTE = ((1., .53, .24, 1), (.39, .91, 1., 1), (1., .81, .37, 1),
           (.97, .47, .61, 1), (.66, .94, .65, 1), (.65, .60, 1., 1),
           (.28, .90, .78, 1), (.96, .75, 1., 1))
CORAL, CYAN, GOLD = PALETTE[:3]
SNOW = (.72, .86, .90, 1)
SHADE = (.16, .33, .45, 1)
ICE = (.25, .69, .83, 1)
COLD = (.079, .22, .29, 1)
RIDGE = (.23, .41, .53, 1)
FOG = (.53, .70, .76)


def quad(mesh, a, b, c, d, tint, tones=None):
    mesh.triangle((a, b, c), tint, vertex_colors=tones[:3] if tones else None)
    mesh.triangle((a, c, d), tint, vertex_colors=(tones[0], tones[2], tones[3]) if tones else None)


def panel(parent, name, pos, size, color):
    x, y, z = pos
    a, b, c = (length / 2 for length in size)
    corners = [(x + u*a, y + v*b, z + w*c) for u, v, w in
               ((-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1),
                (-1, 1, -1), (1, 1, -1), (1, 1, 1), (-1, 1, 1))]
    mesh = Mesh(name)
    for index, face in enumerate(((0, 1, 2, 3), (1, 5, 6, 2), (5, 4, 7, 6), (4, 0, 3, 7),
                                  (3, 2, 6, 7), (4, 5, 1, 0))):
        quad(mesh, *(corners[vertex] for vertex in face), mix(color, COLD, (.08, .22, .38, .21, 0., .45)[index]))
    return mesh.attach(parent)


class Mountain:
    def __init__(self, base, fonts):
        self.base = base
        self.fonts = fonts
        self.root = base.render.attachNewNode("Whiteout mountainside")
        self.sky = self.make_sky()
        fog = Fog("High alpine mist")
        fog.setColor(*FOG)
        fog.setLinearRange(80, 500)
        self.root.setFog(fog)
        self.shapes = self.root.attachNewNode("Sculpture templates")
        self.shapes.hide()
        self.unit = sphere(self.shapes, 16, 10)
        self.static = self.root.attachNewNode("Track and scenery")
        self.runners = self.root.attachNewNode("Racers")
        self.dynamics = self.root.attachNewNode("Weather and trails")
        self.trail_node = None
        self.last_trail = None
        self.camera_ready = False
        self.gate_blades = ()
        self.make_course()
        self.static.flattenStrong()
        self.clouds = self.make_avalanche()
        self.make_racers(8)
        self.display_gate = None

    def make_sky(self):
        mesh = Mesh("Sky gradient")
        levels = ((-pi / 2, (.60, .75, .79, 1)), (-.20, (.67, .81, .82, 1)),
                  (0, (.82, .85, .81, 1)), (.13, (.56, .73, .75, 1)),
                  (.37, (.28, .54, .64, 1)), (.72, (.09, .28, .43, 1)),
                  (pi / 2, (.027, .097, .22, 1)))
        for (lo, low_tint), (hi, high_tint) in zip(levels, levels[1:]):
            for k in range(72):
                a, b = tau * k / 72, tau * (k + 1) / 72
                placements = ((a, lo, low_tint), (b, lo, low_tint), (b, hi, high_tint), (a, hi, high_tint))
                dots = [(720*cos(angle)*cos(alt), 720*sin(angle)*cos(alt), 720*sin(alt)) for angle, alt, _ in placements]
                colors = tuple(mix(tint, (1., .79, .55, 1.), .79*max(0., cos(angle-1.93))**11*exp(-5*abs(alt-.12)))
                               for angle, alt, tint in placements)
                quad(mesh, *dots, low_tint, colors)
        sky = mesh.attach(self.base.render)
        sky.setTwoSided(True)
        sky.setLightOff()
        sky.setDepthWrite(False)
        sky.setBin("background", 0)
        return sky

    def point(self, s, edge, route=-1, z=0.):
        return road_x(s, route) + edge, s, height(s, route) + z

    def road(self, start, end, route):
        top, stone, marks = Mesh("Snow surface"), Mesh("Ice shelf"), Mesh("Course paint")
        rng = Random(81 + route)
        rows = list(range(start, end, 4)) + [end]
        for a, b in zip(rows, rows[1:]):
            wa, wb = width(a, route), width(b, route)
            is_blue = route == 1 or 416 < a < 728
            palette = (.46, .77, .85, 1) if is_blue else SNOW
            tint = mix(palette, (.76, .89, .96, 1), .12 + .12 * sin(a * .103))
            for left, right in zip((-1, -.88, -.49, 0, .49, .88), (-.88, -.49, 0, .49, .88, 1)):
                face = mix(tint, SHADE, rng.uniform(.015, .061) + (.105 if abs(left + right) >= 1.6 else 0))
                z = .045 if route >= 0 else 0.
                quad(top, self.point(a, wa * left, route, z), self.point(a, wa * right, route, z),
                     self.point(b, wb * right, route, z), self.point(b, wb * left, route, z), face)
            for side in (-1, 1):
                ba, bb = wa * side, wb * side
                elevation = -4.0 - 1.8 * sin(a * .037 + side)
                bank = (1.3 if route >= 0 or 840 < a < 1100 else 5.2) * side
                lip = mix(SNOW, ICE, .22 if route != 1 else .63)
                quad(stone, self.point(a, ba, route), self.point(b, bb, route),
                     self.point(b, bb+bank, route, elevation), self.point(a, ba+bank, route, elevation), lip,
                     (lip, lip, RIDGE, SHADE))
                edge_tint = mix(CYAN if route == 1 else CORAL if route == 2 else (.95, .98, .97, 1), palette, .28)
                if a % 16 < 10:
                    quad(marks, self.point(a, ba-side*.44, route, .082), self.point(a, ba-side*.64, route, .082),
                         self.point(b, bb-side*.64, route, .082), self.point(b, bb-side*.44, route, .082), edge_tint)
            for _ in range(4):
                lane = rng.uniform(-wa * .85, wa * .85)
                icy = mix(palette, (1, 1, 1, 1), rng.uniform(.18, .40))
                top.triangle((self.point(a, lane, route, .056), self.point(a+.35, lane+.25, route, .057),
                              self.point(min(b, a+rng.uniform(1.5, 3.9)), lane-.08, route, .058)),
                             icy, vertex_colors=(tint, icy, tint))
        for mesh in (top, stone, marks):
            mesh.attach(self.static).setTwoSided(True)

    def peak(self, mesh, x, y, z, size, rise, rng, snow=.47, hue=RIDGE):
        points = [(x + cos(tau * i / 8) * size * rng.uniform(.74, 1.3),
                   y + sin(tau * i / 8) * size * rng.uniform(.74, 1.3), z+rng.uniform(-4, 4)) for i in range(8)]
        summit = (x + rng.uniform(-.28, .28) * size, y + rng.uniform(-.3, .3) * size, z + rise)
        ring = [tuple(f + (t-f) * rng.uniform(snow-.10, snow+.15) for f, t in zip(point, summit)) for point in points]
        for i, a in enumerate(points):
            j = (i+1) % len(points)
            shade = mix(hue, COLD, .21 + .15 * cos(tau * i / 8 + .6))
            white = mix(SNOW, hue, .13 + .27 * cos(tau * i / 8 + .4) ** 2)
            quad(mesh, a, points[j], ring[j], ring[i], shade, (hue, shade, shade, shade))
            mesh.triangle((ring[i], ring[j], summit), white)

    def fir(self, mesh, x, y, z, size, tint, rng):
        for index in range(3):
            base = z + index * size * .25
            radius = size * (.30-index*.065)
            top = (x+.09*size, y, base+size*.49)
            ring = [(x+radius*cos(tau*i/6), y+radius*sin(tau*i/6), base) for i in range(6)]
            for i in range(6):
                face = mix(tint, SNOW, .09 + rng.random() * .32)
                mesh.triangle((ring[i], ring[(i+1) % 6], top), face,
                              vertex_colors=(face, face, mix(face, SNOW, .48)))

    def terrain(self):
        rng = Random(7704)
        terrain, pines = Mesh("Mountain faces"), Mesh("Alpine spruce")
        for s in range(-100, 1510, 30):
            for side in (-1, 1):
                x = road_x(s) + side * rng.uniform(77, 158)
                self.peak(terrain, x, s+rng.uniform(-23, 23), height(s)-63, rng.uniform(23, 81),
                          rng.uniform(56, 113), rng, hue=mix(RIDGE, FOG + (1,), rng.uniform(.15, .37)))
                x = road_x(s) + side * rng.uniform(175, 270)
                self.peak(terrain, x, s, height(s)-93, rng.uniform(68, 132), rng.uniform(131, 203),
                          rng, hue=(.36, .54, .61, 1))
        for s in range(-40, LENGTH+50, 10):
            for side in (-1, 1):
                protected = any(fork.start - 9 < s < fork.end + 9 and fork.side == side for fork in FORKS)
                if protected:
                    continue
                edge = width(s) + rng.uniform(4.5, 8.5)
                x, _, z = self.point(s, edge*side, z=-5.9)
                if 403 < s < 754 or s > 825:
                    x += side * 2.3
                    self.peak(terrain, x, s, z-4.7, rng.uniform(2, 6), rng.uniform(5, 22), rng, hue=SHADE)
                else:
                    for _ in range(2):
                        self.fir(pines, x+side*rng.uniform(0, 9), s+rng.uniform(-4, 4), z-1.4,
                                 rng.uniform(6.4, 13.3), (.075, .28, .31, 1), rng)
        terrain.attach(self.static).setTwoSided(True)
        pines.attach(self.static).setTwoSided(True)

    def text3d(self, parent, text, pos, size, color, *, heading=0):
        label = TextNode(text)
        label.setFont(self.fonts["label"])
        label.setText(text)
        label.setAlign(TextNode.ACenter)
        label.setTextColor(*color)
        card = parent.attachNewNode(label)
        card.setPos(*pos)
        card.setScale(size)
        card.setH(heading)
        card.setTwoSided(True)
        return card

    def arch(self, s, title, color, *, route=-1, half=None, tall=4.9):
        x, y, z = self.point(s, 0, route)
        half = width(s, route) + .8 if half is None else half
        for side in (-1, 1):
            panel(self.static, "Timing gantry", (x+side*half, y, z+tall*.49), (.40, .48, tall+1.2), COLD)
            panel(self.static, "Luminous post", (x+side*(half-.04), y-.26, z+tall*.50), (.135, .06, tall*.93), color)
        panel(self.static, "Timing gantry", (x, y, z+tall-.02), (half*2+.45, .52, 1.07), COLD)
        panel(self.static, "Gantry light", (x, y-.28, z+tall+.47), (half*2+.51, .09, .10), color)
        self.text3d(self.static, title, (x, y-.28, z+tall-.23), .86, (.94, 1, 1, 1))

    def junctions(self):
        for index, fork in enumerate(FORKS):
            s = fork.start - 17
            side = fork.side
            tint = (GOLD, CYAN, CORAL)[index]
            x, _, z = self.point(s, side * (width(s) - .42))
            panel(self.static, "Cut marker pole", (x, s, z+1.29), (.23, .31, 3.3), COLD)
            panel(self.static, "Cut marker plate", (x-side*2.8, s, z+2.50), (6.2, .37, 1.9), COLD)
            panel(self.static, "Cut marker top", (x-side*2.8, s-.19, z+3.43), (6.2, .07, .096), tint)
            self.text3d(self.static, fork.name.upper(), (x-side*2.8, s-.20, z+2.52), .69, tint)
            arrow = "KEEP RIGHT" if side > 0 else "KEEP LEFT"
            self.text3d(self.static, arrow, (x-side*2.8, s-.20, z+1.91), .47, SNOW)
            for distance in range(fork.start-9, fork.end, 12):
                route = index if distance >= fork.start + 24 else -1
                x, y, z = self.point(distance, side*(width(distance, route)+.20), route)
                panel(self.static, "Cut boundary stake", (x, y, z+.50), (.15, .15, 1.2), tint)

    def tunnel(self):
        rng = Random(805)
        rock = Mesh("Blue glacial cavity")
        lights = Mesh("Tunnel lighting")
        start, end = 566, 658
        for y in range(start, end, 4):
            rings = []
            for s in (y, y+4):
                span = 8.4 if s <= start+6 or s >= end-6 else width(s, 1)+1.65
                x, _, z = self.point(s, 0, 1)
                rings.append([(x+span*cos(i*pi/8), s, z-.53+(8.85 + .48*sin(s*.17))*sin(i*pi/8))
                              for i in range(9)])
            for i in range(8):
                tone = mix((.093, .28, .42, 1), ICE, rng.uniform(.17, .54))
                quad(rock, rings[0][i], rings[1][i], rings[1][i+1], rings[0][i+1], tone,
                     (tone, mix(tone, COLD, .16), mix(tone, ICE, .11), tone))
            if (y-start) % 20 == 0:
                for i in (1, 2, 5, 6):
                    x, _, z = rings[0][i]
                    dx = .58 if i < 4 else -.58
                    quad(lights, (x-dx*.14, y-.08, z-.20), (x+dx, y-.08, z-.59),
                         (x+dx, y+.35, z-.59), (x-dx*.14, y+.35, z-.20), CYAN)
        rock.attach(self.static).setTwoSided(True)
        lights.attach(self.static).setTwoSided(True)
        fork = FORKS[1]
        self.arch(fork.shutter, "BLUE TUNNEL", CYAN, route=1, half=width(fork.shutter, 1)+.28, tall=5.8)
        x, s, z = self.point(fork.shutter, 0, 1)
        left = width(s, 1)
        self.gate_blades = tuple(panel(self.dynamics, "Tunnel shutter", (x, s+.15, z+i*.72),
                                       (left*2.1, .42, .49), mix(CORAL, COLD, .25)) for i in range(1, 8))

    def make_course(self):
        self.terrain()
        self.road(-65, LENGTH+50, -1)
        for index, fork in enumerate(FORKS):
            self.road(fork.start, fork.end, index)
        self.junctions()
        self.tunnel()
        self.rough_ice()
        for start, title in ((9, "WHITEOUT"), (412, "BLUE HOLLOW"), (828, "KNIFE EDGE"), (LENGTH, "FINISH")):
            self.arch(start, title, (CORAL if start >= 828 else CYAN), tall=5.45)
        stripe = Mesh("Start, checkpoint and finish lines")
        for s in (0, *CHECKPOINTS[1:], LENGTH):
            wide = width(s)
            for idx in range(24):
                a = -wide+idx*wide/12
                b = a+wide/12
                tint = ((.91, .97, 1, 1) if idx % 2 else COLD) if s in (0, LENGTH) else mix(CYAN, ICE, .42)
                quad(stripe, self.point(s-.34, a, z=.09), self.point(s-.34, b, z=.09),
                     self.point(s+.34, b, z=.09), self.point(s+.34, a, z=.09), tint)
        stripe.attach(self.static).setTwoSided(True)

    def rough_ice(self):
        rng = Random(1194)
        mesh = Mesh("Rough ice patches")
        for patch in ROUGH_ICE:
            a, b, c = (patch.lane-patch.half_width, patch.lane+patch.half_width, patch.lane)
            # Angular blue ice, with small ridges along the edges of the slow zone.
            rim = ((patch.start, c), (patch.start+2, b), (patch.end-2, b), (patch.end, c),
                   (patch.end-3, a), (patch.start+3, a))
            outline = [self.point(s, x, z=.075) for s, x in rim]
            for index, point in enumerate(outline):
                tone = mix((.32, .54, .73, 1), (.48, .78, .89, 1), rng.uniform(.12, .65))
                mesh.triangle((self.point(patch.start+patch.length*.42, c, z=.08), point, outline[(index+1) % 6]), tone)
            for k in range(6):
                s = patch.start+3+k*(patch.length-5)/6
                x = (a if k % 2 else b) + rng.uniform(-.22, .22)
                mesh.triangle((self.point(s, x, z=.12), self.point(s+1.34, x-.14, z=.12),
                               self.point(s+.43, x-.46, z=rng.uniform(.32, .58))), (.70, .89, .96, 1))
            for side in (-1, 1):
                x, y, z = self.point(patch.start+2, c+side*(patch.half_width+.19))
                panel(self.static, "Rough ice flag", (x, y, z+.38), (.12, .17, .89), GOLD)
        mesh.attach(self.static).setTwoSided(True)

    def make_racers(self, count):
        self.runners.getChildren().detach()
        self.actors = []
        self.tags = []
        self.shadows = []
        self.spray = []
        for index in range(count):
            rig = penguin(self.runners, self.unit, PALETTE[index], False)
            rig.root.setScale(2.45)
            for side in (-1, 1):
                oval(rig.root, self.unit, "Racing cap", (side*.19, .063, .755), (.043, .124, .064), PALETTE[index])
            oval(rig.root, self.unit, "Team racing stripe", (0, .208, .445), (.061, .035, .113), PALETTE[index])
            self.actors.append(rig)
            shadow = oval(self.runners, self.unit, "Contact shadow", (0, 0, 0), (.68, 1.11, .032), (.30, .45, .53, 1))
            self.shadows.append(shadow)
            label = self.text3d(self.runners, "", (0, 0, 0), .53, (.98, .99, 1, 1))
            label.node().setShadow(.08, .11)
            label.node().setShadowColor(.014, .07, .105, 1)
            label.setEffect(BillboardEffect.makePointEye())
            label.setLightOff()
            self.tags.append(label)
            self.spray.append(tuple(oval(self.runners, self.unit, "Snow crystals", (0, 0, 0),
                                         (.09, .13, .065), (.82, .95, .99, 1)) for _ in range(6)))

    def race_labels(self, names):
        self.make_racers(len(names))
        for label, name in zip(self.tags, names):
            label.node().setText(name.upper())
        self.camera_ready = False
        self.last_trail = None
        if self.trail_node:
            self.trail_node.removeNode()
            self.trail_node = None

    def make_avalanche(self):
        rng = Random(412)
        return [(oval(self.dynamics, self.unit, "Avalanche plume", (0, 0, 0),
                      (rng.uniform(4, 9), rng.uniform(3.6, 6.8), rng.uniform(2.8, 7.4)),
                      mix(SNOW, (1, 1, 1, 1), rng.random()*.82)),
                 rng.uniform(-17, 17), rng.uniform(-13, 3), rng.uniform(-.5, 3.4), rng.random()*tau)
                for _ in range(24)]

    def draw_trails(self, race, focus):
        if race.tick == self.last_trail or race.tick % 6:
            return
        self.last_trail = race.tick
        if self.trail_node:
            self.trail_node.removeNode()
        chalk = LineSegs("Fresh racing lines")
        chalk.setThickness(2.5)
        strands = [[] for _ in race.racers]
        for bucket in sorted(race.trails):
            for point in race.trails[bucket]:
                if abs(point.s-focus) < 125 and race.tick-point.tick < 156:
                    strands[point.owner].append(point)
        for index, strand in enumerate(strands):
            for a, b in zip(strand, strand[1:]):
                if not 0 < b.tick-a.tick <= 10 or not 0 < b.s-a.s < 6:
                    continue
                color = mix(PALETTE[index], SNOW, (race.tick-a.tick)/165)
                chalk.setColor(*color)
                for offset in (-.28, .28):
                    chalk.moveTo(a.x+offset, a.s, height(a.s, a.route)+.118)
                    chalk.drawTo(b.x+offset, b.s, height(b.s, b.route)+.118)
        self.trail_node = self.dynamics.attachNewNode(chalk.create())

    def update(self, race, focus, dt, menu_clock=None, look_back=False):
        for index, (rig, racer) in enumerate(zip(self.actors, race.racers)):
            label, shadow = self.tags[index], self.shadows[index]
            visible = not racer.eliminated and (not racer.recovery or racer.recovery % 10 < 7)
            for node in (rig.root, label, shadow):
                node.show() if visible else node.hide()
            z = height(racer.s, racer.route)
            path_heading = road_x(racer.s+4, racer.route) - road_x(racer.s, racer.route) + racer.lateral * .21
            if menu_clock is None:
                rig.root.setPos(racer.x, racer.s, z+.23+.042*sin(race.time*9.4+index))
                rig.root.setHpr(186-degrees(atan2(path_heading, 4)), 68 if racer.boosting else 59, -2.1*racer.lateral)
            else:
                rig.root.setPos(racer.x, racer.s, z+.038*sin(menu_clock*2.6+index))
                rig.root.setHpr(161+(index % 3)*18, 8+3*sin(menu_clock*1.8+index), 4*sin(menu_clock+index))
            shadow.setPos(racer.x, racer.s, z+.11)
            label.setPos(racer.x, racer.s, z+2.79)
            if index == focus or menu_clock is not None or (len(race.racers) > 2 and abs(racer.s-race.racers[focus].s) < 11.):
                label.hide()
            for j, crystal in enumerate(self.spray[index]):
                scatter = racer.boosting or abs(racer.lateral) > 3.3
                if not visible or not scatter or menu_clock is not None or racer.recovery:
                    crystal.hide()
                    continue
                crystal.show()
                age = (race.time*3.6+j/6+index*.13) % 1.
                s = racer.s-.75-age*3.4
                x = racer.x-age*racer.lateral*.17 + sin(j*17.+index)*age*1.4
                crystal.setPos(x, s, height(s, racer.route)+.16+sin(age*pi)*.62)
                crystal.setScale(.055+.055*age, .11+.073*age, .06+.05*age)
        for cloud, dx, ds, dz, phase in self.clouds:
            s = race.danger+ds
            cloud.setPos(road_x(s)+dx+2*sin(race.time*1.8+phase), s, height(s)+dz+1.4*cos(race.time*2.3+phase))
            cloud.setHpr(race.time*28+phase*20, race.time*17, phase*47)
        gate_open = race.time < FORKS[1].deadline
        if gate_open != self.display_gate:
            for blade in self.gate_blades:
                blade.hide() if gate_open else blade.show()
            self.display_gate = gate_open
        racer = race.racers[focus]
        if look_back:
            cam = Vec3(racer.x-3.2, racer.s+6, height(racer.s, racer.route)+5.35)
            target = Vec3(road_x(racer.s-52, racer.route), racer.s-52, height(racer.s-52, racer.route)+3.)
        elif menu_clock is None:
            self.draw_trails(race, racer.s)
            lag = 10.8 + .050 * racer.speed
            aim = 17. + .25 * racer.speed
            cam = Vec3(racer.x - racer.lateral*.14, racer.s-lag, height(racer.s, racer.route)+5.75)
            target = Vec3(racer.x*.60+road_x(racer.s+aim, racer.route)*.40, racer.s+aim,
                          height(racer.s+aim, racer.route)+2.25)
        else:
            cam = Vec3(racer.x-6.8+1.7*sin(menu_clock*.33), racer.s+11.2, height(racer.s)+3.8)
            target = Vec3(racer.x+5.4, racer.s-2.1, height(racer.s)+1.53)
        ratio = 1-exp(-dt*6) if self.camera_ready else 1.
        camera = self.base.camera
        camera.setPos(camera.getPos()+(cam-camera.getPos())*ratio)
        target = target if not self.camera_ready else self.look+(target-self.look)*ratio
        self.look = target
        camera.lookAt(target)
        self.sky.setPos(camera.getPos())
        self.camera_ready = True
