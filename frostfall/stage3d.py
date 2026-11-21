"""The Arctic arena and its real-time 3D artwork."""

from dataclasses import dataclass
from math import atan2, cos, degrees, pi, sin, tau
from random import Random

from panda3d.core import (
    Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat, GeomVertexWriter,
    NodePath, Point2, Point3, Shader, TextNode, TransparencyAttrib, Vec3, Vec4,
)

from . import materials3d
from .rules import CELLS

FLOE = 1.07
TOP = .107
WATER_LEVEL = -.24
MINT = (.30, 1, .76, 1)
CORAL = (1, .48, .36, 1)
AZURE = (.38, .67, 1, 1)
GOLD = (1, .81, .36, 1)
VIOLET = (.76, .62, 1, 1)
TEAM = (CORAL, AZURE)
DARK = (.037, .16, .22, 1)
FIRST_BITE = .51
BITE_GAP = .15
BITE_LENGTH = .13
SEAL_LAUNCH = .23
SEAL_IMPACT = .84
SEAL_DURATION = 1.10
STRIKE_RECOVERY = .86


def center(cell, z=TOP):
    row, col = divmod(cell, 8)
    return Point3((col - 3.5) * FLOE, (3.5 - row) * FLOE, z)


def mix(first, second, ratio):
    return tuple(x + (y - x) * ratio for x, y in zip(first, second))


def ease(t):
    return t * t * (3 - 2 * t)


def phase(age, start, end):
    return ease(max(0., min(1., (age - start) / (end - start))))


def lerp_angle(first, second, ratio):
    delta = (second - first + 180) % 360 - 180
    return first + delta * ratio


class Mesh:
    def __init__(self, name):
        self.name = name
        self.data = GeomVertexData(name, GeomVertexFormat.getV3n3c4(), Geom.UHStatic)
        self.position = GeomVertexWriter(self.data, "vertex")
        self.normal = GeomVertexWriter(self.data, "normal")
        self.color = GeomVertexWriter(self.data, "color")
        self.faces = GeomTriangles(Geom.UHStatic)
        self.count = 0

    def triangle(self, points, color, normals=None, vertex_colors=None):
        points = tuple(Vec3(point) for point in points)
        if normals is None:
            normal = (points[1] - points[0]).cross(points[2] - points[0])
            normal.normalize()
            normals = (normal,) * 3
        for position, normal, pigment in zip(points, normals, vertex_colors or (color,) * 3):
            self.position.addData3(position)
            self.normal.addData3(normal)
            self.color.addData4(*pigment)
        self.faces.addVertices(self.count, self.count + 1, self.count + 2)
        self.count += 3

    def fan(self, points, color, core=None):
        if core is None:
            core = sum((Vec3(p) for p in points), Vec3(0)) / len(points)
        for index, point in enumerate(points):
            self.triangle((core, point, points[(index + 1) % len(points)]), color)

    def attach(self, parent):
        geometry = Geom(self.data)
        geometry.addPrimitive(self.faces)
        node = GeomNode(self.name)
        node.addGeom(geometry)
        return parent.attachNewNode(node)


def flat_shape(name, parent, points, color, z=0):
    mesh = Mesh(name)
    mesh.fan(tuple((x, y, z) for x, y in points), color)
    node = mesh.attach(parent)
    node.setTwoSided(True)
    return node


def circle(radius, count=40):
    return [(radius * cos(tau * i / count), radius * sin(tau * i / count)) for i in range(count)]


def clipped_square(radius, clip):
    low, high = -radius + clip, radius - clip
    return [(low, -radius), (high, -radius), (radius, low), (radius, high),
            (high, radius), (low, radius), (-radius, high), (-radius, low)]


def fracture_profile(cell):
    """Cut chips into a square footprint while leaving room for neighboring floes."""
    rng = Random(8913 + cell)
    corners = [(-.49 + rng.uniform(-.027, .027), -.49 + rng.uniform(-.027, .027)),
               (.49 + rng.uniform(-.027, .027), -.49 + rng.uniform(-.027, .027)),
               (.49 + rng.uniform(-.027, .027), .49 + rng.uniform(-.027, .027)),
               (-.49 + rng.uniform(-.027, .027), .49 + rng.uniform(-.027, .027))]
    points = []
    damaged_sides = rng.sample(range(4), rng.choice((1, 2, 2, 3)))
    for i, (x, y) in enumerate(corners):
        next_x, next_y = corners[(i + 1) % 4]
        dx, dy = next_x - x, next_y - y
        chip = rng.uniform(.25, .68)
        depth = rng.uniform(.075, .144) if i in damaged_sides else rng.uniform(-.022, .020)
        for along, cut in ((rng.uniform(.07, .14), 0), (chip - .098, 0),
                           (chip, depth), (chip + .103, depth * .19), (rng.uniform(.86, .95), 0)):
            points.append((x + along * dx - dy * cut, y + along * dy + dx * cut))
    return sorted(points, key=lambda point: atan2(point[1], point[0]))


def game_floe(parent, cell, profile):
    rng = Random(721 + cell)
    mesh = Mesh("Fractured ice slab")
    palette = ((.43, .70, .85, 1), (.54, .81, .89, 1), (.53, .73, .86, 1), (.44, .77, .87, 1))
    top = rng.choice(palette)
    rim = (.54, .84, .95, 1)
    edge = (.16, .47, .70, 1)
    core = (.05, .21, .42, 1)
    levels = ((.915, TOP), (1, TOP - .057), (.94, -.092), (.87, -.238), (.74, -.335))
    rings = [[(x * scale, y * scale, z + (rng.uniform(-.032, .026) if index else 0))
              for x, y in profile] for index, (scale, z) in enumerate(levels)]
    tones = [mix(top, (.75, .92, .98, 1), rng.uniform(0, .47)) for _ in profile]
    for i, point in enumerate(rings[0]):
        j = (i + 1) % len(profile)
        mesh.triangle(((0, 0, TOP), point, rings[0][j]), top, vertex_colors=(top, tones[i], tones[j]))
    for index, (upper, lower) in enumerate(zip(rings, rings[1:])):
        face = (rim, edge, core, core)[index]
        for i in range(len(profile)):
            j = (i + 1) % len(profile)
            tone = mix(face, (.61, .80, .94, 1), rng.uniform(0, .21))
            mesh.triangle((upper[i], lower[i], lower[j]), tone)
            mesh.triangle((upper[i], lower[j], upper[j]), mix(tone, core, .10))

    slab = mesh.attach(parent)
    slab.setShaderInput("material_kind", 2)
    fractures = Mesh("Etched seams and splinters")
    for i in rng.sample(range(len(profile)), 2):
        x, y = profile[i]
        reach = rng.uniform(.31, .49)
        points = ((x * .89, y * .89), (x * .69 - y * .12, y * .69 + x * .12),
                  (x * reach + y * .08, y * reach - x * .08))
        for line, (start, end) in enumerate(zip(points, points[1:])):
            ax, ay = start
            bx, by = end
            offset = Vec3(ay - by, bx - ax, 0)
            offset.normalize()
            offset *= .012 - line * .003
            a, b = Vec3(ax, ay, TOP + .008), Vec3(bx, by, TOP + .008)
            fractures.triangle((a, a + offset, b), (.20, .44, .62, 1))
            fractures.triangle((a + offset, a + offset * 2, b), (.68, .91, .98, 1))
        mid_x, mid_y = points[1]
        fractures.triangle(((mid_x, mid_y, TOP + .009), (mid_x + .015, mid_y + .007, TOP + .009),
                            (mid_x * .9 + y * .18, mid_y * .9 - x * .18, TOP + .009)),
                           (.49, .76, .88, 1))
    fractures.attach(slab).setTwoSided(True)
    return slab

def outline(name, parent, profile, inner_scale, color):
    mesh = Mesh(name)
    for i, (ax, ay) in enumerate(profile):
        bx, by = profile[(i + 1) % len(profile)]
        a, b = (ax, ay, 0), (bx, by, 0)
        c, d = (bx * inner_scale, by * inner_scale, 0), (ax * inner_scale, ay * inner_scale, 0)
        mesh.triangle((a, b, c), color)
        mesh.triangle((a, c, d), color)
    return mesh.attach(parent)


def sphere(parent, slices=24, stacks=16):
    mesh = Mesh("Sculpted curve")

    def surface(row, col):
        v, h = pi * row / stacks, tau * col / slices
        return Vec3(sin(v) * cos(h), sin(v) * sin(h), cos(v))

    for row in range(stacks):
        for col in range(slices):
            a, b = surface(row, col), surface(row + 1, col)
            c, d = surface(row + 1, col + 1), surface(row, col + 1)
            if row < stacks - 1:
                mesh.triangle((a, b, c), (1, 1, 1, 1), (a, b, c))
            if row:
                mesh.triangle((a, c, d), (1, 1, 1, 1), (a, c, d))
    return mesh.attach(parent)


def floe_mesh(parent, rng, snow, side, *, glacier=False):
    mesh = Mesh("Beveled glacier" if glacier else "Layered ice")
    profile = [(x + rng.uniform(-.025, .025), y + rng.uniform(-.025, .025))
               for x, y in clipped_square(.499, rng.uniform(.079, .151))]
    levels = ((.86, TOP), (1, .037), (.969, -.059), (.91, -.172), (.83, -.34))
    rings = [[(x * scale, y * scale, z) for x, y in profile] for scale, z in levels]
    mesh.fan(rings[0], snow)
    for index, (front, back) in enumerate(zip(rings, rings[1:])):
        face_color = mix(snow, side, (.26, .56, .86, 1)[index])
        for i in range(len(profile)):
            j = (i + 1) % len(profile)
            color = mix(face_color, (.07, .25, .40, 1), rng.uniform(.01, .19))
            mesh.triangle((front[i], back[i], back[j]), color)
            mesh.triangle((front[i], back[j], front[j]), mix(color, side, .095))
    return mesh.attach(parent)


def oval(parent, unit, name, position, size, tone):
    node = unit.copyTo(parent)
    node.setName(name)
    node.setPos(*position)
    node.setScale(*size)
    node.setColorScale(*tone)
    return node


def loft(parent, name, stations, palette, divisions=16):
    mesh = Mesh(name)
    rings = [[(x, ry * cos(i * tau / divisions), z + rz * sin(i * tau / divisions))
              for i in range(divisions)] for x, ry, rz, z in stations]
    normals = [(0, cos(i * tau / divisions), sin(i * tau / divisions)) for i in range(divisions)]
    for first, second in zip(rings, rings[1:]):
        for i in range(divisions):
            j = (i + 1) % divisions
            tint = palette(sin((i + .5) * tau / divisions))
            mesh.triangle((first[i], second[j], second[i]), tint, (normals[i], normals[j], normals[i]))
            mesh.triangle((first[i], first[j], second[j]), tint, (normals[i], normals[j], normals[j]))
    return mesh.attach(parent)


def fish_model(parent):
    """Model a golden fish with visible flanks, fins, gills, and a forked tail."""
    root = parent.attachNewNode("Golden herring")
    eye_mesh = sphere(parent, 10, 6)
    gold = (1, .70, .18, 1)
    brass = (.75, .34, .075, 1)
    amber = (1, .48, .06, 1)
    cream = (1, .93, .63, 1)
    body = (
        (-.093, .009, .012, .000), (-.067, .021, .033, .003), (-.031, .035, .049, .007),
        (.017, .040, .053, .005), (.058, .032, .039, .002), (.089, .021, .024, -.004),
        (.105, .008, .011, -.009),
    )
    scales = loft(root, "Tapered body", body,
                  lambda height: mix(cream, gold, (height+1)*.6) if height <= .66
                  else mix(gold, brass, (height-.66)/.34), 14)
    scales.setShaderInput("material_kind", 3)

    fins = Mesh("Forked tail, dorsal fin and pectoral fins")
    joint = (-.089, 0, 0)
    fork = (-.141, 0, .002)
    for side in (-1, 1):
        tip = (-.182, 0, side*.061)
        ridge = (-.118, .009, side*.022)
        fins.triangle((joint, ridge, tip), amber)
        fins.triangle((ridge, fork, tip), gold)
        fins.triangle((joint, fork, ridge), brass)
        fins.triangle(((.039, side*.030, -.014), (-.050, side*.054, -.030),
                       (-.024, side*.026, -.043)), amber)
        fins.triangle(((.031, side*.024, -.018), (-.024, side*.026, -.043),
                       (-.012, side*.038, -.033)), gold)
    fins.triangle(((.041, 0, .044), (.005, 0, .081), (-.048, 0, .051)), brass)
    fins.triangle(((.041, 0, .044), (.005, 0, .081), (-.015, .010, .049)), gold)
    fins.attach(root).setTwoSided(True)

    detail = Mesh("Gill lines and scale highlights")
    for side in (-1, 1):
        gill = ((.052, side*.021, .031), (.037, side*.035, .014),
                (.040, side*.038, -.007), (.053, side*.024, -.024))
        for start, end in zip(gill, gill[1:]):
            a, b = Vec3(*start), Vec3(*end)
            offset = Vec3(.007, side*.001, 0)
            detail.triangle((a, b, a+offset), brass)
            detail.triangle((b, b+offset, a+offset), brass)
        for x, width in ((-.048, .023), (-.024, .035), (.001, .039), (.022, .041)):
            y = side*width
            detail.triangle(((x-.013, y, .014), (x+.004, y+side*.001, .020),
                             (x+.009, y, .013)), cream)
        oval(root, eye_mesh, "Eye rim", (.074, side*.027, .012), (.014, .006, .014), cream)
        oval(root, eye_mesh, "Eye", (.077, side*.031, .012), (.009, .004, .009), (.060, .13, .19, 1))
        oval(root, eye_mesh, "Eye highlight", (.080, side*.035, .017), (.0035, .0025, .0035), (1, 1, .94, 1))
    eye_mesh.removeNode()
    detail.attach(root).setTwoSided(True)
    root.flattenStrong()
    return root


# Fish stay close to the near edge so a penguin can stand behind its catch.
FISH_GROUPS = {
    1: ((.025, -.030, 24, 1.54),),
    2: ((-.154, .073, -18, 1.27), (.167, -.046, 19, 1.24)),
    3: ((-.216, .012, 22, 1.03), (.153, .114, 10, 1.16), (.130, -.100, -11, 1.11)),
    4: ((-.171, .107, -19, .93), (.173, .115, 17, .93),
        (-.140, -.103, 24, .91), (.173, -.093, 12, .90)),
}

def leopard_seal(parent, unit):
    root = parent.attachNewNode("Deepfin the leopard seal")
    body = root.attachNewNode("Spotted seal coat")
    slate = (.29, .36, .48, 1)
    silver = (.62, .70, .77, 1)
    dark = (.072, .095, .15, 1)
    stations = ((-1.08, .067, .051, -.036), (-.89, .126, .096, -.024),
                (-.49, .232, .183, .002), (-.06, .289, .233, .015),
                (.32, .278, .239, .029), (.55, .216, .205, .058),
                (.72, .213, .192, .077), (.89, .190, .156, .053),
                (1.05, .141, .103, .025), (1.13, .068, .060, .015))
    loft(body, "Tapered silver body", stations, lambda height: mix(silver, slate, (height + 1) * .5), 28)
    spots = Mesh("Leopard markings")
    rng = Random(840)
    for left, right in zip(stations[1:-2], stations[2:-1]):
        for i in range(9):
            along = (i % 3 + .5) / 3
            turn = i * 2.40 + rng.uniform(-.26, .26)
            width, length = rng.uniform(.031, .072), rng.uniform(.024, .061)

            def coat(u, angle):
                x, ry, rz, z = mix(left, right, u)
                return (x, (ry + .004) * cos(angle), z + (rz + .004) * sin(angle))

            center_spot = coat(along, turn)
            edges = []
            for j in range(7):
                angle = tau * j / 7
                u = along + cos(angle) * length / (right[0] - left[0]) * rng.uniform(.68, 1.1)
                edges.append(coat(max(.014, min(.986, u)), turn + sin(angle) * width * 5))
            color = mix(dark, slate, rng.uniform(.13, .46))
            for a, b in zip(edges, edges[1:] + edges[:1]):
                spots.triangle((center_spot, a, b), color)
    spots.attach(body).setTwoSided(True)

    oval(body, unit, "Broad seal muzzle", (1.025, 0, -.003), (.133, .153, .101), silver)
    oval(body, unit, "Nose", (1.133, 0, .040), (.050, .075, .044), dark)
    muzzle = Mesh("Mouth and whiskers")
    for side in (-1, 1):
        oval(body, unit, "Eye", (.841, side * .168, .116), (.048, .025, .042), dark)
        oval(body, unit, "Eye glint", (.855, side * .191, .132), (.013, .008, .012), (.92, .97, 1, 1))
        mouth = ((.863, side * .172, -.066), (1.004, side * .143, -.069), (1.138, side * .046, -.046))
        for a, b in zip(mouth, mouth[1:]):
            muzzle.triangle((a, b, (b[0], b[1], b[2] + .018)), dark)
        for i in range(3):
            x = 1.052 - .033 * i
            a = (x, side * .13, .015 - .017 * i)
            b = (x - .05 - i * .018, side * (.25 + .015 * i), .037 - .043 * i)
            muzzle.triangle((a, b, (x - .032, a[1], a[2] - .004)), silver)
    muzzle.attach(body).setTwoSided(True)
    body.flattenStrong()

    flippers = []
    tail = root.attachNewNode("Paired hind flippers")
    tail.setX(-.99)
    for side in (-1, 1):
        paddle = root.attachNewNode("Foreflipper")
        paddle.setPos(.31, side * .21, -.084)
        oval(paddle, unit, "Long foreflipper", (-.15, side * .164, -.033),
             (.267, .126, .048), slate).setH(-side * 39)
        flippers.append(paddle)
        oval(tail, unit, "Hind paddle", (-.155, side * .106, 0), (.228, .091, .044), slate).setH(-side * 24)
    return root, tail, flippers


def penguin(parent, unit, color, role):
    root = parent.attachNewNode("Penguin")
    body = root.attachNewNode("Body")
    head_art = root.attachNewNode("Head art")
    coat = (.075, .119, .19, 1)
    white = (.94, .96, .91, 1)
    black = (.019, .042, .065, 1)
    orange = (1, .56, .19, 1)

    def blob(name, position, scale, tone, roll=0, *, on_head=False):
        node = oval(head_art if on_head else body, unit, name, position, scale, tone)
        node.setR(roll)
        return node

    blob("Body", (0, .018, .363), (.263, .227, .331), coat)
    blob("Cream chest", (0, -.128, .335), (.212, .132, .261), white)
    for sign in (-1, 1):
        blob("Webbed foot", (sign * .105, -.109, .053), (.094, .131, .052), orange, sign * 6)
    blob("Head", (0, -.025, .691), (.251, .227, .238), coat, on_head=True)
    for sign in (-1, 1):
        blob("Eye mask", (sign * .092, -.185, .686), (.116, .088, .132), white, -sign * 11, on_head=True)
        blob("Eye", (sign * .087, -.265, .731), (.040, .019, .050), black, on_head=True)
        blob("Eye highlight", (sign * .087 - .010, -.282, .748), (.012, .007, .013), (1, 1, .97, 1), on_head=True)
    beak = Mesh("Upper beak")
    a, b = (-.092, -.242, .655), (.092, -.242, .655)
    top, tip = (0, -.246, .696), (0, -.375, .647)
    beak.triangle((a, top, tip), orange)
    beak.triangle((top, b, tip), (1, .67, .23, 1))
    beak.triangle((a, tip, b), (.27, .075, .045, 1))
    beak.attach(head_art).setTwoSided(True)
    jaw = Mesh("Lower beak")
    # The hinge sits under the head, with the tip extending forward along -Y.
    left, right = (-.082, 0, 0), (.082, 0, 0)
    front, chin = (0, -.127, -.006), (0, -.013, -.046)
    jaw.triangle((left, front, chin), (.78, .32, .09, 1))
    jaw.triangle((chin, front, right), (.88, .36, .11, 1))
    jaw.triangle((left, right, front), (.31, .092, .055, 1))

    circle_mesh = Mesh("Wool scarf")
    band = [(0, .552, 1), (0, .488, 1.03), (0, .464, .94)]
    for row in range(len(band) - 1):
        for i in range(32):
            angles = (tau * i / 32, tau * (i + 1) / 32)
            points = []
            for _, z, scale in (band[row], band[row + 1]):
                points += [(.245 * cos(angle) * scale, -.02 + .222 * sin(angle) * scale,
                            z + .014 * sin(angle + .5)) for angle in angles]
            tone = mix(color, (.14, .15, .24, 1), .073 if i % 4 else .16)
            a, b, c, d = points
            circle_mesh.triangle((a, c, d), tone)
            circle_mesh.triangle((a, d, b), tone)
    wrap = circle_mesh.attach(body)
    wrap.setTwoSided(True)
    blob("Scarf knot", (-.145, -.182, .505), (.082, .069, .058), color, 15)
    tail = Mesh("Scarf tail")
    tail.triangle(((-.187, -.161, .503), (-.247, -.111, .467), (-.310, .042, .385)), color)
    tail.triangle(((-.187, -.161, .503), (-.310, .042, .385), (-.253, .062, .429)),
                  mix(color, (1, .98, .94, 1), .18))
    tail.attach(body).setTwoSided(True)
    if role:
        blob("Defender helmet", (0, -.006, .841), (.254, .232, .153), color, on_head=True)
        blob("Soft helmet lining", (0, -.032, .800), (.252, .231, .038), (.94, .95, .94, 1), on_head=True)
        for side in (-1, 1):
            blob("Ear flap", (side * .217, -.054, .743), (.068, .076, .107), color, on_head=True)
        shield = Mesh("Defender shield")
        points = ((-.115, -.260, .460), (.115, -.260, .460), (.099, -.269, .335), (0, -.270, .273),
                  (-.099, -.269, .335))
        shield.fan(points, mix(color, (.14, .25, .47, 1), .19), (0, -.315, .376))
        shield.attach(body).setTwoSided(True)
        blob("Shield crest", (0, -.315, .382), (.046, .012, .052), (.99, .93, .71, 1))
    else:
        blob("Attacker visor band", (0, -.039, .832), (.254, .221, .076), color, -6, on_head=True)
        blob("Raised snow goggles", (0, -.226, .853), (.155, .075, .055), (.11, .24, .38, 1), -6, on_head=True)
        for side in (-1, 1):
            blob("Amber goggle lens", (side * .074, -.283, .853), (.057, .027, .035), GOLD, -6, on_head=True)
    for side in (-1, 1):
        blob("Rosy cheeks", (side * .160, -.242, .654), (.034, .017, .023), (.96, .48, .41, 1), on_head=True)
    body.flattenStrong()
    head_art.flattenStrong()
    head = root.attachNewNode("Head pivot")
    head.setZ(.60)
    head_art.wrtReparentTo(head)
    jaw_node = jaw.attach(head)
    jaw_node.setPos(0, -.245, .048)
    jaw_node.setTwoSided(True)

    flippers = tuple(oval(root, unit, "Flipper", (0, 0, 0), (1, 1, 1), (.065, .107, .174, 1))
                     for _ in (-1, 1))
    rig = PenguinRig(root, head, jaw_node, flippers)
    rig.pose()
    return rig


@dataclass
class PenguinRig:
    root: NodePath
    head: NodePath
    jaw: NodePath
    flippers: tuple[NodePath, NodePath]

    def pose(self, reach=0., height=.41, nod=0., bite=0.):
        self.head.setP(nod)
        self.jaw.setP(bite)
        for side, flipper in zip((-1, 1), self.flippers):
            shoulder = Vec3(side * (.224 + .056 * reach), .002 - .070 * reach, .514)
            rest = Vec3(side * .311, -.031, .203)
            grasp = Vec3(side * .127, -.462, height)
            tip = rest + (grasp - rest) * reach
            flipper.setPos((shoulder + tip) * .5)
            flipper.lookAt(tip)
            flipper.setScale(.068, (tip - shoulder).length() * .57, .082)


@dataclass
class Meal:
    piece: int
    fish: list[tuple[NodePath, Point3, Vec3, float]]
    age: float = 0.

    @property
    def duration(self):
        return FIRST_BITE + BITE_GAP * (len(self.fish) - 1) + BITE_LENGTH + .16


@dataclass
class Tile:
    root: NodePath
    ice: NodePath
    fish: NodePath
    bait: NodePath
    warning: NodePath
    marker: NodePath
    highlight: NodePath
    selection: NodePath
    frost: NodePath
    value: int = -1


@dataclass
class Break:
    cell: int
    age: float
    duration: float
    fragments: list
    rings: list
    crack: NodePath
    attack: bool
    has_ice: bool


@dataclass
class SealStrike:
    cell: int
    age: float
    has_ice: bool


class Arena:
    def __init__(self, render, font):
        self.root = render.attachNewNode("Frostfall coast")
        self.root.setShader(Shader.make(Shader.SL_GLSL, materials3d.VERTEX, materials3d.SURFACE))
        self.root.setShaderInput("eye", Vec3(0, -14, 19))
        self.root.setShaderInput("material_kind", 0)
        self.root.setShaderInput("frost_tint", Vec4(0))
        self.root.setShaderInput("cap_tint", Vec4(0))
        self.root.setShaderInput("scene_time",0.)
        self.font = font
        self.world_clock = 0
        self.shadows = []
        self.breaks = []
        self.brace_rings = []
        self.effects = self.root.attachNewNode("Weather effects")
        self.overlay = self.root.attachNewNode("Move and hazard markers")
        self.overlay.setShaderOff(1)
        self.mesh_bank = NodePath("Reusable models")
        self.unit = sphere(self.mesh_bank)
        self.fish_model = fish_model(self.mesh_bank)
        self.trail = [oval(self.effects, self.unit, "Skid spark", (0, 0, 0), (.042, .035, .033),
                           (.74, .96, 1, 1)) for _ in range(7)]
        for spark in self.trail:
            spark.hide()
        self.seal, self.seal_tail, self.seal_flippers = leopard_seal(self.effects, self.unit)
        self.seal.hide()
        self.seal_strike = None
        self.breach_spray = []
        for _ in range(16):
            drop = oval(self.effects, self.unit, "Breach spray", (0, 0, 0),
                        (.021, .021, .046), (.62, .92, 1, 1))
            drop.hide()
            self.breach_spray.append(drop)
        self.fragment = floe_mesh(self.mesh_bank, Random(429), (.75, .93, .95, 1), (.24, .66, .84, 1))
        self.fragment.setShaderInput("material_kind", 1)

        self.water = flat_shape("Waves", self.root, [(-70, -70), (70, -70), (70, 70), (-70, 70)], (1, 1, 1, 1),
                                WATER_LEVEL)
        self.water.setShader(Shader.make(Shader.SL_GLSL, materials3d.VERTEX, materials3d.WATER))
        self.water.setShaderInput("tide_time", 0.)
        self.water.setShaderInput("pressure", Vec4(0))
        self.ripples = []
        for index in range(4):
            self.water.setShaderInput(f"ripple{index}",Vec4(0,0,-10,0))
        self.shadow_shader = Shader.make(Shader.SL_GLSL, materials3d.VERTEX, materials3d.SHADOW)
        self.background_ice = self.scenery()
        from .environment3d import Coast
        self.coast = Coast(self)
        self.tiles = [self.make_tile(cell) for cell in CELLS]
        self.rigs = [penguin(self.root, self.unit, TEAM[piece // 2], piece % 2) for piece in range(4)]
        self.pieces = [rig.root for rig in self.rigs]
        self.teams = [outline("Team base", self.overlay, circle(.285), .878, TEAM[piece // 2])
                      for piece in range(4)]
        for piece in self.pieces:
            piece.setScale(.91)
            shadow = flat_shape("Soft contact shadow", self.root, [(-.55, -.55), (.55, -.55), (.55, .55), (-.55, .55)],
                                (1, 1, 1, 1))
            shadow.setShader(self.shadow_shader)
            shadow.setShaderInput("shadow_center", Vec3(0))
            shadow.setShaderInput("spread", .55)
            shadow.setDepthWrite(False)
            shadow.setTransparency(TransparencyAttrib.MAlpha)
            shadow.setBin("transparent", 0)
            self.shadows.append(shadow)
        self.route = self.overlay.attachNewNode("Hovered route")
        self.focus_marker = outline("Keyboard cursor", self.overlay, clipped_square(.473, .113), .965,
                                    (.97, .99, 1, 1))
        self.focus_marker.hide()
        self.moving = None
        self.meal = None
        self.hovered = None

    def scenery(self):
        terrain = self.root.attachNewNode("Coastal pack ice")
        terrain.setShaderInput("material_kind", 1)
        rng = Random(9408)
        # Broken shelves sit clear of the square playing surface.
        shelves = [(-10, 5.7, 3.8, 1.5, 1.8), (-7.8, 7.2, 3.6, 1.8, 2.2), (-4.4, 8.6, 3.2, 2, 1.7),
                   (5.9, 5.05, 1.8, 1.35, 1.8), (5.35, 6.65, 2.1, 1.4, 2.0),
                   (5.5, 8.0, 3.0, 2.8, 2.8), (8.5, 6.8, 3.9, 3.15, 2.75), (10.1, 3.65, 3, 2.95, 2.3),
                   (9.8, -6.8, 4.1, 2.4, 2.3), (6.5, -8, 2.8, 1.45, 1.9), (-9, -6.65, 4.5, 1.22, 1.3)]
        for x, y, sx, sy, sz in shelves:
            if abs(x) < 7.5:
                continue
            ice = floe_mesh(terrain, rng, (.46, .71, .79, 1), (.10, .30, .46, 1), glacier=True)
            ice.setPos(x, y, -.11)
            ice.setScale(sx, sy, sz)
            ice.setH(rng.uniform(-40, 40))
        for _ in range(22):
            x, y = rng.uniform(-15, 14), rng.uniform(-12, 12)
            if max(abs(x), abs(y)) < 4.72:
                continue
            scale = rng.uniform(.075, .48) * (1.5 if abs(x) + abs(y) > 12 else 1)
            floe = self.fragment.copyTo(terrain)
            floe.setPos(x, y, -.23)
            floe.setH(rng.uniform(0, 360))
            floe.setScale(scale, scale * rng.uniform(.57, 1.41), scale * .82)
            floe.setColorScale(.67, .83, .88, 1)
        terrain.flattenStrong()
        return terrain

    def make_tile(self, cell):
        root = self.root.attachNewNode(f"Floe {cell}")
        root.setPos(center(cell, 0))
        profile = fracture_profile(cell)
        ice = game_floe(root, cell, profile)
        inset = [(x * .877, y * .877) for x, y in profile]
        overlay = root.attachNewNode("Floe markings")
        overlay.setShaderOff(1)
        overlay.setZ(TOP + .014)
        highlight = overlay.attachNewNode("Legal destination")
        highlight.setZ(.003)
        sheen = flat_shape("Destination tint", highlight, inset, (1, 1, 1, .15), .001)
        sheen.setTransparency(TransparencyAttrib.MAlpha)
        sheen.setDepthWrite(False)
        outline("Lit fracture edge", highlight, inset, .950, (1, 1, 1, 1))
        for x in (-.30,.30):
            flat_shape("Destination glint",highlight,((x-.025,.10),(x,.137),(x+.025,.10),(x,.063)),
                       (1,1,1,1),.004)
        highlight.hide()

        selection = outline("Selected origin", overlay, inset, .930, (1, 1, 1, 1))
        selection.setZ(.006)
        selection.hide()

        warning = overlay.attachNewNode("Deepfin warning")
        warning.setZ(.009)
        outline("Coral fracture outline", warning, inset, .925, CORAL)
        outline("Warning ring", warning, circle(.310), .926, GOLD).setZ(.001)
        for angle in (0, 90, 180, 270):
            chevron = flat_shape("Hazard chevron", warning,
                                 ((-.077, .423), (0, .376), (.077, .423), (0, .405)), CORAL, .002)
            chevron.setH(angle)
        warning.flattenStrong()
        warning.hide()
        marker = overlay.attachNewNode("Bait")
        marker.setPos(.305, .292, .014)
        flat_shape("Bait badge", marker, circle(.106, 8), (.21, .12, .10, 1))
        outline("Amber bait rim", marker, circle(.105, 8), .78, GOLD).setZ(.004)
        flat_shape("Bait symbol", marker, ((0, -.055), (.038, 0), (0, .062), (-.038, 0)), GOLD, .006)
        marker.hide()

        frost = overlay.attachNewNode("Frost Warden")
        frost.setPos(-.265, .23, .014)
        flat_shape("Frozen badge", frost, circle(.131, 10), (.21, .12, .49, 1))
        for angle in (0, 60, 120):
            spoke = flat_shape("Snow crystal", frost, ((-.082, -.011), (.082, -.011),
                                                      (.082, .011), (-.082, .011)), (.94, .91, 1, 1), .006)
            spoke.setH(angle)
        frost.hide()

        pickup = self.unit.copyTo(root)
        pickup.setPos(.28, .272, TOP + .056)
        pickup.setScale(.070, .074, .088)
        pickup.setColorScale(1, .70, .28, 1)
        pickup.hide()

        fish = root.attachNewNode("Three-dimensional fish")
        fish.setPos(0, -.248, TOP + .030)
        return Tile(root, ice, fish, pickup, warning, marker, highlight, selection, frost)

    def draw_fish(self, tile, value, cell):
        if value == tile.value:
            return
        tile.value = value
        tile.fish.getChildren().detach()
        if value < 1:
            return
        count = min(4, value)
        rng = Random(1949 + cell)
        facing = -1 if rng.random() < .5 else 1
        shade = (.069, .24, .35, .55)
        fade = (*shade[:3], 0)
        shadows = tile.fish.attachNewNode("Fish contact shadows")
        for x, y, heading, scale in FISH_GROUPS[count]:
            x *= facing
            heading = heading * facing + rng.uniform(-8, 8)
            if facing < 0:
                heading += 180
            fish = self.fish_model.copyTo(tile.fish)
            fish.setPos(x, y, .038 * scale - .012)
            fish.setScale(scale)
            fish.setHpr(heading, rng.uniform(58, 74) * facing, rng.uniform(-5, 4))

            contact = Mesh("Soft shadow under fish")
            edge = [(sx-.019, sy, 0) for sx, sy in circle(.099, 14)]
            for i, first in enumerate(edge):
                second = edge[(i + 1) % len(edge)]
                contact.triangle(((-.019, 0, 0), first, second), shade, vertex_colors=(shade, fade, fade))
            shadow = contact.attach(shadows)
            shadow.setPos(x, y, -.026)
            shadow.setScale(scale*1.27, scale*.69, 1)
            shadow.setH(heading)
            shadow.setShaderOff(1)
            shadow.setTransparency(TransparencyAttrib.MAlpha)
            shadow.setDepthWrite(False)
        if value > count:
            caption = TextNode("Fish school size")
            caption.setFont(self.font)
            caption.setText(str(value))
            caption.setTextColor(*DARK)
            caption.setAlign(TextNode.ACenter)
            node = tile.fish.attachNewNode(caption)
            node.setPos(0, .18, .004)
            node.setScale(.21)
            node.setP(-90)
            node.setShaderOff(1)
        shadows.flattenStrong()

    def sync(self, state, *, restart=False, intact=None):
        if restart:
            self.moving = None
            self.finish_meal()
            for effect in self.breaks:
                self.remove_break(effect)
            self.breaks.clear()
            for ring, _ in self.brace_rings:
                ring.removeNode()
            self.brace_rings.clear()
            self.seal_strike = None
            self.hide_breach()
            self.ripples.clear()
            for spark in self.trail:
                spark.hide()
        breaking = {effect.cell for effect in self.breaks if effect.has_ice}
        threat = self.threatened_cell(state)
        for cell, tile in enumerate(self.tiles):
            awaiting_impact = cell == threat and self.seal_strike is not None and not state.has_ice(cell)
            if not awaiting_impact:
                self.draw_fish(tile, state.fish[cell], cell)
            tint = {2: Vec4(.76,.98,.92,.27),3: Vec4(.82,.83,1,.29)}.get(state.fish[cell],Vec4(0))
            tile.ice.setShaderInput("cap_tint",tint)
            if (state.has_ice(cell) if intact is None else cell in intact):
                tile.ice.show()
                tile.ice.setZ(0)
                tile.ice.setHpr(0, 0, 0)
                tile.root.show()
            elif cell not in breaking:
                tile.root.hide()
            tile.bait.show() if cell in state.pickups else tile.bait.hide()
            tile.marker.show() if cell in state.markers else tile.marker.hide()
            tile.warning.show() if cell == threat else tile.warning.hide()
            tile.frost.show() if cell in state.frozen or cell in state.marks else tile.frost.hide()
            if cell in state.frozen:
                tile.ice.setShaderInput("frost_tint", Vec4(.52, .41, .84, .57))
            elif cell in state.marks:
                tile.ice.setShaderInput("frost_tint", Vec4(.61, .48, .96, .28))
            elif cell == threat:
                tile.ice.setShaderInput("frost_tint", Vec4(.94, .39, .36, .45))
            else:
                tile.ice.setShaderInput("frost_tint", Vec4(0))
        for index, (piece, cell) in enumerate(zip(self.pieces, state.positions)):
            moving = self.moving is not None and self.moving[0] == index
            if cell < 0 and not moving:
                piece.hide()
                self.shadows[index].hide()
                self.teams[index].hide()
                continue
            piece.show()
            self.shadows[index].show()
            self.teams[index].show()
            if not moving:
                piece.setPos(center(cell))
                piece.setHpr(13 if index // 2 == 0 else -12, 0, 0)
                self.position_shadow(index, piece)

    def position_shadow(self, index, piece, floor=TOP):
        shadow = self.shadows[index]
        target = piece.getPos()
        shadow.setPos(target.x + .049, target.y + .037, floor + .008)
        shadow.setShaderInput("shadow_center", shadow.getPos())
        self.teams[index].setPos(target.x, target.y, floor + .013)

    def show_options(self, state, selected, allowed, hover):
        if hover != self.hovered and hover in allowed:
            self.water_ripple(center(hover), .34)
        self.hovered=hover if hover in allowed else None
        for cell, tile in enumerate(self.tiles):
            action = allowed.get(cell)
            if action:
                color = (CORAL if action.kind == "rescue" or cell == state.shark else
                         GOLD if action.kind == "bait" else VIOLET if action.kind == "brace" else MINT)
                if hover == cell:
                    color = mix(color, (1, 1, 1, 1), .48)
                tile.highlight.setColorScale(*color)
                tile.highlight.show()
            else:
                tile.highlight.hide()
            if selected is not None and cell == state.positions[selected]:
                tile.selection.setColorScale(*TEAM[selected // 2])
                tile.selection.show()
            else:
                tile.selection.hide()
        self.route.getChildren().detach()
        action = allowed.get(hover)
        if action is None or action.kind not in ("move", "brace"):
            return
        start, end = center(state.positions[action.penguin]), center(action.target)
        delta = end - start
        length = delta.length()
        heading = degrees(atan2(delta.y, delta.x))
        mark = self.route.attachNewNode("Trajectory")
        mark.setPos(start)
        mark.setH(heading)
        mark.setBin("fixed", 10)
        beam = CORAL if action.target == state.shark else VIOLET if action.kind == "brace" else (.83, 1, .96, 1)
        for index in range(2, int(length / .23)):
            x = index * .23
            dash = flat_shape("Route arrow", mark, ((x-.074, -.072), (x+.070, 0),
                                                  (x-.074, .072), (x-.037, 0)), DARK, .030)
            dash.setDepthWrite(False)
            flat_shape("Route glow", mark, ((x-.048, -.044), (x+.042, 0), (x-.048, .044)),
                       beam, .033).setDepthWrite(False)
        marker = self.route.attachNewNode("Departure cue")
        marker.setPos(start.x, start.y, TOP + .025)
        outline("Departure ring", marker, circle(.359), .891, VIOLET if action.kind == "brace" else GOLD)
        mark.flattenStrong()

    def brace_effect(self, cell):
        ring = outline("Reinforced ice bloom", self.overlay, clipped_square(.43, .115), .80, VIOLET)
        ring.setPos(center(cell, TOP + .053))
        ring.setTransparency(TransparencyAttrib.MAlpha)
        ring.setDepthWrite(False)
        self.brace_rings.append((ring, 0.))

    def focus_tile(self, cell):
        if cell is None:
            self.focus_marker.hide()
        else:
            self.focus_marker.setPos(center(cell, TOP + .028))
            self.focus_marker.show()

    def collect_fish(self, piece, cell, *, delay=0.):
        self.finish_meal()
        tile = self.tiles[cell]
        caught = []
        for prop in tile.fish.getChildren():
            if prop.getName() == self.fish_model.getName():
                prop.wrtReparentTo(self.effects)
                caught.append((prop, prop.getPos(), prop.getHpr(), prop.getSx()))
        if not caught:
            return 0.
        self.meal = Meal(piece, caught, age=-delay)
        return self.meal.duration

    def finish_meal(self):
        if self.meal:
            for prop, *_ in self.meal.fish:
                prop.removeNode()
            self.rigs[self.meal.piece].pose()
            self.meal = None

    def animate_meal(self, dt):
        meal = self.meal
        if meal is None:
            return
        meal.age += dt
        age = meal.age
        if age < 0:
            return
        if age >= meal.duration:
            self.finish_meal()
            return
        rig = self.rigs[meal.piece]
        lift = phase(age, .31, .51)
        relax = phase(age, meal.duration - .13, meal.duration)
        reach = phase(age, .01, .29) * (1 - relax)
        crouch = phase(age, 0., .16) * (1 - lift)
        bite = sum(sin(pi * max(0., min(1., (age - FIRST_BITE - BITE_GAP * i) / BITE_LENGTH)))
                   for i in range(len(meal.fish)))
        grip_height = .29 + .26 * lift - .019 * bite
        rig.pose(reach, grip_height, 15 * crouch + 13 * bite, 35 * bite)
        for i, (prop, start, heading, scale) in enumerate(meal.fish):
            swallow = FIRST_BITE + BITE_GAP * i
            if age >= swallow + BITE_LENGTH:
                prop.hide()
                continue
            pickup = phase(age, .10 + .025 * i, .35 + .018 * i)
            nibble = phase(age, swallow, swallow + BITE_LENGTH)
            stagger = i - (len(meal.fish) - 1) / 2
            held = Point3(stagger * .091, -.418 - .031 * i, grip_height + stagger * .058)
            mouth = rig.root.getRelativePoint(rig.jaw, Point3(0, -.107, .015))
            target = self.effects.getRelativePoint(rig.root, held + (mouth - held) * nibble)
            pos = start + (target - start) * pickup
            pos.z += .13 * sin(pi * pickup)
            prop.setPos(pos)
            prop.setHpr(lerp_angle(heading.x, rig.root.getH() + 12 - 22 * stagger, pickup),
                        lerp_angle(heading.y, 19 + 15 * stagger - 20 * nibble, pickup),
                        lerp_angle(heading.z, -5 + 22 * nibble, pickup))
            prop.setScale(scale * (1 - phase(age, swallow + .07, swallow + BITE_LENGTH)))

    def slide(self, piece, origin, destination, jump, duration, *, delay=0.):
        start, end = center(origin), center(destination)
        delta = end - start
        heading = degrees(atan2(delta.x, -delta.y))
        self.moving = (piece, start, end, jump, -delay, duration, heading, self.pieces[piece].getH())
        if not delay:
            self.water_ripple(end, .6)

    def water_ripple(self, spot, strength=1):
        self.ripples.append((spot.x,spot.y,self.world_clock,strength))
        self.ripples=self.ripples[-4:]

    def threatened_cell(self, state):
        strike = self.seal_strike
        if strike is not None and strike.has_ice and strike.age < SEAL_IMPACT:
            return strike.cell
        return state.shark

    def strike(self, cell, delay, *, has_ice):
        self.seal_strike = SealStrike(cell, -delay, has_ice)
        self.fracture(cell, delay + SEAL_IMPACT, attack=True, has_ice=has_ice)

    def fracture(self, cell, delay=0, *, attack=False, has_ice=True):
        if not delay:
            self.water_ripple(center(cell), 1.6 if attack else 1.)
        rng = Random(cell * 10821)
        origin = center(cell)
        fragments = []
        shards = (16 if attack else 7) if has_ice else 0
        count = shards + (20 if attack else 8)
        for i in range(count):
            angle = tau * i / count + rng.uniform(-.17, .17)
            scale = rng.uniform(.090, .28) if i < shards else rng.uniform(.024, .058)
            if i < shards:
                part = self.fragment.copyTo(self.effects)
                part.setScale(scale, scale * rng.uniform(.55, 1.20), scale * 1.55)
            else:
                part = oval(self.effects, self.unit, "Splash droplet", (0, 0, 0),
                            (scale, scale, scale * 1.7), (.45, .87, 1, 1))
            part.hide()
            fragments.append((part, cos(angle), sin(angle), rng.uniform(.76, 1.5), rng.uniform(85, 210)))
        rings = []
        for index in range(3):
            ring = outline("Splash ripple", self.overlay, circle(.42 + index * .18), .88 + index * .027,
                           (.62, .94, 1, .83 - index * .14))
            ring.setTransparency(TransparencyAttrib.MAlpha)
            ring.setDepthWrite(False)
            ring.setPos(origin.x, origin.y, WATER_LEVEL + .011 + index * .001)
            ring.hide()
            rings.append(ring)
        crack = self.overlay.attachNewNode("Splintering ice")
        crack.setPos(center(cell, TOP + .026))
        crack.hide()
        if has_ice:
            for arm in range(6):
                angle = tau * arm / 6 + rng.uniform(-.21, .21)
                angled = crack.attachNewNode("Fracture line")
                angled.setH(degrees(angle))
                points = ((0, 0), (.12, -.039), (.26, .026), (.425, -.041))
                for (x, y), (ox, oy) in zip(points, points[1:]):
                    flat_shape("Split", angled, ((x-.011, y-.016), (ox+.008, oy-.018),
                                                 (ox+.012, oy+.015), (x-.011, y+.016)),
                               (.11, .29, .48, 1))
            crack.flattenStrong()
        self.breaks.append(Break(cell, -delay, .86 if attack else .68, fragments, rings, crack, attack, has_ice))

    def remove_break(self, effect):
        for fragment, *_ in effect.fragments:
            fragment.removeNode()
        for node in [*effect.rings, effect.crack]:
            node.removeNode()

    def hide_breach(self):
        self.seal.hide()
        for drop in self.breach_spray:
            drop.hide()

    def animate_seal(self, dt):
        strike = self.seal_strike
        if strike is None:
            return
        spot = center(strike.cell)
        age = strike.age + dt
        if strike.age < SEAL_LAUNCH <= age:
            self.water_ripple(spot, 1.45)
        strike.age = age
        if age >= SEAL_DURATION:
            self.hide_breach()
            self.seal_strike = None
            return
        if age < SEAL_LAUNCH:
            return
        climb = phase(age, .18, .54)
        descent = max(0., (age - .56) / (SEAL_DURATION - .56)) ** 2
        pitch = 61 - 131 * phase(age, .34, .86)
        self.seal.show()
        self.seal.setPos(spot.x, spot.y, -1.08 + climb * 2.72 - descent * 2.90)
        self.seal.setHpr(-28 + 13 * phase(age, .42, .84), 0, -pitch)
        self.seal_tail.setR(24 * sin(age * 15) * (1 - descent))
        for side, flipper in zip((-1, 1), self.seal_flippers):
            flipper.setH(side * (39 * phase(age, .55, .88) - 14))
            flipper.setP(side * 21 * sin(age * 9))
        splash = (age - SEAL_LAUNCH) / .46
        for i, drop in enumerate(self.breach_spray):
            if splash >= 1:
                drop.hide()
                continue
            angle = tau * i / len(self.breach_spray)
            ray = .23 + (.57 + .08 * (i % 4)) * splash
            z = TOP + sin(pi * splash) * (.60 + .16 * (i % 4)) - .24 * splash
            drop.setPos(spot.x + cos(angle) * ray, spot.y + sin(angle) * ray, z)
            drop.setHpr(degrees(angle), 37 * splash, 22 * splash)
            drop.setScale(.023 * (1 - .61 * splash), .023 * (1 - .61 * splash), .072)
            drop.show()

    def animate_break(self, effect, dt):
        if effect.age < 0 <= effect.age + dt:
            self.water_ripple(center(effect.cell), 2.25 if effect.attack else 1.)
            if effect.has_ice:
                tile = self.tiles[effect.cell]
                tile.root.setPos(center(effect.cell, 0))
                tile.root.setHpr(0, 0, 0)
                tile.warning.hide()
                if effect.attack:
                    self.draw_fish(tile, 0, effect.cell)
        effect.age += dt
        if effect.age < 0:
            return False
        t = min(1, effect.age / effect.duration)
        origin = center(effect.cell)
        suspense = .055 if effect.attack else .19
        burst = max(0., (t - suspense) / (1 - suspense))
        if effect.has_ice:
            tile = self.tiles[effect.cell]
            if t < .41:
                effect.crack.show()
            else:
                effect.crack.hide()
            tile.ice.setP(-54 * burst + sin(t * 56) * (1 - burst) * 2.3)
            tile.ice.setR(33 * burst)
            tile.ice.setZ(-1.36 * burst ** 1.22)
            if burst >= .59:
                tile.root.hide()
        if burst > 0:
            for index, ring in enumerate(effect.rings):
                ring.show()
                ring.setScale(.67 + burst * (2.05 + index * .17))
                ring.setColorScale(1, 1, 1, (1 - burst) ** 1.65)
            for part, dx, dy, velocity, rotate in effect.fragments:
                part.show()
                distance = .15 + burst * velocity * (1.52 if effect.attack else 1.18)
                part.setPos(origin.x + dx * distance, origin.y + dy * distance,
                            TOP + sin(pi * burst) * velocity * (1.17 if effect.attack else .95) - .84 * burst)
                part.setHpr(burst * rotate, burst * rotate * 1.5, burst * rotate * .77)
        if t == 1:
            self.remove_break(effect)
            return True
        return False

    def animate(self, dt, state, motion):
        if motion:
            self.world_clock += dt
        self.water.setShaderInput("tide_time", self.world_clock)
        self.root.setShaderInput("scene_time",self.world_clock)
        self.coast.animate(dt,motion)
        self.animate_seal(dt)
        danger = self.threatened_cell(state)
        clock = self.world_clock
        if danger >= 0 and motion:
            spot = center(danger)
            self.water.setShaderInput("pressure", Vec4(spot.x, spot.y, .6, clock))
        else:
            self.water.setShaderInput("pressure", Vec4(0))
        breaking = {effect.cell for effect in self.breaks if effect.has_ice and effect.age >= 0}
        for cell, tile in enumerate(self.tiles):
            if tile.root.isHidden() or cell in breaking:
                continue
            bob = sin(clock * 1.2 + cell * .61) * .008 if motion else 0.
            lift = .022 if cell == self.hovered else 0.
            rumble = 0.
            if cell == danger:
                throb = .5 + .5 * sin(clock * 7.2)
                rumble = (.028 + .024 * throb) if motion else 0.
                tile.warning.setColorScale(1, .77 + .23 * throb, .62 + .38 * throb, 1)
            elif cell in state.marks and cell not in state.frozen and motion:
                rumble = .012 * (.5 + .5 * sin(clock * 5.4 + cell))
            offset = Vec3(sin(clock * 40) * rumble, sin(clock * 31) * rumble * .65,
                          bob + lift + sin(clock * 24) * rumble * .42)
            tile.root.setPos(center(cell, 0) + offset)
            tile.root.setHpr(sin(clock * 27) * rumble * 22,
                             sin(clock * 32) * rumble * 68, sin(clock * 37) * rumble * 63)
            tile.fish.setR(sin(clock * 1.9 + cell) * 1.3 if motion else 0)
        remaining = []
        for ring, age in self.brace_rings:
            age += dt
            if age >= .72:
                ring.removeNode()
                continue
            progress = age / .72
            ring.setScale(.88 + progress * .24)
            ring.setColorScale(1, 1, 1, 1-progress)
            remaining.append((ring, age))
        self.brace_rings = remaining
        if self.moving:
            index, start, end, jump, age, duration, heading, before = self.moving
            if age < 0 <= age + dt:
                self.water_ripple(end, .6)
            age += dt
            t = max(0., min(1., age / duration))
            piece = self.pieces[index]
            move = ease(t)
            spot = start + (end - start) * move
            spot.z += sin(t * pi) * (.58 if jump else .095)
            piece.setPos(spot)
            facing = lerp_angle(before, heading, min(1, t * 4))
            piece.setHpr(facing, sin(t * pi) * (-18 if jump else 20), sin(t * pi) * -8)
            self.position_shadow(index, piece)
            delta = end - start
            across = Vec3(-delta.y, delta.x, 0)
            across.normalize()
            for j, spark in enumerate(self.trail):
                behind = move - .035 * (j + 1) * min(1, 3 / delta.length())
                phase = sin(pi * max(0, min(1, behind)))
                if jump or behind <= 0 or t >= 1:
                    spark.hide()
                    continue
                dust = start + delta * behind + across * ((-1) ** j) * (.09 + j * .026)
                dust.z += .025 + phase * (.05 + j * .014)
                spark.setPos(dust)
                spark.show()
            if t < 1:
                self.moving = (index, start, end, jump, age, duration, heading, before)
            else:
                self.moving = None
                piece.setHpr(13 if index // 2 == 0 else -12, 0, 0)
                if state.positions[index] < 0:
                    piece.hide()
                    self.shadows[index].hide()
                    self.teams[index].hide()
        self.animate_meal(dt)
        moving = self.moving[0] if self.moving else -1
        for index, (piece, cell) in enumerate(zip(self.pieces, state.positions)):
            if cell >= 0 and moving != index:
                tile = self.tiles[cell].root
                floor = self.root.getRelativePoint(tile, Point3(0, 0, TOP))
                phase = self.world_clock * (5 if state.active == index // 2 else 3.1) + index * 1.3
                sway = sin(phase) * (4.4 if state.active == index // 2 else 2.0) if motion else 0
                piece.setP(tile.getP())
                piece.setR(sway + tile.getR())
                piece.setSz(.91 + sin(phase) * .019 if motion else .91)
                piece.setPos(floor)
                if motion and state.over and state.winner == index // 2:
                    piece.setZ(floor.z + max(0, sin(phase * 2.4)) * .20)
                self.position_shadow(index, piece, floor.z)
        self.breaks = [effect for effect in self.breaks if not self.animate_break(effect, dt)]
        for index in range(4):
            ripple = self.ripples[index] if index < len(self.ripples) else (0, 0, -10, 0)
            self.water.setShaderInput(f"ripple{index}", Vec4(*ripple))

    def pick(self, camera, lens, pointer, pieces=()):
        near, far = Point3(), Point3()
        if not lens.extrude(Point2(*pointer), near, far):
            return None
        near = self.root.getRelativePoint(camera, near)
        far = self.root.getRelativePoint(camera, far)
        ray = far - near
        hits = []
        for cell in pieces:
            if cell < 0:
                continue
            for height, radius in ((.32, .24), (.68, .22)):
                point = center(cell, TOP + height)
                distance = (point - near).dot(ray) / ray.lengthSquared()
                if (point - (near + ray * distance)).lengthSquared() <= radius ** 2:
                    hits.append((distance, cell))
        if hits:
            return min(hits)[1]
        fraction = (TOP - near.z) / ray.z
        if not 0 <= fraction <= 1:
            return None
        point = near + ray * fraction
        col = int((point.x + 4 * FLOE) // FLOE)
        row = int((4 * FLOE - point.y) // FLOE)
        if 0 <= row < 8 and 0 <= col < 8:
            return row * 8 + col
        return None

