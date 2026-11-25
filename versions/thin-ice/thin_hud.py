"""The match display, player controls, and menu for Thin Ice."""

from math import ceil

from panda3d.core import TextNode

from frostfall.hud3d import Button,HUD
from thin_rules import DASH_COOLDOWN, THIN
from thin_stage import GOLD,MINT,TEAM


INK=(.92,.99,1.,1)
MUTED=(.58,.73,.79,1)
GLASS=(.028,.071,.12,.94)
LINE=(.23,.43,.52,.88)
CORAL,AZURE=TEAM
MODES=(("Play vs Minimax",("Human","Minimax")),("Play vs MCTS",("Human","MCTS")),
       ("Local duel",("Human","Human")),("Watch Minimax vs MCTS",("Minimax","MCTS")))


class ThinHUD(HUD):
    def card(self,bounds,accent=LINE,fill=GLASS):
        x,y,w,h=bounds
        self.rounded(x,y,w,h,accent,12*self.s)
        return self.rounded(x+1,y+1,w-2,h-2,fill,11*self.s)

    def action(self,title,bounds,fn,primary=False):
        x,y,w,h=bounds
        if primary:
            frame=self.card(bounds,MINT,(.27,.78,.71,1))
        else:
            frame=self.card(bounds,LINE,(.073,.14,.19,1))
        self.text(title,x+15*self.s,y+.66*h,17,(.019,.12,.14,1) if primary else INK,"label")
        self.buttons.append(Button(bounds,fn,frame))

    def draw(self,game,width,height):
        self.begin(width,height)
        if game.page=="menu":
            self.menu(game)
        else:
            self.match_hud(game)
        if game.modal:
            self.draw_dialog(game)

    def menu(self,game):
        s=self.s
        w=min(self.w-36*s,392*s)
        h=467*s
        x=28*s
        y=max(14*s,min(self.h*.24,self.h-h-18*s))
        self.card((x,y,w,h))
        self.rounded(x+24*s,y+24*s,34*s,3*s,MINT,2*s)
        self.text("FROSTFALL",x+67*s,y+30*s,13,MINT,"label")
        self.text("THIN ICE",x+22*s,y+109*s,79,INK,"heavy")
        self.paragraph("Race the shoal. Break the ice behind you.",x+24*s,y+138*s,w-48*s,17,MUTED,lines=2)
        for index,(name,players) in enumerate(MODES):
            self.action(f"{index+1}   {name}",(x+24*s,y+(169+57*index)*s,w-48*s,46*s),
                        lambda players=players:game.start(players),index==0)
        self.action("How to play",(x+24*s,y+414*s,133*s,34*s),game.help)
        self.action("Exit",(x+w-100*s,y+414*s,76*s,34*s),game.userExit)

    def badge(self,game,team,x,y,w):
        s=self.s
        color=TEAM[team]
        player=game.state.skaters[team]
        self.card((x,y,w,77*s))
        self.rounded(x+13*s,y+12*s,7*s,7*s,color,3*s)
        self.text(("CORAL","AZURE")[team],x+25*s,y+21*s,15,color,"label")
        self.text(game.players[team].upper(),x+14*s,y+41*s,11,MUTED,"label")
        self.text(player.score,x+w-12*s,y+47*s,38,INK,"heavy",TextNode.ARight)
        self.text("DASH",x+13*s,y+65*s,9,MUTED,"label")
        bar=w-68*s
        self.rounded(x+47*s,y+57*s,bar,6*s,(.15,.28,.34,1),3*s)
        charge=1.-player.cooldown/DASH_COOLDOWN
        if charge>0:
            self.rounded(x+47*s,y+57*s,bar*charge,6*s,color,3*s)

    def match_hud(self,game):
        s=self.s
        w,h=self.w,self.h
        middle=w*.5
        badge_w=min(181*s,(w-100*s)*.32)
        left=middle-54*s-badge_w
        right=middle+54*s
        self.badge(game,0,left,22*s,badge_w)
        self.badge(game,1,right,22*s,badge_w)
        self.card((middle-45*s,16*s,90*s,86*s),MINT if game.seconds>10 else CORAL)
        self.text("TIME",middle,39*s,11,MUTED,"label",TextNode.ACenter)
        self.text(f"0:{ceil(game.seconds):02}",middle,78*s,39,INK if game.seconds>10 else CORAL,"heavy",TextNode.ACenter)
        if not self.compact:
            self.text("FROSTFALL",27*s,35*s,12,MINT,"label")
            self.text("THIN ICE",25*s,73*s,39,INK,"heavy")
            self.text("Dark floes crack on dash",28*s,96*s,11,MUTED)
            self.action("Pause  P",(w-122*s,37*s,94*s,35*s),game.pause)
        for side,decision in enumerate(game.telemetry):
            if game.overlay and decision is not None:
                x=left if side==0 else right
                self.card((x,108*s,badge_w,62*s))
                self.text(decision.action,x+10*s,132*s,13,INK,"label")
                units="nodes" if game.players[side]=="Minimax" else "rollouts"
                self.text(f"{decision.effort} {units}",x+10*s,154*s,11,MUTED)
        y=h-62*s
        row_width=min(w-40*s,940*s)
        sx=(w-row_width)/2
        self.card((sx,y,row_width,43*s))
        if game.players==("Human","Human"):
            guide="CORAL  WASD · Q dash · Space brake     /     AZURE  Arrows · Enter dash · Slash brake"
        elif game.players[0]=="Human":
            guide="WASD or arrows  ·  Q dash  ·  Space brake  ·  H AI decisions"
        else:
            guide="AI duel  ·  H shows decisions  ·  P pauses  ·  R rematch"
        self.text(guide,middle,y+26*s,13,INK,"label",TextNode.ACenter)
        breaking=any(game.state.ice[cell]>game.state.tick for cell in THIN)
        if breaking:
            self.text("THIN ICE BREAKING",middle,y-11*s,17,CORAL,"label",TextNode.ACenter)
        for x,y,side,life in game.labels:
            self.text("+1" if side<2 else "SPLASH",x,y,23*(.80+life*.20),GOLD if side<2 else CORAL,
                      "heavy",TextNode.ACenter)

    def draw_dialog(self,game):
        s=self.s
        self.buttons.clear()
        self.rounded(0,0,self.w,self.h,(.01,.04,.075,.79),1)
        w=min(self.w-28*s,523*s)
        h=(321 if game.modal=="help" else 253)*s
        x,y=(self.w-w)/2,(self.h-h)/2
        self.card((x,y,w,h),MINT)
        if game.modal=="help":
            title="How to skate"
            detail="Steer with WASD, press Q to dash, and hold Space to brake. Skating over golden fish scores a point. Dash from thin ice and it cracks before sinking. Falling costs a point, then you return to solid ice. The higher score after 45 seconds wins."
            self.text(title,x+24*s,y+58*s,44,INK,"heavy")
            self.paragraph(detail,x+24*s,y+98*s,w-48*s,18,MUTED,lines=6)
            self.action("Back",(x+24*s,y+h-65*s,w-48*s,43*s),game.resume,True)
            return
        if game.modal=="result":
            a,b=(p.score for p in game.state.skaters)
            title="Draw" if a==b else ("Coral wins" if a>b else "Azure wins")
            detail=f"{a}  –  {b} fish"
            first=("Rematch",game.rematch)
        else:
            title,detail,first="Paused","The ice is holding.",("Resume",game.resume)
        self.text(title,x+24*s,y+64*s,49,INK,"heavy")
        self.text(detail,x+27*s,y+111*s,20,MUTED)
        bw=(w-60*s)/2
        self.action(first[0],(x+24*s,y+h-70*s,bw,46*s),first[1],True)
        self.action("Modes",(x+36*s+bw,y+h-70*s,bw,46*s),game.home)
