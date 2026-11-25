"""Playable 3D client for the Icebound Docks fork."""

from threading import Event

from panda3d.core import LineSegs

from .client3d import Frostfall3D
from .docks import (DOCK_INDEX, DOCKS, DOCK_NAMES, LINKS, Turn, advance, attacker_moves,
                    defender_moves, new_match, open_routes, slide)
from .docks_ai import search
from .docks_hud import DocksHUD
from .rules import destinations, label
from .stage3d import BITE_GAP, BITE_LENGTH, CORAL, FIRST_BITE, GOLD, MINT, TEAM, TOP, VIOLET, center, circle, outline


MUTED_COLOR = (.56, .73, .82, 1)


class IceboundDocks3D(Frostfall3D):
    def __init__(self, window_type="onscreen", audio_enabled=True):
        self.routes = self.orders = None
        self.routes_key = self.orders_key = None
        self.animation_board = None
        self.playback = []
        super().__init__(window_type, audio_enabled, hud_type=DocksHUD)

    @property
    def match_mode(self):
        return "ICEBOUND DOCKS"

    @staticmethod
    def make_match(seed, first):
        return new_match(seed, first)

    def board_state(self):
        return self.animation_board if self.animation_board is not None else self.state

    def home(self):
        self.animation_board = None
        self.playback.clear()
        super().home()
        self.clear_draft()

    def launch(self, seed=None, first=None):
        self.animation_board = None
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
        self.defender_order = self.attacker_order = None
        self.draft_board = self.state
        self.plan_actions = ()
        self.phase = "idle"
        self.brace = False
        self.selected = self.cursor = self.hover = None
        self.options_key = None
        self.invalidate()

    def start_draft(self):
        self.clear_draft()
        self.plan_actions = defender_moves(self.state)
        if self.plan_actions:
            self.set_phase("defender", self.team * 2 + 1)
        else:
            self.prepare_attacker()

    def set_phase(self, phase, piece):
        self.phase = phase
        self.selected = piece
        self.cursor = self.state.positions[piece] if piece is not None else None
        self.hover = None
        self.hud.focus = -1
        self.options_key = None
        self.invalidate()

    def prepare_attacker(self):
        self.brace = False
        self.draft_board = slide(self.state, self.defender_order)
        self.plan_actions = attacker_moves(self.draft_board)
        if self.plan_actions:
            self.set_phase("attacker", self.team * 2)
        else:
            self.set_phase("ready", None)

    @property
    def can_undo(self):
        return self.actionable and (self.defender_order is not None or self.attacker_order is not None)

    def undo_order(self):
        if not self.can_undo:
            return
        if self.attacker_order is not None:
            self.attacker_order = None
            self.prepare_attacker()
        else:
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

    def can_brace(self):
        return (self.actionable and self.phase == "defender"
                and any(action.kind == "brace" for action in self.plan_actions))

    def toggle_brace(self):
        if self.can_brace():
            self.brace = not self.brace
            self.options_key = None
            self.invalidate()

    def current_actions(self):
        if not self.actionable:
            return {}
        kind = "brace" if self.brace else "move"
        return {action.target: action for action in self.plan_actions if action.kind == kind}

    def select(self, piece):
        if piece == self.selected:
            self.cursor = self.state.positions[piece]

    def pick(self, cell):
        action = self.current_actions().get(cell)
        if action is None:
            return
        self.sounds.play("click")
        if self.phase == "defender":
            self.defender_order = action
            self.prepare_attacker()
        elif self.phase == "attacker":
            self.attacker_order = action
            self.plan_actions = ()
            self.set_phase("ready", None)

    def confirm(self):
        if self.actionable and self.phase == "ready" and self.hud.focus < 0:
            self.commit()
        else:
            super().confirm()

    def commit(self):
        if self.actionable and self.phase == "ready":
            self.apply(Turn(self.defender_order, self.attacker_order))

    def order_summary(self, role, action):
        if action:
            start = self.state.positions[action.penguin]
            prefix = "Brace " if action.kind == "brace" else ""
            return f"{prefix}{label(start)} to {label(action.target)}"
        if self.actionable and self.phase == role.lower():
            return "Choose a floe"
        if self.actionable and (self.phase == "ready" or (role == "Defender" and self.phase == "attacker")):
            return "Trapped · skips"
        return "Waiting"

    def move_hint(self):
        if self.state.over and self.animation_board is None:
            return "Match complete", self.state.reason, MINT
        if self.delay > 0 or self.animation_board is not None:
            return "Playing the turn", "Defender slides first, then the Attacker.", MUTED_COLOR
        if self.controllers[self.team] != "Human":
            return f"{self.controllers[self.team]} is thinking", "Comparing pairs of slides.", TEAM[self.team]
        if self.phase == "ready":
            return "Orders ready", "Confirm to play both moves, or undo to change a destination.", MINT
        defender = self.phase == "defender"
        role, color = ("Defender", VIOLET) if defender else ("Attacker", MINT)
        option = self.current_actions().get(self.hover)
        if option is None:
            detail = "Choose a lit floe. Use Brace to keep this floe open." if defender else (
                "Choose a lit floe on the board left by the Defender's slide.")
            return f"Choose the {role}", detail, color
        board = self.state if defender else self.draft_board
        projected = slide(board, option)
        description = []
        if projected.owners != board.owners:
            description.append(f"Claim {DOCK_NAMES[DOCK_INDEX[option.target]]} dock.")
        cut = [(a, b) for a, b, paths in LINKS if open_routes(board, paths) and not open_routes(projected, paths)]
        if cut:
            a, b = cut[0]
            description.append(f"Cuts the {DOCK_NAMES[a]}–{DOCK_NAMES[b]} link.")
            color = CORAL
        if defender and not cut:
            foes = (2 - self.team*2, 3 - self.team*2)
            removed = sum(len(set(destinations(board, piece)) - set(destinations(projected, piece))) for piece in foes)
            if removed:
                description.append(f"Removes {removed} rival destinations.")
        if not description:
            description.append("Starting floe stays open." if projected.has_ice(board.positions[option.penguin]) else
                               "Starting floe sinks.")
        return f"{role} to {label(option.target)} · +{board.fish[option.target]} fish", " ".join(description), color

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
            self.delay = .12

    def play_next(self):
        action = self.playback.pop(0)
        before = self.animation_board
        self.animation_board = slide(before, action)
        origin = before.positions[action.penguin]
        travel = .29
        self.arena.slide(action.penguin, origin, action.target, False, travel)
        if action.kind == "brace":
            self.arena.brace_effect(origin)
        elif origin not in DOCK_INDEX:
            self.arena.fracture(origin, delay=.08)
            self.sound_queue.append((self.match_time+.16, "break"))
        meal = 0.
        if before.fish[action.target]:
            meal = self.arena.collect_fish(action.penguin, action.target, delay=travel)
            if meal:
                for index in range(len(self.arena.meal.fish)):
                    when = travel + FIRST_BITE + index*BITE_GAP + BITE_LENGTH*.82
                    self.sound_queue.append((self.match_time+when, "bite"))
        self.delay = travel + max(.08, meal)
        self.sounds.play("warden" if action.kind == "brace" else "move")
        self.arena.sync(self.animation_board)

    def finish_playback(self):
        self.animation_board = None
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
                if self.phase == "ready":
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

    def draw_links(self):
        state = self.board_state()
        key = state.fish, state.empty_ice, state.owners
        if key == self.routes_key:
            return
        self.routes_key = key
        if self.routes is not None:
            self.routes.removeNode()
        self.routes = self.arena.overlay.attachNewNode("Dock routes and flags")
        lines = LineSegs("Ice links")
        lines.setThickness(2.5)
        for a, b, paths in LINKS:
            intact = open_routes(state, paths)
            owner = state.owners[a]
            shared = owner >= 0 and owner == state.owners[b]
            for path in paths:
                color = TEAM[owner] if shared else (.57, .96, .95, 1)
                lines.setColor(*(color if path in intact else (.34, .53, .64, .65)))
                for start, end in zip(path, path[1:]):
                    if state.has_ice(start) and state.has_ice(end):
                        lines.moveTo(center(start, TOP+.038))
                        lines.drawTo(center(end, TOP+.038))
        self.routes.attachNewNode(lines.create())
        for dock, cells in enumerate(DOCKS):
            owner = state.owners[dock]
            color = GOLD if owner < 0 else TEAM[owner]
            for cell in cells:
                ring = outline("Dock platform", self.routes, circle(.355), .87, color)
                ring.setPos(center(cell, TOP+.044))

    def draw_orders(self):
        orders = (self.defender_order, self.attacker_order) if self.actionable else (None, None)
        key = self.state.positions, orders
        if key == self.orders_key:
            return
        self.orders_key = key
        if self.orders is not None:
            self.orders.removeNode()
        self.orders = self.arena.overlay.attachNewNode("Planned slides")
        for action, color in zip(orders, (VIOLET, MINT)):
            if action is None:
                continue
            origin = self.state.positions[action.penguin]
            start, end = center(origin, TOP+.08), center(action.target, TOP+.08)
            route = LineSegs("Planned slide")
            route.setThickness(3)
            route.setColor(*color)
            for index in range(10):
                route.moveTo(start + (end-start)*(index/10))
                route.drawTo(start + (end-start)*((index+.61)/10))
            self.orders.attachNewNode(route.create())
            ring = outline("Planned landing", self.orders, circle(.285), .87, color)
            ring.setPos(end)

    def update(self, dt):
        super().update(dt)
        self.draw_links()
        self.draw_orders()
