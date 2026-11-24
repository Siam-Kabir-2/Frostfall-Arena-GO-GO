"""Resolution-aware menus and HUD for the 3D arena."""

import os
from dataclasses import dataclass
from math import cos, pi, sin
from pathlib import Path

from panda3d.core import DynamicTextFont, Filename, TextNode, Texture, TransparencyAttrib

from .panels import ice_outline, ice_slab
from .geometry import Mesh, mix

INK = (.91, .97, .99, 1)
MUTED = (.61, .74, .82, 1)
FEED = (.69, .82, .88, 1)
NIGHT = (.034, .053, .129, 1)
PAPER = (.046, .083, .166, .98)
EDGE = (.29, .40, .64, .98)


@dataclass
class Button:
    area: tuple
    action: object
    frame: object
    highlight: object = None

    def hit(self, point):
        x, y, w, h = self.area
        return x <= point[0] < x + w and y <= point[1] < y + h


def load_fonts():
    bundled = Path(__file__).resolve().parents[1] / "assets" / "fonts"
    windows = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    linux = Path("/usr/share/fonts/truetype/dejavu")
    styles = {
        "body": ("Barlow-SemiBold.ttf", "seguisb.ttf", "DejaVuSans.ttf", 58),
        "label": ("BarlowSemiCondensed-ExtraBold.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf", 64),
        "heavy": ("BarlowCondensed-Black.ttf", "seguibl.ttf", "DejaVuSans-Bold.ttf", 110),
    }
    fonts = {}
    for key, (game_face, windows_face, linux_face, resolution) in styles.items():
        for asset in (bundled / game_face, windows / windows_face, linux / linux_face):
            if not asset.is_file():
                continue
            # Give each window its own glyph atlas, including when a second client runs in one process.
            font = DynamicTextFont(Filename.fromOsSpecific(str(asset.resolve())))
            if font.isValid():
                font.setPixelsPerUnit(resolution)
                font.setMinfilter(Texture.FTLinearMipmapLinear)
                font.setMagfilter(Texture.FTLinear)
                font.setTextureMargin(5)
                fonts[key] = font
                break
        else:
            fonts[key] = TextNode.getDefaultFont()
    return fonts


class HudLayout:
    def __init__(self, base, fonts):
        self.layer = base.pixel2d.attachNewNode("Go Go 3D interface")
        self.layer.setDepthWrite(False)
        self.layer.setDepthTest(False)
        self.layer.setTransparency(TransparencyAttrib.MAlpha)
        self.fonts = fonts
        self.measure = TextNode("Text measurement")
        self.measure.setFont(fonts["body"])
        self.buttons = []
        self.position = 0
        self.focus = -1
        self.blocked = []

    def begin(self, width, height):
        self.layer.getChildren().detach()
        self.buttons.clear()
        self.blocked.clear()
        self.position = 0
        self.w, self.h = width, height
        self.compact = width / height < 1.36
        self.s = max(.53, min(1.32, height / 900, width / (680 if self.compact else 1140)))

    def geometry(self, name, points, color):
        node = Mesh(name)
        node.fan(tuple((x, 0, -y) for x, y in points), color)
        return self.attach(node)

    def attach(self, node):
        result = node.attach(self.layer)
        result.setTwoSided(True)
        result.setBin("fixed", self.position)
        self.position += 1
        return result

    def ice_panel(self, x, y, w, h, *, panel=True, primary=False, disabled=False, accent=None):
        panel = self.attach(ice_slab(w, h, self.s, panel=panel, primary=primary, disabled=disabled, accent=accent))
        panel.setPos(x, 0, -y)
        return panel

    def rounded(self, x, y, w, h, color, radius):
        r = min(radius, w*.5, h*.5)
        points = []
        for index, (cx, cy) in enumerate(((x+w-r,y+r), (x+w-r,y+h-r), (x+r,y+h-r), (x+r,y+r))):
            for i in range(7):
                angle = (index-1+i/6)*pi/2
                points.append((cx+r*cos(angle), cy+r*sin(angle)))
        return self.geometry("Rounded HUD surface", points, color)

    def shape(self, x, y, w, h, color, corner=0):
        k = min(corner, w / 2, h / 2)
        return self.geometry("Interface shape", ((x + k, y), (x + w - k, y), (x + w, y + k),
                                (x + w, y + h - k), (x + w - k, y + h), (x + k, y + h),
                                (x, y + h - k), (x, y + k)), color)

    def card(self, x, y, w, h, edge=EDGE, fill=PAPER, corner=13):
        self.shape(x, y, w, h, edge, corner)
        return self.shape(x + 1, y + 1, w - 2, h - 2, fill, max(0, corner - 1))

    def plate(self, x, y, w, h, accent, *, strong=False):
        s = self.s
        self.shape(x + 2*s, y + 5*s, w, h, (.012, .021, .053, .88), 12*s)
        edge = mix(EDGE, accent, .78 if strong else .36)
        background = mix(PAPER, accent, .15 if strong else .07)
        frame = self.card(x, y, w, h, edge, background, 11*s)
        self.shape(x + 14*s, y + 1*s, min(w*.58, w - 25*s), 2*s, accent if strong else edge)
        return frame

    def text(self, value, x, y, size, color=INK, style="body", align=TextNode.ALeft):
        node = TextNode("Interface text")
        node.setFont(self.fonts[style])
        node.setAlign(align)
        node.setText(str(value))
        node.setTextColor(*color)
        path = self.layer.attachNewNode(node)
        path.setPos(x, 0, -y)
        path.setScale(size * self.s)
        path.setBin("fixed", self.position)
        self.position += 1
        return path

    def paragraph(self, value, x, y, width, size=17, color=MUTED, lines=3, *, align=TextNode.ALeft):
        scale = size * self.s
        current, result = "", []
        for word in value.split():
            proposed = f"{current} {word}" if current else word
            if current and self.measure.calcWidth(proposed) * scale > width:
                result.append(current)
                current = word
            else:
                current = proposed
        if current:
            result.append(current)
        for index, line in enumerate(result[:lines]):
            self.text(line, x, y + index * scale * 1.32, size, color, align=align)

    def track_ice_button(self, area, action, frame):
        x, y, w, h = area
        highlight = self.attach(ice_outline(w, h, self.s, 1.7*self.s))
        highlight.setPos(x, 0, -y)
        highlight.hide()
        self.buttons.append(Button(area, action, frame, highlight))

    def button(self, title, area, action, *, primary=False, disabled=False, arrow=False, size=16):
        x, y, w, h = area
        s = self.s
        ink = (.54, .69, .75, 1) if disabled else NIGHT if primary else (.98, 1, 1, 1)
        frame = self.ice_panel(x, y, w, h, panel=False, primary=primary, disabled=disabled)
        if not disabled:
            self.track_ice_button(area, action, frame)
        title = title.upper()
        if arrow:
            label = self.text(title, x + 17*s, y + h*.64, size, ink, "label")
            self.text("›", x + w - 17*s, y + h*.66, 23, ink, "label", TextNode.ARight)
        else:
            label = self.text(title, x + w*.5, y + h*.64, size, ink, "label", TextNode.ACenter)
        if not primary or disabled:
            label.node().setShadow(.044, .082)
            label.node().setShadowColor(.012, .074, .106, .91)

    def focus_buttons(self, mouse):
        for index, button in enumerate(self.buttons):
            hover = button.hit(mouse) or index == self.focus
            scale = (1.18, 1.21, 1.21, 1) if hover else (1, 1, 1, 1)
            button.frame.setColorScale(*scale)
            if button.highlight is not None:
                button.highlight.show() if hover else button.highlight.hide()

    def handle_click(self, point):
        for button in reversed(self.buttons):
            if button.hit(point):
                self.focus = -1
                button.action()
                return True
        return False

    def contains(self, point):
        return (any(x <= point[0] < x + w and y <= point[1] < y + h for x, y, w, h in self.blocked)
                or any(button.hit(point) for button in self.buttons))

    def wordmark(self, value, x, y, size, face):
        s = self.s
        self.text(value, x+1.7*s, y+4*s, size, (.016, .095, .166, 1), "heavy")
        self.text(value, x, y-1.4*s, size, (.94, .994, 1, 1), "heavy")
        self.text(value, x, y, size, face, "heavy")

    def dialog(self, title, subtitle, width, height):
        s = self.s
        self.buttons.clear()
        self.blocked = [(0, 0, self.w, self.h)]
        self.shape(0, 0, self.w, self.h, (.009, .022, .042, .72))
        w, h = width * s, height * s
        x, y = (self.w - w) * .5, (self.h - h) * .5
        self.ice_panel(x, y, w, h)
        self.wordmark(title.upper(), x+31*s, y+63*s, 46, (.84, .96, 1, 1))
        if subtitle:
            self.text(subtitle, x + 32*s, y + 96*s, 17, MUTED)
        return x, y, w, h
