"""Run Frostfall Thin Ice, a real-time two-skater arena."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

from direct.filter.FilterManager import FilterManager
from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from panda3d.core import Filename,OrthographicLens,Point2,Point3,Shader,Texture,loadPrcFileData

from frostfall import materials3d
from frostfall.hud3d import load_fonts
from thin_ai import search,simple
from thin_hud import MODES,ThinHUD
from thin_rules import FPS,IDLE,ROUND_TICKS,State,steer,step
from thin_stage import Stage


SIM_STEP=1/FPS
DIFFICULTY_POLL=14
KEYS=("w","a","s","d","q","space","arrow_up","arrow_left","arrow_down","arrow_right","enter","/")


class ThinIce(ShowBase):
    def __init__(self,window_type="onscreen",seed=0,audio=True):
        super().__init__(windowType=window_type)
        if not self.win or not self.win.isValid():
            raise RuntimeError("Thin Ice could not create a 3D window.")
        self.disableMouse()
        self.setBackgroundColor(.028,.069,.12)
        self.lens=OrthographicLens()
        self.lens.setNearFar(.1,165)
        self.cam.node().setLens(self.lens)
        self.camera.setPos(0,-22.1,17.3)
        self.camera.lookAt(0,.35,0)
        self.filter=FilterManager(self.win,self.cam)
        self.screen=self.filter.renderSceneInto()
        if self.screen is not None:
            texture=self.screen.getTexture()
            texture.setMinfilter(Texture.FTLinear)
            texture.setMagfilter(Texture.FTLinear)
            self.screen.setShader(Shader.make(Shader.SL_GLSL,materials3d.SCREEN_VERTEX,materials3d.EDGE_SMOOTH))
            self.screen.setShaderInput("scene",texture)
        self.stage=Stage(self.render,self.camera)
        self.hud=ThinHUD(self,load_fonts())
        self.executor=ThreadPoolExecutor(max_workers=2,thread_name_prefix="thin-ice")
        self.cancel=Event()
        self.jobs=[None,None]
        self.players=MODES[0][1]
        self.seed=seed
        self.muted=not audio
        self.sounds={}
        if audio:
            folder=Path(__file__).with_name("assets")/"sounds"
            for action in ("fish","crack","dash","sink","fall"):
                path=folder/f"{action}.wav"
                if path.is_file():
                    self.sounds[action]=self.loader.loadSfx(Filename.fromOsSpecific(str(path)))
        self.keys=set()
        self.dash_requests=set()
        self.size=(0,0)
        self.overlay=False
        for key in KEYS:
            self.accept(key,self.press,[key])
            self.accept(key+"-up",self.release,[key])
        for key,action in (("mouse1",self.click),("escape",self.escape),("p",self.pause),
                           ("r",self.rematch),("h",self.toggle_overlay),("m",self.toggle_audio),
                           ("tab",self.next_button)):
            self.accept(key,action)
        for index in range(1,5):
            self.accept(str(index),self.choose,[index-1])
        self.home()
        self.taskMgr.add(self.tick,"Thin Ice game loop")
        self.update(0.)

    def press(self,key):
        if self.page=="match" and self.modal is None and key in ("q","enter") and key not in self.keys:
            self.dash_requests.add(key)
        self.keys.add(key)
        if key=="enter" and (self.page=="menu" or self.modal):
            self.confirm()

    def release(self,key):
        self.keys.discard(key)

    def stop_search(self):
        self.cancel.set()
        for job in self.jobs:
            if job:
                job.cancel()
        self.jobs=[None,None]

    def reset(self):
        self.stop_search()
        self.cancel=Event()
        self.state=State(self.seed)
        self.telemetry=[None,None]
        self.steering=[IDLE,IDLE]
        self.modal=None
        self.accumulated=0.
        self.redraw=0.
        self.popups=[]
        self.labels=[]
        self.dash_requests.clear()
        self.stage.clear()
        self.hud.focus=-1

    def home(self):
        self.reset()
        self.page="menu"

    def start(self,players):
        self.reset()
        self.players=players
        self.keys.clear()
        self.page="match"

    def rematch(self):
        if self.page=="match":
            self.start(self.players)

    def help(self):
        self.modal="help"
        self.redraw=0.

    def resume(self):
        self.modal=None
        self.redraw=0.

    def pause(self):
        if self.page=="match" and self.modal in (None,"pause"):
            self.modal=None if self.modal else "pause"
            self.redraw=0.

    def escape(self):
        if self.modal=="result":
            self.home()
        elif self.modal:
            self.resume()
        elif self.page=="match":
            self.pause()
        else:
            self.userExit()

    def choose(self,index):
        if self.page=="menu" and self.modal is None:
            self.start(MODES[index][1])

    def toggle_overlay(self):
        self.overlay=not self.overlay
        self.redraw=0.

    def toggle_audio(self):
        self.muted=not self.muted

    @property
    def seconds(self):
        return (ROUND_TICKS-self.state.tick)/FPS

    def next_button(self):
        if self.hud.buttons:
            self.hud.focus=(self.hud.focus+1)%len(self.hud.buttons)

    def confirm(self):
        if 0<=self.hud.focus<len(self.hud.buttons):
            self.hud.buttons[self.hud.focus].action()

    def mouse_pixels(self):
        node=self.mouseWatcherNode
        if node and node.hasMouse():
            cursor=node.getMouse()
            return ((1+cursor.x)*self.size[0]*.5,(1-cursor.y)*self.size[1]*.5)
        return (-100.,-100.)

    def click(self):
        self.hud.handle_click(self.mouse_pixels())

    def human(self,side):
        def directional(up,left,down,right):
            return (int(right in self.keys)-int(left in self.keys),int(up in self.keys)-int(down in self.keys))

        if side==1:
            dash="enter" in self.dash_requests
            self.dash_requests.discard("enter")
            return steer(*directional("arrow_up","arrow_left","arrow_down","arrow_right"),
                         dash=dash,brake="/" in self.keys)
        x,y=directional("w","a","s","d")
        if self.players[1]!="Human" and (x,y)==(0,0):
            x,y=directional("arrow_up","arrow_left","arrow_down","arrow_right")
        dash="q" in self.dash_requests
        self.dash_requests.discard("q")
        return steer(x,y,dash=dash,brake="space" in self.keys)

    def controls(self):
        for side,name in enumerate(self.players):
            if name=="Human":
                self.steering[side]=self.human(side)
            else:
                job=self.jobs[side]
                if job and job.done():
                    decision=job.result()
                    self.steering[side]=decision.control
                    self.telemetry[side]=decision
                    self.jobs[side]=None
                if self.telemetry[side] is None:
                    self.steering[side]=simple(self.state,side)
                if self.state.tick%DIFFICULTY_POLL==0 and self.jobs[side] is None:
                    self.jobs[side]=self.executor.submit(search,self.state.clone(),side,name,self.cancel.is_set)
        return self.steering

    def step_game(self):
        events=[]
        step(self.state,self.controls(),events)
        if events:
            self.stage.add_events(events)
            for kind,team,x,y in events:
                if kind in ("fish","fall"):
                    self.popups.append((x,y,team if kind=="fish" else team+2,self.stage.elapsed))
            if not self.muted:
                for key in {kind for kind,*_ in events}:
                    if key in self.sounds:
                        self.sounds[key].play()
            self.redraw=0.
        if self.state.over:
            self.stop_search()
            self.modal="result"
            self.redraw=0.

    def project(self,x,y,height):
        pixel=Point2()
        if self.lens.project(self.cam.getRelativePoint(self.render,Point3(x,y,height)),pixel):
            return ((1+pixel.x)*self.size[0]*.5,(1-pixel.y)*self.size[1]*.5)
        return None

    def update(self,dt):
        width,height=max(1,self.win.getXSize()),max(1,self.win.getYSize())
        if self.size!=(width,height):
            self.size=width,height
            self.pixel2d.setScale(2/width,1,2/height)
            aspect=width/height
            self.lens.setFilmSize(max(19.9,13.25*aspect),max(13.25,19.9/aspect))
            if self.screen is not None:
                self.screen.setShaderInput("viewport_size",float(width),float(height))
            self.redraw=0.
        if self.page=="match" and self.modal is None:
            self.accumulated+=dt
            while self.accumulated>=SIM_STEP and not self.state.over:
                self.step_game()
                self.accumulated-=SIM_STEP
        self.stage.update(self.state,0. if self.modal=="pause" else dt)
        self.redraw-=dt
        if self.redraw<=0:
            self.labels=[]
            self.popups=[popup for popup in self.popups if self.stage.elapsed-popup[-1]<.66]
            for x,y,side,created in self.popups:
                age=self.stage.elapsed-created
                point=self.project(x,y,.53+age*1.4)
                if point:
                    self.labels.append((*point,side,1.-age/.66))
            self.hud.draw(self,width,height)
            self.redraw=.085
        self.hud.focus_buttons(self.mouse_pixels())

    def tick(self,task):
        self.update(min(.055,self.taskMgr.globalClock.getDt()))
        return Task.cont

    def destroy(self):
        if hasattr(self,"executor"):
            self.stop_search()
            self.executor.shutdown(wait=True,cancel_futures=True)
        if hasattr(self,"filter"):
            self.filter.cleanup()
            self.filter.ignoreAll()
        super().destroy()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode",choices=("minimax","mcts","local","watch"))
    parser.add_argument("--seed",type=int,default=0)
    args=parser.parse_args()
    loadPrcFileData("Thin Ice", """
window-title Frostfall - Thin Ice
win-size 1440 900
load-display pandagl
sync-video 1
framebuffer-multisample 1
multisamples 4
textures-power-2 none
notify-level warning
""")
    game=ThinIce(seed=args.seed)
    try:
        if args.mode:
            game.choose(("minimax","mcts","local","watch").index(args.mode))
        game.run()
    finally:
        game.destroy()


if __name__=="__main__":
    main()
