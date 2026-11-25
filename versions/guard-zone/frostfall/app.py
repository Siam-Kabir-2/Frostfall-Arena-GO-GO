"""Window, input, animation timeline and match presentation."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
from random import Random, SystemRandom
import sys
from threading import Event as CancelFlag

if __name__ == "__main__" and not __package__:
    # Let a direct script launch resolve the same imports as a package launch.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "frostfall"

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame as pg

from . import art as a
from .ai import PRESETS, search
from .rules import (ROLES, TEAMS, bait_round, choices, decide_team,
                    label, new_match, transition)

SETTINGS = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".config") / "FrostfallArena" / "settings.json"
OPTIONS = {"sound": True, "motion": True, "fullscreen": False}
WINDOW_FLAGS = pg.RESIZABLE
MODES = ("Hybrid Adventure", "Classic")
ALGORITHMS = ("Minimax", "MCTS")


@dataclass
class Button:
    bounds: pg.Rect
    action: object
    label: str


@dataclass
class Effect:
    kind: str
    cell: int
    start: float
    duration: float
    color: tuple
    amount: int = 0


def load_preferences():
    try:
        saved = json.loads(SETTINGS.read_text(encoding="utf-8"))
        return {key: saved.get(key) if isinstance(saved.get(key), bool) else value
                for key, value in OPTIONS.items()}
    except (ValueError, OSError, AttributeError):
        return OPTIONS.copy()


class Game:
    def __init__(self, *, preferences=None, initial_size=None):
        pg.mixer.pre_init(22050, -16, 2, 512)
        pg.init()
        self.preferences = load_preferences() if preferences is None else preferences.copy()
        self.persist_preferences = preferences is None
        desktop = pg.display.get_desktop_sizes()[0]
        self.window_size = initial_size or (min(1440, max(550, desktop[0] - 100)),
                                            min(900, max(450, desktop[1] - 130)))
        pg.display.set_caption("Frostfall Arena — Hybrid Adventure")
        self.screen = pg.display.set_mode((0, 0) if self.preferences["fullscreen"] else self.window_size,
                                          pg.FULLSCREEN if self.preferences["fullscreen"] else WINDOW_FLAGS)
        pg.display.set_icon(a.penguin(54, 1, 0))
        self.audio = a.Audio(self.preferences["sound"])
        self.running = True
        self.page = "home"
        self.modal = None
        self.buttons = []
        self.focus = -1
        self.pointer = (-100, -100)
        self.time = 0.0
        self.clock = pg.time.Clock()
        self.state = None
        self.selected = None
        self.cursor = None
        self.bait = False
        self.brace = False
        self.controls = ("Human", "Minimax")
        self.difficulty = "Standard"
        self.mode = 0
        self.lineup = 0
        self.side = 0
        self.opponent = "MCTS"
        self.algorithms = ["Minimax", "MCTS"]
        self.arena_setup = False
        self.setup_seed = None
        self.seed_entry = False
        self.seed_text = ""
        self.speed = 1
        self.log = []
        self.stats = [[0, 0, 0.0], [0, 0, 0.0]]
        self.effect_list = []
        self.scheduled_sounds = []
        self.slide = None
        self.ready_at = 0
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="frostfall-ai")
        self.future = None
        self.cancel_flag = CancelFlag()
        self.future_state = None
        self.board = pg.Rect(0, 0, 1, 1)
        self.cell_size = 1
        self.choice_state = None
        self.actions = ()
        self.canvas = None
        self.viewport = pg.Rect(0, 0, 1, 1)
        rng = Random(731)
        self.snow = [(rng.random(), rng.random(), rng.uniform(.007, .028), rng.uniform(.6, 2.2))
                     for _ in range(66)]
        self.layout()

    def layout(self):
        width, height = self.screen.get_size()
        aspect = width / max(height, 1)
        self.compact = aspect < 1.28
        self.height = 1080 if self.compact else 900
        min_width, max_width = (900, 1190) if self.compact else (1260, 1660)
        self.width = max(min_width, min(max_width, round(self.height * aspect)))
        factor = min(width / self.width, height / self.height)
        scaled = (max(1, round(self.width * factor)), max(1, round(self.height * factor)))
        self.viewport = pg.Rect((width - scaled[0]) // 2, (height - scaled[1]) // 2, *scaled)
        if self.canvas is None or self.canvas.get_size() != (self.width, self.height):
            self.canvas = pg.Surface((self.width, self.height)).convert()
        self.cell_size = 76
        self.board = pg.Rect((self.width - 8 * self.cell_size) // 2,
                             125 if self.compact else 151, 8 * self.cell_size, 8 * self.cell_size)

    def logical(self, point):
        return ((point[0] - self.viewport.left) * self.width / self.viewport.width,
                (point[1] - self.viewport.top) * self.height / self.viewport.height)

    def save_preferences(self):
        if not self.persist_preferences:
            return
        try:
            SETTINGS.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS.write_text(json.dumps(self.preferences), encoding="utf-8")
        except OSError:
            pass

    def toggle_setting(self, key):
        self.preferences[key] = not self.preferences[key]
        if key == "sound":
            self.audio.enabled = self.preferences[key]
        if key == "fullscreen":
            if self.preferences[key]:
                self.window_size = self.screen.get_size()
            self.screen = pg.display.set_mode((0, 0) if self.preferences[key] else self.window_size,
                                              pg.FULLSCREEN if self.preferences[key] else WINDOW_FLAGS)
            self.layout()
        self.save_preferences()

    def show(self, page):
        self.page, self.modal, self.focus = page, None, -1
        self.seed_entry = False
        self.buttons.clear()

    def show_modal(self, modal):
        self.modal, self.focus = modal, -1
        self.buttons.clear()

    def setup(self, arena=False):
        self.arena_setup = arena
        self.show("setup")

    def rotate(self, field, values):
        index = values.index(getattr(self, field))
        setattr(self, field, values[(index + 1) % len(values)])

    def rotate_algorithm(self, team):
        self.algorithms[team] = ALGORITHMS[1 - ALGORITHMS.index(self.algorithms[team])]

    def edit_seed(self):
        self.seed_entry = not self.seed_entry
        self.seed_text = "" if self.setup_seed is None else str(self.setup_seed)
        self.focus = -1

    def confirm_seed(self):
        self.setup_seed = int(self.seed_text) if self.seed_text else None
        self.seed_entry = False

    def cancel_search(self):
        self.cancel_flag.set()
        if self.future:
            self.future.cancel()
        self.future = None

    def launch(self, seed=None, first=None):
        self.cancel_search()
        if seed is None:
            seed = self.setup_seed if self.setup_seed is not None else SystemRandom().randrange(100000, 1000000)
        self.state = new_match(seed, self.mode == 0, SystemRandom().randrange(2) if first is None else first)
        self.controls = tuple(self.algorithms) if self.arena_setup else (
            ("Human", "Human") if self.lineup else
            tuple("Human" if team == self.side else self.opponent for team in range(2)))
        self.selected = self.cursor = self.slide = None
        self.bait = False
        self.brace = False
        self.stats = [[0, 0, 0.0], [0, 0, 0.0]]
        self.log = [("start", f"{TEAMS[self.state.first]} opens the match.")]
        self.effect_list.clear()
        self.scheduled_sounds.clear()
        self.ready_at = self.time + .20
        self.speed = 1
        self.show("match")

    def restart(self):
        self.launch(self.state.seed, self.state.first)

    def exit_match(self):
        self.cancel_search()
        self.scheduled_sounds.clear()
        self.show("home")

    def apply(self, action):
        old = self.state
        self.state, events = transition(old, action)
        self.selected, self.bait, self.focus = None, False, -1
        self.brace = False
        self.cursor = self.state.positions[self.state.rescue] if self.state.rescue >= 0 else None
        team = decide_team(old)
        color = a.TEAM[team]
        motion = self.preferences["motion"]
        tempo = 0.54 if self.speed == 2 else 1
        lock = .13 if motion else .07
        if action.kind in ("move", "rescue", "brace"):
            start = old.positions[action.penguin]
            duration = (.37 if action.kind == "rescue" else .31) * tempo
            if motion:
                self.slide = (action, start, self.time, duration)
                self.effect_list.append(Effect("melt" if action.kind == "move" else "jump",
                                               start, self.time, duration + .46 * tempo, color, old.fish[start]))
                fish = old.fish[action.target]
                if fish:
                    self.effect_list.append(Effect("score", action.target, self.time + duration, .65 * tempo,
                                                   color, fish))
            lock = duration if motion else .08
        for event in events:
            self.log.insert(0, (event.kind, event.text))
            if event.kind in ("strike", "freeze", "thaw"):
                start = self.time + lock * .76
                duration = (.63 if event.kind == "strike" else .35) * tempo
                if motion:
                    self.effect_list.extend(Effect(event.kind, cell, start, duration, a.CORAL if event.kind == "strike" else a.AZURE)
                                            for cell in event.cells)
                    lock += duration * .9
                self.scheduled_sounds.append((start, event.kind))
            elif event.kind in ("shark", "pickup", "bait", "rescue", "move", "brace", "result"):
                start = self.time + (lock if event.kind in ("shark", "result") else 0)
                self.scheduled_sounds.append((start, "freeze" if event.kind == "brace" else event.kind))
        self.log = self.log[:22]
        self.ready_at = self.time + lock

    def available(self):
        if self.state is not self.choice_state:
            self.actions = choices(self.state)
            self.choice_state = self.state
        return self.actions

    def current_actions(self):
        if self.state.over:
            return ()
        if self.state.rescue >= 0:
            return self.available()
        kind = "bait" if self.bait else "brace" if self.brace else "move"
        return tuple(action for action in self.available()
                     if action.kind == kind and action.penguin == self.selected)

    def toggle_bait(self):
        if not self.can_interact() or not any(action.kind == "bait" for action in self.available()):
            return
        self.bait = not self.bait
        self.brace = False
        if self.selected is not None and not self.current_actions():
            self.selected = None

    def can_interact(self):
        return (self.page == "match" and not self.modal and not self.state.over
                and self.time >= self.ready_at and self.controls[decide_team(self.state)] == "Human")

    def toggle_brace(self):
        if self.can_interact() and any(action.kind == "brace" for action in self.available()):
            self.brace = not self.brace
            self.bait = False
            self.select(self.state.active * 2 + 1)

    def pick(self, cell):
        if not self.can_interact():
            return
        state = self.state
        if state.rescue < 0 and cell in state.positions:
            piece = state.positions.index(cell)
            if piece // 2 == state.active:
                if not self.bait or any(action.kind == "bait" and action.penguin == piece for action in self.available()):
                    self.select(piece)
                    return
        for action in self.current_actions():
            if cell == action.target:
                self.apply(action)
                return

    def select(self, piece):
        cell = self.state.positions[piece]
        if cell >= 0:
            self.selected = piece
            self.cursor = cell
            if piece % 2 == 0:
                self.brace = False
            self.audio.play("click")

    def update(self):
        self.effect_list = [effect for effect in self.effect_list if self.time < effect.start + effect.duration]
        pending = []
        for when, key in self.scheduled_sounds:
            if when <= self.time:
                self.audio.play(key)
            else:
                pending.append((when, key))
        self.scheduled_sounds = pending
        if self.page != "match" or self.modal or self.time < self.ready_at:
            return
        state = self.state
        if state.over:
            self.show_modal("result")
            return
        actions = self.available()
        if len(actions) == 1 and actions[0].kind == "pass":
            self.apply(actions[0])
            self.ready_at = self.time + .25 / self.speed
            return
        team = decide_team(state)
        algorithm = self.controls[team]
        if algorithm == "Human":
            return
        if self.future is None:
            self.cancel_flag = CancelFlag()
            self.future_state = state
            self.future = self.pool.submit(search, state, algorithm, self.difficulty, self.cancel_flag.is_set)
        elif self.future.done():
            decision = self.future.result()
            self.future = None
            if state is self.future_state:
                stats = self.stats[team]
                stats[0] += 1
                stats[1] += decision.effort
                stats[2] += decision.seconds
                self.apply(decision.action)
                if self.arena_setup:
                    self.ready_at += .13 / self.speed

    def key(self, event):
        key = event.key
        if self.seed_entry:
            if key in (pg.K_RETURN, pg.K_KP_ENTER):
                self.confirm_seed()
            elif key == pg.K_ESCAPE:
                self.seed_entry = False
            elif key == pg.K_BACKSPACE:
                self.seed_text = self.seed_text[:-1]
            elif event.unicode in "0123456789" and event.unicode and len(self.seed_text) < 9:
                self.seed_text += event.unicode
            return
        if key == pg.K_F11:
            self.toggle_setting("fullscreen")
        elif key == pg.K_m:
            self.toggle_setting("sound")
        elif key == pg.K_ESCAPE:
            if self.modal == "result":
                self.exit_match()
            elif self.modal:
                self.show_modal("pause" if self.modal == "match_settings" else None)
            elif self.page == "match":
                if self.bait or self.selected is not None:
                    self.bait, self.selected = False, None
                    self.brace = False
                else:
                    self.show_modal("pause" if not self.state.over else "result")
            else:
                self.show("home")
        elif key == pg.K_p and self.page == "match" and self.modal in (None, "pause"):
            self.show_modal(None if self.modal else ("result" if self.state.over else "pause"))
        elif key == pg.K_TAB or (key in (pg.K_UP, pg.K_DOWN) and (self.page != "match" or self.modal)):
            if self.buttons:
                backwards = (key == pg.K_UP or key == pg.K_TAB and event.mod & pg.KMOD_SHIFT)
                self.focus = ((self.focus - 1 if self.focus >= 0 else -1) if backwards else self.focus + 1) % len(self.buttons)
        elif key in (pg.K_RETURN, pg.K_KP_ENTER, pg.K_SPACE) and 0 <= self.focus < len(self.buttons):
            self.activate(self.buttons[self.focus])
        elif self.can_interact():
            if key in (pg.K_1, pg.K_2) and self.state.rescue < 0:
                self.focus = -1
                self.select(self.state.active * 2 + key - pg.K_1)
            elif key == pg.K_b and self.state.rescue < 0:
                self.focus = -1
                self.toggle_bait()
            elif key == pg.K_r:
                self.focus = -1
                self.toggle_brace()
            elif key in (pg.K_LEFT, pg.K_RIGHT, pg.K_UP, pg.K_DOWN, pg.K_a, pg.K_d, pg.K_w, pg.K_s):
                self.focus = -1
                if self.cursor is None:
                    team = decide_team(self.state)
                    self.cursor = next(cell for cell in self.state.positions[team * 2:team * 2 + 2] if cell >= 0)
                else:
                    row, column = divmod(self.cursor, 8)
                    row += (key in (pg.K_DOWN, pg.K_s)) - (key in (pg.K_UP, pg.K_w))
                    column += (key in (pg.K_RIGHT, pg.K_d)) - (key in (pg.K_LEFT, pg.K_a))
                    self.cursor = max(0, min(7, row)) * 8 + max(0, min(7, column))
                self.pointer = (-100, -100)
            elif key in (pg.K_RETURN, pg.K_SPACE, pg.K_KP_ENTER) and self.cursor is not None:
                self.pick(self.cursor)

    def cell_at(self, pointer):
        if self.board.collidepoint(pointer):
            x = int((pointer[0] - self.board.left) // self.cell_size)
            y = int((pointer[1] - self.board.top) // self.cell_size)
            return y * 8 + x
        return None

    def cell_rect(self, cell):
        row, column = divmod(cell, 8)
        return pg.Rect(self.board.left + column * self.cell_size, self.board.top + row * self.cell_size,
                       self.cell_size, self.cell_size)

    def activate(self, button):
        self.audio.play("click")
        button.action()

    def click(self, point, mouse_button):
        self.focus = -1
        if mouse_button == 3 and self.can_interact() and self.state.rescue < 0:
            self.selected, self.bait, self.cursor = None, False, None
            self.brace = False
        elif mouse_button == 1:
            for button in reversed(self.buttons):
                if button.bounds.collidepoint(point):
                    self.activate(button)
                    return
            if self.page == "match" and not self.modal:
                cell = self.cell_at(point)
                if cell is not None:
                    self.pick(cell)

    def button(self, label, bounds, action, *, primary=False, icon=None, enabled=True, small=False,
               align="center"):
        bounds = pg.Rect(bounds)
        hover = enabled and (bounds.collidepoint(self.pointer) or self.focus == len(self.buttons))
        if primary:
            fill = (173, 249, 234) if hover else a.MINT
            border, ink = (196, 255, 243), (8, 29, 38)
        else:
            fill = (26, 62, 76) if hover else (15, 39, 53)
            border, ink = (99, 177, 183) if hover else (53, 88, 103), a.INK
        if not enabled:
            fill, border, ink = (14, 33, 45), (36, 61, 76), a.DIM
        a.panel(self.canvas, bounds, color=fill, border=border, radius=9)
        if enabled:
            self.buttons.append(Button(bounds, action, label))
        if icon:
            a.icon(self.canvas, icon, (bounds.left + (22 if label else bounds.width // 2), bounds.centery),
                   ink, 18)
        if label:
            if align == "left":
                a.text(self.canvas, label, bounds.left + (42 if icon else 15), bounds.centery,
                       15 if small else 19, ink, "strong", "midleft")
                a.icon(self.canvas, "arrow", (bounds.right - 22, bounds.centery), ink, 16)
            else:
                a.text(self.canvas, label, bounds.centerx + (10 if icon else 0), bounds.centery,
                       15 if small else 19, ink, "strong", "center")

    def flakes(self):
        if not self.preferences["motion"]:
            return
        for x, y, drift, radius in self.snow:
            point = (round(((x + self.time * drift * .45) % 1) * self.width),
                     round(((y + self.time * drift) % 1) * self.height))
            pg.draw.circle(self.canvas, (147, 195, 210) if radius > 1.6 else (84, 133, 156),
                           point, round(radius))

    def brand(self, x, y, scale=1):
        mark = pg.Rect(x, y, 42, 42)
        a.panel(self.canvas, mark, color=(21, 55, 67), border=(63, 108, 117), radius=10)
        a.icon(self.canvas, "peak", mark.center, a.MINT, 26)
        a.text(self.canvas, "FROSTFALL ARENA", x + 56, y + 21, round(17 * scale),
               a.INK, "label", "midleft")

    def home(self):
        x = 60 if self.compact else 78
        self.brand(x, 43)
        self.button("", (self.width - x - 96, 43, 42, 42),
                    lambda: self.toggle_setting("sound"), icon="sound" if self.audio.enabled else "mute")
        self.button("", (self.width - x - 42, 43, 42, 42), lambda: self.show("settings"), icon="gear")
        y = 220 if self.compact else 200
        a.pill(self.canvas, "ARCTIC SURVIVAL STRATEGY", x + 5, y, a.MINT, (21, 63, 70), "snow")
        title_size = 104 if self.compact else 117
        a.text(self.canvas, "Frostfall", x, y + 37, title_size, a.INK, "display")
        a.text(self.canvas, "Arena", x, y + 143, title_size, a.MINT, "italic")
        a.text(self.canvas, "Hybrid Adventure", x + 8, y + 279, 27, (221, 245, 250), "strong")
        a.wrap(self.canvas, "Slide across Arctic ice, collect fish and stay ahead of the Deepfin Shark.",
               x + 8, y + 326, 440, 20, (187, 219, 231), step=29)
        by = y + 419
        self.button("Play", (x + 5, by, 252, 60), self.setup, primary=True, icon="play", align="left")
        self.button("AI Arena", (x + 269, by, 177, 60), lambda: self.setup(True), icon="spark")
        foot = self.height - 84
        pg.draw.line(self.canvas, (72, 115, 132), (x + 5, foot - 18), (self.width - x, foot - 18))
        self.button("How to Play", (x + 5, foot, 145, 43), lambda: self.show("help"), small=True)
        self.button("Exit", (x + 161, foot, 80, 43), lambda: setattr(self, "running", False), small=True)
        a.text(self.canvas, "CLASSIC  /  ADVENTURE  /  AI ARENA", self.width - x, foot + 21,
               14, (184, 217, 224), "label", "midright")

    def view_header(self, title, description):
        self.button("Back", (46, 39, 112, 44), lambda: self.show("home"), icon="back", small=True)
        a.text(self.canvas, title, self.width / 2, 97, 53, a.INK, "display", "midtop")
        a.text(self.canvas, description, self.width / 2, 169, 20, (184, 218, 229), "body", "midtop")

    def setup_view(self):
        arena = self.arena_setup
        self.view_header("AI Arena" if arena else "Match Setup", "Watch two algorithms compete on the same ice."
                         if arena else "Choose the rules and who takes the ice.")
        width = 680
        x, y = (self.width - width) // 2, 230 if not self.compact else 262
        a.panel(self.canvas, (x, y, width, 451 if arena else 511), color=(9, 29, 43), radius=19)
        rows = [("Rules", MODES[self.mode], lambda: self.rotate("mode", (0, 1)))]
        if arena:
            rows += [("Coral algorithm", self.algorithms[0], lambda: self.rotate_algorithm(0)),
                     ("Azure algorithm", self.algorithms[1], lambda: self.rotate_algorithm(1))]
        else:
            rows += [("Players", ("Human vs AI", "Local two-player")[self.lineup], lambda: self.rotate("lineup", (0, 1)))]
            rows += [("Your team", TEAMS[self.side], lambda: self.rotate("side", (0, 1))),
                     ("Opponent", self.opponent, lambda: self.rotate("opponent", ALGORITHMS))]
        rows += [("Difficulty", self.difficulty, lambda: self.rotate("difficulty", tuple(PRESETS)))]
        for index, (caption, value, action) in enumerate(rows):
            line = y + 25 + 60 * index
            inactive = not arena and self.lineup and caption in ("Your team", "Opponent", "Difficulty")
            a.text(self.canvas, caption, x + 28, line + 20, 19, a.DIM if inactive else a.MUTED,
                   "body", "midleft")
            self.button(value, (x + 300, line, 351, 43), action, small=True, align="left", enabled=not inactive)
        seed_row = y + (263 if arena else 323)
        title = self.seed_text + "▏" if self.seed_entry else ("Enter seed" if self.setup_seed is None else str(self.setup_seed))
        a.text(self.canvas, "Board seed", x + 28, seed_row + 21, 19, a.MUTED, "body", "midleft")
        self.button(title, (x + 300, seed_row, 224, 43),
                    self.confirm_seed if self.seed_entry else self.edit_seed, small=True, align="left")
        self.button("Random", (x + 532, seed_row, 119, 43), self.clear_seed,
                    small=True, enabled=self.seed_entry or self.setup_seed is not None)
        hint = ("Type a seed and press Enter." if self.seed_entry else
                "Leave the seed blank for a random board." if self.setup_seed is None else
                "A saved seed reproduces the starting board.")
        a.text(self.canvas, hint, x + 29, seed_row + 56, 16, a.MUTED)
        self.button("Start match", (x + 28, seed_row + 104, width - 56, 56), self.start_from_setup,
                    primary=True, icon="play")

    def start_from_setup(self):
        if self.seed_entry:
            self.confirm_seed()
        self.launch()

    def clear_seed(self):
        self.seed_entry = False
        self.setup_seed = None

    def help_view(self):
        self.view_header("How to Play", "Collect fish, preserve escape routes and watch the warnings.")
        cards = [
            ("diamond", a.MINT, "Slide & score", "Slide in a straight or diagonal line to collect fish where you land. Your starting tile sinks. Water, frozen ice and other penguins block the path."),
            ("shark", a.CORAL, "Deepfin Shark", "Deepfin marks a tile on rounds 3, 9, 15 and every six rounds after that. If caught at the strike, choose an adjacent safe tile and lose up to 2 fish. A penguin with no safe jump is eliminated."),
            ("snow", a.AZURE, "Frost Warden", "On rounds 6, 12, 18 and every six rounds after that, the Warden marks up to two empty tiles. They freeze for the next round if still empty, then thaw."),
            ("bait", a.GOLD, "Shark Bait", "Pick up bait by sliding off its tile. In the round before a shark warning, spend your turn placing bait within three cells of a friendly penguin to redirect the next strike. Each team can deploy once."),
        ]
        width, step = (400, 213) if self.compact else (481, 210)
        x = (self.width - (width * 2 + 18)) // 2
        for index, (symbol, color, title, body) in enumerate(cards):
            cx, cy = x + index % 2 * (width + 18), 228 + index // 2 * step
            a.panel(self.canvas, (cx, cy, width, step - 15), color=(11, 33, 48))
            a.icon(self.canvas, symbol, (cx + 34, cy + 35), color, 24)
            a.text(self.canvas, title, cx + 59, cy + 20, 24, a.INK, "strong")
            a.wrap(self.canvas, body, cx + 25, cy + 65, width - 49, 17, a.MUTED, step=24)
        y = 228 + 2 * step + 5
        a.panel(self.canvas, (x, y, 2 * width + 18, 126), color=(11, 33, 48))
        a.text(self.canvas, "Winning & controls", x + 24, y + 16, 20, a.INK, "strong")
        a.wrap(self.canvas, "Adventure ends at 30 fish or when one team traps the other. Press R to brace a floe with your Defender once each match.",
               x + 24, y + 49, width * 2 - 30, 17, a.MUTED, step=23)
        a.text(self.canvas, "1 / 2  Select penguin     ·     Arrows / WASD  Aim     ·     Enter  Confirm     ·     B  Bait     ·     P  Pause",
               x + 24, y + 93, 15, a.MINT, "label")

    def settings(self, overlay=False):
        x = (self.width - 600) // 2
        y = (self.height - 370) // 2 if overlay else 242
        if not overlay:
            self.view_header("Settings", "Adjust the game to how you play.")
        a.panel(self.canvas, (x, y, 600, 370), color=(10, 30, 43), border=(61, 109, 124), radius=21)
        a.text(self.canvas, "Preferences", x + 29, y + 24, 29, a.INK, "strong")
        rows = [("Sound effects", "Movement, hazards and interface cues", "sound"),
                ("Motion effects", "Snow, slides, and ice-breaking animations", "motion"),
                ("Fullscreen", "Switch between fullscreen and a resizable window", "fullscreen")]
        for index, (title, hint, key) in enumerate(rows):
            line = y + 84 + index * 67
            a.text(self.canvas, title, x + 30, line, 19, a.INK, "strong")
            a.text(self.canvas, hint, x + 30, line + 25, 15, a.MUTED)
            enabled = self.preferences[key]
            self.button("On" if enabled else "Off", (x + 455, line + 2, 115, 42),
                        lambda key=key: self.toggle_setting(key), primary=enabled, small=True)
        if overlay:
            self.button("Return to pause", (x + 30, y + 302, 540, 44),
                        lambda: self.show_modal("pause"), icon="back", small=True)
        else:
            a.text(self.canvas, "M  Toggle sound     ·     F11  Toggle fullscreen", x + 30, y + 318, 16, a.MINT, "label")


    def hazard(self):
        state = self.state
        if state.rescue >= 0:
            return ("shark", a.CORAL, "Emergency jump", "Choose an adjacent highlighted tile. The rescue costs up to 2 fish.")
        if state.shark >= 0:
            return ("shark", a.CORAL, "Deepfin warning", f"{label(state.shark)} breaks after both teams act.")
        if state.marks:
            marked = " and ".join(map(label, state.marks))
            return ("snow", a.AZURE, "Warden warning", f"{marked} freeze if empty at the end of this round.")
        if state.frozen:
            return ("snow", a.AZURE, "Lanes frozen", "Frozen lanes block slides until the next round.")
        if not state.adventure:
            return ("peak", a.MINT, "Classic rules", "Collect fish where you land and keep a route open.")
        shark = state.round + ((3 - state.round) % 6)
        warden = state.round + ((-state.round) % 6)
        if shark < warden:
            return ("shark", a.GOLD, f"Deepfin · Round {shark}", "Bait can be deployed this round." if bait_round(state.round)
                    else "The shark marks one tile before either team acts.")
        return ("snow", a.AZURE, f"Warden · Round {warden}", "The Warden can freeze two empty lanes.")

    def match_header(self):
        state = self.state
        y, margin = 34, 43
        self.brand(margin, y)
        if not self.compact:
            a.pill(self.canvas, "AI ARENA" if self.arena_setup else MODES[int(not state.adventure)].upper(),
                   283, y + 7, a.MINT)
        team = decide_team(state)
        display_team = a.TEAM[team]
        a.text(self.canvas, f"ROUND {state.round:02}", self.width / 2, y + 1,
               17, a.MUTED, "label", "midtop")
        description = "Match complete" if state.over else (
            f"{TEAMS[team]} rescue" if state.rescue >= 0 else f"{TEAMS[team]} turn")
        a.text(self.canvas, description, self.width / 2, y + 20, 24, display_team, "strong", "midtop")
        if not self.modal:
            endpoint = self.width - margin
            self.button("", (endpoint - 160, y, 40, 42), lambda: self.toggle_setting("sound"),
                        icon="sound" if self.audio.enabled else "mute")
            self.button("Pause", (endpoint - 109, y, 109, 42),
                        lambda: self.show_modal("result" if self.state.over else "pause"),
                        icon="pause", small=True)
            if self.arena_setup:
                self.button(f"{self.speed}×", (endpoint - 227, y, 56, 42),
                            lambda: setattr(self, "speed", 3 - self.speed), small=True)
        pg.draw.line(self.canvas, (51, 86, 104), (margin, 93), (self.width - margin, 93))

    def sidebar(self):
        s = self.canvas
        state = self.state
        team = decide_team(state)
        symbol, tone, title, detail = self.hazard()
        if self.compact:
            left, y, w = 29, 777, (self.width - 82) // 2
            right = self.width - 29 - w
            a.panel(s, (left, y, w, 218), color=(10, 30, 43))
            a.panel(s, (right, y, w, 218), color=(10, 30, 43))
            self.score_rows(right + 14, y + 15, w - 28, compact=True)
            self.feed(right + 17, y + 112, w - 34, 87, rows=2)
            a.icon(s, symbol, (left + 28, y + 30), tone, 24)
            a.text(s, title, left + 53, y + 17, 23, a.INK, "strong")
            a.wrap(s, detail, left + 17, y + 58, w - 34, 17, a.MUTED, step=22, limit=2)
            a.text(s, ROLES[self.selected % 2] + " selected" if self.selected is not None else
                   ("AI Arena" if self.arena_setup else MODES[int(not state.adventure)]),
                   left + 17, y + 113, 17, a.TEAM[team], "strong")
            if state.adventure and not self.modal:
                enabled = self.can_interact() and any(action.kind == "bait" for action in self.available())
                self.button("Cancel bait" if self.bait else "Deploy bait", (left + 16, y + 151, w - 32, 48),
                            self.toggle_bait, enabled=enabled, primary=self.bait, icon="bait", small=True)
            elif not state.adventure:
                a.text(s, "1 / 2  Select     •     Arrows  Aim     •     Enter  Confirm", left + 17, y + 164, 15, a.MUTED, "label")
            return

        x = 43 if self.width >= 1400 else 29
        y = 124
        width = min(268, (self.width - 670) // 2 - x - 24)
        a.panel(s, (x, y, width, 184), color=(10, 30, 43))
        a.text(s, "FIELD CONDITIONS", x + 18, y + 17, 15, a.MUTED, "label")
        a.panel(s, (x + 19, y + 47, 38, 38), color=a.shade(a.PANEL, tone, .17),
                border=a.shade(a.PANEL, tone, .48), radius=10)
        a.icon(s, symbol, (x + 38, y + 66), tone, 23)
        a.text(s, title, x + 67, y + 66, 19, a.INK, "strong", "midleft")
        a.wrap(s, detail, x + 19, y + 102, width - 40, 17, a.MUTED, step=23, limit=3)

        py = y + 199
        a.panel(s, (x, py, width, 204 if state.adventure else 149), color=(10, 30, 43))
        a.text(s, "YOUR COMMAND" if self.controls[team] == "Human" else "ON THE ICE",
               x + 18, py + 17, 15, a.MUTED, "label")
        if self.selected is not None:
            role = self.selected % 2
            s.blit(a.penguin(46, team, role), (x + 16, py + 48))
            a.text(s, ROLES[role], x + 75, py + 48, 22, a.INK, "strong")
            a.text(s, f"{label(state.positions[self.selected])}  ·  {len(self.current_actions())} targets",
                   x + 75, py + 79, 15, a.MUTED, "mono")
        else:
            description = ("AI chooses a penguin." if self.controls[team] != "Human" else
                           "A penguin needs a safe jump." if state.rescue >= 0 else "Select one of your penguins.")
            a.wrap(s, description, x + 19, py + 57, width - 38, 18, a.INK, step=24, limit=2)
        if state.adventure:
            enabled = not self.modal and self.can_interact() and any(action.kind == "bait" for action in self.available())
            if not self.modal:
                self.button("Cancel bait" if self.bait else "Deploy bait", (x + 17, py + 112, width - 34, 43),
                            self.toggle_bait, enabled=enabled, primary=self.bait, icon="bait", small=True)
            a.text(s, "Use bait before a shark round.", x + 19, py + 172, 13, a.MUTED)

        ky = py + (219 if state.adventure else 164)
        a.panel(s, (x, ky, width, 168), color=(10, 30, 43))
        a.text(s, "QUICK CONTROLS", x + 18, ky + 17, 15, a.MUTED, "label")
        controls = (("1 / 2", "Select penguin"), ("WASD", "Move cursor"), ("ENTER", "Confirm"), ("P", "Pause"))
        for index, (key, hint) in enumerate(controls):
            line = ky + 47 + index * 27
            a.rect(s, (24, 52, 66), (x + 18, line, 59, 21), 4)
            a.text(s, key, x + 47, line + 10, 13, a.MINT, "mono", "center")
            a.text(s, hint, x + 88, line + 10, 15, a.MUTED, "body", "midleft")

        rw = min(276, width + 8)
        rx = self.width - x - rw
        a.panel(s, (rx, y, rw, 277), color=(10, 30, 43))
        a.text(s, "FISH SCORE", rx + 19, y + 17, 15, a.MUTED, "label")
        self.score_rows(rx + 16, y + 47, rw - 32)
        if self.arena_setup:
            budget = PRESETS[self.difficulty]
            a.text(s, f"Depth {budget[0]} · {budget[1]} MCTS sims", rx + 20, y + 248, 14, a.MUTED, "mono")
        else:
            a.text(s, "Collect fish where you land.", rx + 19, y + 246, 14, a.MUTED)
        a.panel(s, (rx, y + 292, rw, 360), color=(10, 30, 43))
        a.text(s, "MATCH LOG", rx + 19, y + 309, 15, a.MUTED, "label")
        self.feed(rx + 19, y + 343, rw - 38, 290, rows=5)

    def score_rows(self, x, y, width, compact=False):
        state = self.state
        current = decide_team(state)
        for team in range(2):
            cx = x + (team * ((width + 10) // 2) if compact else 0)
            cy = y + (0 if compact else team * 96)
            w = (width - 10) // 2 if compact else width
            h = 79 if compact else 88
            color = a.TEAM[team]
            active = team == current and not state.over
            a.panel(self.canvas, (cx, cy, w, h), color=a.shade(a.NIGHT, color, .105 if active else .054),
                    border=a.shade(a.PANEL, color, .67 if active else .25), radius=10)
            if not compact:
                self.canvas.blit(a.penguin(46, team, 0), (cx + 8, cy + 9))
            tx = cx + (13 if compact else 58)
            a.text(self.canvas, TEAMS[team], tx, cy + 10, 20, color, "strong")
            a.text(self.canvas, f"{state.scores[team]:02}", cx + w - 16, cy + 33, 38, a.INK, "mono", "midright")
            a.text(self.canvas, self.controls[team], tx, cy + 37, 15, a.MUTED, "body")
            if state.adventure:
                bait = "Bait spent" if state.deployed[team] else "Bait ready" if state.inventory[team] else "No bait"
                a.icon(self.canvas, "bait", (tx + 6, cy + 64), a.GOLD if state.inventory[team] else a.DIM, 14)
                a.text(self.canvas, bait, tx + 17, cy + 64, 13, a.GOLD if state.inventory[team] else a.MUTED,
                       "body", "midleft")

    def feed(self, x, y, width, height, rows):
        colors = {"shark": a.CORAL, "strike": a.CORAL, "danger": a.CORAL, "eliminated": a.CORAL,
                  "freeze": a.AZURE, "warden": a.AZURE, "thaw": a.AZURE, "bait": a.GOLD, "pickup": a.GOLD,
                  "move": a.MINT, "result": a.MINT}
        for index, (kind, message) in enumerate(self.log[:rows]):
            line = y + index * (height // rows)
            pg.draw.circle(self.canvas, colors.get(kind, a.DIM), (x + 4, line + 10), 3)
            a.wrap(self.canvas, message, x + 15, line, width - 16, 15, a.INK if index == 0 else a.MUTED,
                   step=18, limit=2)
            if index < min(len(self.log), rows) - 1:
                pg.draw.line(self.canvas, (35, 62, 77), (x, line + height // rows - 6),
                             (x + width, line + height // rows - 6))

    def draw_board(self):
        s = self.canvas
        state, board, size = self.state, self.board, self.cell_size
        stage = board.inflate(62, 61)
        a.panel(s, stage.move(0, 4), color=(5, 16, 28), border=(11, 25, 36), radius=19)
        a.panel(s, stage, color=(11, 33, 50), border=(71, 120, 142), radius=18)
        a.panel(s, board.inflate(8, 8), color=(9, 33, 52), border=(38, 80, 103), radius=6)
        for index, column in enumerate("ABCDEFGH"):
            a.text(s, column, board.x + size * (index + .5), board.y - 16, 14, a.MUTED, "mono", "center")
            a.text(s, str(index + 1), board.x - 17, board.y + size * (index + .5), 14, a.MUTED, "mono", "center")
        allowed = {action.target: action for action in self.current_actions()}
        pointed = self.cell_at(self.pointer)
        target = pointed if pointed is not None else self.cursor
        if not self.can_interact():
            allowed = {}
        ghost = {}
        landing_fish = {}
        for effect in self.effect_list:
            if effect.kind == "melt" and self.time - effect.start < .15:
                ghost[effect.cell] = effect
            if effect.kind == "strike" and self.time < effect.start:
                ghost[effect.cell] = effect
            if effect.kind == "score" and self.time < effect.start:
                landing_fish[effect.cell] = effect.amount

        for cell, fish in enumerate(state.fish):
            bounds = self.cell_rect(cell)
            cx, cy = bounds.center
            if state.has_ice(cell) or cell in ghost:
                s.blit(a.ice_tile(size - 2, cell % 8), (bounds.x + 1, bounds.y + 1))
                if cell in ghost:
                    fish = ghost[cell].amount
                self.tile_content(cell, landing_fish.get(cell, fish), bounds, allowed, target)
            else:
                a.rect(s, (12 + cell % 4, 38 + cell % 5, 56 + cell % 5), bounds.inflate(-4, -4), 6)
                for line in range(3):
                    shift = (cell * 19 + line * 13) % 38
                    y = bounds.y + 20 + line * 15
                    xx = bounds.x + 8 + shift
                    pg.draw.lines(s, (24, 57 + line * 3, 77 + line * 3), False,
                                  ((xx, y), (xx + 5, y - 2), (xx + 14, y - 2), (xx + 19, y - 4)))
                if cell == state.shark:
                    a.icon(s, "shark", (cx, cy), a.CORAL, 29)
        if target in allowed:
            action = allowed[target]
            if action.kind == "move":
                start_cell = state.positions[action.penguin]
                row, col = divmod(start_cell, 8)
                target_row, target_col = divmod(target, 8)
                count = max(abs(row - target_row), abs(col - target_col))
                for step in range(1, count):
                    x = col + (target_col - col) * step // count
                    y = row + (target_row - row) * step // count
                    center = self.cell_rect(y * 8 + x).center
                    pg.draw.circle(s, (43, 126, 131), (center[0], center[1] - 3), 7, 1)
                    pg.draw.circle(s, (197, 255, 243), (center[0], center[1] - 3), 3)
        self.draw_pieces()
        self.draw_effects()
        if self.cursor is not None and pointed is None and self.can_interact():
            bounds = self.cell_rect(self.cursor).inflate(-11, -13).move(0, -2)
            for x, sx in ((bounds.left, 1), (bounds.right, -1)):
                for y, sy in ((bounds.top, 1), (bounds.bottom, -1)):
                    pg.draw.lines(s, a.INK, False, ((x + 8 * sx, y), (x, y), (x, y + 8 * sy)), 2)

    def tile_content(self, cell, fish, bounds, allowed, target):
        s, state = self.canvas, self.state
        cx, cy = bounds.center
        tint = None
        piece = state.positions.index(cell) if cell in state.positions else None
        if cell == state.shark or cell in state.marks or cell in state.frozen:
            tint = a.CORAL if cell == state.shark else a.AZURE
        if cell in allowed:
            kind = allowed[cell].kind
            tint = {"bait": a.GOLD, "rescue": a.CORAL}.get(kind, a.MINT)
        if tint:
            layer = pg.Surface(bounds.size, pg.SRCALPHA)
            box = pg.Rect(5, 5, bounds.width - 10, bounds.height - 14)
            if cell in state.frozen:
                a.rect(layer, (25, 90, 144, 188), box, 8)
                pg.draw.lines(layer, (156, 219, 247, 164), False,
                              ((10, 39), (20, 30), (28, 31), (38, 17), (48, 12), (63, 19)), 2)
                pg.draw.lines(layer, (156, 219, 247, 164), False,
                              ((39, 64), (44, 56), (56, 54), (64, 41)), 2)
            else:
                a.rect(layer, (*a.shade(tint, (15, 111, 129), .40), 168 if cell == target else 111),
                       box, 8)
            a.rect(layer, (*tint, 240), box, 8, 2 if cell == target or cell in state.frozen else 1)
            s.blit(layer, bounds)
        if cell == state.shark or cell in state.marks or cell in state.frozen:
            shark = cell == state.shark
            tone = a.CORAL if shark else a.AZURE
            if piece is None:
                symbol_color = ((121, 52, 67) if shark else
                                (217, 246, 255) if cell in state.frozen else (21, 77, 106))
                a.icon(s, "shark" if shark else "snow", (cx, cy - 7), symbol_color, 33)
            a.rect(s, (58, 37, 52) if shark else (26, 77, 110), (bounds.x + 6, bounds.y + 7, 21, 20), 5)
            a.icon(s, "shark" if shark else "snow", (bounds.x + 17, bounds.y + 17), tone, 15)
        if cell in state.pickups or cell in state.markers:
            deployed = cell in state.markers
            badge = pg.Rect(bounds.right - 25, bounds.y + 7, 19, 20)
            a.rect(s, a.GOLD if deployed else (68, 57, 48), badge, 6)
            a.icon(s, "bait", badge.center, a.NIGHT if deployed else a.GOLD, 15)
        if fish:
            spot = pg.Rect(bounds.right - 32, bounds.bottom - 22, 26, 15)
            a.rect(s, (205, 239, 247), spot, 6)
            a.icon(s, "fish", (spot.x + 8, spot.centery), (16, 61, 82), 11)
            a.text(s, fish, spot.right - 3, spot.centery, 12, (13, 55, 78), "strong", "midright")
        if cell in allowed:
            color = a.GOLD if allowed[cell].kind == "bait" else a.CORAL if allowed[cell].kind == "rescue" else a.MINT
            pg.draw.circle(s, (30, 89, 105), (cx, cy - 5), 7 if cell == target else 4, 1)
            pg.draw.circle(s, a.INK if cell == target else color, (cx, cy - 5), 3 if cell == target else 2)
        if piece is not None and piece == self.selected:
            a.rect(s, a.INK, bounds.inflate(-9, -13).move(0, -2), 9, 2)
            a.rect(s, a.TEAM[piece // 2], bounds.inflate(-15, -19).move(0, -2), 8, 2)

    def draw_pieces(self):
        state = self.state
        slide = self.slide
        moving = slide and self.time < slide[2] + slide[3]
        display = []
        for piece, cell in enumerate(state.positions):
            if cell < 0:
                continue
            cx, cy = self.cell_rect(cell).center
            if piece == state.rescue:
                cy -= max(0, math.sin(self.time * 8) * 5) if self.preferences["motion"] else 0
            if moving and slide[0].penguin == piece:
                action, origin, start, duration = slide
                sx, sy = self.cell_rect(origin).center
                t = (self.time - start) / duration
                p = 1 - (1 - t) ** 2
                cx = sx + (cx - sx) * p
                cy = sy + (cy - sy) * p - math.sin(math.pi * p) * (36 if action.kind == "rescue" else 8)
            display.append((cy, cx, piece))
        for cy, cx, piece in sorted(display):
            sprite = a.penguin(57, piece // 2, piece % 2)
            self.canvas.blit(sprite, sprite.get_rect(center=(round(cx), round(cy - 8))))

    def draw_effects(self):
        for effect in self.effect_list:
            p = (self.time - effect.start) / effect.duration
            if not 0 <= p < 1:
                continue
            center = self.cell_rect(effect.cell).center
            color = effect.color
            if effect.kind == "score":
                shade = a.shade(color, a.MUTED, p)
                tx, ty = center[0], center[1] - 19 - round(p * 49)
                a.text(self.canvas, f"+{effect.amount}", tx + 1, ty + 2, 26, a.NIGHT, "strong", "center")
                a.text(self.canvas, f"+{effect.amount}", tx, ty, 26, shade, "strong", "center")
                continue
            layer = pg.Surface((182, 175), pg.SRCALPHA)
            ox, oy = 91, 86
            if effect.kind in ("strike", "melt", "jump"):
                alpha = round(156 * (1 - p))
                rad = round(12 + 37 * p)
                pg.draw.ellipse(layer, (*color, alpha), (ox - rad, oy - rad // 2, rad * 2, rad), 2)
                if effect.kind == "strike":
                    a.icon(layer, "shark", (ox, oy - 9 - round(24 * p)), (*color, alpha), 64)
            else:
                a.icon(layer, "snow", (ox, oy), (*color, round(190 * (1 - p))), 38 + round(42 * p))
            for n in range(12):
                angle = n * math.tau / 12 + .33
                r = p * (37 + (n * 13) % 27)
                x = round(ox + math.cos(angle) * r)
                y = round(oy + math.sin(angle) * r * .68 - 16 * math.sin(math.pi * p))
                pg.draw.polygon(layer, (*color, round(238 * (1 - p))), ((x, y - 4), (x + 3, y), (x, y + 3), (x - 2, y)))
            self.canvas.blit(layer, (center[0] - ox, center[1] - oy))

    def match_footer(self):
        state = self.state
        team = decide_team(state)
        algorithm = self.controls[team]
        color, symbol = a.TEAM[team], "diamond"
        if state.over:
            title, hint = "Match complete", state.reason
        elif self.time < self.ready_at:
            title, hint = "Resolving turn", "Watch the board for changes."
        elif algorithm != "Human":
            title, hint, symbol = f"{TEAMS[team]} · {algorithm}", "Choosing a safe jump…" if state.rescue >= 0 else "Thinking…", "spark"
        elif state.rescue >= 0:
            title, hint, symbol = "Jump to safety", "Pay up to 2 fish and collect any fish where you land.", "shark"
        elif self.bait:
            title, hint, symbol = "Deploy shark bait", ("Choose a friendly penguin first." if self.selected is None else
                                "Choose a highlighted tile to lure Deepfin here."), "bait"
            color = a.GOLD
        elif self.brace:
            title, hint, symbol = "Brace ice", "Slide with your Defender to keep the starting tile in play.", "shield"
        elif self.selected is not None:
            count = len(self.current_actions())
            title = ROLES[self.selected % 2]
            hint = "Choose a highlighted tile. Hover to preview the route." if count else "This penguin is trapped. Try your other penguin."
            if state.adventure and self.selected % 2 and any(action.kind == "brace" for action in self.available()):
                hint = "Choose a destination, or press R once per match to save this tile."
        else:
            title, hint = f"{TEAMS[team]} to move", "Select either of your penguins to see where it can slide."
        margin = 29 if self.compact else 43
        y = self.height - (66 if self.compact else 76)
        h = 49 if self.compact else 53
        a.panel(self.canvas, (margin, y, self.width - margin * 2, h), color=(13, 38, 50),
                border=(48, 90, 107), radius=11)
        a.icon(self.canvas, symbol, (margin + 24, y + h / 2), color, 20)
        caption = a.text(self.canvas, title, margin + 44, y + h / 2, 17, color, "strong", "midleft")
        a.text(self.canvas, hint, caption.right + 16, y + h / 2, 16, a.INK, "body", "midleft")
        a.text(self.canvas, f"SEED {state.seed}", self.width - margin - 16, y + h / 2,
               14, a.MUTED, "mono", "midright")

    def match_view(self):
        self.match_header()
        self.draw_board()
        self.sidebar()
        self.match_footer()
        if self.modal:
            self.buttons.clear()
            veil = pg.Surface(self.canvas.get_size(), pg.SRCALPHA)
            veil.fill((3, 12, 21, 196))
            self.canvas.blit(veil, (0, 0))
            if self.modal == "result":
                self.results()
            elif self.modal == "match_settings":
                self.settings(overlay=True)
            else:
                self.pause_view()

    def pause_view(self):
        x, y = (self.width - 520) // 2, (self.height - 409) // 2
        a.panel(self.canvas, (x, y, 520, 409), color=(11, 31, 46), border=(60, 108, 127), radius=20)
        a.icon(self.canvas, "pause", (self.width // 2, y + 38), a.MINT, 27)
        a.text(self.canvas, "Match paused", self.width // 2, y + 63, 42, a.INK, "display", "midtop")
        for index, (label, action, icon) in enumerate((
            ("Resume match", lambda: self.show_modal(None), "play"),
            ("Restart this board", self.restart, "restart"),
            ("Settings", lambda: self.show_modal("match_settings"), "gear"),
            ("Back to main menu", self.exit_match, "back"),
        )):
            self.button(label, (x + 42, y + 137 + index * 57, 436, 46), action, primary=index == 0, icon=icon)

    def results(self):
        state = self.state
        height = 527 if self.arena_setup else 460
        x, y = (self.width - 638) // 2, (self.height - height) // 2
        tone = a.TEAM[state.winner] if state.winner >= 0 else a.MINT
        champion = f"{TEAMS[state.winner]} wins" if state.winner >= 0 else "Match drawn"
        a.panel(self.canvas, (x, y, 638, height), color=(10, 32, 47), border=a.shade(a.PANEL, tone, .76), radius=22)
        a.icon(self.canvas, "peak", (self.width // 2, y + 42), tone, 40)
        a.text(self.canvas, champion, self.width // 2, y + 73, 55, tone, "display", "midtop")
        a.text(self.canvas, f"{state.reason}  ·  Round {state.round}  ·  Seed {state.seed}",
               self.width // 2, y + 149, 16, a.MUTED, "mono", "midtop")
        for team in range(2):
            cx = x + 31 + 293 * team
            tc = a.TEAM[team]
            a.panel(self.canvas, (cx, y + 196, 282, 101), color=a.shade(a.NIGHT, tc, .1),
                    border=a.shade(a.PANEL, tc, .52), radius=12)
            self.canvas.blit(a.penguin(63, team, 0), (cx + 10, y + 211))
            a.text(self.canvas, TEAMS[team], cx + 82, y + 210, 23, tc, "strong")
            a.text(self.canvas, self.controls[team], cx + 82, y + 244, 17, a.MUTED)
            a.text(self.canvas, f"{state.scores[team]:02}", cx + 264, y + 248, 45, a.INK, "mono", "midright")
            if self.arena_setup:
                decisions, effort, duration = self.stats[team]
                metric = "nodes" if self.controls[team] == "Minimax" else "sims"
                a.text(self.canvas, f"{decisions} decisions · {effort:,} {metric}", cx + 4, y + 316, 15, a.MUTED, "mono")
                a.text(self.canvas, f"{(duration / max(1, decisions)) * 1000:.0f} ms mean decision",
                       cx + 4, y + 341, 15, a.MUTED, "mono")
        bottom = y + height - 86
        self.button("Rematch", (x + 31, bottom, 282, 48), self.restart, primary=True, icon="restart")
        self.button("Main menu", (x + 324, bottom, 282, 48), self.exit_match, icon="back")

    def render(self):
        self.buttons.clear()
        self.canvas.blit(a.backdrop(self.canvas.get_size(), self.page == "home"), (0, 0))
        if self.page != "match":
            self.flakes()
        {
            "home": self.home,
            "setup": self.setup_view,
            "help": self.help_view,
            "settings": self.settings,
            "match": self.match_view,
        }[self.page]()
        self.screen.fill((5, 15, 25))
        content = self.canvas if self.canvas.get_size() == self.viewport.size else pg.transform.smoothscale(
            self.canvas, self.viewport.size)
        self.screen.blit(content, self.viewport)
        pg.display.flip()

    def event(self, event):
        if event.type == pg.QUIT:
            self.running = False
        elif event.type == pg.VIDEORESIZE:
            if not self.preferences["fullscreen"]:
                self.window_size = (event.w, event.h)
            self.layout()
        elif event.type == pg.MOUSEMOTION:
            self.pointer = self.logical(event.pos)
        elif event.type == pg.MOUSEBUTTONDOWN:
            self.pointer = self.logical(event.pos)
            self.click(self.pointer, event.button)
        elif event.type == pg.KEYDOWN:
            self.key(event)

    def close(self):
        self.cancel_search()
        self.pool.shutdown(wait=True, cancel_futures=True)
        a.font.cache_clear()
        pg.quit()

    def run(self):
        try:
            while self.running:
                elapsed = min(.075, self.clock.tick(60) / 1000)
                if self.modal not in ("pause", "match_settings"):
                    self.time += elapsed
                for event in pg.event.get():
                    self.event(event)
                self.update()
                self.render()
        finally:
            self.close()


if __name__ == "__main__":
    Game().run()

