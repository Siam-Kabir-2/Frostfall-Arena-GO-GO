"""Playable Go Go edition in the original Frostfall Arena 3D presentation."""

import argparse
import sys
from math import copysign

from direct.task import Task
from panda3d.core import PerspectiveLens, Point2, Point3, WindowProperties, loadPrcFileData

from arena import CLOCK_EPSILON, COLS, ROSTER, ROWS, STEP, Match, RedeployAction, UpgradeAction
from frostfall.client3d import BoardWindow
from frostfall.stage3d import TOP, ease
from gogo_hud import GoGoHUD, dock_layout, match_header_layout, ui_scale
from gogo_scenery import ArenaBackdrop
from gogo_sound import GoGoSounds
from gogo_stage import GoGoStage, world
from planners import DRAFT_PLANNERS, draft_snapshot
from sprites import STANDING_HEIGHT

MODES = ("cpu", "local", "showdown")
SETUP_MODES = {"cpu_setup": "cpu", "ai_setup": "showdown"}


class GoGo3D(BoardWindow):
    def __init__(self, window_type="onscreen", audio_enabled=True, *, fit_bounds=None):
        self.fit_bounds = fit_bounds or initial_window()
        self.windowed_bounds = self.fit_bounds
        super().__init__(window_type, audio_enabled, hud_type=GoGoHUD, sounds_type=GoGoSounds,
                         smoothing_strength=.35)
        self.backdrop = ArenaBackdrop(self)
        self.lens = PerspectiveLens()
        self.lens.setNearFar(.25, 140)
        self.lens.setFocalLength(1.)
        self.cam.node().setLens(self.lens)
        self.mode = None
        self.modal = None
        self.match = Match()
        self.stage = GoGoStage(self.arena, self.loader)
        self.arena.root.hide()
        self.ai_algorithms = ["minimax", "mcts"]
        self.cpu_algorithm = "mcts"
        self.selected = None
        self.drag_start = None
        self.notice = ""
        self.notice_time = 0.
        self.decisions = {}
        self.ai_move = {}
        self.ai_turn = 0
        self.first_turn = 1
        self.ai_delay = 0.
        self.accumulator = 0.
        self.hud_clock = 0.
        self.overhead = False
        self.view_amount = 0.
        self.camera_key = None
        self.last_phase = "prep"
        self.seed = None
        self.accept("mouse1", self.click)
        self.accept("mouse1-up", self.release)
        self.accept("mouse3", self.right_click)
        for key, mode in zip("123", MODES):
            self.accept(key, self.mode_key, [mode])
        self.accept("escape", self.escape)
        self.accept("v", self.toggle_view)
        self.accept("p", self.open_modal, ["pause"])
        self.accept("space", self.confirm)
        self.accept("u", self.select_upgrade, [0])
        self.accept("f10", self.fit_window)
        self.accept("f11", self.toggle_fullscreen)
        self.taskMgr.add(self.tick, "Go Go arena update")
        self.update(0)

    def mode_key(self, mode):
        if self.mode is None and self.modal in (None, "help"):
            if mode == "local":
                self.start(mode)
            else:
                self.open_modal("cpu_setup" if mode == "cpu" else "ai_setup")

    def human(self, side):
        return self.mode == "local" or self.mode == "cpu" and side == 0

    def team_name(self, side):
        if self.mode == "cpu" and side == 1:
            return f"Azure {self.ai_planner(side).label}"
        return ("Coral", "Azure")[side]

    def ai_planner(self, side, *, mode=None):
        mode = self.mode if mode is None else mode
        return DRAFT_PLANNERS[self.cpu_algorithm if mode == "cpu" else self.ai_algorithms[side]]

    def select_ai(self, mode, side, key):
        if DRAFT_PLANNERS[key] != self.ai_planner(side, mode=mode):
            self.sounds.play("select")
        if mode == "cpu":
            self.cpu_algorithm = key
        else:
            self.ai_algorithms[side] = key
        self.hud_clock = 0.

    def start(self, mode):
        self.stop_search()
        self.mode = mode
        self.arena.root.show()
        self.modal = None
        self.match = Match(self.seed, public_draft=mode == "showdown")
        self.first_turn = 1-self.first_turn
        self.reset_draft()

    def reset_draft(self):
        self.sounds.stop_effects()
        self.sounds.set_scene(True)
        self.sounds.play("draft")
        self.selected = self.drag_start = None
        self.accumulator = 0.
        self.notice = ""
        self.notice_time = 0.
        self.decisions.clear()
        self.ai_move.clear()
        self.ai_turn = 1 if self.mode == "cpu" else (self.first_turn+self.match.round_number-1) % 2
        self.ai_delay = .27
        self.last_phase = "prep"
        self.hud_clock = 0.

    def rematch(self):
        self.start(self.mode)

    def next_round(self):
        if self.match.next_round():
            self.stop_search()
            self.reset_draft()

    def home(self):
        self.stop_search()
        self.sounds.stop_effects()
        self.sounds.set_scene(False)
        self.sounds.play("back")
        self.mode = self.modal = self.selected = self.drag_start = None
        self.arena.root.hide()
        self.hud_clock = 0.

    def open_modal(self, name):
        if name == "pause" and (self.mode is None or self.match.phase == "end"):
            return
        if self.modal == name:
            self.close_modal()
            return
        if name == "pause":
            self.sounds.stop_effects()
        self.modal = name
        self.sounds.play("open")
        self.hud_clock = 0.

    def close_modal(self):
        if self.modal:
            self.sounds.play("back")
        self.modal = None
        self.hud_clock = 0.

    def escape(self):
        if self.modal:
            self.close_modal()
        elif self.selected:
            self.selected = self.drag_start = None
            self.sounds.play("back")
            self.hud_clock = 0.
        elif self.mode:
            self.open_modal("pause")

    def confirm(self):
        if self.mode is None:
            if self.modal in SETUP_MODES:
                self.start(SETUP_MODES[self.modal])
            return
        if self.modal:
            return
        if self.match.phase == "round_end":
            self.next_round()
        elif self.match.phase == "end":
            self.rematch()
        elif self.mode == "cpu":
            self.ready(0)

    def toggle_view(self):
        self.overhead = not self.overhead
        self.sounds.play("camera")
        self.hud_clock = 0.

    def toggle_sound(self):
        self.sound = not self.sound
        self.sounds.set_enabled(self.sound)
        self.sounds.play("select")
        self.hud_clock = 0.

    def fit_window(self):
        if hasattr(self.win, "requestProperties"):
            # Keep the launch coordinates. The graphics backend can change DPI awareness.
            x, y, width, height = self.fit_bounds
            bounds = WindowProperties()
            bounds.setUndecorated(False)
            bounds.setOrigin(x, y)
            bounds.setSize(width, height)
            self.win.requestProperties(bounds)
            self.fullscreen = False
            self.sounds.play("camera")
            self.hud_clock = 0.

    def toggle_fullscreen(self):
        if not hasattr(self.win, "requestProperties"):
            return
        properties = WindowProperties()
        current = self.win.getProperties()
        if current.getUndecorated():
            x, y, width, height = self.windowed_bounds
            properties.setUndecorated(False)
        else:
            x, y = current.getXOrigin(), current.getYOrigin()
            width, height = self.win.getXSize(), self.win.getYSize()
            self.windowed_bounds = x, y, width, height
            x, y, width, height = monitor_bounds(x+width//2, y+height//2, self.pipe)
            properties.setUndecorated(True)
        properties.setOrigin(x, y)
        properties.setSize(width, height)
        self.win.requestProperties(properties)
        self.fullscreen = properties.getUndecorated()
        self.sounds.play("camera")
        self.hud_clock = 0.

    def message(self, text):
        self.notice = text
        self.notice_time = 2.55
        self.sounds.play("denied")
        self.hud_clock = 0.

    def ready(self, side):
        if self.modal or not self.human(side) or self.match.phase != "prep":
            return
        team = self.match.sides[side]
        if team.to_deploy:
            self.message(f"Place your {team.to_deploy} remaining penguins before Ready.")
            return
        if not team.field:
            self.message("Deploy a penguin before locking the draft.")
            return
        self.selected = self.drag_start = None
        self.lock_draft(side)
        self.hud_clock = 0.

    def lock_draft(self, side):
        team = self.match.sides[side]
        was_ready = team.ready
        self.match.lock(side)
        if team.ready != was_ready and self.match.phase == "prep":
            self.sounds.play("ready" if team.ready else "back", 1. if self.human(side) else .72)

    def select_upgrade(self, side):
        if self.modal or not self.human(side) or not self.match.editable(side):
            return
        if not any(self.match.can_upgrade(side, cell) for cell in self.match.sides[side].field):
            self.message("No penguin can upgrade this round.")
            return
        choice = side, "upgrade", None
        self.selected = None if self.selected == choice else choice
        self.sounds.play("select" if self.selected else "back")
        self.hud_clock = 0.

    def deploy(self, cell):
        if not self.selected or cell is None:
            return False
        side, kind, origin = self.selected
        if not self.human(side) or not self.match.editable(side) or not self.match.legal_cell(side, cell):
            return False
        if kind == "card":
            message = self.match.buy(side, origin, cell)
        elif kind == "return":
            message = self.match.redeploy(side, origin, cell)
        elif kind == "upgrade":
            message = self.match.upgrade(side, cell)
        elif cell == origin:
            return False
        else:
            message = self.match.move(side, origin, cell)
        if message:
            self.message(message)
        else:
            self.selected = None
            self.notice_time = 0.
            self.sounds.play({"card": "buy", "return": "place", "upgrade": "upgrade", "unit": "place"}[kind])
            self.hud_clock = 0.
        return True

    def click(self):
        pointer, pixels = self.mouse_position()
        self.press(pointer, pixels)

    def press(self, pointer, pixels):
        self.drag_start = None
        if self.hud.handle_click(pixels):
            self.hud_clock = 0.
            return
        if self.modal or self.mode is None or self.match.phase != "prep":
            return
        card = self.hud.card_at(pixels)
        if card and self.human(card[0]) and self.match.editable(card[0]):
            self.selected, self.drag_start = card, pixels
            self.sounds.play("select")
            self.hud_clock = 0.
            return
        if self.hud.contains(pixels):
            return
        cell = self.stage.pick(self.cam, self.lens, pointer)
        if self.deploy(cell) or cell is None:
            return
        for side, team in enumerate(self.match.sides):
            if self.human(side) and self.match.editable(side) and cell in team.field:
                self.selected = side, "unit", cell
                self.drag_start = pixels
                self.sounds.play("select")
                self.hud_clock = 0.
                break

    def release(self):
        pointer, pixels = self.mouse_position()
        self.drop(pointer, pixels)

    def drop(self, pointer, pixels):
        origin, self.drag_start = self.drag_start, None
        if origin and not self.hud.contains(pixels) and sum(abs(a-b) for a, b in zip(pixels, origin)) > 7:
            self.deploy(self.stage.pick(self.cam, self.lens, pointer))

    def right_click(self):
        pointer, pixels = self.mouse_position()
        if self.modal or self.hud.contains(pixels):
            return
        if self.selected:
            self.selected = self.drag_start = None
            self.sounds.play("back")
            self.hud_clock = 0.
            return
        cell = self.stage.pick(self.cam, self.lens, pointer)
        if cell:
            for side in (0, 1):
                if self.human(side) and self.match.editable(side) and cell in self.match.sides[side].field:
                    self.match.sell(side, cell)
                    self.sounds.play("sell")
                    self.hud_clock = 0.

    def tick_ai(self, dt):
        if self.mode not in ("cpu", "showdown") or self.match.phase != "prep":
            return
        if self.mode == "showdown" and self.match.sides[self.ai_turn].ready:
            self.ai_turn = 1-self.ai_turn
        side = self.ai_turn
        if self.match.sides[side].ready:
            return
        if self.future:
            if not self.future.done():
                return
            decision = self.future.result()
            self.future = None
            self.decisions[side] = decision
            action = decision.action
            if action is None:
                self.lock_draft(side)
            else:
                message = self.match.apply_draft(side, action)
                if message:
                    self.message(message)
                elif isinstance(action, UpgradeAction):
                    unit = self.match.sides[side].field[action.cell]
                    self.ai_move[side] = f"Upgraded {ROSTER[unit.hero].name} to rank {unit.rank}."
                    self.sounds.play("upgrade", .69)
                elif isinstance(action, RedeployAction):
                    unit = self.match.sides[side].field[action.cell]
                    self.ai_move[side] = f"Repositioned {ROSTER[unit.hero].name}."
                    self.sounds.play("place", .69)
                else:
                    self.ai_move[side] = f"Deployed {ROSTER[action.hero].name}."
                    self.sounds.play("buy", .69)
            if self.mode == "showdown":
                self.ai_turn = 1-side
            self.ai_delay = .20
            self.hud_clock = 0.
            return
        self.ai_delay -= dt
        if self.ai_delay <= 0:
            if self.match.draft_actions(side, 1):
                self.future = self.pool.submit(self.ai_planner(side).choose, draft_snapshot(self.match), side)
            else:
                self.lock_draft(side)

    def play(self, dt):
        if self.mode is None or self.modal:
            return
        self.notice_time = max(0., self.notice_time-dt)
        self.tick_ai(dt)
        self.accumulator += dt
        self.sync_phase()
        while self.accumulator+CLOCK_EPSILON >= STEP:
            self.accumulator = max(0., self.accumulator-STEP)
            previous_count = self.match.seconds_left if self.match.phase == "countdown" else None
            self.sounds.step_battle(self.match)
            self.sync_phase()
            if previous_count is not None and self.match.phase == "countdown" and self.match.seconds_left < previous_count:
                self.sounds.play("countdown")
                self.hud_clock = 0.
            if self.mode == "showdown" and self.match.phase == "round_end" and self.match.time+CLOCK_EPSILON >= 2.8:
                self.next_round()

    def sync_phase(self):
        if self.match.phase != self.last_phase:
            self.last_phase = self.match.phase
            self.selected = self.drag_start = None
            self.stop_search()
            self.play_phase_cue()
            self.hud_clock = 0.

    def play_phase_cue(self):
        if self.match.phase == "countdown":
            self.sounds.play("countdown")
            return
        if self.match.phase == "fight":
            self.sounds.play("fight")
            return
        final = self.match.phase == "end"
        winner = self.match.winner if final else self.match.round_winner
        if winner == -1:
            cue = "draw"
        elif self.mode == "cpu" and winner == 1:
            cue = "defeat" if final else "round_loss"
        else:
            cue = "victory" if final else "round_win"
        self.sounds.play(cue)

    def camera_layout(self, width, height, dt):
        target = float(self.overhead)
        remaining = target-self.view_amount
        self.view_amount += copysign(min(abs(remaining), dt/.32), remaining) if dt else remaining
        key = width, height, self.view_amount
        if key == self.camera_key:
            return
        self.camera_key = key
        compact = width/height < 1.36
        scale = ui_scale(width, height)
        angled = Point3(0, -23, 19.5 if compact else 14.4)
        overhead = Point3(0, -.025, 28)
        blend = ease(self.view_amount)
        self.camera.setPos(angled+(overhead-angled)*blend)
        self.camera.lookAt(0, 0, .035)
        self.arena.root.setShaderInput("eye", self.camera.getPos())
        # Keep the cove visible to each side of the front-facing board.
        gutter = 25*scale if compact else max(25*scale, width*.17*(1-blend))
        left, right = gutter, width-gutter
        _, _, _, header = match_header_layout(width, scale)
        top = max(header, height*.167*(1-blend))+8*scale
        lower_left, _, status = dock_layout(width, height, scale)
        bottom = min(lower_left[1], status[1])-17*scale
        cols, rows = (-.12, COLS+.12), (-.12, ROWS+.12)
        corners = [self.cam.getRelativePoint(self.arena.root, world(col, row, z))
                   for col in cols for row in rows for z in (-.205, TOP)]
        # Camera-facing sprites need headroom that the tile corners alone cannot give them.
        for col in (.5, COLS-.5):
            foot = self.cam.getRelativePoint(self.arena.root, world(col, .5))
            corners.append(foot+Point3(0, 0, STANDING_HEIGHT+.19))
        # At focal length one, project onto the film plane before calculating the fit.
        film = [(p.x/p.y, p.z/p.y) for p in corners]
        xs, zs = zip(*film)
        lo_x, hi_x, lo_z, hi_z = min(xs), max(xs), min(zs), max(zs)
        pixels = min(max(1., right-left)/(hi_x-lo_x), max(1., bottom-top)/(hi_z-lo_z))
        self.lens.setFilmSize(width/pixels, height/pixels)
        self.lens.setFilmOffset((lo_x+hi_x)/2+(width-left-right)/(2*pixels),
                                (lo_z+hi_z)/2+(top+bottom-height)/(2*pixels))
        self.hud_clock = 0.

    def project(self, point, *, visible=True):
        normalized = Point2()
        inside = self.lens.project(self.cam.getRelativePoint(self.arena.root, point), normalized)
        if visible and not inside:
            return None
        width, height = self.size
        return (1+normalized.x)*width/2, (1-normalized.y)*height/2

    def update(self, dt):
        width, height = self.viewport_size()
        home = self.mode is None
        self.backdrop.update(width, height, home=home)
        pointer, pixels = self.mouse_position()
        if not home:
            self.camera_layout(width, height, dt)
            self.play(dt)
            hover = None if self.hud.contains(pixels) else self.stage.pick(self.cam, self.lens, pointer)
            self.stage.update(self.match, 0. if self.modal else dt,
                              selected=self.selected if not self.modal else None, hover=hover)
        self.hud_clock -= dt
        if self.hud_clock <= 0:
            self.hud.draw(self, width, height, pixels)
            self.hud_clock = .05
        self.hud.focus_buttons(pixels)

    def tick(self, task):
        # The fixed-step match clock must keep up when rendering drops below 17 fps.
        self.update(self.global_clock.getDt())
        return Task.cont


def monitor_bounds(x, y, pipe):
    if sys.platform == "win32":
        from ctypes import Structure, byref, sizeof, windll, wintypes

        class MonitorInfo(Structure):
            _fields_ = (("size", wintypes.DWORD), ("monitor", wintypes.RECT),
                        ("work", wintypes.RECT), ("flags", wintypes.DWORD))

        monitor_from_point = windll.user32.MonitorFromPoint
        monitor_from_point.argtypes = (wintypes.POINT, wintypes.DWORD)
        monitor_from_point.restype = wintypes.HMONITOR
        get_monitor_info = windll.user32.GetMonitorInfoW
        get_monitor_info.argtypes = (wintypes.HMONITOR, wintypes.LPVOID)
        info = MonitorInfo()
        info.size = sizeof(info)
        monitor = monitor_from_point(wintypes.POINT(x, y), 2)
        if monitor and get_monitor_info(monitor, byref(info)):
            rect = info.monitor
            return rect.left, rect.top, rect.right-rect.left, rect.bottom-rect.top
    return 0, 0, pipe.getDisplayWidth(), pipe.getDisplayHeight()


def initial_window():
    left, top, right, bottom = 0, 0, 1280, 720
    if sys.platform == "win32":
        from ctypes import byref, windll, wintypes

        area = wintypes.RECT()
        if windll.user32.SystemParametersInfoW(0x0030, 0, byref(area), 0):
            left, top, right, bottom = area.left, area.top, area.right, area.bottom
    # Panda's configured origin is the client area, leaving the native title bar above it.
    scale = min(1., (right-left-36)/1440, (bottom-top-80)/900)
    width, height = max(1, round(1440*scale)), max(1, round(900*scale))
    return left+(right-left-width)//2, top+54, width, height


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=MODES)
    parser.add_argument("--coral-ai", choices=DRAFT_PLANNERS, default="minimax")
    parser.add_argument("--azure-ai", choices=DRAFT_PLANNERS, default="mcts", help="Azure's draft algorithm in either AI mode")
    parser.add_argument("--mute", action="store_true")
    parser.add_argument("--seed", type=int, help="repeat the starting hands in player modes")
    args = parser.parse_args()
    x, y, w, h = initial_window()
    loadPrcFileData("Frostfall Arena Go Go", f"""
window-title Frostfall Arena Go Go - 3D
win-size {w} {h}
win-origin {x} {y}
sync-video 1
framebuffer-multisample 1
multisamples 4
textures-power-2 none
notify-level warning
""")
    game = GoGo3D(audio_enabled=not args.mute, fit_bounds=(x, y, w, h))
    try:
        game.seed = args.seed
        game.ai_algorithms[:] = args.coral_ai, args.azure_ai
        game.cpu_algorithm = args.azure_ai
        if args.mode:
            game.start(args.mode)
        game.run()
    finally:
        game.destroy()


if __name__ == "__main__":
    main()
