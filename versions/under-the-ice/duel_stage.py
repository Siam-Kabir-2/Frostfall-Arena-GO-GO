"""A lit, side-view glacier with animated 3D swimmers and shared landmarks."""

from math import cos, sin, tau
from random import Random

from panda3d.core import LineSegs, NodePath, Point3, Shader, TransparencyAttrib, Vec3, Vec4

from duel import AIR_VENTS, FISH, PASS, POINTS
from frostfall import materials3d
from frostfall.stage3d import CORAL, GOLD, MINT, TEAM, Mesh, fish_model, leopard_seal, oval, penguin, sphere


POOL = """
#version 150
uniform float scene_time;
in vec3 world;
out vec4 p3d_FragColor;
void main() {
    vec2 p = world.xz;
    float depth = clamp((3.04-p.y)/10.8,0.,1.);
    vec3 water = mix(vec3(.065,.28,.34),vec3(.024,.057,.113),pow(depth,.72));
    float glow = exp(-pow((abs(p.x)-10.6+.22*depth)/(1.0+depth*3.7),2.));
    float shafts = glow*(.83+.17*sin(p.x*4.+p.y*.9+scene_time*.5));
    water += vec3(.035,.14,.143)*shafts*(1.-.73*depth);
    float wave = abs(sin(p.x*1.6+p.y*1.8+scene_time*.33)+sin(p.x*2.1-p.y*2.8+scene_time*.42));
    water += vec3(.021,.039,.044)*pow(max(0.,1.-wave),6.)*(1.-.7*depth);
    vec3 sky = mix(vec3(.069,.163,.208),vec3(.024,.06,.12),clamp((p.y-3.04)/6.,0.,1.));
    sky += vec3(.023,.094,.085)*exp(-pow((p.y-5.2-sin(p.x*.18))*.92,2.));
    p3d_FragColor = vec4(mix(water,sky,smoothstep(2.98,3.11,p.y)),1.);
}
"""


def spot(cell, y=0.):
    x, z = POINTS[cell]
    return Point3(x, y, z)


def outline(parent, name, points, color, width=1.8, close=False):
    pen = LineSegs(name)
    pen.setThickness(width)
    pen.setColor(*color)
    pen.moveTo(points[0])
    for point in points[1:]:
        pen.drawTo(point)
    if close:
        pen.drawTo(points[0])
    return parent.attachNewNode(pen.create())


def ring(parent, name, scale, color, width=2.):
    points = tuple(Point3(scale*cos(tau*i/38), 0, scale*sin(tau*i/38)) for i in range(38))
    return outline(parent, name, points, color, width, close=True)


def glacier(parent, name, center, scale, palette, rng):
    geometry = Mesh(name)
    count = 9
    radii = [rng.uniform(.82, 1.17) for _ in range(count)]
    levels = [(-1., .64), (-.51, 1.0), (.19, .88), (.72, .58), (1., .28)]
    tiers = []
    for z, radius in levels:
        tiers.append([Vec3(cos(tau*i/count)*radii[i]*radius+z*.13, sin(tau*i/count)*radii[i]*radius,
                           z+rng.uniform(-.09,.09)) for i in range(count)])
    for lower, upper in zip(tiers, tiers[1:]):
        for i in range(count):
            j = (i+1) % count
            geometry.triangle((lower[i], lower[j], upper[j]), rng.choice(palette))
            geometry.triangle((lower[i], upper[j], upper[i]), rng.choice(palette))
    geometry.fan(tuple(tiers[-1]), palette[0])
    result = geometry.attach(parent)
    result.setPos(*center)
    result.setScale(*scale)
    result.setShaderInput("material_kind", 1)
    result.setTwoSided(True)
    return result


def shelf(parent, left, right, rng):
    mesh = Mesh("Glacier shelf and snow cap")
    stations = [left] + [left+i*(right-left)/10 for i in range(1, 10)] + [right]
    profile = []
    for x in stations:
        profile.append(((x, -1.65+rng.uniform(-.21,.21), 3.23+rng.uniform(-.08,.08)),
                        (x, -1.34+rng.uniform(-.18,.18), 2.82+rng.uniform(-.16,.13)), (x, 2.5, 3.26)))
    for (a, b, c), (d, e, f) in zip(profile, profile[1:]):
        mesh.triangle((a, b, d), (.41, .72, .81, 1))
        mesh.triangle((b, e, d), (.31, .61, .74, 1))
        mesh.triangle((a, d, f), (.86, .96, .98, 1))
        mesh.triangle((a, f, c), (.75, .91, .96, 1))
    roof = mesh.attach(parent)
    roof.setShaderInput("material_kind", 1)
    roof.setTwoSided(True)


class Stage:
    duration = .62

    def __init__(self, render, camera):
        self.root = render.attachNewNode("Under the Ice shared cavern")
        self.root.setShader(Shader.make(Shader.SL_GLSL, materials3d.VERTEX, materials3d.SURFACE))
        self.root.setShaderInput("eye", camera.getPos())
        self.root.setShaderInput("material_kind", 0)
        self.root.setShaderInput("frost_tint", Vec4(0))
        self.root.setShaderInput("cap_tint", Vec4(0))
        self.root.setShaderInput("scene_time", 0.)
        self.elapsed = 0.
        self.playback = None
        self.bank = NodePath("Model assets")
        self.unit = sphere(self.bank)
        self.fish_asset = fish_model(self.bank)
        self.build_cave()
        self.swimmers = tuple(penguin(self.root, self.unit, color, 0) for color in TEAM)
        for rig in self.swimmers:
            rig.root.setScale(1.69)
        self.seal, self.tail, self.flippers = leopard_seal(self.root, self.unit)
        self.seal.setScale(1.43)
        self.overlay = self.root.attachNewNode("Navigation cues")
        self.overlay.setShaderOff(1)
        self.overlay.setTransparency(TransparencyAttrib.MAlpha)
        self.school = []
        self.nodes = []
        self.glows = []
        self.trails = None
        for cell, amount in enumerate(FISH):
            buoy = self.overlay.attachNewNode("Swim landmark")
            buoy.setPos(spot(cell, -.43))
            self.nodes.append(ring(buoy, "Lane marker", .115, (.38,.72,.78,.79), 1.3))
            self.glows.append(ring(buoy, "Legal destination", .39 if cell in AIR_VENTS else .30,
                                   (1,1,1,1), 2.4))
            school = self.root.attachNewNode("Herring school")
            for index in range(amount):
                herring = self.fish_asset.copyTo(school)
                herring.setScale(2.38 if amount == 1 else 2.0)
                herring.setPos((index-(amount-1)/2)*.44, .12*index, .11*sin(index*2.1))
                herring.setH(18 if (cell+index)%2 else 165)
            self.school.append(school)
        self.warning = ring(self.overlay, "Deepfin strike marker", .54, CORAL, 3.)
        self.focus_ring = ring(self.overlay, "Selected destination", .48, MINT, 3.)
        self.route_key = None

    def build_cave(self):
        rng = Random(6119)
        sky = Mesh("Water column and twilight")
        sky.fan(((-44, 15,-26), (44,15,-26), (44,15,22), (-44,15,22)), (1,1,1,1))
        sky_node = sky.attach(self.root)
        sky_node.setTwoSided(True)
        sky_node.setShader(Shader.make(Shader.SL_GLSL, materials3d.VERTEX, POOL))
        wall = ((.20,.46,.55,1),(.15,.35,.47,1),(.27,.55,.65,1),(.12,.29,.41,1))
        distant = ((.085,.198,.29,1),(.105,.25,.34,1),(.14,.29,.38,1))
        snow = ((.57,.79,.86,1),(.32,.64,.76,1),(.43,.74,.80,1),(.29,.59,.72,1))
        for i in range(18):
            x = -18+i*2.1
            glacier(self.root, "Distant cavern ridges", (x, 7., -3+rng.uniform(-1,1)),
                    (rng.uniform(1.2,2.5), 1.35, rng.uniform(2.1,4.4)), distant, rng)
        for i in range(20):
            x = -17.2+i*1.8
            glacier(self.root, "Ocean floor", (x, .7+rng.uniform(-.5,.9), -7.4+rng.uniform(-.17,.28)),
                    (rng.uniform(1.2,1.95),rng.uniform(1.4,2.4),rng.uniform(.65,1.25)), wall, rng)
        for x in (-14.75, 14.75):
            glacier(self.root, "Framing ice wall", (x, 1.9,-1.9), (2.5,3.7,4.5), snow, rng)
            glacier(self.root, "Surface glacier", (x, 4., 3.6), (3.0,3.4,2.3), snow, rng)
        for x in (-6.7, -.8, 5.8):
            glacier(self.root, "Hanging blue ice", (x, 4.4, 1.9), (1.8,1.7,1.4), wall, rng)
            glacier(self.root, "Sea floor spire", (x, 3.1,-5.6), (.62,1.2,2.2), wall, rng)
        for left, right in ((-23,-11.65),(-9.6,9.6),(11.65,23)):
            shelf(self.root,left,right,rng)
        self.plankton = []
        for i in range(54):
            x, z = rng.uniform(-15,15), rng.uniform(-6.5,2.7)
            size = rng.uniform(.014,.039)
            bubble = oval(self.root,self.unit,"Drifting plankton",(x,3.1,z),(size,size,size),(.35,.70,.78,1))
            self.plankton.append((bubble,x,z,rng.random()*tau))
        for vent in AIR_VENTS:
            x, _ = POINTS[vent]
            lights = self.root.attachNewNode("Vent edge lights")
            for side in (-1,1):
                px=x+side*.94
                oval(lights,self.unit,"Beacon ice housing",(px,-.74,3.29),(.14,.17,.15),(.29,.75,.87,1))
                oval(lights,self.unit,"Vent light",(px,-.82,3.41),(.073,.070,.075),(.68,1,.97,1))

    def play(self, before, action, after):
        landing = before.positions[before.active] if action == PASS else action
        self.playback = before, landing, after, self.elapsed

    def reset(self):
        self.playback = None
        self.route_key = None

    def update(self, dt, state, allowed, hover):
        self.elapsed += dt
        self.root.setShaderInput("scene_time", self.elapsed)
        finished = 1.
        before = state
        landing = -1
        if self.playback:
            before, landing, _, started = self.playback
            finished = min(1., (self.elapsed-started)/self.duration)
            if finished >= 1:
                self.playback = None
        for side, rig in enumerate(self.swimmers):
            position = state.positions[side]
            shared = state.positions[0] == state.positions[1]
            end = spot(position, .36 if shared and side else -.42 if shared else 0.)
            end.z -= .69 if position not in AIR_VENTS else .15
            roll = 0.
            if finished < 1 and (side == before.active or before.positions[side] != position):
                start = spot(before.positions[side]); start.z -= .15 if before.positions[side] in AIR_VENTS else .69
                if side == before.active and position != landing:
                    reached = spot(landing); reached.z -= .69
                    end = start+(reached-start)*min(1., finished*1.8) if finished < .56 else (
                        reached+(end-reached)*min(1., (finished-.56)/.44))
                else:
                    pace = finished*finished*(3-2*finished)
                    end = start+(end-start)*pace
                roll = (-40 if end.x>=start.x else 40)*sin(finished*tau*.5)
            rig.root.setPos(end.x,end.y,end.z + (.04*sin(self.elapsed*4+side) if position not in AIR_VENTS else 0))
            rig.root.setHpr(-16 if side==0 else 16, 0, roll)
            rig.pose(.16+.11*sin(self.elapsed*7+side) if position not in AIR_VENTS else 0.)
        mark_state = before if finished < .60 else state
        for cell, school in enumerate(self.school):
            if FISH[cell] and mark_state.fish & (1<<cell):
                school.show()
                school.setPos(spot(cell, .22)+Vec3(.08*sin(self.elapsed*1.5+cell),0,.40+.09*sin(self.elapsed*2+cell)))
            else:
                school.hide()
        seal_start,seal_end = spot(before.seal,1.03),spot(state.seal,1.03)
        position = seal_start+(seal_end-seal_start)*finished
        self.seal.setPos(position.x, position.y, position.z+.18*sin(self.elapsed*1.8))
        direction = POINTS[state.warning][0]-POINTS[state.seal][0]
        self.seal.setH(9 if direction>=0 else 172)
        self.tail.setH(10*sin(self.elapsed*4))
        for bubble,x,z,phase in self.plankton:
            bubble.setPos(x+.28*sin(.48*self.elapsed+phase),3.1,z+.18*sin(self.elapsed*.7+phase))
        self.draw_navigation(state, allowed, hover)

    def draw_navigation(self,state,allowed,hover):
        key = state,allowed,hover
        if self.route_key == key:
            return
        self.route_key = key
        if self.trails is not None:
            self.trails.removeNode()
        self.trails = self.overlay.attachNewNode("Current dive lanes")
        origin = state.positions[state.active]
        for index,marker in enumerate(self.glows):
            if index in allowed:
                marker.show()
                marker.setColorScale(*(CORAL if index==state.warning else MINT))
                a,b = spot(origin,.39),spot(index,.39)
                for step in range(2,11):
                    outline(self.trails,"Route dashes",(a+(b-a)*(step/12),a+(b-a)*((step+.53)/12)),
                            (.61,.95,.89,.93) if index==hover else (.43,.75,.76,.55),2.4 if index==hover else 1.25)
            else:
                marker.hide()
        self.warning.setPos(spot(state.warning,-.72))
        self.focus_ring.show() if hover in allowed else self.focus_ring.hide()
        if hover in allowed:
            self.focus_ring.setPos(spot(hover,-.76))
