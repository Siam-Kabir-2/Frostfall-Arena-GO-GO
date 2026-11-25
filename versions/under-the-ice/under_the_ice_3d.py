"""Launch the shared-cave Frostfall duel in Panda3D."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from math import hypot
from threading import Event

from direct.filter.FilterManager import FilterManager
from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from panda3d.core import OrthographicLens, Point2, Shader, Texture, loadPrcFileData

from duel import AIR, AIR_VENTS, FISH, NAMES, PASS, TEAMS, TO_AIR, State, advance, choices, count_fish
from duel_ai import search
from duel_hud import MODES, DuelHUD
from duel_stage import Stage, spot
from frostfall import materials3d
from frostfall.hud3d import MUTED, load_fonts
from frostfall.stage3d import CORAL, GOLD, MINT, TEAM


class UnderIce3D(ShowBase):
    def __init__(self, window_type="onscreen", seed=0):
        super().__init__(windowType=window_type)
        if not self.win or not self.win.isValid():
            raise RuntimeError("The 3D dive window could not open.")
        self.disableMouse()
        self.setBackgroundColor(.03,.085,.13)
        self.lens = OrthographicLens()
        self.lens.setNearFar(.1,130)
        self.cam.node().setLens(self.lens)
        self.camera.setPos(0,-49,9.4)
        self.camera.lookAt(0,0,-.82)
        self.filter = FilterManager(self.win,self.cam)
        self.screen_shader = self.filter.renderSceneInto()
        if self.screen_shader is not None:
            scene = self.screen_shader.getTexture()
            scene.setMinfilter(Texture.FTLinear)
            scene.setMagfilter(Texture.FTLinear)
            self.screen_shader.setShader(Shader.make(Shader.SL_GLSL,materials3d.SCREEN_VERTEX,materials3d.EDGE_SMOOTH))
            self.screen_shader.setShaderInput("scene",scene)
        self.hud = DuelHUD(self,load_fonts())
        self.stage = Stage(self.render,self.camera)
        self.pool = ThreadPoolExecutor(max_workers=1,thread_name_prefix="dive-search")
        self.cancel = Event()
        self.future = None
        self.seed = seed
        self.players = ("Human","Human")
        self.size = (0,0)
        self.hud_key = None
        self.home()
        for key,action in (("mouse1",self.click),("escape",self.escape),("p",self.pause),("r",self.rematch),
                           ("tab",self.cycle),("enter",self.confirm),("space",self.confirm)):
            self.accept(key,action)
        for value in range(1,10):
            self.accept(str(value),self.number,[value])
        self.taskMgr.add(self.tick,"Shared dive frame")
        self.update(0)

    def stop_search(self):
        self.cancel.set()
        if self.future:
            self.future.cancel()
        self.future = None

    def reset(self):
        self.stop_search()
        self.state = State(self.seed)
        self.effort = [0,0]
        self.modal = None
        self.delay = 0.
        self.message = ""
        self.hover = self.selected = None
        self.hud.focus = -1
        self.hud_key = None
        self.stage.reset()

    def home(self):
        self.reset()
        self.page = "menu"

    def start(self, players):
        self.reset()
        self.page = "match"
        self.players = players
        self.delay = .18

    def rematch(self):
        if self.page == "match":
            self.start(self.players)

    def help(self):
        self.modal = "help"

    def pause(self):
        if self.page == "match" and self.modal in (None,"pause"):
            self.modal = None if self.modal else "pause"

    def resume(self):
        self.modal = None

    def escape(self):
        if self.modal == "result":
            self.home()
        elif self.modal:
            self.resume()
        elif self.page == "match":
            self.pause()
        else:
            self.userExit()

    @property
    def available(self):
        if self.page != "match" or self.modal or self.delay > 0 or self.players[self.state.active] != "Human":
            return ()
        return choices(self.state)

    @property
    def turn_team(self):
        if self.stage.playback:
            return self.stage.playback[0].active
        return self.state.active

    def number(self, value):
        if self.page == "menu" and self.modal is None and value <= len(MODES):
            self.start(MODES[value-1][1])
        elif value <= len(self.available):
            self.apply(self.available[value-1])

    def cycle(self):
        available = self.available
        if available:
            index = available.index(self.selected)+1 if self.selected in available else 0
            self.selected = available[index % len(available)]
        elif self.hud.buttons:
            self.hud.focus = (self.hud.focus+1) % len(self.hud.buttons)

    def confirm(self):
        if self.hud.focus in range(len(self.hud.buttons)):
            self.hud.buttons[self.hud.focus].action()
        elif self.selected in self.available:
            self.apply(self.selected)
        elif self.hover in self.available:
            self.apply(self.hover)

    def mouse_pixels(self):
        node = self.mouseWatcherNode
        if node and node.hasMouse():
            value=node.getMouse()
            return ((1+value.x)*self.size[0]*.5,(1-value.y)*self.size[1]*.5)
        return (-100.,-100.)

    def project(self,cell):
        point = Point2()
        if self.lens.project(self.cam.getRelativePoint(self.render,spot(cell,-.53)),point):
            return ((1+point.x)*self.size[0]*.5,(1-point.y)*self.size[1]*.5)
        return None

    def at(self,point):
        available = self.available
        if not available or self.hud.contains(point):
            return None
        best, distance = None, 33*self.hud.s
        for cell in available:
            location = self.project(cell) if cell != PASS else None
            if location:
                near = hypot(location[0]-point[0],location[1]-point[1])
                if near < distance:
                    best,distance=cell,near
        return best

    def click(self):
        mouse = self.mouse_pixels()
        if not self.hud.handle_click(mouse):
            cell = self.at(mouse)
            if cell is not None:
                self.apply(cell)

    def apply(self, action):
        before = self.state
        self.state, events = advance(before,action)
        self.message = ". ".join(events) if events else (
            f"{TEAMS[before.active]} moved to {NAMES[action]}" if action != PASS else f"{TEAMS[before.active]} waits")
        self.delay = self.stage.duration+.05
        self.stage.play(before,action,self.state)
        self.hover = self.selected = None

    def hint(self):
        team = self.state.active
        if self.delay > 0 and self.message:
            return f"{TEAMS[self.turn_team]} moves",self.message,TEAM[self.turn_team]
        if self.state.over:
            return "Match complete",self.state.reason,GOLD
        if self.players[team] != "Human":
            return f"{self.players[team]} is thinking",f"{TEAMS[team]} is choosing a swim lane.",MUTED
        if self.hover in self.available and self.hover != PASS:
            option = self.hover
            if option in AIR_VENTS:
                haul = count_fish(self.state.cargo[team])
                detail = f"Bank {haul} fish and refill air." if haul else "Refill air at the surface."
                return NAMES[option],detail,MINT
            fish = FISH[option] if self.state.fish & (1<<option) else 0
            room = self.state.air[team]-1
            if option == self.state.warning:
                detail = "Deepfin strikes here this round."
            elif room < TO_AIR[option]:
                detail = "There may not be enough air to get back to a vent."
            else:
                detail = f"{room} air left after the swim."
            name = NAMES[option]+(f"  +{fish} fish" if fish else "")
            return name,detail,CORAL if option==self.state.warning or room<TO_AIR[option] else MINT
        return f"{TEAMS[team]} to dive","Click a lit destination or press its number. Bank your catch at either air opening.",TEAM[team]

    def update_rules(self):
        if self.page != "match" or self.modal or self.delay > 0:
            return
        if self.state.over:
            self.modal = "result"
            return
        if choices(self.state) == (PASS,):
            self.apply(PASS)
            return
        group = self.state.active
        algorithm = self.players[group]
        if algorithm == "Human":
            return
        if self.future is None:
            self.cancel = Event()
            self.future = self.pool.submit(search,self.state,algorithm,self.cancel.is_set)
        elif self.future.done():
            decision = self.future.result()
            self.future = None
            self.effort[group] = decision.effort
            self.apply(decision.action)

    def update(self,dt):
        width,height = max(1,self.win.getXSize()),max(1,self.win.getYSize())
        if (width,height) != self.size:
            self.size = width,height
            self.pixel2d.setScale(2/width,1,2/height)
            aspect = width/height
            self.lens.setFilmSize(max(29.5,17.8*aspect),max(17.8,29.5/aspect))
            if self.screen_shader is not None:
                self.screen_shader.setShaderInput("viewport_size",float(width),float(height))
        visual = 0. if self.modal == "pause" else dt
        self.delay = max(0.,self.delay-visual)
        self.update_rules()
        mouse = self.mouse_pixels()
        pointed = self.at(mouse)
        self.hover = pointed if pointed is not None else self.selected
        self.stage.update(visual,self.state,self.available,self.hover)
        key = (self.size,self.state,self.page,self.modal,self.hover,self.delay>0,self.players,tuple(self.effort))
        if key != self.hud_key:
            self.hud_key = key
            self.hud.draw(self,width,height)
        self.hud.focus_buttons(mouse)

    def tick(self, task):
        self.update(min(.06,self.taskMgr.globalClock.getDt()))
        return Task.cont

    def destroy(self):
        if hasattr(self,"pool"):
            self.stop_search()
            self.pool.shutdown(wait=True,cancel_futures=True)
        if hasattr(self,"filter"):
            self.filter.cleanup()
            self.filter.ignoreAll()
        super().destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode",choices=("local","minimax","mcts","race"))
    parser.add_argument("--seed",type=int,default=0,help="Set the opening Deepfin patrol.")
    args = parser.parse_args()
    loadPrcFileData("Under the Ice Duel","""
window-title Frostfall - Under the Ice 3D
win-size 1440 900
load-display pandagl
sync-video 1
framebuffer-multisample 1
multisamples 4
textures-power-2 none
notify-level warning
""")
    game = UnderIce3D(seed=args.seed)
    try:
        if args.mode:
            game.start(MODES[("local","minimax","mcts","race").index(args.mode)][1])
        game.run()
    finally:
        game.destroy()


if __name__ == "__main__":
    main()
