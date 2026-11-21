"""Map the supplied ice artwork onto solid tiles for both arena cameras."""

from enum import IntEnum
from pathlib import Path

from panda3d.core import (
    Filename, Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat,
    GeomVertexWriter, NodePath, Texture,
)

from frostfall.stage3d import TOP

SHEET = Path(__file__).resolve().parent / "assets" / "glowing-ice-tiles.png"
# Solid artwork in the 2172 × 724 sheet. The airy glow is outside these bounds.
REGIONS = (
    (101, 60, 305, 285), (470, 61, 286, 284), (807, 59, 276, 283),
    (1137, 61, 282, 280), (1468, 60, 278, 280), (1790, 56, 289, 285),
    (50, 418, 240, 241), (326, 424, 231, 235), (594, 424, 221, 235),
    (851, 422, 224, 237), (1108, 427, 226, 231),
)
# The first pair is a corner on the ice surface. The second is the matching
# point on the painted top, measured from the upper-left of its source region.
RIM = (
    ((-.34, .47), (.19, .028)),
    ((.34, .47), (.82, .028)),
    ((.48, .33), (.96, .17)),
    ((.48, -.33), (.96, .67)),
    ((.34, -.47), (.83, .822)),
    ((-.34, -.47), (.17, .822)),
    ((-.48, -.33), (.04, .67)),
    ((-.48, .33), (.04, .17)),
)


class TileSkin(IntEnum):
    AZURE = 6
    CORAL = 7
    HOVER = 8
    UPGRADE = 9
    SELECTED = 10


class BoardTile:
    def __init__(self, board, skins, variant):
        self.root = board.attachNewNode("Board tile")
        self.skins = skins
        self.variant = variant
        self.skin = variant
        self.surface = skins[variant].instanceTo(self.root)

    def show_skin(self, skin=None):
        skin = self.variant if skin is None else skin
        if skin != self.skin:
            self.surface.removeNode()
            self.surface = self.skins[skin].instanceTo(self.root)
            self.skin = skin


def load_tile_skins(loader):
    texture = loader.loadTexture(Filename.fromOsSpecific(str(SHEET)))
    texture.setMinfilter(Texture.FTLinearMipmapLinear)
    texture.setMagfilter(Texture.FTLinear)
    texture.setWrapU(Texture.WMClamp)
    texture.setWrapV(Texture.WMClamp)
    bank = NodePath("Ice tile skins")
    return tuple(ice_mesh(bank, texture, variant) for variant in range(len(REGIONS)))


def ice_mesh(parent, texture, variant):
    data = GeomVertexData("Textured ice slab", GeomVertexFormat.getV3c4t2(), Geom.UHStatic)
    position = GeomVertexWriter(data, "vertex")
    color = GeomVertexWriter(data, "color")
    uv = GeomVertexWriter(data, "texcoord")
    triangles = GeomTriangles(Geom.UHStatic)
    width, height = texture.getXSize(), texture.getYSize()
    left, top, source_w, source_h = REGIONS[variant]
    index = 0

    def face(vertices, tone):
        nonlocal index
        for (x, y), z, (u, v) in vertices:
            position.addData3(x, y, z)
            color.addData4(tone, tone, tone, 1)
            uv.addData2((left+u*source_w)/width, 1-(top+v*source_h)/height)
        triangles.addVertices(index, index+1, index+2)
        index += 3

    def side_vertex(vertex, scale, z, depth=None):
        (x, y), (u, v) = vertex
        # Use the layered front of the art around the thickness of the slab.
        sample = (u, v) if depth is None else (.5+.60*x, depth)
        return (x*scale, y*scale), z, sample

    center = (0, 0), TOP, (.50, .425)
    for a, b in zip(RIM, RIM[1:]+RIM[:1]):
        upper_a, upper_b = side_vertex(a, 1, TOP), side_vertex(b, 1, TOP)
        face((center, upper_b, upper_a), 1)

        bevel_a, bevel_b = side_vertex(a, 1.025, .048, .861), side_vertex(b, 1.025, .048, .861)
        base_a, base_b = side_vertex(a, .925, -.205, .979), side_vertex(b, .925, -.205, .979)
        y = (a[0][1]+b[0][1])/2
        tone = .76+.20*(.5-y)
        face((upper_a, bevel_a, bevel_b), tone)
        face((upper_a, bevel_b, upper_b), tone)
        face((bevel_a, base_a, base_b), tone)
        face((bevel_a, base_b, bevel_b), tone)

    geom = Geom(data)
    geom.addPrimitive(triangles)
    node = GeomNode(f"Ice variant {variant+1}")
    node.addGeom(geom)
    surface = parent.attachNewNode(node)
    surface.setTexture(texture)
    surface.setTwoSided(True)
    return surface
