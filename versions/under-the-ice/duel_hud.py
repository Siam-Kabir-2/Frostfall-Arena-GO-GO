"""Menus, shared dive scores, and projected swim choices."""

from panda3d.core import TextNode

from duel import AIR, AIR_VENTS, GOAL, NAMES, PASS, TEAMS, count_fish
from frostfall.hud3d import HUD, INK, MUTED, NIGHT
from frostfall.stage3d import CORAL, GOLD, MINT, TEAM


MODES = (("Local duel", ("Human", "Human")), ("Play vs Minimax", ("Human", "Minimax")),
         ("Play vs MCTS", ("Human", "MCTS")), ("Watch Minimax vs MCTS", ("Minimax", "MCTS")))


class DuelHUD(HUD):
    def draw(self, game, width, height):
        self.begin(width, height)
        if game.page == "menu":
            self.menu(game)
        else:
            self.game_view(game)
        if game.modal in ("help", "pause", "result"):
            self.show_dialog(game)

    def menu(self, game):
        s, x = self.s, self.margin
        y = max(15*s, self.h*.21)
        w, h = min(self.w-2*x, 434*s), 504*s
        y = min(y, self.h-h-12*s)
        self.ice_panel(x, y, w, h)
        self.text("FROSTFALL", x+25*s, y+35*s, 16, MINT, "label")
        self.text("UNDER THE ICE", x+22*s, y+100*s, 62, INK, "heavy")
        self.paragraph("Two divers. One cave. Bring your catch to the surface.", x+25*s, y+137*s,
                       w-49*s, 17, MUTED, lines=2)
        for index, (caption, players) in enumerate(MODES):
            area = (x+25*s, y+(164+63*index)*s, w-50*s, 49*s)
            self.button(f"{index+1}  {caption}", area, lambda players=players: game.start(players),
                        primary=index==0, arrow=True, size=18)
        self.button("How to play", (x+25*s, y+438*s, 136*s, 38*s), game.help)
        self.button("Exit", (x+w-107*s, y+438*s, 82*s, 38*s), game.userExit)

    def score(self, game, team, x, y, w):
        s, state, color = self.s, game.state, TEAM[team]
        active = team == game.turn_team and not state.over
        self.ice_panel(x,y,w,90*s,panel=False,accent=color)
        if active:
            self.rounded(x+12*s,y+6*s,w-24*s,3*s,color,2*s)
        self.text(TEAMS[team].upper(),x+13*s,y+29*s,15,color,"label")
        self.text(f"{state.scores[team]} / {GOAL}",x+w-14*s,y+42*s,33,INK,"heavy",TextNode.ARight)
        self.text(f"{count_fish(state.cargo[team])} carrying  /  {state.lives[team]} lives",x+13*s,y+53*s,12,INK,"label")
        self.text(game.players[team].upper(),x+13*s,y+74*s,10,MUTED,"label")
        if game.effort[team]:
            units = "nodes" if game.players[team] == "Minimax" else "sims"
            self.text(f"{game.effort[team]} {units}",x+w-13*s,y+74*s,10,MUTED,"label",TextNode.ARight)

    def game_view(self, game):
        s, width, height = self.s,self.w,self.h
        middle = width/2
        top = 19*s
        broad = min(212*s,(width-54*s)/2.45)
        if not self.compact:
            self.text("FROSTFALL",27*s,34*s,12,MINT,"label")
            self.text("UNDER THE ICE",25*s,73*s,38,INK,"heavy")
            self.match_button("Pause",(width-109*s,40*s,81*s,35*s),game.pause,key="P")
        self.score(game,0,middle-43*s-broad,top,broad)
        self.score(game,1,middle+43*s,top,broad)
        self.ice_panel(middle-36*s,top+8*s,72*s,69*s,panel=False)
        self.text("ROUND",middle,top+31*s,11,MUTED,"label",TextNode.ACenter)
        self.text(f"{game.state.round:02}",middle,top+63*s,27,INK,"heavy",TextNode.ACenter)
        self.blocked.append((0,0,width,114*s))

        self.markers(game)
        sx, y = 24*s, height-109*s
        gap, span = 12*s,width-48*s
        threat_w = min(323*s, span*.30)
        info_w = span-threat_w-gap
        right = sx+info_w+gap
        self.ice_panel(sx,y,info_w,91*s,accent=TEAM[game.turn_team])
        self.ice_panel(right,y,threat_w,91*s,accent=CORAL)
        message, body, tone = game.hint()
        self.text(message,sx+17*s,y+28*s,22,tone,"heavy")
        self.paragraph(body,sx+17*s,y+52*s,info_w-34*s,15,INK,lines=2)
        self.text(f"DEEPFIN · {NAMES[game.state.warning].upper()}",right+13*s,y+24*s,13,CORAL,"label")
        when = "Strikes after this move" if game.state.turn else "Strikes after both moves"
        self.text(when,right+13*s,y+46*s,12,MUTED)
        self.text(f"Air  ·  Coral {game.state.air[0]}/{AIR}  ·  Azure {game.state.air[1]}/{AIR}",
                  right+13*s,y+71*s,13,INK,"label")
        self.blocked.append((0,y,width,height-y))

    def markers(self, game):
        s = self.s
        for cell in AIR_VENTS:
            projected = game.project(cell)
            if projected is None:
                continue
            x,y = projected
            title = NAMES[cell].upper()
            if cell in game.available:
                title = f"{game.available.index(cell)+1}  {title}"
            self.text(title,x,y-42*s,13,MINT,"label",TextNode.ACenter)
        for number,cell in enumerate(game.available,1):
            if cell == PASS or cell in AIR_VENTS:
                continue
            point = game.project(cell)
            if point is None:
                continue
            x,y = point
            self.rounded(x-9*s,y+15*s,18*s,17*s,(.014,.08,.12,.95),4*s)
            self.text(number,x,y+28*s,11,MINT,"label",TextNode.ACenter)

    def show_dialog(self, game):
        s=self.s
        if game.modal == "help":
            x,y,w,h = self.dialog("How to dive", "Both teams share the same fish and swim lanes.", 595, 435)
            points = (("Swim or surface", "Click a lit landmark. Tab selects a destination and Enter plays it. Teams take one move at a time."),
                      ("Fish and air", "Catch fish on landing. Return to either vent to bank them and refill air. A dive that runs out of air loses its catch and a life."),
                      ("Watch Deepfin", "The red ring marks where Deepfin strikes after both teams have moved. Reach eight fish or outlast the other diver."))
            for index,(title,body) in enumerate(points):
                row=y+(135+77*index)*s
                self.text(title,x+31*s,row,17,MINT,"label")
                self.paragraph(body,x+31*s,row+24*s,w-62*s,15,INK,lines=2)
            self.button("Back",(x+31*s,y+h-52*s,w-62*s,34*s),game.resume)
            return
        if game.modal == "result":
            title = "Draw" if game.state.winner < 0 else f"{TEAMS[game.state.winner]} wins"
            detail = game.state.reason
            x,y,w,h = self.dialog(title,detail,510,270)
            self.text(f"{game.state.scores[0]} – {game.state.scores[1]} fish banked",x+w/2,y+148*s,21,
                      GOLD,"label",TextNode.ACenter)
            self.button("Rematch",(x+28*s,y+h-72*s,215*s,45*s),game.rematch,primary=True)
            self.button("Modes",(x+257*s,y+h-72*s,225*s,45*s),game.home)
            return
        x,y,w,h = self.dialog("Match paused", "", 455, 316)
        for index, (title, action) in enumerate((("Resume",game.resume),("Restart",game.rematch),("Modes",game.home))):
            self.button(title,(x+29*s,y+(104+62*index)*s,w-58*s,46*s),action,primary=index==0,arrow=True)
