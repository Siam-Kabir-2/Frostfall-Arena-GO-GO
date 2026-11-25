"""Menus, course telemetry, results and replay controls."""

from math import sin

from panda3d.core import TextNode

from frostfall.hud3d import HUD
from whiteout_rules import FORKS, HZ, LENGTH, SECTIONS, clamp, section
from whiteout_stage import CORAL, CYAN, GOLD, PALETTE

INK = (.94, .988, 1., 1)
MUTED = (.67, .80, .86, 1)
EDGE = (.20, .37, .47, .96)
GLASS = (.026, .088, .132, .95)
TRACK = (.095, .23, .30, 1)
CENTER, RIGHT = TextNode.ACenter, TextNode.ARight


def timestamp(ticks):
    seconds = ticks / HZ
    return f"{int(seconds // 60):02d}:{seconds % 60:05.2f}"


class WhiteoutHUD(HUD):
    def panel(self, x, y, w, h, accent=CYAN):
        s = self.s
        self.shape(x+2*s, y+4*s, w, h, (.022, .068, .096, .35), 8*s)
        self.card(x, y, w, h, EDGE, GLASS, 8*s)
        self.shape(x+10*s, y, min(w*.4, 39*s), 2*s, accent)

    def title(self, game):
        s = self.s
        self.fade_left(220*s, 778*s)
        x = 68*s
        y = self.h * .16
        self.shape(x, y-12*s, 26*s, 2*s, CYAN)
        self.text("F R O S T F A L L", x+37*s, y-6*s, 21, CYAN, "label")
        self.text("WHITEOUT", x-6*s, y+99*s, 136, INK, "heavy")
        self.text("A downhill penguin race", x, y+133*s, 24, MUTED)
        self.button("Quick race", (x, y+170*s, 356*s, 62*s), lambda: game.start("quick"), primary=True, arrow=True, size=25)
        self.text("1   /   8 RACERS", x+218*s, y+209*s, 13, (.04, .18, .23, 1), "label")
        self.button("AI showdown", (x, y+245*s, 356*s, 55*s), lambda: game.start("ai"), arrow=True, size=22)
        self.text("2   /   WATCH", x+218*s, y+279*s, 13, CYAN, "label")
        self.button("Rival duel", (x, y+311*s, 356*s, 55*s), lambda: game.start("duel"), arrow=True, size=22)
        self.text("3   /   VS MCTS", x+218*s, y+345*s, 13, CYAN, "label")
        self.text("STEER  A D   /   BOOST  SPACE   /   BRAKE  S", x, self.h-49*s, 14, INK, "label")

    def live(self, game):
        race = game.race
        index = game.focus
        racer = race.racers[index]
        x, y, s = self.margin, self.margin, self.s
        mode = "REPLAY" if game.state == "replay" else "AI SHOWDOWN" if game.mode == "ai" else "RIVAL DUEL" if game.mode == "duel" else "QUICK RACE"
        rank = race.order().index(index)+1
        self.panel(x, y, 215*s, 125*s, PALETTE[index])
        self.text(mode, x+15*s, y+26*s, 15, PALETTE[index], "label")
        self.text(f"P{rank:02d}", x+13*s, y+84*s, 63, INK, "heavy")
        self.text(f"/ {len(race.racers):02d}", x+137*s, y+78*s, 22, MUTED, "label")
        self.text(racer.name.upper(), x+16*s, y+108*s, 15, MUTED, "label")
        right = self.w-x
        self.panel(right-193*s, y, 193*s, 125*s, CORAL)
        gap = racer.s-race.danger
        danger = CORAL if gap < 48 and racer.active else INK
        self.text("AVALANCHE GAP", right-177*s, y+26*s, 15, CORAL, "label")
        label = f"{max(0, int(gap))} m" if racer.active else "SAFE" if racer.finished else "OUT"
        self.text(label, right-178*s, y+78*s, 50, danger, "heavy")
        self.text(timestamp(race.tick), right-16*s, y+108*s, 17, MUTED, "label", RIGHT)
        plot_width = min(465*s, self.w-2*(x+225*s))
        if plot_width >= 175*s:
            self.course(race, racer, index, (self.w-plot_width)*.5, y, plot_width)
        else:
            self.text(section(racer.s).upper(), self.w/2, y+150*s, 15, CYAN, "label", CENTER)
        if game.insight and game.mode != "quick":
            self.decisions(game, right-259*s, y+142*s)
        self.bottom(game, racer, right, x)
        status = self.event_text(game, racer)
        if status:
            self.text(status, self.w/2, self.h*.35, 26, INK, "heavy", CENTER).node().setShadow(.07, .087)
        if game.countdown > 0:
            self.text(str(max(1, int(game.countdown+.9999))), self.w/2, self.h*.50, 122, INK, "heavy", CENTER).node().setShadow(.058, .067)
        elif race.tick < 47 and game.state == "race":
            self.text("GO!", self.w/2, self.h*.50, 99, CYAN, "heavy", CENTER).node().setShadow(.058, .067)

    def course(self, race, racer, index, x, y, w):
        s = self.s
        self.panel(x, y, w, 65*s)
        self.text(section(racer.s).upper(), x+13*s, y+23*s, 15, INK, "label")
        self.text(f"{int(clamp(racer.s/LENGTH)*100):02d}%", x+w-13*s, y+23*s, 15, MUTED, "label", RIGHT)
        left, length = x+14*s, w-28*s
        bar = y+44*s
        self.shape(left, bar, length, 3*s, TRACK)
        self.shape(left, bar, max(s, length*clamp(racer.s/LENGTH)), 3*s, CYAN)
        for start, _ in SECTIONS[1:]:
            self.shape(left+length*start/LENGTH, bar-3*s, s, 9*s, MUTED)
        self.shape(left+length*clamp(race.danger/LENGTH), bar-5*s, 2*s, 13*s, CORAL)
        for i, competitor in enumerate(race.racers):
            if not competitor.eliminated and i != index:
                self.rounded(left+length*clamp(competitor.s/LENGTH)-2*s, bar-1*s, 4*s, 5*s, PALETTE[i], 2*s)
        self.rounded(left+length*clamp(racer.s/LENGTH)-4*s, bar-3*s, 8*s, 9*s, INK, 4*s)

    def decisions(self, game, x, y):
        s = self.s
        self.panel(x, y, 259*s, (33+66*len(game.decisions))*s, GOLD)
        self.text("AI TELEMETRY", x+14*s, y+23*s, 15, GOLD, "label")
        for row, (index, decision) in enumerate(sorted(game.decisions.items())):
            name = game.race.racers[index].name
            baseline = y+(49+row*65)*s
            self.text(name.upper(), x+14*s, baseline, 14, PALETTE[index], "label")
            if decision:
                self.text(decision.plan.label, x+14*s, baseline+19*s, 16, INK)
                work = "nodes" if index == 0 and game.mode == "ai" else "rollouts"
                self.text(f"{decision.work} {work}  /  depth {decision.depth}  /  {decision.seconds*1000:.0f} ms",
                          x+14*s, baseline+37*s, 12, MUTED, "label")
            else:
                self.text("Waiting for first search", x+14*s, baseline+23*s, 14, MUTED)

    def bottom(self, game, racer, right, left):
        s = self.s
        y = self.h-self.margin-106*s
        self.panel(left, y, 231*s, 106*s)
        self.text(f"{racer.speed*3.6:03.0f}", left+13*s, y+62*s, 62, INK, "heavy")
        self.text("KM/H", left+130*s, y+56*s, 17, MUTED, "label")
        self.text("DRAFTING  + SPEED" if racer.draft else ("SPACE  BOOST" if game.has_player else "TAB  SWITCH CAMERA"),
                  left+16*s, y+88*s, 14, CYAN if racer.draft else MUTED, "label")
        x = right-231*s
        self.panel(x, y, 231*s, 106*s, GOLD)
        self.text("BOOST RESERVE", x+15*s, y+28*s, 16, GOLD, "label")
        self.text(f"{int(racer.energy*100)}%", right-15*s, y+28*s, 16, INK, "label", RIGHT)
        for bar in range(12):
            self.shape(x+(15+bar*17)*s, y+42*s, 13*s, 17*s, TRACK, 1.5*s)
            amount = clamp(racer.energy*12-bar)
            if amount > .001:
                self.shape(x+(15+bar*17)*s, y+42*s, 13*s*amount, 17*s, GOLD, 1.5*s)
        self.text("BOOSTING" if racer.boosting else "PACKED SNOW  + CHARGE" if racer.draft else "P  PAUSE",
                  x+15*s, y+88*s, 14, INK if racer.boosting else MUTED, "label")
        if game.mode != "quick" and self.w > 680*s:
            self.text("H  AI TELEMETRY   /   TAB  CAMERA", self.w*.5, self.h-self.margin+4*s, 13, INK, "label", CENTER)
        if game.state == "replay":
            self.text("V  BACK TO RESULTS", self.w*.5, self.h-self.margin-21*s, 14, GOLD, "label", CENTER)
        if racer.recovery == 0 and racer.active and racer.route == -1 and racer.next_fork < len(FORKS):
            fork = FORKS[racer.next_fork]
            if 0 < fork.start-racer.s < 86 and self.w > 680*s:
                tint = (GOLD, CYAN, CORAL)[racer.next_fork]
                direction = "RIGHT" if fork.side > 0 else "LEFT"
                self.text(f"{fork.name.upper()}  /  KEEP {direction}", self.w*.5, y-11*s, 19, tint, "label", CENTER).node().setShadow(.075, .086)
                if fork.shutter:
                    remaining = fork.deadline-game.race.time
                    shutter = f"SHUTTER CLOSES IN {remaining:.1f}s" if remaining > 0 else "SHUTTER CLOSED  /  STAY ON MAIN COURSE"
                    self.text(shutter, self.w*.5, y+12*s, 13, INK, "label", CENTER).node().setShadow(.07, .07)
        if racer.active and 0 < racer.s-game.race.danger < 44:
            self.shape(0, 0, self.w, (2.7+1.5*sin(game.race.time*10))*s, CORAL)

    def event_text(self, game, racer):
        if racer.eliminated:
            return racer.eliminated.upper()
        if racer.finished:
            return f"FINISHED  /  {timestamp(racer.finished)}"
        if game.race.tick-racer.event_tick < (140 if racer.recovery else 79):
            return racer.event.upper()
        return ""

    def pause(self, game):
        s = self.s
        x, y = self.w*.5-158*s, self.h*.5-113*s
        self.shape(0, 0, self.w, self.h, (.023, .075, .10, .52))
        self.panel(x, y, 316*s, 226*s)
        self.text("PAUSED", self.w*.5, y+64*s, 64, INK, "heavy", CENTER)
        self.button("Resume", (x+24*s, y+88*s, 268*s, 48*s), game.toggle_pause, primary=True)
        self.button("Main menu", (x+24*s, y+148*s, 268*s, 48*s), game.to_menu)

    def results(self, game):
        s = self.s
        race = game.final_race
        order = race.order()
        winner = race.racers[order[0]]
        w = 574*s
        h = (270+len(order)*37)*s
        x, y = self.w*.5-w*.5, self.h*.50-h*.50
        self.shape(0, 0, self.w, self.h, (.023, .075, .10, .42))
        self.panel(x, y, w, h, PALETTE[order[0]])
        self.text("RACE RESULTS", x+26*s, y+36*s, 16, CYAN, "label")
        summary = f"{winner.name.upper()} WINS" if winner.finished else "AVALANCHE WINS"
        self.text(summary, x+23*s, y+106*s, 62, INK, "heavy")
        self.text("RACER", x+68*s, y+147*s, 14, MUTED, "label")
        self.text("RESULT", x+w-27*s, y+147*s, 14, MUTED, "label", RIGHT)
        for rank, index in enumerate(order):
            racer = race.racers[index]
            row = y+(153+rank*37)*s
            self.shape(x+22*s, row, w-44*s, 33*s, (.075, .191, .25, 1) if rank % 2 == 0 else (.047, .132, .179, 1), 3*s)
            self.text(f"{rank+1:02d}", x+35*s, row+22*s, 18, PALETTE[index], "label")
            self.text(racer.name, x+68*s, row+22*s, 18, INK)
            result = timestamp(racer.finished) if racer.finished else f"{racer.eliminated}  /  {int(racer.s)} m"
            self.text(result, x+w-35*s, row+22*s, 17 if racer.finished else 14, MUTED, align=RIGHT)
        base = y+h-81*s
        self.button("R  Rematch", (x+22*s, base, 161*s, 47*s), game.rematch, primary=True, size=17)
        self.button("V  Replay", (x+195*s, base, 183*s, 47*s), game.toggle_replay, size=17)
        self.button("Menu", (x+390*s, base, 161*s, 47*s), game.to_menu, size=17)

    def draw(self, game):
        self.begin(game.win.getXSize(), game.win.getYSize())
        if game.state == "menu":
            self.title(game)
        elif game.state == "results":
            self.results(game)
        else:
            self.live(game)
            if game.paused:
                self.pause(game)
