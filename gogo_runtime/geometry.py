"""Geometry and palette used by the Go Go 3D board and HUD."""

from math import cos, sin, tau

from panda3d.core import Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat, GeomVertexWriter, Vec3

FLOE = 1.07
TOP = .107
GOLD = (1, .81, .36, 1)
TEAM = ((1, .48, .36, 1), (.38, .67, 1, 1))


def mix(first, second, ratio):
    return tuple(x + (y - x) * ratio for x, y in zip(first, second))


def ease(t):
    return t * t * (3 - 2 * t)


def circle(radius, count=40):
    return [(radius * cos(tau * i / count), radius * sin(tau * i / count)) for i in range(count)]


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
