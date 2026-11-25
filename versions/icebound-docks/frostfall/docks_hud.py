"""Frostfall's match HUD with paired orders and the dock network."""

from panda3d.core import Point2, TextNode

from .docks import DOCKS, DOCK_NAMES, LINKS, ROUND_LIMIT, open_routes
from .hud3d import HUD, INK, MUTED
from .rules import TEAMS
from .stage3d import GOLD, MINT, TEAM, VIOLET, center


class DocksHUD(HUD):
    def title_screen(self, game):
        s = self.s
        x = 31*s
        w, h = min(self.w-2*x, 420*s), 388*s
        y = self.h-h-24*s if self.compact else (self.h-h)*.47
        if not self.compact:
            self.fade_left(125*s, 470*s)
        self.ice_panel(x, y, w, h)
        self.wordmark("ICEBOUND DOCKS", x+24*s, y+65*s, min(50, (w/s-48)/8.9), INK)
        self.paragraph("Hold two connected docks through your rival's reply.", x+24*s, y+94*s,
                       w-48*s, 16, MUTED, lines=2)
        modes = (("Play vs Minimax", ("Human", "Minimax")), ("Play vs MCTS", ("Human", "MCTS")),
                 ("Local duel", ("Human", "Human")), ("Watch Minimax vs MCTS", ("Minimax", "MCTS")))
        for index, (title, players) in enumerate(modes):
            self.button(title, (x+24*s, y+(128+52*index)*s, w-48*s, 43*s),
                        lambda players=players: game.start_match(players), primary=index == 0, arrow=True)
        self.button("How to play", (x+24*s, y+340*s, 115*s, 32*s), lambda: game.open_modal("help"))
        self.button("Settings", (x+w-197*s, y+340*s, 92*s, 32*s), lambda: game.open_modal("settings"))
        self.button("Exit", (x+w-95*s, y+340*s, 71*s, 32*s), game.userExit)

    def score(self, game, team, x, y, w):
        s, color = self.s, TEAM[team]
        state = game.board_state()
        live = game.team == team and not game.state.over and game.delay <= 0
        side = x+12*s if team == 0 else x+w-12*s
        align = TextNode.ALeft if team == 0 else TextNode.ARight
        self.text(TEAMS[team].upper(), side, y+20*s, 14, color, "heavy", align)
        self.text(f"{state.owners.count(team)} DOCKS  ·  {state.scores[team]} FISH", side, y+39*s,
                  12, INK, "label", align)
        self.text(game.controllers[team].upper(), side, y+54*s, 9, MUTED, "label", align)
        if live:
            self.rounded(x+12*s, y+2*s, w-24*s, 2*s, color, s)

    def board_labels(self, game):
        super().board_labels(game)
        state = game.board_state()
        s = self.s
        for dock, cells in enumerate(DOCKS):
            owner = state.owners[dock]
            color = GOLD if owner < 0 else TEAM[owner]
            point = sum((center(cell, .56) for cell in cells[1:]), center(cells[0], .56)) / len(cells)
            spot = Point2()
            if not game.lens.project(game.cam.getRelativePoint(game.render, point), spot):
                continue
            x, y = (1+spot.x)*self.w/2, (1-spot.y)*self.h/2
            if (163 if self.compact else 99)*s < y < self.h-142*s:
                self.ice_panel(x-37*s, y-22*s, 74*s, 21*s, panel=False, accent=color)
                self.text(DOCK_NAMES[dock].upper(), x, y-7*s, 10, color, "heavy", TextNode.ACenter)

    def action_dock(self, game):
        s = self.s
        width = min(self.w-30*s, 1210*s)
        x, y, h = (self.w-width)/2, self.h-119*s, 101*s
        gap = 9*s
        crew, controls = width*.32, width*.30
        middle = width-crew-controls-2*gap
        mx, rx = x+crew+gap, x+crew+gap+middle+gap
        state = game.board_state()
        title, detail, color = game.move_hint()
        self.ice_panel(x, y, crew, h, accent=TEAM[game.team])
        self.ice_panel(mx, y, middle, h, accent=color)
        self.ice_panel(rx, y, controls, h, accent=MINT)
        self.blocked.extend(((x, y, crew, h), (mx, y, middle, h), (rx, y, controls, h)))
        for index, (name, action) in enumerate((('Defender', game.defender_order), ('Attacker', game.attacker_order))):
            selected = game.actionable and game.phase == name.lower()
            ty = y+(35+35*index)*s
            self.symbol("shield" if index == 0 else "attack", x+17*s, ty-5*s, 15,
                        VIOLET if index == 0 else MINT)
            self.text(name.upper(), x+30*s, ty, 11, INK if selected else MUTED, "heavy")
            summary = game.order_summary(name, action)
            self.text(summary, x+crew-13*s, ty, 11, INK, "label", TextNode.ARight)
        self.text(title, mx+11*s, y+27*s, 16, color, "heavy")
        self.paragraph(detail, mx+11*s, y+49*s, middle-22*s, 13, INK, lines=3)

        if state.pending >= 0:
            status = f"{TEAMS[state.pending]} must hold through this reply"
        else:
            status = "   ".join(f"{DOCK_NAMES[a][0]}–{DOCK_NAMES[b][0]} {len(open_routes(state, paths))}/2"
                                for a, b, paths in LINKS)
        self.text(status, rx+controls/2, y+20*s, 10, GOLD if state.pending >= 0 else MINT,
                  "label", TextNode.ACenter)
        button_w = (controls-25*s)/2
        self.match_button("Brace", (rx+8*s, y+27*s, button_w, 25*s), game.toggle_brace, key="R",
                          active=game.brace, disabled=not game.can_brace())
        self.match_button("Undo", (rx+17*s+button_w, y+27*s, button_w, 25*s), game.undo_order,
                          disabled=not game.can_undo)
        if game.actionable and game.phase == "ready":
            self.match_button("Confirm turn", (rx+8*s, y+60*s, controls-16*s, 29*s),
                              game.commit, key="Enter", active=True)
        else:
            caption = "Routes open per link" if state.pending < 0 else "Take a dock or break the link"
            self.paragraph(caption, rx+controls/2, y+73*s, controls-16*s, 11, MUTED, lines=2,
                           align=TextNode.ACenter)

    def help(self, game):
        s = self.s
        x, y, w, h = self.dialog("How to play", "Capture two docks and keep their ice link intact.", 584, 490)
        points = (
            ("Plan a paired turn", "Pick a Defender slide, then an Attacker slide. Confirm to play both. A trapped penguin skips its move."),
            ("Take a dock", "Only the Attacker raises flags. Either Harbor entrance claims the same dock. Flags stay until a rival Attacker lands."),
            ("Keep a link open", "The thin lines on the ice show the routes. A normal slide sinks its starting floe. Dock platforms stay, and R lets each Defender brace once."),
            ("Survive the reply", f"Hold two connected docks after your rival's full turn to win. Fish collected on landing decide otherwise if all links break, both sides are trapped, or {ROUND_LIMIT} rounds end."),
        )
        for index, (title, detail) in enumerate(points):
            line = y+(128+73*index)*s
            self.text(title, x+30*s, line, 17, MINT, "heavy")
            self.paragraph(detail, x+30*s, line+21*s, w-60*s, 14, INK, lines=3)
        self.button("Back", (x+30*s, y+h-54*s, w-60*s, 36*s), game.close_modal)
