"""Animated Arctic scenery surrounding the playable ice."""

from math import cos, pi, sin, tau
from random import Random

from panda3d.core import TransparencyAttrib, Vec3

from .stage3d import TOP, Mesh, TEAM, WATER_LEVEL, circle, flat_shape, floe_mesh, game_floe, mix, outline, oval


class Coast:
    def __init__(self, arena):
        self.root = arena.root.attachNewNode("Arctic sanctuary")
        self.root.setShaderInput("material_kind", 1)
        self.clock = 0.
        self.drifters = []
        self.buoys = []
        rng = Random(8319)
        banks = self.root.attachNewNode("Ice shelves and frozen groves")

        # Leave a clear water channel between the coastline and the game board.
        for side in (-1, 1):
            shelf = self.shelf(side, rng)
            shelf.flattenStrong()
            for y in (-4.8, -2.1, .1, 2.1, 4.5):
                x = side * rng.uniform(5.67, 6.27)
                self.ice_pile(banks, x, y, rng)
            for distance, y, height in ((6.12, -3.54, 1.18), (6.8, -2.6, .95),
                                        (6.05, -.44, 1.58), (6.86, .7, 1.05),
                                        (6.10, 2.72, 1.26), (7.0, 2.16, 1.39)):
                self.ice_tree(banks, side*distance, y, height, rng)
            for j in range(3):
                self.peak(side*(6.15 + j*.51), 3.3 + j*1.13, .63 + j*.34, rng)
            # Flags and team-colored expedition lamps give the arena a place in the coast.
            position = Vec3(side * 5.22, -2.9, -.13)
            self.lantern(arena, position, side < 0)
        banks.flattenStrong()

        self.pack_ice(Random(2861))

        self.snow = self.root.attachNewNode("Drifting snow")
        self.snow.setShaderOff(1)
        snow = Mesh("Snow crystals")
        for _ in range(100):
            x,y,z = rng.uniform(-10,10),rng.uniform(-10,10),rng.uniform(1,5)
            size = rng.uniform(.011,.027)
            pigment = (.83,.94,1,rng.uniform(.20,.58))
            a,b,c,d = (x-size,y,z),(x+size,y,z),(x+size,y,z+size*1.5),(x-size,y,z+size*1.5)
            snow.triangle((a,b,c),pigment)
            snow.triangle((a,c,d),pigment)
        snow.attach(self.snow).setTwoSided(True)
        self.snow.setTransparency(TransparencyAttrib.MAlpha)
        self.snow.setDepthWrite(False)

        self.gusts = [self.wind_ribbon(x, y, rng) for x, y in
                      ((-6.8, -4.4), (-6.7, .1), (-5.4, 3.8), (.7, 4.85),
                       (4.6, -4.5), (5.32, -1.4), (5.44, 3.3))]
        self.leapers = []
        for x, y, period, phase in ((-4.91, -.58, 6.8, .33), (4.87, 1.66, 8.2, 4.1),
                                    (4.75, -3.55, 9.4, 5.6)):
            fish = arena.fish_model.copyTo(self.root)
            fish.setShaderInput("material_kind", 0)
            fish.setScale(2.25)
            fish.setColorScale(.86, .94, .88, 1)
            spray = []
            for _ in range(6):
                drop = oval(self.root, arena.unit, "Splash droplet", (0, 0, 0),
                            (.023, .023, .034), (.61, .89, 1, 1))
                drop.setShaderOff(1)
                spray.append(drop)
            splash = outline("Fish splash", self.root, circle(.18, 30), .84, (.57, .87, .98, 1))
            splash.setShaderOff(1)
            splash.setTransparency(TransparencyAttrib.MAlpha)
            splash.setDepthWrite(False)
            fish.hide()
            splash.hide()
            for drop in spray:
                drop.hide()
            self.leapers.append((fish, splash, spray, x, y, period, phase))

    def pack_ice(self, rng):
        field = self.root.attachNewNode("Drifting broken ice")
        slots = []
        for side in (-1, 1):
            slots.extend((side*rng.uniform(4.90, 5.02), y + rng.uniform(-.25, .25), .62)
                         for y in (-3.88, -2.35, -1.31, .40, 2.39, 3.76))
            slots.extend((x + rng.uniform(-.20, .20), side*rng.uniform(5.12, 5.51), .90)
                         for x in (-4.00, -2.78, -1.64, -.15, 1.12, 2.39, 3.82))
        for index, (x, y, span) in enumerate(slots):
            count = rng.randint(7, 11)
            points = []
            for i in range(count):
                angle = tau * (i + rng.uniform(-.22, .22)) / count
                radius = rng.uniform(.34, .57)
                points.append((radius*cos(angle), radius*sin(angle)))
            ice = game_floe(field, 1400 + index, points)
            width = span * rng.uniform(.41, 1.0)
            depth = width * rng.uniform(.47, 1.08)
            heading = rng.uniform(0, 360)
            thickness = rng.uniform(.38, .68)
            ice.setScale(width, depth, thickness)
            ice.setColorScale(.69, .83, .89, 1)
            foam = Mesh("Broken waterline")
            for i, (x1, y1) in enumerate(points):
                if rng.random() < .35:
                    continue
                x2, y2 = points[(i + 1) % count]
                first, second = (x1, y1, 0), (x2, y2, 0)
                inside = ((x1+x2)*.47, (y1+y2)*.47, 0)
                bright, fade = (.57, .89, .96, .33), (.57, .89, .96, 0)
                foam.triangle((first, second, inside), bright, vertex_colors=(fade, fade, bright))
            wake = foam.attach(field)
            wake.setShaderOff(1)
            wake.setTransparency(TransparencyAttrib.MAlpha)
            wake.setDepthWrite(False)
            home = Vec3(x, y, WATER_LEVEL + .057 - TOP*thickness)
            self.drifters.append((ice, wake, home, width, depth, heading, rng.uniform(0, tau)))

    def ice_pile(self, parent, x, y, rng):
        for size, lift in ((1.10, .26), (.76, .44), (.42, .62)):
            slab = floe_mesh(parent, rng, (.59, .82, .93, 1), (.12, .39, .62, 1))
            slab.setPos(x + rng.uniform(-.29, .29), y + rng.uniform(-.38, .38), lift)
            slab.setScale(size, size * rng.uniform(.75, 1.04), size * 1.13)
            slab.setHpr(rng.uniform(0, 130), rng.uniform(-15, 15), rng.uniform(-17, 17))

    def ice_tree(self, parent, x, y, height, rng):
        mesh = Mesh("Frozen pine")
        bark = (.15, .25, .31, 1)
        ground = .35
        trunk = [(x + .055*cos(i*tau/6), y + .055*sin(i*tau/6), ground-.07) for i in range(6)]
        for i, a in enumerate(trunk):
            b = trunk[(i+1) % len(trunk)]
            a_top = (a[0]+.04, a[1], ground+height*.68)
            b_top = (b[0]+.04, b[1], ground+height*.68)
            mesh.triangle((a, b, b_top), bark)
            mesh.triangle((a, b_top, a_top), bark)

        for level, width in enumerate((.34, .27, .205, .125)):
            phase = rng.uniform(0, tau)
            height_fraction = .24 + level * .19
            z = ground + height*height_fraction
            tip = Vec3(x + .065*level/3, y, z + height*.25)
            hem = []
            for i in range(12):
                angle = phase+i*tau/12
                radius = height * width * (1 if i % 2 == 0 else .69) * rng.uniform(.86, 1.10)
                hem.append(Vec3(x+radius*cos(angle), y+radius*sin(angle), z+rng.uniform(-.035, .027)))
            for i, a in enumerate(hem):
                b = hem[(i+1) % len(hem)]
                green = mix((.08, .28, .37, 1), (.25, .57, .64, 1), rng.uniform(.13, .55))
                mesh.triangle((a, b, tip), green)
                snow_a = a + (tip - a) * rng.uniform(.23, .34) + Vec3(0, 0, .013)
                snow_b = b + (tip - b) * rng.uniform(.23, .34) + Vec3(0, 0, .013)
                mesh.triangle((snow_a, snow_b, tip + Vec3(0, 0, .015)), (.68, .88, .96, 1))
        mesh.attach(parent).setTwoSided(True)

    def wind_ribbon(self, x, y, rng):
        mesh = Mesh("Windblown ice dust")
        clear = (.73, .90, .98, 0)
        mist = (.73, .90, .98, .30)
        for offset in (0, .11, .24):
            points = [(i*.15, offset+sin(i*.73+offset*8)*.06, sin(i*.33)*.06) for i in range(11)]
            for i, (a, b) in enumerate(zip(points, points[1:])):
                a_top = (a[0], a[1]+.028, a[2]+.012)
                b_top = (b[0], b[1]+.028, b[2]+.012)
                tint = mix(clear, mist, sin(pi*i/10))
                next_tint = mix(clear, mist, sin(pi*(i+1)/10))
                mesh.triangle((a, b, b_top), tint, vertex_colors=(tint, next_tint, clear))
                mesh.triangle((a, b_top, a_top), tint, vertex_colors=(tint, clear, clear))
        ribbon = mesh.attach(self.root)
        ribbon.setPos(x, y, .36)
        ribbon.setTwoSided(True)
        ribbon.setShaderOff(1)
        ribbon.setTransparency(TransparencyAttrib.MAlpha)
        ribbon.setDepthWrite(False)
        return ribbon, x, y, rng.uniform(0, 5)

    def shelf(self, side, rng):
        root = self.root.attachNewNode("Fractured coastal ridge")
        mesh = Mesh("Weathered glacier walls")
        crevices = Mesh("Ridges and crevices")
        inside = [(side*(5.32+rng.uniform(-.14,.57)), -6.2+j*.72, rng.uniform(.12,.28)) for j in range(19)]
        for j in range(len(inside)-1):
            a,b = inside[j],inside[j+1]
            edge_a,edge_b = Vec3(*a),Vec3(*b)
            lower_a,lower_b = Vec3(a[0]+side*.12,a[1],-.67),Vec3(b[0]+side*.12,b[1],-.67)
            outer_a,outer_b = Vec3(a[0]+side*2.8,a[1],a[2]+.35),Vec3(b[0]+side*2.8,b[1],b[2]+.35)
            wall = (.13+rng.random()*.12,.32+rng.random()*.15,.52+rng.random()*.13,1)
            mesh.triangle((edge_a,lower_a,lower_b),wall)
            mesh.triangle((edge_a,lower_b,edge_b),(.23,.53,.71,1))
            snow_normal=(Vec3(0,0,1),)*3
            snow = (.49+rng.random()*.12,.67+rng.random()*.09,.81+rng.random()*.09,1)
            mesh.triangle((edge_a,edge_b,outer_b),snow,snow_normal)
            mesh.triangle((edge_a,outer_b,outer_a),snow,snow_normal)
            # Pale ice exposed on alternating shelves forms a seam above the water.
            seam_a = edge_a + (outer_a-edge_a)*.29
            seam_b = edge_b + (outer_b-edge_b)*.14
            seam_a.z += .009
            seam_b.z += .009
            surface_b = edge_b + Vec3(0,0,.008)
            mesh.triangle((edge_a+Vec3(0,0,.008),surface_b,seam_b),(.36,.61,.76,1),snow_normal)
            mesh.triangle((edge_a+Vec3(0,0,.008),seam_b,seam_a),(.39,.63,.78,1),snow_normal)
            if j % 2:
                inner = seam_a + Vec3(side*.04, .035, .015)
                middle = outer_a*.52 + outer_b*.13 + edge_b*.35 + Vec3(0, 0, .026)
                far = outer_a*.35 + outer_b*.65 + Vec3(0, 0, .018)
                crevices.triangle((inner, middle+Vec3(0,.055,.006), middle),(.27,.49,.66,1))
                crevices.triangle((middle, middle+Vec3(0,.055,.006), far),(.29,.53,.69,1))
            # Striations break up the wall into deep blue vertical crevices.
            r=.36
            x=a[0]*(1-r)+b[0]*r
            y=a[1]*(1-r)+b[1]*r
            mesh.triangle(((x-side*.013,y,-.54),(x-side*.013,y+.065,.04),
                           (x-side*.018,y+.14,-.49)),(.08,.29,.48,1))
        mesh.attach(root).setTwoSided(True)
        crevices.attach(root).setTwoSided(True)
        foam = Mesh("Shoreline foam")
        for a,b in zip(inside,inside[1:]):
            offset = -.15*side
            points = ((a[0]+offset,a[1],WATER_LEVEL+.016),(b[0]+offset,b[1],WATER_LEVEL+.016),
                      (b[0]-side*.25,b[1],WATER_LEVEL+.016),(a[0]-side*.25,a[1],WATER_LEVEL+.016))
            foam.triangle(points[:3],(.49,.86,.92,.32))
            foam.triangle((points[0],points[2],points[3]),(.49,.86,.92,.32))
        node=foam.attach(root)
        node.setTwoSided(True)
        node.setShaderOff(1)
        node.setTransparency(TransparencyAttrib.MAlpha)
        node.setDepthWrite(False)
        return root

    def peak(self,x,y,size,rng):
        mesh=Mesh("Glacial pinnacle")
        count=6
        base=[Vec3(x+cos(i*tau/count)*size*.87,y+sin(i*tau/count)*size*.64,.15) for i in range(count)]
        tip=Vec3(x-size*.16,y+.15,size*2.4)
        snow_tip=tip-Vec3(0,0,.03)
        for j in range(count):
            a,b=base[j],base[(j+1)%count]
            tint=(.24,.48,.66,1) if j%3==0 else (.38,.64,.79,1)
            mesh.triangle((a,b,tip),tint)
            snow_a=a+(tip-a)*rng.uniform(.47,.70)
            snow_b=b+(tip-b)*rng.uniform(.50,.72)
            normal=(b-a).cross(tip-a)
            normal.normalize()
            if normal.z<0:
                normal=-normal
            lift=normal*.014
            mesh.triangle((snow_a+lift,snow_b+lift,snow_tip+lift),(.89,.96,1,1))
        mesh.attach(self.root).setTwoSided(True)

    def lantern(self,arena,position,coral):
        root=self.root.attachNewNode("Expedition beacon")
        root.setPos(position)
        root.setShaderInput("material_kind",0)
        color=TEAM[0 if coral else 1]
        oval(root,arena.unit,"Buoy base",(0,0,.08),(.20,.20,.13),(.07,.16,.25,1))
        oval(root,arena.unit,"Mast",(0,0,.45),(.025,.025,.39),(.29,.43,.51,1))
        bulb=oval(root,arena.unit,"Signal",(0,0,.82),(.065,.065,.12),color)
        bulb.setShaderOff(1)
        self.buoys.append((root,position,bulb,color))
        sail=Mesh("Expedition pennant")
        sail.triangle(((0,0,.72),(.32,0,.65),(0,0,.54)),color)
        sail.attach(root).setTwoSided(True)
        light=flat_shape("Beacon reflection",self.root,circle(.38,32),(*color[:3],.13),WATER_LEVEL+.012)
        light.setPos(position.x,position.y,0)
        light.setShaderOff(1)
        light.setTransparency(TransparencyAttrib.MAlpha)
        light.setDepthWrite(False)

    def animate(self,dt,motion):
        if motion:
            self.clock+=dt
        t=self.clock
        for ice, wake, home, width, depth, heading, phase in self.drifters:
            x = home.x + sin(t*.28 + phase)*.16
            y = home.y + cos(t*.25 + phase)*.23
            turn = heading + sin(t*.21 + phase)*17
            ice.setPos(x, y, home.z + sin(t*1.31+phase)*.029)
            ice.setHpr(turn, sin(t*.92+phase)*5, sin(t*1.05+phase)*4)
            wake.setPos(x, y, WATER_LEVEL+.008)
            wake.setH(turn)
            swell = 1.28 + .10*sin(t*1.11+phase)
            wake.setScale(width*swell, depth*swell, 1)
            wake.setColorScale(1, 1, 1, .61 + .22*sin(t+.44*phase))
        for index,(root,home,bulb,color) in enumerate(self.buoys):
            root.setZ(home.z+sin(t*1.4+index)*.025)
            root.setR(sin(t*.8+index)*2.7)
            brightness=.87+sin(t*2.7+index)*.13
            bulb.setColorScale(color[0]*brightness,color[1]*brightness,color[2]*brightness,1)
        self.snow.setPos(sin(t*.11)*.55,cos(t*.08)*.36,1-(t*.12 % 2))
        for ribbon, x, y, phase in self.gusts:
            progress = (t*.35+phase) % 1
            ribbon.setPos(x+progress*1.31, y+progress*.27, .39+sin(progress*pi)*.19)
            ribbon.setColorScale(1, 1, 1, sin(progress*pi)**2 if motion else 0)
        for fish, splash, spray, x, y, period, phase in self.leapers:
            elapsed = (t+phase) % period if motion else period
            flight = .96
            progress = min(1, elapsed/flight)
            direction = 1 if x < 0 else -1
            landing = y + direction*.98
            if elapsed < flight:
                fish.show()
                fish.setPos(x+.16*sin(progress*pi), y+direction*.98*progress,
                            WATER_LEVEL-.10+.86*4*progress*(1-progress))
                fish.setHpr(90*direction, 0, 70*(progress*2-1))
            else:
                fish.hide()
            impact = (elapsed-flight)/.69
            if 0 <= impact < 1:
                splash.show()
                splash.setPos(x, landing, WATER_LEVEL+.017)
                splash.setScale(.65+impact*2.6)
                splash.setColorScale(1, 1, 1, (1-impact)**1.5)
                for i, drop in enumerate(spray):
                    direction_angle = i*tau/len(spray)
                    radius = .36*impact
                    drop.show()
                    drop.setPos(x+cos(direction_angle)*radius, landing+sin(direction_angle)*radius,
                                WATER_LEVEL+.037+sin(impact*pi)*(.31 + .032*i))
            else:
                splash.hide()
                for drop in spray:
                    drop.hide()

