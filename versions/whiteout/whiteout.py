"""Launch Frostfall: Whiteout."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from direct.showbase.ShowBase import ShowBase
from panda3d.core import AmbientLight, AntialiasAttrib, ClockObject, DirectionalLight, Filename, Vec4, loadPrcFileData

from frostfall.hud3d import load_fonts
from whiteout_ai import control, mcts, minimax, quick_control
from whiteout_hud import WhiteoutHUD
from whiteout_rules import DT, Control, Race, clamp
from whiteout_stage import FOG, Mountain

ROOT = Path(__file__).resolve().parent
MODES = {
    "quick": ("You", "Glacier", "Echo", "Flint", "Mistral", "Kite", "Shiver", "Atlas"),
    "ai": ("Minimax", "MCTS"),
    "duel": ("You", "MCTS"),
}

loadPrcFileData("Whiteout", """
window-title Frostfall: Whiteout
win-size 1440 900
sync-video true
show-frame-rate-meter false
framebuffer-multisample 1
multisamples 4
textures-power-2 none
notify-level warning
""")


class Whiteout(ShowBase):
    def __init__(self, window_type=None, audio=True):
        super().__init__(windowType=window_type)
        self.disableMouse()
        self.setBackgroundColor(*FOG, 1)
        self.camLens.setNearFar(.20, 1150)
        self.camLens.setFov(75)
        self.render.setAntialias(AntialiasAttrib.MAuto)
        self.make_lights()
        fonts = load_fonts()
        self.stage = Mountain(self, fonts)
        self.hud = WhiteoutHUD(self, fonts)
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="Whiteout AI")
        self.jobs = {}
        self.decisions = {}
        self.held = set()
        self.clock = ClockObject.getGlobalClock()
        self.accumulator = self.menu_clock = self.hud_clock = 0.
        self.paused = False
        self.insight = True
        sounds = ROOT / "assets" / "sounds"
        self.sounds = ({name: self.loader.loadSfx(Filename.fromOsSpecific(str(sounds / f"{name}.wav")))
                        for name in ("dash", "fall", "fish", "crack", "wind")} if audio else {})
        wind = self.sounds.get("wind")
        if wind:
            wind.setLoop(True)
            wind.setVolume(.23)
            wind.play()
        self.previous_boost = self.previous_draft = False
        self.previous_event = -400
        self.state = "menu"
        self.to_menu()
        self.bind()
        self.taskMgr.add(self.frame, "Whiteout frame")

    def make_lights(self):
        ambient = AmbientLight("Snow bounce")
        ambient.setColor(Vec4(.77, .82, .88, 1))
        sun = DirectionalLight("Alpine afternoon")
        sun.setColor(Vec4(.36, .35, .31, 1))
        self.render.setLight(self.render.attachNewNode(ambient))
        direction = self.render.attachNewNode(sun)
        direction.setHpr(-43, -51, 0)
        self.render.setLight(direction)

    def bind(self):
        for key in ("a", "d", "s", "arrow_left", "arrow_right", "arrow_down", "space", "c"):
            self.accept(key, self.held.add, [key])
            self.accept(f"{key}-up", self.held.discard, [key])
        for key, mode in zip(("1", "2", "3"), MODES):
            self.accept(key, self.select_mode, [mode])
        self.accept("p", self.toggle_pause)
        self.accept("escape", self.escape)
        self.accept("r", self.rematch)
        self.accept("v", self.toggle_replay)
        self.accept("tab", self.switch_camera)
        self.accept("h", self.toggle_insight)
        self.accept("mouse1", self.click)
        self.accept("window-event", self.window_status)

    @property
    def has_player(self):
        return self.mode != "ai" and self.state == "race" and self.focus == 0

    def window_status(self, window):
        if window == self.win and hasattr(window, "getProperties") and not window.getProperties().getForeground():
            self.held.clear()

    def mouse_point(self):
        if self.mouseWatcherNode and self.mouseWatcherNode.hasMouse():
            point = self.mouseWatcherNode.getMouse()
            return ((point.x+1)*self.win.getXSize()/2, (1-point.y)*self.win.getYSize()/2)
        return -1, -1

    def click(self):
        self.hud.handle_click(self.mouse_point())

    def select_mode(self, mode):
        if self.state == "menu":
            self.start(mode)

    def cancel_searches(self):
        for future in self.jobs.values():
            future.cancel()
        self.jobs.clear()

    def to_menu(self):
        self.cancel_searches()
        self.mode = "quick"
        self.state = "menu"
        self.race = Race(MODES[self.mode])
        for racer, position in zip(self.race.racers, ((80, -2.8), (76, 1.3), (78, 5.2), (71, -6.4),
                                                     (72, -1.5), (71, 7.5), (66, 1.2), (63, 5.4))):
            racer.s, racer.lane = position
        self.focus = 0
        self.countdown = 0.
        self.paused = False
        self.held.clear()
        self.stage.race_labels(MODES[self.mode])
        self.stage.update(self.race, self.focus, 0, self.menu_clock)
        self.refresh()

    def start(self, mode):
        self.cancel_searches()
        self.mode = mode
        self.state = "race"
        self.race = Race(MODES[mode])
        self.focus = 0
        self.countdown = 3.0
        self.accumulator = 0.
        self.paused = False
        self.controls_history = []
        self.decisions_history = {}
        self.decisions = {0: None, 1: None} if mode == "ai" else {1: None} if mode == "duel" else {}
        self.held.clear()
        self.previous_boost = self.previous_draft = False
        self.previous_event = -400
        self.stage.race_labels(MODES[mode])
        self.stage.update(self.race, self.focus, 0)
        self.refresh()

    def rematch(self):
        if self.state != "menu":
            self.start(self.mode)

    def toggle_pause(self):
        if self.state in ("race", "replay"):
            self.paused = not self.paused
            self.held.clear()
            self.refresh()

    def escape(self):
        if self.state == "results" or self.paused:
            self.to_menu()
        elif self.state != "menu":
            self.toggle_pause()

    def switch_camera(self):
        if self.state == "replay" or (self.state == "race" and (self.mode == "ai" or not self.race.racers[0].active)):
            self.focus = (self.focus+1) % len(self.race.racers)
            self.stage.camera_ready = False
            self.refresh()

    def toggle_insight(self):
        self.insight = not self.insight
        self.refresh()

    def toggle_replay(self):
        if self.state == "replay":
            self.show_results()
        elif self.state == "results" and self.controls_history:
            self.state = "replay"
            self.race = Race(MODES[self.mode])
            self.decisions = dict.fromkeys(self.decisions)
            self.countdown = self.accumulator = 0.
            self.focus = self.final_race.order()[0] if self.mode == "quick" else 0
            self.paused = False
            self.stage.race_labels(MODES[self.mode])
            self.stage.update(self.race, self.focus, 0)
            self.refresh()

    def show_results(self):
        if self.state == "race":
            self.final_race = self.race
        self.cancel_searches()
        self.state = "results"
        self.paused = False
        self.race = self.final_race
        self.focus = self.race.order()[0]
        self.stage.camera_ready = False
        self.refresh()

    def player_control(self):
        left = bool({"a", "arrow_left"} & self.held)
        right = bool({"d", "arrow_right"} & self.held)
        return Control(float(right)-float(left), "space" in self.held, bool({"s", "arrow_down"} & self.held))

    def update_decisions(self):
        new = False
        for index, job in tuple(self.jobs.items()):
            if job.done():
                self.decisions[index] = job.result()
                del self.jobs[index]
                new = True
        if new:
            self.decisions_history[self.race.tick] = self.decisions.copy()
        if self.race.tick % 32 == 0:
            for index in self.decisions:
                if index not in self.jobs and self.race.racers[index].active:
                    algorithm = minimax if index == 0 else mcts
                    self.jobs[index] = self.executor.submit(algorithm, self.race.copy(), index)

    def advance(self):
        if self.state == "replay":
            if self.race.tick >= len(self.controls_history):
                self.show_results()
                return
            self.decisions = self.decisions_history.get(self.race.tick, self.decisions)
            self.race.step(self.controls_history[self.race.tick])
        else:
            if self.decisions:
                self.update_decisions()
            controls = []
            for index in range(len(self.race.racers)):
                decision = self.decisions.get(index)
                if index == 0 and self.mode != "ai":
                    move = self.player_control()
                elif decision:
                    move = control(self.race, index, decision.plan)
                else:
                    move = quick_control(self.race, index)
                controls.append(move)
            self.controls_history.append(tuple(controls))
            self.race.step(controls)
        if self.race.done:
            self.show_results()

    def refresh(self):
        self.hud_clock = 0.
        self.hud.draw(self)

    def sound(self, name, volume):
        sfx = self.sounds.get(name)
        if sfx:
            sfx.setVolume(volume)
            sfx.play()

    def tick_audio(self):
        wind = self.sounds.get("wind")
        if not wind:
            return
        racer = self.race.racers[self.focus]
        gap = clamp((80-racer.s+self.race.danger)/80)
        moving = self.state in ("race", "replay") and not self.paused and self.countdown == 0 and racer.active
        wind.setVolume(.12+racer.speed*.007+gap*.23 if moving else .12)
        wind.setPlayRate(.83+racer.speed*.012 if moving else .86)
        if self.state != "race" or not moving:
            return
        if racer.boosting and not self.previous_boost:
            self.sound("dash", .49)
        if racer.draft and not self.previous_draft:
            self.sound("fish", .19)
        if racer.event_tick != self.previous_event and racer.event_tick > 0:
            self.sound("fall" if racer.recovery else "crack", .39)
        self.previous_boost, self.previous_draft, self.previous_event = racer.boosting, racer.draft, racer.event_tick

    def frame(self, task):
        dt = min(.075, max(.0, self.clock.getDt()))
        if self.state == "menu":
            self.menu_clock += dt
        if self.state in ("race", "replay") and not self.paused:
            if self.countdown:
                self.countdown = max(0., self.countdown-dt)
            else:
                self.accumulator += dt
                while self.accumulator >= DT and self.state in ("race", "replay"):
                    self.accumulator -= DT
                    self.advance()
        self.stage.update(self.race, self.focus, dt, self.menu_clock if self.state == "menu" else None,
                          "c" in self.held and self.state in ("race", "replay"))
        self.tick_audio()
        self.hud_clock += dt
        if self.hud_clock > .083 or self.win.getXSize() != self.hud.w or self.win.getYSize() != self.hud.h:
            self.refresh()
        self.hud.focus_buttons(self.mouse_point())
        return task.cont

    def destroy(self):
        if hasattr(self, "executor"):
            self.cancel_searches()
            self.executor.shutdown(cancel_futures=True)
        super().destroy()


def main():
    parser = argparse.ArgumentParser(description="Frostfall: Whiteout 3D penguin racing")
    parser.add_argument("--mode", choices=MODES, help="start a race directly")
    parser.add_argument("--mute", action="store_true", help="disable sound")
    args = parser.parse_args()
    game = Whiteout(audio=not args.mute)
    try:
        if args.mode:
            game.start(args.mode)
        game.run()
    finally:
        game.destroy()


if __name__ == "__main__":
    main()
