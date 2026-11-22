"""Draw the arena UI and map the printed draft frame to live controls."""

from dataclasses import dataclass
from pathlib import Path

from panda3d.core import CardMaker, Filename, Point2, SamplerState, Shader, Texture, TransparencyAttrib, Vec4

SHEET = Path(__file__).resolve().parent / "assets" / "coral-azure-ui.png"
DOCK_SHEET = SHEET.with_name("frostfall-bottom-hud.png")
FRAME_SHEET = SHEET.with_name("dual-team-hud-bar.png")
SCORE_SHEET = SHEET.with_name("neon-scoreboard.png")
BATTLE_SHEET = SHEET.with_name("icy-battle-crest.png")
TITLE_SHEET = SHEET.with_name("crystal-title-badge.png")
BUTTON_SHEET = SHEET.with_name("icy-header-buttons.png")
HOME_SHEET = SHEET.with_name("home-menu-sprites.png")
HOME_TOOLBAR_SHEET = SHEET.with_name("home-toolbar-sprites.png")
HELP_SHEET = SHEET.with_name("how-to-play-panel.png")
SETTINGS_SHEET = SHEET.with_name("settings-panel.png")
SWITCH_SHEETS = {on: SHEET.with_name(f"settings-{'on' if on else 'off'}.png") for on in (True, False)}
HELP_PANEL = (100, 0, 1348, 1086)
SETTINGS_PANEL = (72, 0, 1376, 1086)
SWITCH_REGIONS = {True: (262, 63, 1910, 685), False: (212, 56, 1954, 677)}
SETTINGS_ROWS = ((749, 354, 1244, 522), (749, 548, 1245, 709))
HOME_REGIONS = {
    "logo": (49, 0, 725, 313),
    "panel": (20, 314, 682, 1065),
    "heading": (727, 121, 1420, 310),
    "local": (691, 350, 1442, 586),
    "cpu": (688, 588, 1439, 791),
    "showdown": (688, 797, 1439, 1001),
}
HOME_TOOL_REGIONS = {
    "help": (107, 77, 1344, 504),
    "sound": (56, 544, 484, 1000),
    "settings": (509, 544, 941, 1000),
    "exit": (963, 544, 1398, 1000),
}
SCOREBOARD_REGION = (44, 55, 2130, 665)
TITLE_REGION = (35, 24, 1738, 809)
HEADER_BUTTON_REGIONS = {
    "view": (92, 57, 706, 690),
    "home": (779, 56, 1382, 681),
    "pause": (1450, 62, 2072, 696),
}
REGIONS = {
    "toolbar": (1476, 631, 1606, 684),
    "shell": (1871, 605, 1930, 664),
    "coral_crest": (1939, 595, 2007, 670),
    "azure_crest": (2093, 602, 2157, 666),
}
DOCK_REGIONS = {
    "blank_crest": (711, 387, 859, 551),
    "coral_focus": (276, 554, 399, 717),
    "azure_focus": (523, 551, 660, 718),
    "azure_tag": (1509, 392, 1710, 470),
}
FRAME_REGIONS = {
    "draft_frame": (12, 190, 2160, 550),
    "coral_dock": (12, 190, 977, 550),
    "azure_dock": (1197, 190, 2160, 550),
}
FRAME_WIDTH, FRAME_HEIGHT = 2148, 360
CORAL_WIDTH, CREST_WIDTH = 965, 220
BATTLE_REGION = (12, 106, 2160, 622)
BATTLE_FIELDS = (
    ((124, 229, 443, 294), (671, 229, 929, 294),
     ((113, 265), (280, 432), (445, 596), (612, 763), (776, 927))),
    ((1257, 229, 1594, 294), (1812, 229, 2064, 294),
     ((1250, 1403), (1415, 1567), (1581, 1733), (1746, 1898), (1912, 2065))),
)
# Overlay bounds on the new frame, in source pixels.
DOCK_FIELDS = (
    ((167, 231, 634, 299), (718, 234, 904, 295), (99, 305, 304, 341), (564, 311, 674, 344)),
    ((1350, 231, 1799, 299), (1876, 234, 2069, 295), (1265, 305, 1470, 341), (1727, 311, 1838, 344)),
)
DOCK_SLOTS = (
    ((96, 205), (213, 323), (330, 439), (446, 555), (563, 674)),
    ((1263, 1371), (1379, 1488), (1495, 1605), (1611, 1721), (1727, 1838)),
)
DOCK_BUTTONS = (
    ((688, 326, 925, 406), (688, 413, 925, 494)),
    ((1848, 326, 2093, 406), (1848, 413, 2093, 494)),
)

PANEL_VERTEX = """
#version 150
uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;
out vec2 uv;

void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    uv = p3d_MultiTexCoord0;
}
"""

SETTINGS_FRAGMENT = """
#version 150
uniform sampler2D p3d_Texture0;
uniform vec4 first_row;
uniform vec4 second_row;
in vec2 uv;
out vec4 p3d_FragColor;
vec2 uv_dx;
vec2 uv_dy;

vec4 panel_color(vec2 pixel, vec2 size) {
    vec2 sample_uv = vec2(pixel.x / size.x, 1.0 - pixel.y / size.y);
    return textureGrad(p3d_Texture0, sample_uv, uv_dx, uv_dy);
}

void main() {
    uv_dx = dFdx(uv);
    uv_dy = dFdy(uv);
    vec2 size = vec2(textureSize(p3d_Texture0, 0));
    vec2 pixel = vec2(uv.x, 1.0 - uv.y) * size;
    for (int i = 0; i < 2; ++i) {
        vec4 bounds = i == 0 ? first_row : second_row;
        vec2 lo = bounds.xy;
        vec2 hi = bounds.zw;
        vec2 f = (pixel - lo) / (hi - lo);
        if (all(greaterThan(f, vec2(0))) && all(lessThan(f, vec2(1)))) {
            // Recover the panel gradient from the pixels surrounding each printed toggle.
            vec4 top = mix(panel_color(lo, size), panel_color(vec2(hi.x, lo.y), size), f.x);
            vec4 bottom = mix(panel_color(vec2(lo.x, hi.y), size), panel_color(hi, size), f.x);
            vec4 sides = mix(panel_color(vec2(lo.x, pixel.y), size), panel_color(vec2(hi.x, pixel.y), size), f.x);
            vec4 ends = mix(panel_color(vec2(pixel.x, lo.y), size), panel_color(vec2(pixel.x, hi.y), size), f.y);
            p3d_FragColor = clamp(sides + ends - mix(top, bottom, f.y), 0.0, 1.0);
            return;
        }
    }
    p3d_FragColor = textureGrad(p3d_Texture0, uv, uv_dx, uv_dy);
}
"""


@dataclass(frozen=True)
class DraftDock:
    name: tuple
    shells: tuple
    hand: tuple
    next_label: tuple
    slots: tuple
    upgrade: tuple
    ready: tuple


def fit_region(area, region, pixels):
    left, top, right, bottom = region
    x, y, w, h = area
    sx, sy = w/(right-left), h/(bottom-top)
    l, t, r, b = pixels
    return x+(l-left)*sx, y+(t-top)*sy, (r-l)*sx, (b-t)*sy


def region_aspect(region):
    left, top, right, bottom = region
    return (right-left)/(bottom-top)


class ArenaKit:
    def __init__(self, loader, hud):
        self.hud = hud
        self.texture = loader.loadTexture(Filename.fromOsSpecific(str(SHEET)))
        self.dock_texture = loader.loadTexture(Filename.fromOsSpecific(str(DOCK_SHEET)))
        self.frame_texture = loader.loadTexture(Filename.fromOsSpecific(str(FRAME_SHEET)))
        self.score_texture = loader.loadTexture(Filename.fromOsSpecific(str(SCORE_SHEET)))
        self.battle_texture = loader.loadTexture(Filename.fromOsSpecific(str(BATTLE_SHEET)))
        self.title_texture = loader.loadTexture(Filename.fromOsSpecific(str(TITLE_SHEET)))
        self.button_texture = loader.loadTexture(Filename.fromOsSpecific(str(BUTTON_SHEET)))
        self.home_texture = loader.loadTexture(Filename.fromOsSpecific(str(HOME_SHEET)))
        self.home_toolbar = loader.loadTexture(Filename.fromOsSpecific(str(HOME_TOOLBAR_SHEET)))
        self.dialog_textures = {name: loader.loadTexture(Filename.fromOsSpecific(str(path)))
                                for name, path in (("help", HELP_SHEET), ("settings", SETTINGS_SHEET))}
        self.switch_textures = {on: loader.loadTexture(Filename.fromOsSpecific(str(path)))
                                for on, path in SWITCH_SHEETS.items()}
        self.settings_shader = Shader.make(Shader.SL_GLSL, PANEL_VERTEX, SETTINGS_FRAGMENT)
        home_textures = (self.home_texture, self.home_toolbar, *self.dialog_textures.values(),
                         *self.switch_textures.values())
        for texture in (self.texture, self.dock_texture, self.title_texture, self.button_texture, *home_textures):
            texture.setMinfilter(Texture.FTLinearMipmapLinear)
            texture.setMagfilter(Texture.FTLinear)
        for texture in home_textures:
            # Keep the small lettering and edges sharp when the sprite sheets are scaled down.
            sampler = SamplerState(texture.getDefaultSampler())
            sampler.setLodBias(-.7)
            sampler.setAnisotropicDegree(4)
            texture.setDefaultSampler(sampler)
        for texture in (self.frame_texture, self.score_texture, self.battle_texture):
            texture.setMinfilter(Texture.FTLinear)
            texture.setMagfilter(Texture.FTLinear)

    def draw(self, name, area):
        if name in FRAME_REGIONS:
            return self.quad(name, area, FRAME_REGIONS[name], self.frame_texture)
        if name in DOCK_REGIONS:
            return self.quad(name, area, DOCK_REGIONS[name], self.dock_texture)
        return self.quad(name, area, REGIONS[name], self.texture)

    def quad(self, name, area, pixels, texture):
        x, y, w, h = area
        l, t, r, b = pixels
        width, height = texture.getXSize(), texture.getYSize()
        maker = CardMaker(name)
        maker.setFrame(x, x+w, -y-h, -y)
        maker.setUvRange(Point2(l/width, 1-b/height), Point2(r/width, 1-t/height))
        node = self.hud.layer.attachNewNode(maker.generate())
        node.setTexture(texture)
        node.setTransparency(TransparencyAttrib.MAlpha)
        node.setBin("fixed", self.hud.position)
        self.hud.position += 1
        return node

    def scoreboard(self, area):
        self.quad("Neon penguin scoreboard", area, SCOREBOARD_REGION, self.score_texture)

    def title_badge(self, area):
        self.quad("Crystal title badge", area, TITLE_REGION, self.title_texture)

    def header_button(self, name, area):
        return self.quad(f"Header {name}", area, HEADER_BUTTON_REGIONS[name], self.button_texture)

    def home_sprite(self, name, area):
        x, y, w, h = area
        left, top = round(x), round(y)
        area = (left, top, round(x+w)-left, round(y+h)-top)
        if name in HOME_TOOL_REGIONS:
            return self.quad(name, area, HOME_TOOL_REGIONS[name], self.home_toolbar)
        return self.quad(name, area, HOME_REGIONS[name], self.home_texture)

    def dialog_panel(self, name, area, pixels):
        panel = self.dialog_detail(name, f"{name} panel", area, pixels)
        if name == "settings":
            panel.setShader(self.settings_shader)
            panel.setShaderInput("first_row", Vec4(*SETTINGS_ROWS[0]))
            panel.setShaderInput("second_row", Vec4(*SETTINGS_ROWS[1]))

    def dialog_detail(self, panel, name, area, pixels):
        return self.quad(name, area, pixels, self.dialog_textures[panel])

    def setting_switch(self, name, area, on):
        return self.quad(name, area, SWITCH_REGIONS[on], self.switch_textures[on])

    def battle_frame(self, area):
        self.quad("Icy battle crest", area, BATTLE_REGION, self.battle_texture)

    @staticmethod
    def dock(side, area):
        name = "coral_dock" if side == 0 else "azure_dock"
        region = FRAME_REGIONS[name]

        def position(pixels):
            return fit_region(area, region, pixels)

        heading, counter, hand, next_label = map(position, DOCK_FIELDS[side])
        slots = tuple(position((l, 342, r, 499)) for l, r in DOCK_SLOTS[side])
        upgrade, ready = map(position, DOCK_BUTTONS[side])
        return DraftDock(heading, counter, hand, next_label, slots, upgrade, ready)
