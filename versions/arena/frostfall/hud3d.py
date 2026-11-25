"""Resolution-aware menus and HUD for the 3D arena."""

import os
from dataclasses import dataclass
from math import cos, pi, sin
from pathlib import Path

from panda3d.core import DynamicTextFont, Filename, Point2, TextNode, Texture, TransparencyAttrib

from .frostui import ice_outline, ice_slab
from .rules import ADVENTURE_GOAL, ROLES, TEAMS, destinations
from .stage3d import AZURE, CORAL, GOLD, MINT, TEAM, VIOLET, Mesh, center, mix

INK = (.91, .97, .99, 1)
MUTED = (.61, .74, .82, 1)
DIM = (.41, .58, .67, 1)
FEED = (.69, .82, .88, 1)
NIGHT = (.034, .053, .129, 1)
PAPER = (.046, .083, .166, .98)
EDGE = (.29, .40, .64, .98)
ACID = (.058, .17, .185, 1)
COLORS = {"strike": CORAL, "danger": CORAL, "shark": CORAL, "warden": VIOLET, "freeze": VIOLET,
          "thaw": AZURE, "brace": VIOLET, "bait": GOLD, "pickup": GOLD, "rescue": MINT, "move": MINT}


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


class HUD:
    def __init__(self, base, fonts):
        self.layer = base.pixel2d.attachNewNode("Frostfall interface")
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
        self.margin = 37 * self.s

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

    def fade_left(self, full_until, faded_until):
        dark = (.011, .034, .067, .91)
        clear = (*dark[:3], 0)
        self.shape(0, 0, full_until, self.h, dark)
        strip = Mesh("Soft shadow behind the interface")
        a, b = (full_until, 0, 0), (faded_until, 0, 0)
        c, d = (faded_until, 0, -self.h), (full_until, 0, -self.h)
        strip.triangle((a, b, c), dark, vertex_colors=(dark, clear, clear))
        strip.triangle((a, c, d), dark, vertex_colors=(dark, clear, dark))
        self.attach(strip)

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

    def symbol(self, name, x, y, size, color):
        s = size * self.s
        paths = {
            "shield": (((-.46, -.38), (0, -.5), (.46, -.38), (.38, .19), (0, .51), (-.38, .19)),),
            "attack": (((.06, -.56), (-.43, .10), (-.03, .10), (-.14, .55), (.45, -.14), (.06, -.14)),),
            "crystal": (((-.49, .39), (-.14, -.48), (-.03, .39)),
                        ((-.03, .39), (-.14, -.48), (.20, -.28), (.49, .39))),
            "warning": (((0, -.58), (.10, -.41), (-.43, .41), (-.58, .41)),
                        ((0, -.58), (.58, .41), (.44, .41), (-.10, -.41)),
                        ((-.58, .41), (.58, .41), (.51, .53), (-.51, .53)),
                        ((-.058, -.15), (.058, -.15), (.049, .14), (-.049, .14)),
                        ((-.052, .24), (.052, .24), (.052, .34), (-.052, .34))),
            "fish": (((-.21, -.05), (.05, -.34), (.33, -.24), (.57, 0), (.33, .24), (.05, .34), (-.21, .05)),
                     ((-.16, 0), (-.55, -.32), (-.55, .32))),
            "play": (((-.26, -.51), (.56, 0), (-.26, .51)),),
        }
        for path in paths[name]:
            self.geometry(name, [(x + px*s, y + py*s) for px, py in path], color)

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

    def match_button(self, title, area, action, *, key=None, active=False, disabled=False):
        x, y, w, h = area
        s = self.s
        ink = (.54, .69, .75, 1) if disabled else NIGHT if active else INK
        frame = self.ice_panel(x, y, w, h, panel=False, primary=active, disabled=disabled)
        label_size = 13 if h < 33*s else 15
        label_x = x+w*.5
        if key:
            label_x -= 9*s
            self.rounded(x+w-22*s, y+h*.5-7*s, 14*s, 14*s, (.024, .099, .148, .65), 3*s)
            self.text(key, x+w-15*s, y+h*.5+3*s, 9, INK if active else MUTED, "label", TextNode.ACenter)
        self.text(title.upper(), label_x, y+h*.5+label_size*s*.29, label_size, ink, "label", TextNode.ACenter)
        if not disabled:
            self.track_ice_button(area, action, frame)

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

    def title_screen(self, game):
        s = self.s
        x = (28 if self.compact else 42)*s
        bright, blue = (.86, .96, 1, 1), (.36, .86, .99, 1)
        if self.compact:
            y = self.h-247*s
            w = self.w-2*x
            self.ice_panel(x, y, w, 219*s)
            self.wordmark("FROSTFALL ARENA", x+29*s, y+78*s, min(59, (w/s-58)/7.3), bright)
            self.paragraph("Collect fish. Cut off your rivals.", x+30*s, y+112*s, w-60*s, 19, INK, 1)
            play_w = (w-74*s)*.56
            self.button("Play match", (x+29*s, y+143*s, play_w, 50*s),
                        lambda: game.open_modal("setup"), primary=True, arrow=True, size=19)
            self.button("AI Arena", (x+45*s+play_w, y+143*s, w-74*s-play_w, 50*s),
                        game.setup_arena, arrow=True, size=18)
        else:
            self.fade_left(127*s, 515*s)
            w, h = 411*s, 425*s
            y = (self.h-h)*.46
            self.ice_panel(x, y, w, h)
            self.wordmark("FROSTFALL", x+27*s, y+106*s, 79, bright)
            self.wordmark("ARENA", x+26*s, y+200*s, 116, blue)
            self.paragraph("Collect fish. Cut off your rivals.", x+29*s, y+243*s, w-58*s, 19, INK, 1)
            self.button("Play match", (x+27*s, y+288*s, w-54*s, 55*s),
                        lambda: game.open_modal("setup"), primary=True, arrow=True, size=21)
            self.button("AI Arena", (x+27*s, y+355*s, w-54*s, 43*s),
                        game.setup_arena, arrow=True, size=18)
        right = self.w-x
        self.button("How to play", (right-247*s, 24*s, 124*s, 40*s), lambda: game.open_modal("help"))
        self.button("Settings", (right-111*s, 24*s, 111*s, 40*s), lambda: game.open_modal("settings"))
        self.button("Exit", (x, (24*s if self.compact else self.h-67*s), 76*s, 37*s), game.userExit)

    def match(self, game):
        s, x = self.s, 27*self.s
        mid = self.w * .5
        score_w = min(self.w-2*x, (440 if self.compact else 482)*s)
        self.scoreboard(game, mid-score_w*.5, 19*s, score_w)
        if self.compact:
            self.ice_panel(x, 112*s, 180*s, 29*s, panel=False)
            self.text(game.match_mode, x+12*s, 131*s, 11, INK, "label")
            self.blocked.append((x, 112*s, 180*s, 29*s))
        else:
            self.ice_panel(x, 25*s, 232*s, 57*s, panel=False)
            self.symbol("crystal", x+21*s, 53*s, 18, (.66, .89, .97, 1))
            self.wordmark("FROSTFALL ARENA", x+37*s, 51*s, 23, INK)
            self.text(game.match_mode, x+38*s, 68*s, 10, FEED, "label")
            self.blocked.append((x, 25*s, 232*s, 57*s))
        right = self.w-x
        y = (110 if self.compact else 38)*s
        buttons = (("View", "V", 67, game.toggle_view, game.overhead),
                   ("Log", "L", 61, game.toggle_log, game.show_log),
                   ("Pause", "P", 74, game.toggle_pause, game.modal == "pause"))
        for name, key, width, action, active in reversed(buttons):
            self.match_button(name, (right-width*s, y, width*s, 33*s), action, key=key, active=active)
            right -= (width+5)*s

        if game.banner:
            title, detail, color, _ = game.banner
            y = (151 if self.compact else 102)*s
            w = 230*s
            banner_x = mid-w/2 if self.compact else x
            self.ice_panel(banner_x, y, w, 49*s, panel=False, accent=color)
            self.blocked.append((banner_x, y, w, 49*s))
            self.symbol("warning" if color == CORAL else "shield", banner_x+20*s, y+22*s, 17, color)
            self.text(title, banner_x+38*s, y+22*s, 15, INK, "heavy")
            self.text(detail, banner_x+38*s, y+39*s, 10, color, "label")

        self.action_dock(game)
        self.board_labels(game)
        if game.show_log:
            self.log(game)

    def board_labels(self, game):
        s = self.s
        state = game.state
        flags = []
        if state.shark >= 0 and not state.over:
            flags.append((state.shark, "STRIKE", CORAL, 69))
        action = game.current_actions().get(game.hover)
        if action and action.target != state.shark:
            if action.kind == "move":
                fish = state.fish[action.target]
                if fish:
                    flags.append((action.target, f"+{fish} FISH", GOLD, 69))
            else:
                title, tone = {"brace": ("SAVE ICE", VIOLET), "bait": ("BAIT", GOLD),
                               "rescue": ("JUMP", MINT)}[action.kind]
                flags.append((action.target, title, tone, 69))
        for cell, caption, tone, width in flags:
            point = game.cam.getRelativePoint(game.render, center(cell, 1.02 if cell in state.positions else .34))
            projected = Point2()
            if not game.lens.project(point, projected):
                continue
            mid = min(self.w-width*s/2, max(width*s/2, (1+projected.x)*self.w/2))
            py = (1-projected.y)*self.h/2 - 30*s
            if py < (149 if self.compact else 104)*s or py > self.h-(209 if self.compact else 151)*s:
                continue
            self.ice_panel(mid-width*s/2, py, width*s, 22*s, panel=False, accent=tone)
            self.text(caption, mid, py+15*s, 10, tone, "label", TextNode.ACenter)
            self.geometry("Tile indicator pointer", ((mid-4*s, py+23*s), (mid+4*s, py+23*s),
                                                     (mid, py+28*s)), tone)

    def scoreboard(self, game, x, y, width):
        s = self.s
        round_w = 76*s
        span = (width-round_w-20*s)*.5
        mid = x+width*.5
        h = 75*s
        self.ice_panel(x, y, width, h)
        self.blocked.append((x, y, width, h))
        self.shape(mid-round_w*.5, y+11*s, round_w, 53*s, (.35, .65, .76, .69), 9*s)
        self.shape(mid-round_w*.5+s, y+12*s, round_w-2*s, 51*s, (.035, .13, .20, 1), 8*s)
        self.text("ROUND", mid, y+25*s, 9, FEED, "label", TextNode.ACenter)
        self.text(f"{game.state.round:02}", mid, y+(48 if game.state.adventure else 53)*s, 25, INK,
                  "heavy", TextNode.ACenter)
        if game.state.adventure:
            self.text(f"FIRST TO {ADVENTURE_GOAL}", mid, y+58*s, 8, FEED, "label", TextNode.ACenter)
        self.score(game, 0, x+10*s, y+10*s, span)
        self.score(game, 1, mid+round_w*.5, y+10*s, span)

    def score(self, game, team, x, y, w):
        s, color = self.s, TEAM[team]
        live = game.team == team and not game.state.over
        align = TextNode.ARight if team else TextNode.ALeft
        edge = x+w-11*s if team else x+11*s
        heading = edge+(-11 if team else 11)*s
        self.rounded(edge-(5*s if team else 0), y+17*s, 5*s, 5*s, color, 2.5*s)
        self.text(TEAMS[team].upper(), heading, y+23*s, 13, color, "heavy", align)
        current = game.state.scores[team]
        number_x = x+13*s if team else x+w-13*s
        self.text(str(current), number_x, y+43*s, 34, INK, "heavy",
                  TextNode.ALeft if team else TextNode.ARight)
        meter_x, meter_w = x+11*s, w-22*s
        if game.state.adventure:
            self.rounded(meter_x, y+51*s, meter_w, 3*s, (.28, .43, .57, .33), 1.5*s)
            if current:
                fill = meter_w*min(1, current/ADVENTURE_GOAL)
                self.rounded(meter_x+(meter_w-fill if team else 0), y+51*s, fill, 3*s, color, 1.5*s)
        self.text(game.controllers[team].upper(), heading, y+40*s, 10, FEED, "label", align)
        if live:
            turn_x = meter_x+meter_w-57*s if team else meter_x
            self.rounded(turn_x, y+2*s, 57*s, 2*s, color, s)
        if game.recent_score and game.recent_score[0] == team and not self.compact:
            amount = game.recent_score[1]
            tag_x = x+5*s if team else x+w-67*s
            self.ice_panel(tag_x, y+78*s, 62*s, 22*s, panel=False, accent=GOLD)
            self.text(f"+{amount} FISH", tag_x+31*s, y+93*s, 10, GOLD, "label", TextNode.ACenter)

    def roles(self, game, x, y, width):
        s, team = self.s, game.team
        span = (width-7*s)*.5
        h = 45*s
        for role in (0, 1):
            piece = team*2+role
            cell = game.state.positions[piece]
            dx = x + role*(span+7*s)
            picked = game.selected == piece and game.actionable
            accent = VIOLET if picked and game.brace else TEAM[team] if cell >= 0 else DIM
            frame = self.ice_panel(dx, y, span, h, panel=False, primary=picked, disabled=cell < 0, accent=accent)
            ink = NIGHT if picked else INK
            detail = (.037, .175, .23, 1) if picked else FEED
            self.shape(dx+9*s, y+10*s, 24*s, 25*s, mix(NIGHT, accent, .25), 5*s)
            self.symbol("attack" if role == 0 else "shield", dx+20.5*s, y+22*s, 14, accent)
            self.text(ROLES[role].upper(), dx+40*s, y+20*s, 14, ink, "label")
            mobility = len(tuple(destinations(game.state, piece))) if cell >= 0 else 0
            if cell < 0:
                status = "Eliminated"
            elif game.state.rescue >= 0:
                status = "Jump required" if game.state.rescue == piece else "Waiting"
            else:
                status = ("1 move" if mobility == 1 else f"{mobility} moves") if mobility else "Trapped"
            self.text(status, dx+40*s, y+35*s, 10, detail)
            if span >= 123*s:
                self.text(str(role+1), dx+span-10*s, y+20*s, 10, detail, "label", TextNode.ARight)
            if cell >= 0 and game.actionable and game.state.rescue < 0:
                self.track_ice_button((dx, y, span, h), lambda role=role: game.number(role+1), frame)

    def action_dock(self, game):
        s = self.s
        gap = (17 if self.compact else 23)*s
        width = min(self.w-44*s, 1244*s)
        x = (self.w-width)*.5
        floor = self.h-125*s
        h = 100*s
        team = game.team
        color = TEAM[team]
        title = ("MATCH COMPLETE" if game.state.over else "RESCUE JUMP" if game.state.rescue >= 0
                 else f"{TEAMS[team].upper()} TURN")
        if self.compact:
            crew_w = (width-gap)*.54
            field_x = x+crew_w+gap
            preview_w = min(width, 456*s)
            preview_x, preview_y = (self.w-preview_w)*.5, floor-69*s
            preview_h = 58*s
        else:
            space = width-2*gap
            crew_w = space*.334
            preview_w = space-2*crew_w
            preview_x = x+crew_w+gap
            field_x = preview_x+preview_w+gap
            preview_y = floor+12*s
            preview_h = 76*s
        field_w = self.w-x-field_x
        self.ice_panel(x, floor, crew_w, h, accent=color)
        self.blocked.append((x, floor, crew_w, h))
        self.rounded(x+14*s, floor+20*s, 6*s, 6*s, color, 3*s)
        self.text(title, x+26*s, floor+27*s, 12 if self.compact else 13, color, "heavy")
        self.roles(game, x+10*s, floor+38*s, crew_w-20*s)

        heading, detail, tone = game.move_hint()
        preview_center = preview_x+preview_w*.5
        guide_color = INK if tone in (MINT, MUTED) else tone
        self.ice_panel(preview_x, preview_y, preview_w, preview_h, panel=False,
                       accent=None if guide_color == INK else guide_color)
        self.blocked.append((preview_x, preview_y, preview_w, preview_h))
        self.text(heading, preview_center, preview_y+(21 if self.compact else 30)*s, 17 if self.compact else 20,
                  guide_color, "heavy", TextNode.ACenter)
        self.paragraph(detail, preview_center, preview_y+(37 if self.compact else 51)*s, preview_w-23*s,
                       12 if self.compact else 13, INK, 2, align=TextNode.ACenter)

        heading, detail, tone = game.hazard()
        self.ice_panel(field_x, floor, field_w, h, accent=tone)
        self.blocked.append((field_x, floor, field_w, h))
        hazard_color = INK if tone == MINT else tone
        self.symbol("warning" if game.state.adventure and tone in (CORAL, GOLD) else "shield",
                    field_x+18*s, floor+23*s, 13, hazard_color)
        self.text(heading, field_x+30*s, floor+28*s, 13 if self.compact else 15, hazard_color, "heavy")
        self.paragraph(detail, field_x+13*s, floor+46*s, field_w-26*s, 11 if self.compact else 12, INK, 2)
        if game.state.adventure:
            button_w = (field_w-35*s)*.5
            y = floor+68*s
            self.match_button("Cancel" if game.brace else "Brace used" if game.state.brace_used[team] else "Brace",
                              (field_x+13*s, y, button_w, 24*s), game.toggle_brace,
                              key="R", active=game.brace, disabled=not game.can_brace())
            self.match_button("Cancel" if game.bait else "Bait", (field_x+22*s+button_w, y, button_w, 24*s),
                              game.toggle_bait, key="B", active=game.bait, disabled=not game.can_bait())

    def log(self, game):
        s = self.s
        width = min(345*s, self.w - self.margin*2)
        x, y = self.w - self.margin - width, (151 if self.compact else 102)*s
        height = (68 + min(6, len(game.log)) * 45)*s
        self.ice_panel(x, y, width, height)
        self.blocked.append((x, y, width, height))
        self.text("MATCH LOG", x + 19*s, y + 33*s, 15, INK, "label")
        for index, (kind, message) in enumerate(game.log[:6]):
            ty = y + (68 + index * 44)*s
            self.shape(x + 20*s, ty - 10*s, 5*s, 5*s, COLORS.get(kind, DIM), 2*s)
            self.paragraph(message, x + 33*s, ty, width - 51*s, 15, FEED, 2)

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

    def setup(self, game):
        s = self.s
        x, y, w, h = self.dialog("AI Arena" if game.arena_mode else "Match setup",
                                 "Choose the rules and who takes the ice.", 582, 497)
        rows = [("Rules", "Hybrid Adventure" if game.adventure else "Classic", game.toggle_rules)]
        if game.arena_mode:
            rows += [("Coral algorithm", game.ai_teams[0], lambda: game.rotate_ai(0)),
                     ("Azure algorithm", game.ai_teams[1], lambda: game.rotate_ai(1))]
        else:
            rows += [("Players", "Local two player" if game.local else "Human vs AI", game.toggle_local),
                     ("Opponent", "Local player" if game.local else game.opponent, game.rotate_opponent)]
        rows += [("AI difficulty", game.difficulty, game.rotate_difficulty)]
        for index, (caption, value, action) in enumerate(rows):
            ty = y + (127 + index * 58)*s
            self.text(caption, x + 32*s, ty + 26*s, 17, INK, "label")
            disabled = not game.arena_mode and game.local and caption in ("Opponent", "AI difficulty")
            self.button(value, (x + 246*s, ty, w - 277*s, 43*s), action, arrow=True, disabled=disabled)
        ty = y + h - 124*s
        self.button(f"Seed {game.seed_text}|" if game.editing_seed else
                    ("Set board seed" if game.next_seed is None else f"Seed {game.next_seed}"),
                    (x+31*s, ty, w-62*s, 37*s), game.toggle_seed, arrow=True)
        self.button("Back", (x+31*s, y+h-67*s, 112*s, 44*s), game.close_modal)
        self.button("Start match", (x+156*s, y+h-67*s, w-187*s, 44*s), game.launch, primary=True, arrow=True)

    def pause(self, game):
        s = self.s
        if game.modal == "result":
            state = game.state
            title = "Match drawn" if state.winner < 0 else f"{TEAMS[state.winner]} wins"
            tall = 378 if game.arena_mode else 310
            x, y, w, h = self.dialog(title, state.reason, 520, tall)
            for team, score in enumerate(state.scores):
                tx = x + (31 + team * 233)*s
                self.plate(tx, y+126*s, 218*s, 57*s, TEAM[team], strong=state.winner == team)
                self.text(TEAMS[team], tx+16*s, y+162*s, 22, TEAM[team], "label")
                self.text(str(score), tx+199*s, y+164*s, 32, INK, "heavy", TextNode.ARight)
                if game.arena_mode:
                    turns, effort, seconds = game.stats[team]
                    units = "nodes" if game.controllers[team] == "Minimax" else "simulations"
                    self.text(f"{effort:,} {units}", tx+2*s, y+214*s, 15, MUTED)
                    self.text(f"{1000 * seconds / max(1, turns):.0f} ms per decision", tx+2*s, y+240*s, 15, MUTED)
            self.button("Rematch", (x+31*s, y+h-78*s, 218*s, 48*s), game.rematch, primary=True)
            self.button("Main menu", (x+264*s, y+h-78*s, 225*s, 48*s), game.home)
        else:
            x, y, w, h = self.dialog("Match paused", "", 470, 380)
            labels = (("Resume", game.close_modal), ("Restart board", game.rematch),
                      ("Settings", lambda: game.open_modal("settings")), ("Main menu", game.home))
            for index, (title, action) in enumerate(labels):
                self.button(title, (x+30*s, y+(105+index*60)*s, w-60*s, 47*s), action,
                            primary=index == 0, arrow=True)

    def settings(self, game):
        s = self.s
        x, y, w, h = self.dialog("Settings", "Adjust effects and display.", 490, 362)
        items = (("Sound effects", game.sound, game.toggle_sound), ("Motion effects", game.motion, game.toggle_motion),
                 ("Fullscreen", game.fullscreen, game.toggle_fullscreen))
        for index, (name, on, action) in enumerate(items):
            ty = y + (123 + index*57)*s
            self.text(name, x+33*s, ty+25*s, 18, INK, "label")
            self.button("On" if on else "Off", (x+w-131*s, ty, 101*s, 42*s), action, primary=on)
        self.button("Back", (x+31*s, y+h-59*s, w-61*s, 36*s), game.close_modal)

    def help(self, game):
        s = self.s
        x, y, w, h = self.dialog("How to play", "Collect fish and keep a route open.", 615, 530)
        points = (
            ("Slide and score", f"Collect fish as soon as you land. In Adventure, reach {ADVENTURE_GOAL} fish or trap the other team to win."),
            ("Watch Deepfin", "The leopard seal breaches at the marked floe at the end of the round. If your penguin is caught, jump to adjacent safe ice."),
            ("Save a route", "Use R once per team to keep your Defender’s starting floe in play when it slides."),
            ("Keyboard controls", "1 or 2 selects. Arrows or WASD aim. Enter confirms. B deploys available bait, V changes the camera, and P pauses."),
        )
        for index, (title, words) in enumerate(points):
            ty = y + (137 + index*83)*s
            self.text(title, x+31*s, ty, 19, MINT, "label")
            self.paragraph(words, x+31*s, ty+25*s, w-62*s, 16, INK)
        self.button("Back", (x+31*s, y+h-56*s, w-62*s, 34*s), game.close_modal)

    def draw(self, game, width, height):
        self.begin(width, height)
        if game.page == "home":
            self.title_screen(game)
        else:
            self.match(game)
        method = {"setup": self.setup, "help": self.help, "settings": self.settings,
                  "result": self.pause, "pause": self.pause}.get(game.modal)
        if method is not None:
            method(game)

