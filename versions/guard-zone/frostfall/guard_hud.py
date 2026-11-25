"""The turn controls and guard legend for the 3D fork."""

from panda3d.core import TextNode

from .guard import FISH_GOAL, ROUND_LIMIT
from .hud3d import HUD, INK, MUTED
from .rules import TEAMS, label
from .stage3d import GOLD, MINT, TEAM, VIOLET


class GuardHUD(HUD):
    def title_screen(self, game):
        s = self.s
        x = 31*s
        w, h = min(self.w-2*x, 420*s), 388*s
        y = self.h-h-24*s if self.compact else (self.h-h)*.47
        if not self.compact:
            self.fade_left(125*s, 470*s)
        self.ice_panel(x, y, w, h)
        self.wordmark("GUARD ZONE", x+24*s, y+65*s, 57, INK)
        self.paragraph("Guard the ice. Send your Attacker to fish.", x+24*s, y+94*s, w-48*s, 16, MUTED, lines=2)
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
        side = x+12*s if team == 0 else x+w-12*s
        align = TextNode.ALeft if team == 0 else TextNode.ARight
        self.text(TEAMS[team].upper(), side, y+20*s, 14, color, "heavy", align)
        self.text(f"{game.board_state().scores[team]} / {FISH_GOAL} FISH", side, y+39*s, 14, INK, "label", align)
        self.text(game.controllers[team].upper(), side, y+54*s, 9, MUTED, "label", align)
        if team == game.team and game.animation_board is None and not game.state.over:
            self.rounded(x+12*s, y+2*s, w-24*s, 2*s, color, s)

    def action_dock(self, game):
        s = self.s
        width = min(self.w-30*s, 1210*s)
        x, y, h = (self.w-width)/2, self.h-119*s, 101*s
        gap = 9*s
        crew, controls = width*.29, width*.28
        mid = width-crew-controls-2*gap
        mx, rx = x+crew+gap, x+crew+gap+mid+gap
        title, detail, color = game.move_hint()
        for px, span, accent in ((x, crew, TEAM[game.team]), (mx, mid, color), (rx, controls, GOLD)):
            self.ice_panel(px, y, span, h, accent=accent)
            self.blocked.append((px, y, span, h))
        for row, (phase, name, symbol, tint) in enumerate((('defender', 'Defender', 'shield', VIOLET),
                                                          ('attacker', 'Attacker', 'attack', MINT))):
            line = y+(37+33*row)*s
            self.symbol(symbol, x+17*s, line-4*s, 14, tint)
            self.text(name.upper(), x+28*s, line, 11, INK if game.phase == phase else MUTED, "heavy")
            summary = "Waiting"
            if game.actionable and game.phase == phase:
                summary = "Choose ice"
            elif phase == 'defender' and game.actionable and game.phase in ('attacker', 'blocked'):
                summary = f"To {label(game.defender_order.target)}" if game.defender_order else "Holding"
            elif phase == 'attacker' and game.phase == 'blocked':
                summary = "No landing"
            self.text(summary, x+crew-10*s, line, 11, INK, "label", TextNode.ARight)
        self.text(title, mx+11*s, y+27*s, 16, color, "heavy")
        self.paragraph(detail, mx+11*s, y+49*s, mid-22*s, 13, INK, lines=3)

        self.symbol("shield", rx+15*s, y+18*s, 13, GOLD)
        self.text("TWO COLORS = CONTESTED", rx+27*s, y+22*s, 10, GOLD, "label")
        bw = (controls-25*s)/2
        self.match_button("Hold", (rx+8*s, y+42*s, bw, 31*s), game.hold, key="H",
                          disabled=not game.actionable or game.phase != "defender")
        self.match_button("Undo", (rx+17*s+bw, y+42*s, bw, 31*s), game.undo_order, disabled=not game.can_undo)
        if game.actionable and game.phase == "blocked":
            self.match_button("Finish turn", (rx+8*s, y+71*s, controls-16*s, 26*s),
                              game.commit, key="Enter", active=True)

    def help(self, game):
        s = self.s
        x, y, w, h = self.dialog("How to play", "Guard Zone on the original 8×8 arena.", 584, 482)
        points = (
            ("Step, then slide", "Move your Defender one tile in any direction, or press H to hold. Then choose an Attacker slide to play the turn."),
            ("Guard and contest", "Enemy penguins can cross a guarded tile. They can land in overlapping guards or outside enemy guards. Two colors mark an overlap."),
            ("Fish crack the ice", "Only the Attacker collects fish on landing. The cracked floe sinks on departure. The Defender steps without collecting or cracking ice."),
            ("Win the match", f"Reach {FISH_GOAL} fish or physically trap both rivals. Guards alone can't win by trapping. The higher fish count wins when the board runs out of fish or after {ROUND_LIMIT} rounds."),
        )
        for index, (title, detail) in enumerate(points):
            line = y+(125+71*index)*s
            self.text(title, x+30*s, line, 17, MINT, "heavy")
            self.paragraph(detail, x+30*s, line+21*s, w-60*s, 14, INK, lines=3)
        self.button("Back", (x+31*s, y+h-51*s, w-62*s, 34*s), game.close_modal)
