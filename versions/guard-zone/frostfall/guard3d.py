"""3D Guard Zone, staged input, and paired slide playback."""

from threading import Event

from .client3d import Frostfall3D
from .guard import Turn, advance, attacker_moves, defender_moves, new_match, slide, zones
from .guard_ai import search
from .guard_hud import GuardHUD
from .guard_stage import GuardArena
from .hud3d import MUTED
from .rules import label
from .stage3d import BITE_GAP, BITE_LENGTH, CORAL, FIRST_BITE, GOLD, MINT, TEAM, VIOLET


class GuardZone3D(Frostfall3D):
    def __init__(self, window_type="onscreen", audio_enabled=True):
        self.animation_board = None
        self.playback = []
        self.arriving = None
        super().__init__(window_type, audio_enabled, hud_type=GuardHUD, arena_type=GuardArena)
        self.accept("h", self.hold)

    @property
    def match_mode(self):
        return "GUARD ZONE"

    @staticmethod
    def make_match(seed, first):
        return new_match(seed, first)

    def board_state(self):
        return self.animation_board if self.animation_board is not None else self.state

    def home(self):
        self.animation_board = self.arriving = None
        self.playback.clear()
        super().home()
        self.clear_draft()

    def launch(self, seed=None, first=None):
        self.animation_board = self.arriving = None
        self.playback.clear()
        super().launch(seed, first)
        self.clear_draft()

    def start_match(self, players):
        self.local = players == ("Human", "Human")
        self.arena_mode = "Human" not in players
        if self.arena_mode:
            self.ai_teams = list(players)
        elif not self.local:
            self.opponent = players[1]
        self.launch()

    def clear_draft(self):
        self.defender_order = None
        self.draft_board = self.state
        self.set_phase("idle", None, ())

    def start_draft(self):
        self.clear_draft()
        options = defender_moves(self.state)
        if options:
            self.set_phase("defender", self.team * 2 + 1, options)
        else:
            self.prepare_attacker()

    def set_phase(self, phase, piece, options):
        self.phase, self.plan_actions = phase, options
        self.selected = piece
        self.cursor = self.state.positions[piece] if piece is not None else None
        self.hover = None
        self.hud.focus = -1
        self.options_key = None
        self.invalidate()

    def prepare_attacker(self, defender=None):
        self.defender_order = defender
        self.draft_board = slide(self.state, defender)
        options = attacker_moves(self.draft_board)
        if options:
            self.set_phase("attacker", self.team*2, options)
        else:
            self.set_phase("blocked", None, ())

    @property
    def can_undo(self):
        return self.actionable and self.phase in ("attacker", "blocked") and bool(defender_moves(self.state))

    def undo_order(self):
        if self.can_undo:
            self.start_draft()

    def clear_selection(self):
        self.undo_order()

    def escape(self):
        if self.page == "match" and self.modal is None:
            if self.can_undo:
                self.undo_order()
            else:
                self.toggle_pause()
        else:
            super().escape()

    def current_actions(self):
        return {action.target: action for action in self.plan_actions} if self.actionable else {}

    def select(self, piece):
        if piece == self.selected:
            self.cursor = self.state.positions[piece]

    def hold(self):
        if self.actionable and self.phase == "defender":
            self.prepare_attacker()

    def pick(self, cell):
        action = self.current_actions().get(cell)
        if action is None:
            return
        self.sounds.play("click")
        if self.phase == "defender":
            self.prepare_attacker(action)
        elif self.phase == "attacker":
            self.apply(Turn(self.defender_order, action))

    def confirm(self):
        if self.actionable and self.phase == "blocked" and self.hud.focus < 0:
            self.commit()
        else:
            super().confirm()

    def commit(self):
        if self.actionable and self.phase == "blocked":
            self.apply(Turn(self.defender_order))

    def move_hint(self):
        if self.state.over and self.animation_board is None:
            return "Match complete", self.state.reason, MINT
        if self.delay > 0 or self.animation_board is not None:
            return "Playing the turn", "Defender steps first, then the Attacker slides.", MUTED
        if self.controllers[self.team] != "Human":
            return f"{self.controllers[self.team]} is thinking", "Comparing guards and slides.", TEAM[self.team]
        if self.phase == "blocked":
            return "Attacker has no landing", "Finish the turn or undo and change the Defender's position.", GOLD
        option = self.current_actions().get(self.hover)
        if self.phase == "defender":
            if option is None:
                return "Choose a Defender step", "Hover to preview the guard zone. Press H to hold.", VIOLET
            _, _, overlap = zones(slide(self.state, option))
            detail = f"{len(overlap)} contested. Both teams can land there." if overlap else (
                "Enemy penguins can cross your guard. They must land outside it.")
            return f"Guard from {label(option.target)}", detail, VIOLET
        if option is None:
            if self.hover in zones(self.draft_board)[1-self.team]:
                return "Enemy guard", "You can slide across this floe and land farther down the lane.", CORAL
            return "Choose an Attacker slide", "Click a lit floe to play the turn and collect its fish.", MINT
        fish = self.draft_board.fish[option.target]
        origin = self.state.positions[option.penguin]
        details = []
        if origin in self.state.cracked:
            details.append(f"{label(origin)} sinks on departure.")
        if fish:
            details.append(f"{label(option.target)} cracks when you fish.")
        return f"Slide to {label(option.target)} · +{fish} fish", " ".join(details) or "Both floes stay intact.", MINT

    def apply(self, turn):
        before = self.state
        self.state, events = advance(before, turn)
        for event in events:
            self.log.insert(0, (event.kind, event.text))
        self.log = self.log[:24]
        self.clear_draft()
        self.animation_board = before
        self.playback = [action for action in (turn.defender, turn.attacker) if action is not None]
        if self.motion and self.playback:
            self.play_next()
        else:
            self.finish_playback()
            self.delay = .14

    def play_next(self):
        action = self.playback.pop(0)
        before = self.animation_board
        self.animation_board = slide(before, action)
        origin = before.positions[action.penguin]
        travel = .21 if action.penguin % 2 else .29
        self.arriving = action.target
        self.arena.slide(action.penguin, origin, action.target, False, travel)
        if not self.animation_board.has_ice(origin):
            self.arena.fracture(origin, delay=.08)
            self.sound_queue.append((self.match_time+.16, "break"))
        meal = 0.
        if before.fish[action.target] and action.penguin % 2 == 0:
            meal = self.arena.collect_fish(action.penguin, action.target, delay=travel)
            if meal:
                for index in range(len(self.arena.meal.fish)):
                    when = travel + FIRST_BITE + index*BITE_GAP + BITE_LENGTH*.82
                    self.sound_queue.append((self.match_time+when, "bite"))
        self.delay = travel + max(.05, meal)
        self.sounds.play("move")
        self.arena.sync(self.animation_board)

    def finish_playback(self):
        self.animation_board = self.arriving = None
        self.playback.clear()
        self.arena.sync(self.state)
        if self.state.over:
            self.sounds.play("result")
        self.invalidate()

    def update_rules(self):
        if self.page != "match" or self.modal or self.delay > 0:
            return
        if self.animation_board is not None:
            if self.playback and self.motion:
                self.play_next()
                return
            self.finish_playback()
        if self.state.over:
            self.open_modal("result")
            return
        if self.controllers[self.team] == "Human":
            if self.phase == "idle":
                self.start_draft()
                if self.phase == "blocked" and not self.can_undo:
                    self.commit()
            return
        if self.future is None:
            self.cancel = Event()
            self.future = self.pool.submit(search, self.state, self.controllers[self.team],
                                           self.difficulty, self.cancel.is_set)
        elif self.future.done():
            choice = self.future.result()
            self.future = None
            metrics = self.stats[self.team]
            metrics[0] += 1
            metrics[1] += choice.effort
            metrics[2] += choice.seconds
            self.apply(choice.action)

    def update(self, dt):
        super().update(dt)
        board = self.board_state()
        planned = None
        if self.actionable and self.phase == "defender":
            action = self.current_actions().get(self.hover)
            if action is not None:
                board, planned = slide(board, action), action.target
        elif self.actionable and self.defender_order is not None:
            board, planned = self.draft_board, self.defender_order.target
        cracked = board.cracked - {self.arriving} if self.arena.moving else board.cracked
        self.arena.show_guards(zones(board), cracked, planned)
