"""Snow-capped ice frames for the Panda3D interface."""

from functools import lru_cache
from math import hypot, pi, sin
from random import Random

from .stage3d import Mesh, mix


PANEL = ((.13, .40, .54, 1), (.026, .109, .171, 1), (.31, .73, .84, 1))
PRIMARY = ((.40, .92, .99, 1), (.12, .54, .73, 1), (.55, .96, 1, 1))
SECONDARY = ((.11, .32, .43, 1), (.035, .15, .23, 1), (.27, .62, .73, 1))
DISABLED = ((.098, .20, .25, 1), (.042, .107, .15, 1), (.19, .34, .41, 1))


def polygon(mesh, points, colors):
    vertices = [(x, 0, -y) for x, y in points]
    for i in range(1, len(vertices) - 1):
        mesh.triangle((vertices[0], vertices[i], vertices[i + 1]), colors[0],
                      vertex_colors=(colors[0], colors[i], colors[i + 1]))


def stroke(mesh, points, width, color):
    for (x, y), (u, v) in zip(points, points[1:]):
        length = hypot(u - x, v - y)
        dx, dy = (v - y) * width / length, (x - u) * width / length
        polygon(mesh, ((x-dx, y-dy), (x+dx, y+dy), (u+dx, v+dy), (u-dx, v-dy)), (color,) * 4)


def ice_profile(w, h, s):
    cut = min(17*s, h*.24, w*.22)
    return ((.44*cut, .20*cut), (1.15*cut, 0), (.34*w, .9*s), (.61*w, 0),
            (w-.78*cut, .11*cut), (w-.20*cut, .65*cut), (w, h*.29),
            (w-.9*s, h*.68), (w-.59*cut, h-.32*cut), (w-1.35*cut, h),
            (.51*w, h-.8*s), (.10*w, h), (.20*cut, h-.57*cut), (0, h*.54), (.13*cut, h*.31))


@lru_cache(maxsize=128)
def ice_outline(w, h, s, inset=0):
    frame = Mesh("Inlaid ice highlight")
    points = [(inset + x*(w-2*inset)/w, inset + y*(h-2*inset)/h) for x, y in ice_profile(w, h, s)]
    stroke(frame, points + points[:1], .88*s, (.79, .98, 1, .94))
    return frame


@lru_cache(maxsize=192)
def ice_slab(w, h, s, *, panel=False, primary=False, disabled=False, accent=None):
    mesh = Mesh("Carved glacier panel" if panel else "Carved ice button")
    outline = ice_profile(w, h, s)
    center = (.52*w, .46*h)
    rng = Random(round(w/s)*97 + round(h/s)*201)
    palette = PANEL if panel else PRIMARY if primary else SECONDARY
    top, bottom, rim = DISABLED if disabled else palette
    if accent is not None and not disabled:
        top = mix(top, accent, .08)
        bottom = mix(bottom, accent, .035)
        rim = mix(rim, accent, .24)
    mid = mix(top, bottom, center[1]/h)
    bevel = (5.5 if panel else 2.7)*s
    inner = [(bevel + x*(w-2*bevel)/w, bevel + y*(h-2*bevel)/h) for x, y in outline]

    # Drop shadow and striated undercut give the slabs a visible edge on bright scenery.
    for dx, dy, color in ((1, 10 if panel else 5.5, (.005, .026, .051, .54)),
                          (0, 5.7 if panel else 3.5, (.019, .16, .25, 1))):
        shape = [(x + dx*s, y + dy*s) for x, y in outline]
        pivot = (center[0] + dx*s, center[1] + dy*s)
        for i, point in enumerate(shape):
            polygon(mesh, (pivot, point, shape[(i+1) % len(shape)]), (color,) * 3)
    for i, point in enumerate(outline):
        j = (i+1) % len(outline)
        left, right = inner[i], inner[j]
        light = 1 - (point[1] + outline[j][1])/(2*h)
        ice_rim = mix((.052, .31, .45, 1), rim, .36 + .64*light)
        deep = mix(bottom, rim, .32 if primary else .18)
        polygon(mesh, (point, outline[j], right, left), (ice_rim, ice_rim, deep, deep))
        shades = tuple(mix(top, bottom, vertex[1]/h) for vertex in (left, right))
        polygon(mesh, (center, left, right), (mid, *shades))
    stroke(mesh, list(inner[1:5]), .48*s, (*rim[:3], .72))
    stroke(mesh, [outline[7], outline[8], outline[9], outline[10], outline[11]], .46*s, (*rim[:3], .69))

    if not disabled:
        for vertices in (((.018,.31), (.16,.095), (.39,.065), (.23,.67)),
                         ((.65,.16), (.94,.15), (.975,.43), (.83,.64)),
                         ((.36,.89), (.58,.62), (.71,.76), (.58,.945))):
            points = [(x*w, y*h) for x, y in vertices]
            polygon(mesh, points, ((*rim[:3], .10), (*rim[:3], .18), (*rim[:3], .07), (*rim[:3], 0)))

    for i, (start, end) in enumerate(((.045, .23), (.29, .49), (.61, .83), (.92, .97))):
        y = h*(.91 if i % 2 else .12)
        tint = (*rim[:3], .16 if disabled else .25)
        points = ((start*w, y), ((start+.55*(end-start))*w, y + (5 if i % 2 else -3.5)*s), (end*w, y))
        stroke(mesh, points, .51*s, tint)
    # Fine fracture networks stay close to the edges, leaving the middle clear for labels.
    if not disabled:
        for index in range(8 if panel else 4):
            side = -1 if index % 2 else 1
            x = w * (rng.uniform(.78, .93) if side == -1 else rng.uniform(.08, .21))
            y = h * (rng.uniform(.64, .88) if (index // 2) % 2 else rng.uniform(.13, .38))
            length = min(w*.20, h*.43, (67 if panel else 24)*s)
            branch = (x + side*length*.32, y + rng.uniform(-.25, .90)*length*.4)
            tip = (x + side*length*.75, y - length*.31)
            fork = (x + side*length*.70, y + length*.43)
            stroke(mesh, ((x, y), branch, tip), .41*s, (*rim[:3], .37 if panel else .46))
            stroke(mesh, (branch, (fork[0] - side*length*.16, fork[1]), fork), .26*s, (*rim[:3], .25))

    if h >= 32*s and not disabled:
        snow_cap(mesh, w, h, s, rng, panel=panel, primary=primary)
    return mesh


def snow_cap(mesh, w, h, s, rng, *, panel, primary):
    depth = min(18*s, h*.135) if panel else (10 if primary else 5.7)*s
    white, snow, blue = (.985, .999, 1, 1), (.79, .93, .98, 1), (.41, .73, .88, 1)
    contour = []
    for i in range(31):
        u = i/30
        taper = max(0, sin(pi*u)) ** .38
        x = 5*s + (w-10*s)*u
        crest = (1.7*s - depth*taper*(.58 + .19*sin(u*17) + .11*sin(u*33)))
        edge = (1.7*s + depth*taper*(.39 + .15*sin(u*21 + 2)))
        contour.append((x, crest, edge))
    for (x, top, low), (nx, nt, nl) in zip(contour, contour[1:]):
        a, b = (x, top), (nx, nt)
        c, d = (nx, nl), (x, low)
        lip, next_lip = (x, .22*top+.78*low), (nx, .22*nt+.78*nl)
        polygon(mesh, (a, b, next_lip, lip), (white, white, snow, snow))
        polygon(mesh, (lip, next_lip, c, d), (snow, snow, blue, blue))
    positions = (.10, .143, .174, .36, .69, .85, .89, .928) if panel else (.12, .16, .80, .846, .88)
    for u in positions:
        x = w*u
        width = rng.uniform(1.2, 3.1)*s
        drop = rng.uniform(5.7, min(17.8, h/s*.15) if panel else 8)*s
        polygon(mesh, ((x-width, h-1.7*s), (x+width, h-1.7*s), (x+.4*width, h+drop)),
                (snow, blue, (.79, .90, .98, .88)))
