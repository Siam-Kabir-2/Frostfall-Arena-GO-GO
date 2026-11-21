"""Playable Panda3D presentation for the Frostfall rules engine."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from random import Random, SystemRandom
from tempfile import TemporaryDirectory
from threading import Event as Cancel
from array import array
from math import sin, tau
import wave

from direct.filter.FilterManager import FilterManager
from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from panda3d.core import Filename, OrthographicLens, Point3, Shader, Texture, WindowProperties

from . import materials3d
from .ai import PRESETS, search
from .hud3d import HUD, MUTED, load_fonts
from .rules import ADVENTURE_GOAL, ROLES, TEAMS, bait_round, choices, decide_team, new_match, transition
from .stage3d import (
    BITE_GAP, BITE_LENGTH, CORAL, FIRST_BITE, GOLD, MINT, SEAL_IMPACT, SEAL_LAUNCH,
    STRIKE_RECOVERY, TEAM, VIOLET, Arena, ease,
)

PREVIEW_SEED = 610830
ALGORITHMS = ("Minimax", "MCTS")


class Sounds:
    """Short original audio cues synthesized locally for the board events."""

    def __init__(self, loader, enabled):
        self.enabled = enabled
        self.bank = {}
        self.files = TemporaryDirectory(prefix="frostfall-audio-") if enabled else None
        if not self.files:
            return
        rng = Random(670)
        sample_rate = 22050
        params = {
            "click": (545, .075, .08),
            "move": (365, .20, .6),
            "break": (101, .51, .88),
            "strike": (64, .63, .77),
            "breach": (124, .33, 1.05),
            "inbound": (143, .54, .10),
            "warden": (680, .40, .22),
            "rescue": (475, .31, .26),
            "bait": (700, .25, .05),
            "result": (279, .65, .07),
            "bite": (260, .079, 1.40),
        }
        for name, (pitch, duration, texture) in params.items():
            samples = array("h")
            for index in range(round(sample_rate * duration)):
                t = index / sample_rate
                progress = t / duration
                envelope = min(1, t * 190) * (1 - progress) ** (1.6 + texture)
                frequency = pitch * (1 + progress * (-.48 if name in ("break", "strike", "breach") else .31))
                tone = sin(tau * frequency * t) + .24 * sin(tau * frequency * 1.51 * t)
                grain = rng.uniform(-1, 1) * texture * (1 - progress)
                samples.append(round(5600 * envelope * (.82 * tone + grain)))
            file = Path(self.files.name) / f"{name}.wav"
            with wave.open(str(file), "wb") as output:
                output.setparams((1, 2, sample_rate, 0, "NONE", "not compressed"))
                output.writeframes(samples.tobytes())
            self.bank[name] = loader.loadSfx(str(Filename.fromOsSpecific(str(file))))

    def play(self, name):
        if self.enabled and name in self.bank and self.bank[name]:
            self.bank[name].play()

    def close(self):
        self.bank.clear()
        if self.files:
            self.files.cleanup()


class BoardWindow(ShowBase):
    def __init__(self, window_type="onscreen", audio_enabled=True, *, hud_type=HUD, sounds_type=Sounds,
                 smoothing_strength=1.):
        super().__init__(windowType=window_type)
        if not self.win or not self.win.isValid():
            raise RuntimeError("Frostfall Arena could not open a Panda3D graphics window.")
        self.disableMouse()
        self.setBackgroundColor(.028, .054, .096)
        self.default_window = (self.win.getXSize(), self.win.getYSize())
        self.fonts = load_fonts()
        self.lens = OrthographicLens()
        self.lens.setNearFar(.25, 140)
        self.cam.node().setLens(self.lens)
        self.filter = FilterManager(self.win, self.cam)
        self.filter_screen = self.filter.renderSceneInto()
        if self.filter_screen is not None:
            texture = self.filter_screen.getTexture()
            texture.setMinfilter(Texture.FTLinear)
            texture.setMagfilter(Texture.FTLinear)
            self.filter_screen.setShader(Shader.make(Shader.SL_GLSL, materials3d.SCREEN_VERTEX, materials3d.EDGE_SMOOTH))
            self.filter_screen.setShaderInput("scene", texture)
            self.filter_screen.setShaderInput("smoothing_strength", smoothing_strength)
        self.arena = Arena(self.render, self.fonts["label"])
        self.hud = hud_type(self, self.fonts)
        self.sounds = sounds_type(self.loader, audio_enabled)
        self.sound = audio_enabled
        self.motion = True
        self.fullscreen = False
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="frostfall-3d-ai")
        self.future = None
        self.cancel = Cancel()
        self.size = (0, 0)
        self.global_clock = self.taskMgr.globalClock

    def viewport_size(self):
        width, height = max(1, self.win.getXSize()), max(1, self.win.getYSize())
        if (width, height) != self.size:
            self.size = (width, height)
            self.pixel2d.setScale(2 / width, 1, 2 / height)
            if self.filter_screen is not None:
                self.filter_screen.setShaderInput("viewport_size", float(width), float(height))
        return width, height

    def mouse_position(self):
        if self.mouseWatcherNode and self.mouseWatcherNode.hasMouse():
            cursor = self.mouseWatcherNode.getMouse()
            w, h = self.size
            return (cursor.x, cursor.y), ((1 + cursor.x)*w/2, (1 - cursor.y)*h/2)
        return None, (-100, -100)

    def stop_search(self):
        self.cancel.set()
        if self.future is not None:
            self.future.cancel()
        self.future = None

    def tick(self, task):
        self.update(min(.06, self.global_clock.getDt()))
        return Task.cont

    def destroy(self):
        if hasattr(self, "pool"):
            self.stop_search()
            self.pool.shutdown(wait=True, cancel_futures=True)
        if hasattr(self, "sounds"):
            self.sounds.close()
        if hasattr(self, "filter"):
            self.filter.cleanup()
            self.filter.ignoreAll()
        super().destroy()


class Frostfall3D(BoardWindow):
    def __init__(self, window_type="onscreen", audio_enabled=True):
        super().__init__(window_type, audio_enabled)
        self.log = []
        self.stats = None
        self.match_time = 0.0
        self.delay = 0.0
        self.sound_queue = []
        self.banner = None
        self.recent_score = None
        self.view_amount = 0.0
        self.overhead = False
        self.camera_key = None
        self.hud_key = None
        self.options_key = None
        self.hover = None
        self.selected = None
        self.cursor = None
        self.keyboard_mode = False
        self.previous_mouse = None
        self.bait = False
        self.brace = False
        self.adventure = True
        self.local = False
        self.opponent = "Minimax"
        self.ai_teams = ["Minimax", "MCTS"]
        self.difficulty = "Standard"
        self.arena_mode = False
        self.next_seed = None
        self.seed_text = ""
        self.editing_seed = False
        self.show_log = False
        self.state = new_match(PREVIEW_SEED)
        self.home()
        self.bind_controls()
        self.update(0)
        self.taskMgr.add(self.tick, "Frostfall frame")

    def bind_controls(self):
        for name, action in {
            "mouse1": self.click, "mouse3": self.clear_selection, "escape": self.escape,
            "enter": self.confirm, "space": self.confirm, "p": self.toggle_pause,
            "v": self.toggle_view, "l": self.toggle_log, "b": self.toggle_bait, "r": self.toggle_brace,
            "f11": self.toggle_fullscreen, "m": self.toggle_sound, "tab": self.focus_next,
            "shift-tab": lambda: self.focus_next(-1), "backspace": self.seed_backspace,
        }.items():
            self.accept(name, action)
        for number in range(10):
            self.accept(str(number), self.number, [number])
        for key, delta in {"w": (-1, 0), "arrow_up": (-1, 0), "s": (1, 0), "arrow_down": (1, 0),
                           "a": (0, -1), "arrow_left": (0, -1), "d": (0, 1), "arrow_right": (0, 1)}.items():
            self.accept(key, self.aim, list(delta))
            self.accept(key + "-repeat", self.aim, list(delta))

    @property
    def team(self):
        return decide_team(self.state)

    @property
    def match_mode(self):
        if self.arena_mode:
            return "AI ARENA  /  ADVENTURE" if self.state.adventure else "AI ARENA  /  CLASSIC"
        return "HYBRID ADVENTURE" if self.state.adventure else "CLASSIC"

    @property
    def actionable(self):
        return (self.page == "match" and self.modal is None and not self.state.over
                and self.delay <= 0 and self.controllers[self.team] == "Human")

    def invalidate(self):
        self.hud_key = None

    def open_modal(self, modal):
        self.return_modal = self.modal if modal in ("help", "settings") else None
        self.modal = modal
        if modal == "setup":
            self.arena_mode = False
        self.hud.focus = -1
        self.invalidate()

    def close_modal(self):
        self.modal = self.return_modal
        self.return_modal = None
        self.editing_seed = False
        self.hud.focus = -1
        self.invalidate()

    def setup_arena(self):
        self.open_modal("setup")
        self.arena_mode = True

    def toggle_rules(self):
        self.adventure = not self.adventure
        self.invalidate()

    def toggle_local(self):
        self.local = not self.local
        self.invalidate()

    def toggle_seed(self):
        if self.editing_seed:
            self.next_seed = int(self.seed_text) if self.seed_text else None
        else:
            self.seed_text = "" if self.next_seed is None else str(self.next_seed)
        self.editing_seed = not self.editing_seed
        self.hud.focus = -1
        self.invalidate()

    def seed_backspace(self):
        if self.editing_seed:
            self.seed_text = self.seed_text[:-1]
            self.invalidate()

    def rotate_opponent(self):
        self.opponent = ALGORITHMS[1 - ALGORITHMS.index(self.opponent)]
        self.invalidate()

    def rotate_ai(self, team):
        self.ai_teams[team] = ALGORITHMS[1 - ALGORITHMS.index(self.ai_teams[team])]
        self.invalidate()

    def rotate_difficulty(self):
        values = tuple(PRESETS)
        self.difficulty = values[(values.index(self.difficulty) + 1) % len(values)]
        self.invalidate()

    def toggle_motion(self):
        self.motion = not self.motion
        self.invalidate()

    def toggle_sound(self):
        self.sound = not self.sound
        self.sounds.enabled = self.sound
        self.invalidate()

    def toggle_fullscreen(self):
        if not hasattr(self.win, "requestProperties"):
            return
        properties = WindowProperties()
        self.fullscreen = not self.fullscreen
        properties.setFullscreen(self.fullscreen)
        if self.fullscreen:
            self.default_window = (self.win.getXSize(), self.win.getYSize())
            properties.setSize(self.pipe.getDisplayWidth(), self.pipe.getDisplayHeight())
        else:
            properties.setSize(*self.default_window)
        self.win.requestProperties(properties)
        self.invalidate()

    def toggle_pause(self):
        if self.page != "match" or self.modal not in (None, "pause"):
            return
        self.close_modal() if self.modal else self.open_modal("pause")

    def toggle_log(self):
        if self.page == "match" and not self.modal:
            self.show_log = not self.show_log
            self.invalidate()

    def toggle_view(self):
        if self.page == "match" and not self.modal:
            self.overhead = not self.overhead

    def clear_selection(self):
        if self.actionable and self.state.rescue < 0:
            self.selected = self.cursor = None
            self.bait = False
            self.brace = False

    def escape(self):
        if self.editing_seed:
            self.editing_seed = False
            self.invalidate()
        elif self.modal == "result":
            self.home()
        elif self.modal:
            self.close_modal()
        elif self.page == "match":
            if self.selected is not None or self.bait:
                self.clear_selection()
            else:
                self.toggle_pause()

    def home(self):
        self.stop_search()
        self.page, self.modal, self.return_modal = "home", None, None
        self.state = new_match(PREVIEW_SEED)
        self.selected = self.cursor = self.hover = None
        self.overhead = self.bait = self.brace = self.show_log = self.editing_seed = False
        self.sound_queue.clear()
        self.banner = self.recent_score = None
        self.arena.sync(self.state, restart=True)
        self.options_key = None
        self.hud.focus = -1
        self.invalidate()

    def launch(self, seed=None, first=None):
        self.stop_search()
        if self.editing_seed:
            self.toggle_seed()
        if seed is None:
            seed = self.next_seed if self.next_seed is not None else SystemRandom().randrange(100000, 1000000)
        if first is None:
            first = SystemRandom().randrange(2) if self.arena_mode or self.local else 0
        self.state = new_match(seed, self.adventure, first)
        if self.arena_mode:
            self.controllers = tuple(self.ai_teams)
        elif self.local:
            self.controllers = ("Human", "Human")
        else:
            self.controllers = ("Human", self.opponent)
        self.page, self.modal, self.return_modal = "match", None, None
        self.selected = self.cursor = self.hover = None
        self.bait = self.brace = self.show_log = False
        self.log = [("start", f"{TEAMS[first]} opens the match.")]
        self.stats = [[0, 0, 0.0], [0, 0, 0.0]]
        self.delay = .12
        self.match_time = 0.
        self.sound_queue.clear()
        self.banner = self.recent_score = None
        self.arena.sync(self.state, restart=True)
        self.options_key = None
        self.hud.focus = -1
        self.invalidate()

    def rematch(self):
        self.launch(self.state.seed, self.state.first)

    def focus_next(self, step=1):
        buttons = self.hud.buttons
        if buttons:
            self.hud.focus = ((self.hud.focus if self.hud.focus >= 0 else (0 if step < 0 else -1)) + step) % len(buttons)

    def confirm(self):
        if self.editing_seed:
            self.toggle_seed()
        elif 0 <= self.hud.focus < len(self.hud.buttons):
            self.sounds.play("click")
            self.hud.buttons[self.hud.focus].action()
        elif self.actionable and self.cursor is not None:
            self.pick(self.cursor)

    def number(self, value):
        if self.editing_seed:
            if len(self.seed_text) < 9:
                self.seed_text += str(value)
                self.invalidate()
        elif self.actionable and self.state.rescue < 0 and value in (1, 2):
            self.hud.focus = -1
            self.keyboard_mode = True
            self.select(self.team * 2 + value - 1)

    def aim(self, row_step, col_step):
        if not self.actionable:
            if self.page == "home" or self.modal:
                self.focus_next(-1 if row_step < 0 or col_step < 0 else 1)
            return
        self.hud.focus = -1
        self.keyboard_mode = True
        if self.cursor is None:
            self.cursor = next(cell for cell in self.state.positions[self.team*2:self.team*2+2] if cell >= 0)
            return
        row, col = divmod(self.cursor, 8)
        self.cursor = max(0, min(7, row + row_step)) * 8 + max(0, min(7, col + col_step))

    def can_bait(self):
        return self.actionable and any(action.kind == "bait" for action in choices(self.state))

    def toggle_bait(self):
        if self.can_bait():
            self.bait = not self.bait
            self.brace = False
            self.sounds.play("bait")

    def can_brace(self):
        return self.actionable and any(action.kind == "brace" for action in choices(self.state))

    def toggle_brace(self):
        if self.can_brace():
            self.brace = not self.brace
            self.bait = False
            self.select(self.team * 2 + 1)

    def current_actions(self):
        if not self.actionable:
            return {}
        allowed = choices(self.state)
        if self.state.rescue >= 0:
            return {action.target: action for action in allowed}
        kind = "bait" if self.bait else "brace" if self.brace else "move"
        return {action.target: action for action in allowed if action.kind == kind and action.penguin == self.selected}

    def select(self, piece):
        cell = self.state.positions[piece]
        if cell >= 0:
            self.selected = piece
            self.cursor = cell
            if piece % 2 == 0:
                self.brace = False
            self.sounds.play("click")

    def pick(self, cell):
        if not self.actionable or cell is None:
            return
        if self.state.rescue < 0 and cell in self.state.positions:
            piece = self.state.positions.index(cell)
            if piece // 2 == self.team:
                self.select(piece)
                return
        action = self.current_actions().get(cell)
        if action is not None:
            self.apply(action)

    def click(self):
        mouse, pixels = self.mouse_position()
        self.hud.focus = -1
        self.keyboard_mode = False
        if self.hud.handle_click(pixels):
            self.sounds.play("click")
        elif mouse and not self.hud.contains(pixels):
            self.pick(self.arena.pick(self.cam, self.lens, mouse, self.state.positions))

    def hazard(self):
        state = self.state
        if not state.adventure:
            return "Classic rules", "Land on a floe to collect its fish. Keep an escape route open.", MINT
        if state.shark < 0 and self.arena.threatened_cell(state) >= 0:
            return "Deepfin is striking", "The marked floe is about to break.", CORAL
        if state.rescue >= 0:
            return "Emergency rescue", "Pick an adjacent safe floe. The jump costs up to two fish.", CORAL
        if state.shark >= 0:
            deadline = "Strikes after this turn." if state.turn else "Strikes after both sides act."
            return "Deepfin target marked", deadline, CORAL
        if state.marks:
            return "Warden warning", "Marked floes freeze this round if empty.", VIOLET
        if state.frozen:
            return "Frozen lanes", "Marked lanes thaw next round.", VIOLET
        shark = state.round + (3 - state.round) % 6
        warden = state.round + (-state.round) % 6
        if shark < warden:
            return f"Deepfin in round {shark}", "You can deploy bait this round." if bait_round(state.round) else (
                "Deepfin marks an ice tile before either player moves."), GOLD
        return f"Warden in round {warden}", "The Warden can freeze two empty lanes.", VIOLET

    def move_hint(self):
        state = self.state
        if state.over:
            return "Match complete", state.reason, MINT
        if self.delay > 0:
            return "Move in progress", "The next turn begins when the ice settles.", MUTED
        if self.controllers[self.team] != "Human":
            return f"{self.controllers[self.team]} is thinking", "The arena will play the next move.", TEAM[self.team]
        if state.rescue >= 0:
            option = self.current_actions().get(self.hover)
            heading = "Choose a safe neighbor"
            if option and state.fish[option.target]:
                heading = f"Jump  +{state.fish[option.target]} fish"
            return heading, "A rescue costs up to two fish and collects any fish where you land.", CORAL
        if self.selected is None:
            return ("Choose who will deploy bait" if self.bait else "Select a penguin",
                    "Click a teammate or press 1 (Attacker) / 2 (Defender).", GOLD if self.bait else MINT)
        if self.bait:
            return "Place your bait", "Choose a gold target to draw Deepfin there next round.", GOLD
        origin = state.positions[self.selected]
        actions = self.current_actions()
        option = actions.get(self.hover)
        name = ROLES[self.selected % 2]
        heading = "Brace and slide" if self.brace else "Slide"
        if self.brace:
            detail = "Deepfin can still break the starting floe." if origin == state.shark else "The starting floe stays open."
            tone = VIOLET
        else:
            detail, tone = "The starting floe sinks after this slide.", MINT
        if option is not None:
            fish = state.fish[option.target]
            if state.adventure and state.scores[self.team] + fish >= ADVENTURE_GOAL:
                return f"Winning slide  +{fish} fish", "This move reaches the fish goal.", GOLD
            if option.target == state.shark:
                detail, tone = "Deepfin will strike the landing tile.", CORAL
            return f"{heading}  +{fish} fish", detail, tone
        if not actions:
            return f"{name} has no moves", "Try selecting your other penguin.", MUTED
        if self.brace:
            return "Choose where to slide", detail, tone
        return f"{name} selected", "Choose a lit destination to collect its fish on landing.", MINT

    def apply(self, action):
        before = self.state
        self.state, events = transition(before, action)
        self.selected = self.hover = None
        self.bait = False
        self.brace = False
        self.cursor = self.state.positions[self.state.rescue] if self.state.rescue >= 0 else None
        self.delay = .12
        self.options_key = None
        meal_time = 0.
        travel_time = 0.
        if action.kind in ("move", "rescue", "brace"):
            origin = before.positions[action.penguin]
            jump = action.kind == "rescue"
            fish = before.fish[action.target]
            move_sound = "rescue" if jump else "warden" if action.kind == "brace" else "move"
            self.sounds.play(move_sound)
            if self.motion:
                travel_time = .41 if jump else .34
                self.arena.slide(action.penguin, origin, action.target, jump, travel_time)
                if fish:
                    meal_time = self.arena.collect_fish(action.penguin, action.target, delay=travel_time)
                if action.kind == "move":
                    self.arena.fracture(origin, delay=.10)
                elif action.kind == "brace":
                    self.arena.brace_effect(origin)
            self.delay = meal_time + ({"move": .62, "rescue": .48, "brace": .43}[action.kind] if self.motion else .11)
            if meal_time:
                for index in range(len(self.arena.meal.fish)):
                    when = travel_time + FIRST_BITE + index * BITE_GAP + BITE_LENGTH * .82
                    self.sound_queue.append((self.match_time + when, "bite"))
            if fish:
                self.recent_score = decide_team(before), fish, self.match_time + travel_time + meal_time + 1.0
            if action.kind == "move":
                self.sound_queue.append((self.match_time + .18, "break"))
        elif action.kind == "bait":
            self.sounds.play("bait")
        elif action.kind == "pass":
            self.delay = .28
        for event in events:
            self.log.insert(0, (event.kind, event.text))
            if event.kind == "shark":
                self.banner = "DEEPFIN INBOUND", "STAY CLEAR OF THE MARKED FLOE", CORAL, self.match_time + 2.2
                self.sounds.play("inbound")
            elif event.kind in ("strike", "miss"):
                when = meal_time + max(travel_time, min(.40, (self.delay - meal_time) * .65))
                impact = when
                if self.motion:
                    self.arena.strike(event.cells[0], when, has_ice=event.kind == "strike")
                    self.sound_queue.append((self.match_time + when + SEAL_LAUNCH, "breach"))
                    impact += SEAL_IMPACT
                    self.delay = impact + STRIKE_RECOVERY
                title = "DEEPFIN STRIKES" if event.kind == "strike" else "DEEPFIN MISSES"
                self.banner = title, ("MARKED FLOE" if event.kind == "strike" else "OPEN WATER"), CORAL, self.match_time + impact + 1.3
                self.sound_queue.append((self.match_time + impact, "strike"))
            if event.kind in ("warden", "freeze", "thaw"):
                self.sounds.play("warden")
            if event.kind == "freeze":
                self.banner = "LANES FROZEN", "THAW NEXT ROUND", VIOLET, self.match_time + 1.45
            if event.kind == "brace":
                self.banner = "ROUTE SAVED", "THE STARTING FLOE STAYS OPEN", VIOLET, self.match_time + 1.2
            if event.kind == "result":
                if self.motion and action.kind == "move":
                    self.delay = max(self.delay, .85)
                self.sound_queue.append((self.match_time + self.delay, "result"))
        self.log = self.log[:24]
        self.arena.sync(self.state)

    def update_rules(self):
        if self.page != "match" or self.modal:
            return
        if self.state.over:
            if self.delay <= 0:
                self.open_modal("result")
            return
        actions = choices(self.state)
        if len(actions) == 1 and actions[0].kind == "pass":
            if self.delay <= 0:
                self.apply(actions[0])
            return
        algorithm = self.controllers[self.team]
        if algorithm == "Human":
            return
        if self.future is None:
            self.cancel = Cancel()
            self.future = self.pool.submit(search, self.state, algorithm, self.difficulty, self.cancel.is_set)
        elif self.delay <= 0 and self.future.done():
            result = self.future.result()
            self.future = None
            metrics = self.stats[self.team]
            metrics[0] += 1
            metrics[1] += result.effort
            metrics[2] += result.seconds
            self.apply(result.action)

    def adjust_camera(self, dt, width, height, ui_scale, compact):
        target = float(self.overhead)
        if self.motion and dt:
            step = min(abs(target - self.view_amount), dt * 3.2)
            self.view_amount += step if self.view_amount < target else -step
        else:
            self.view_amount = target
        k = (width, height, round(self.view_amount, 5), self.page)
        if k == self.camera_key:
            return
        self.camera_key = k
        angle = ease(self.view_amount)
        home = self.page == "home"
        low_angle = not home and not compact
        self.camera.setPos((2.85 if home else 3.0) * (1 - angle),
                           -(16 if home else 21) * (1 - angle) - .24 * angle,
                           (23.5 if home else 15.6 if low_angle else 18.9) * (1-angle) + 28 * angle)
        self.camera.lookAt(0, 0, .035)
        self.arena.root.setShaderInput("eye", self.camera.getPos())
        if home:
            left = (27 if compact else 467) * ui_scale
            top, bottom = 88 * ui_scale, height - (263 if compact else 54) * ui_scale
        else:
            left = 24 * ui_scale
            top, bottom = (145 if compact else 105) * ui_scale, height - (204 if compact else 133) * ui_scale
        right = width - 25 * ui_scale
        corners = [self.cam.getRelativePoint(self.render, Point3(x, y, z))
                   for x in (-4.64, 4.32) for y in (-4.64, 4.32) for z in (-.20, .88)]
        x_min, x_max = min(p.x for p in corners), max(p.x for p in corners)
        z_min, z_max = min(p.z for p in corners), max(p.z for p in corners)
        pixels = min(max(1, right-left)/(x_max-x_min), max(1, bottom-top)/(z_max-z_min))
        self.lens.setFilmSize(width/pixels, height/pixels)
        self.lens.setFilmOffset((x_min+x_max)/2 + (width-left-right)/(2*pixels),
                                (z_min+z_max)/2 + (top+bottom-height)/(2*pixels))

    def update(self, dt):
        width, height = self.viewport_size()
        compact = width / height < 1.36
        scale = max(.53, min(1.32, height / 900, width / (680 if compact else 1140)))
        self.adjust_camera(dt, width, height, scale, compact)
        if not self.modal:
            self.match_time += dt
            self.delay = max(0, self.delay - dt)
            if self.banner and self.match_time >= self.banner[-1]:
                self.banner = None
            if self.recent_score and self.match_time >= self.recent_score[-1]:
                self.recent_score = None
            queue = []
            for deadline, sound in self.sound_queue:
                if deadline <= self.match_time:
                    self.sounds.play(sound)
                else:
                    queue.append((deadline, sound))
            self.sound_queue = queue
        self.arena.animate(dt if not self.modal else 0, self.state, self.motion)
        self.update_rules()
        mouse, pixels = self.mouse_position()
        if mouse is not None and mouse != self.previous_mouse:
            self.keyboard_mode = False
        self.previous_mouse = mouse
        pointed = None if not mouse or self.hud.contains(pixels) else self.arena.pick(self.cam, self.lens, mouse)
        self.hover = (self.cursor if self.keyboard_mode else pointed) if self.actionable else None
        actions = self.current_actions()
        selected = self.selected if self.actionable else None
        options = (self.state, selected, self.bait, self.brace, self.hover, self.actionable, self.keyboard_mode)
        if options != self.options_key:
            self.options_key = options
            self.arena.show_options(self.state, selected, actions, self.hover)
            self.arena.focus_tile(self.cursor if self.keyboard_mode and self.actionable else None)
        display = (self.size, round(self.view_amount, 3), self.state, self.page, self.modal, self.hover,
                   selected, self.bait, self.brace, self.arena.threatened_cell(self.state),
                   self.delay > 0, self.show_log, self.banner, self.recent_score)
        if display != self.hud_key:
            self.hud_key = display
            self.hud.draw(self, width, height)
        self.hud.focus_buttons(pixels)


