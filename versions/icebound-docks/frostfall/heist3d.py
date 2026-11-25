"""A playable 3D Fish Heist match using the shared Frostfall renderer."""

from random import SystemRandom
from threading import Event

from panda3d.core import TextNode, Vec4

from .client3d import BoardWindow
from .heist import CAPACITY, DOCKS, GOAL, ROUNDS, SIZE, advance, board_cell, cell_label, display_cell, legal, new_heist
from .heist_ai import DEPTH, SIMULATIONS, search_heist
from .hud3d import EDGE, HUD, INK, MUTED, NIGHT
from .rules import Action, State, TEAMS
from .stage3d import CORAL, GOLD, MINT, TEAM, TOP, center, circle, clipped_square, flat_shape, outline

ICE = frozenset(display_cell(cell) for cell in range(SIZE ** 2))
PREVIEW_SEED = 610830


class HeistHUD(HUD):
    def scores(self, game):
        s = self.s
        state = game.state
        span = (174 if self.compact else 216) * s
        middle = self.w / 2
        round_width = 68 * s
        for team, x in enumerate((middle - round_width / 2 - span - 8*s, middle + round_width / 2 + 8*s)):
            h, y = 69*s, 19*s
            color = TEAM[team]
            self.plate(x, y, span, h, color, strong=state.active == team and game.page == "match")
            self.text(TEAMS[team].upper(), x + 13*s, y + 22*s, 14, color, "label")
            self.text(game.players[team].upper(), x + span - 13*s, y + 21*s, 10, MUTED, "label", TextNode.ARight)
            self.text(str(state.bank[team]), x + 13*s, y + 58*s, 35, INK, "heavy")
            self.text(f"/ {GOAL} BANKED", x+37*s, y+55*s, 11, MUTED, "label")
            carry_x = x + span - 63*s
            self.symbol("fish", carry_x, y+46*s, 15, GOLD)
            self.text(f"{state.carry[team]} / {CAPACITY}", carry_x+15*s, y+51*s, 13, GOLD, "label")
        self.plate(middle-round_width/2, 26*s, round_width, 56*s, EDGE)
        self.text("ROUND", middle, 47*s, 10, MUTED, "label", TextNode.ACenter)
        self.text(str(state.round), middle, 72*s, 25, INK, "heavy", TextNode.ACenter)

    def scene(self, game):
        s, x = self.s, self.margin
        if not self.compact:
            self.fade_left(278*s, 478*s)
            self.text("FISH HEIST", x, 61*s, 47, INK, "heavy")
            self.text("FROSTFALL ARENA", x+3*s, 82*s, 12, MINT, "label")
        self.scores(game)
        if self.compact:
            self.text("FISH HEIST", x, 129*s, 29, INK, "heavy")
        right = self.w-x
        y = 105*s if self.compact else 30*s
        self.button("View", (right-150*s, y, 68*s, 37*s), game.toggle_view)
        self.button("Pause", (right-75*s, y, 75*s, 37*s), game.toggle_pause)
        self.blocked.append((0, 0, self.w, (152 if self.compact else 98)*s))
        title, hint, color = game.hint()
        if self.compact:
            panel, panel_w, panel_h = self.h-185*s, self.w-x*2, 113*s
        else:
            panel, panel_w, panel_h = 258*s, 306*s, 138*s
            accent = TEAM[game.state.active]
            self.plate(x, 133*s, panel_w, 104*s, accent, strong=True)
            self.text("FIRST TO EIGHT BANKED", x+16*s, 161*s, 12, accent, "label")
            self.text("MATCH COMPLETE" if game.state.over else f"{TEAMS[game.state.active].upper()} TURN",
                      x+16*s, 214*s, 41, INK, "heavy")
        self.plate(x, panel, panel_w, panel_h, color, strong=True)
        self.text(title, x+16*s, panel+39*s, 24 if not self.compact else 21, color, "heavy")
        self.paragraph(hint, x+16*s, panel+69*s, panel_w-30*s, 16, INK, lines=3)
        if not self.compact:
            for index, (symbol, headline, body, tint) in enumerate((
                ("play", "SKATE", "Collect fish you pass over.", MINT),
                ("fish", "BANK", "Land on your matching dock.", GOLD),
                ("attack", "BUMP", "Click an adjacent rival to spill a fish.", CORAL),
            )):
                line = panel + (167+66*index)*s
                self.symbol(symbol, x+15*s, line+9*s, 19, tint)
                self.text(headline, x+37*s, line+10*s, 18, tint, "heavy")
                self.text(body, x+37*s, line+33*s, 14, MUTED)
        if game.flash:
            message, tint = game.flash
            mid = self.w / 2 if self.compact else (self.w+316*s)/2
            top = (158 if self.compact else 105)*s
            self.plate(mid-134*s, top, 268*s, 47*s, tint, strong=True)
            self.text(message, mid, top+32*s, 25, tint, "heavy", TextNode.ACenter)
        y = self.h-46*s
        self.shape(0, y, self.w, 46*s, NIGHT)
        self.text("Click a lit tile   •   Arrows + Enter   •   V View   •   Esc Pause",
                  x, y+28*s, 13, MUTED, "label")
        if not self.compact:
            self.text(f"ROUND LIMIT {ROUNDS}   /   SEED {game.state.seed}", right, y+28*s, 12, MUTED,
                      "label", TextNode.ARight)
        self.blocked.append((x, panel, panel_w, panel_h))
        self.blocked.append((0, y, self.w, 46*s))

    def draw_heist(self, game, width, height):
        self.begin(width, height)
        self.scene(game)
        if game.page == "menu":
            s = self.s
            x, y, w, h = self.dialog("Fish Heist", "Grab a haul. Get it home before your rival cuts you off.", 555, 416)
            for index, (title, players) in enumerate((
                ("Play vs Minimax", ("Human", "Minimax")), ("Play vs MCTS", ("Human", "MCTS")),
                ("Local duel", ("Human", "Human")), ("Watch Minimax vs MCTS", ("Minimax", "MCTS")),
            )):
                self.button(title, (x+30*s, y+(124+60*index)*s, w-60*s, 48*s),
                            lambda players=players: game.start(players), primary=index == 0, arrow=True)
        elif game.page == "pause":
            s = self.s
            x, y, w, h = self.dialog("Match paused", "", 420, 300)
            for index, (text, action) in enumerate((
                ("Resume", game.toggle_pause), ("Restart this board", game.rematch), ("Main menu", game.menu)
            )):
                self.button(text, (x+29*s, y+(105+55*index)*s, w-58*s, 43*s), action, primary=index == 0)
        elif game.page == "result":
            s = self.s
            state = game.state
            title = "Draw" if state.winner < 0 else f"{TEAMS[state.winner]} wins"
            x, y, w, h = self.dialog(title, f"{state.bank[0]}–{state.bank[1]} banked  •  Round {state.round}", 502, 317)
            if "Human" not in game.players:
                text = f"Minimax depth {DEPTH}   •   MCTS {SIMULATIONS} simulations"
                self.text(text, x+32*s, y+142*s, 16, GOLD, "label")
                first = game.players[game.opener]
                self.text(f"{first} opened on seed {state.seed}", x+32*s, y+169*s, 14, MUTED)
            label = "Rematch · swap opener" if "Human" not in game.players else "Rematch"
            self.button(label, (x+30*s, y+h-109*s, w-60*s, 43*s), game.rematch, primary=True, arrow=True)
            self.button("Main menu", (x+30*s, y+h-56*s, w-60*s, 36*s), game.menu)


class FishHeist3D(BoardWindow):
    def __init__(self, window_type="onscreen", audio_enabled=True):
        super().__init__(window_type, audio_enabled, hud_type=HeistHUD)
        self.players = ("Human", "Minimax")
        self.opener = 0
        self.state = new_heist(PREVIEW_SEED)
        self.docks()
        self.carried_models = self.make_cargo()
        self.overhead = False
        self.key_cursor = None
        self.prev_mouse = None
        self.camera_key = None
        self.art_key = None
        self.hud_key = None
        self.menu()
        for event, fn in {"mouse1": self.click, "escape": self.toggle_pause, "p": self.toggle_pause,
                          "v": self.toggle_view, "enter": self.confirm, "space": self.confirm,
                          "tab": self.next_button}.items():
            self.accept(event, fn)
        for event, delta in {"arrow_up": (-1, 0), "arrow_down": (1, 0),
                             "arrow_left": (0, -1), "arrow_right": (0, 1)}.items():
            self.accept(event, self.aim, list(delta))
        self.update(0)
        self.taskMgr.add(self.tick, "Fish Heist frame")

    def docks(self):
        for team, cell in enumerate(DOCKS):
            anchor = self.arena.overlay.attachNewNode(f"{TEAMS[team]} bank dock")
            anchor.setPos(center(display_cell(cell), TOP + .019))
            accent = TEAM[team]
            outline("Dock inlay", anchor, clipped_square(.415, .12), .84, accent)
            outline("Mooring ring", anchor, circle(.25), .95, accent).setZ(.001)
            flat_shape("Dock plaque", anchor, ((-.202, -.405), (.202, -.405), (.245, -.335), (.202, -.267),
                                              (-.202, -.267), (-.245, -.335)), NIGHT, .008)
            name = TextNode("Bank sign")
            name.setFont(self.fonts["label"])
            name.setText("BANK")
            name.setAlign(TextNode.ACenter)
            name.setTextColor(*accent)
            title = anchor.attachNewNode(name)
            title.setPos(0, -.373, .013)
            title.setP(-90)
            title.setScale(.112)

    def make_cargo(self):
        models = []
        for team in range(2):
            pawn = self.arena.pieces[team * 2]
            pile = []
            for number in range(CAPACITY):
                fish = self.arena.fish_model.copyTo(pawn)
                fish.setScale(.72)
                fish.setPos((number-1.5)*.112, -.219, .27 + .04*(number % 2))
                fish.setHpr(-64, 12, -20)
                pile.append(fish)
            models.append(pile)
        return models

    def sync_art(self, restart=False):
        state = self.state
        art_fish = [0] * 64
        for cell, amount in enumerate(state.fish):
            art_fish[display_cell(cell)] = amount
        a, b = map(display_cell, state.positions)
        self.art = State(state.seed, False, self.opener, tuple(art_fish), positions=(a, -1, b, -1),
                         scores=state.bank, active=state.active, round=state.round, over=state.over, winner=state.winner)
        self.arena.sync(self.art, restart=restart, intact=ICE)
        for player, cell in enumerate(DOCKS):
            self.arena.tiles[display_cell(cell)].ice.setShaderInput("frost_tint", Vec4(*TEAM[player][:3], .35))
            for index, fish in enumerate(self.carried_models[player]):
                fish.show() if state.carry[player] > index else fish.hide()

    def menu(self):
        self.stop_search()
        self.hud.focus = -1
        self.page = "menu"
        self.delay = 0.
        self.flash = None
        self.flash_time = 0.
        self.key_cursor = None
        self.sync_art(restart=True)

    def start(self, players, seed=None, opener=0):
        self.stop_search()
        self.players, self.opener = players, opener
        if seed is None:
            seed = SystemRandom().randrange(100000, 1000000)
        self.state = new_heist(seed, opener)
        self.page = "match"
        self.delay = .08
        self.flash = None
        self.flash_time = 0.
        self.key_cursor = None
        self.hud.focus = -1
        self.sync_art(restart=True)

    def rematch(self):
        first = 1 - self.opener if "Human" not in self.players else self.opener
        self.start(self.players, self.state.seed, first)

    def toggle_pause(self):
        if self.page in ("match", "pause"):
            self.page = "pause" if self.page == "match" else "match"
            self.hud.focus = -1

    def toggle_view(self):
        self.overhead = not self.overhead

    def next_button(self):
        if self.hud.buttons:
            self.hud.focus = (self.hud.focus + 1) % len(self.hud.buttons)

    @property
    def can_move(self):
        return (self.page == "match" and self.delay <= 0 and not self.state.over
                and self.players[self.state.active] == "Human")

    def targets(self):
        if not self.can_move:
            return {}
        actions = legal(self.state)
        rival = self.state.positions[1-self.state.active]
        return {rival if action.kind == "bump" else action.target: action for action in actions}

    def aim(self, dy, dx):
        if not self.can_move:
            return
        self.hud.focus = -1
        cell = self.state.positions[self.state.active] if self.key_cursor is None else self.key_cursor
        row, col = divmod(cell, SIZE)
        self.key_cursor = max(0, min(SIZE-1, row+dy)) * SIZE + max(0, min(SIZE-1, col+dx))

    def confirm(self):
        if 0 <= self.hud.focus < len(self.hud.buttons):
            self.hud.buttons[self.hud.focus].action()
        elif self.page == "menu":
            self.start(("Human", "Minimax"))
        elif self.key_cursor in self.targets():
            self.apply(self.targets()[self.key_cursor])

    def click(self):
        pointer, pixels = self.mouse_position()
        self.hud.focus = -1
        self.key_cursor = None
        if self.hud.handle_click(pixels):
            self.sounds.play("click")
            return
        if pointer and not self.hud.contains(pixels):
            action = self.targets().get(self.hit_cell(pointer))
            if action:
                self.apply(action)

    def hit_cell(self, pointer):
        return board_cell(self.arena.pick(self.cam, self.lens, pointer, self.art.positions))

    def hint(self):
        state = self.state
        if state.over:
            return "HAUL COMPLETE", "Banked fish decide the winner.", GOLD
        if self.delay > 0:
            return "ON THE ICE", "Watch the move resolve.", MINT
        if self.players[state.active] != "Human":
            return f"{self.players[state.active].upper()} THINKING", "The rival is planning its next route.", TEAM[state.active]
        action = self.targets().get(self.hover)
        if action:
            _, recap = advance(state, action, validate=False)
            if action.kind == "bump":
                title = "BUMP" + ("  /  SPILL 1 FISH" if recap.spilled else "")
                text = f"Push the rival to {cell_label(action.target)}."
                if recap.rival_banked:
                    text += f" They bank {recap.rival_banked} fish on that dock."
                return title, text, CORAL
            title = f"{cell_label(action.target)}  /  "
            if recap.banked:
                return title + f"BANK {recap.banked}", "This haul counts toward victory.", GOLD
            if recap.caught:
                return title + f"CATCH {recap.caught}", "Carry your haul back to your matching dock.", MINT
            return title + "SKATE", "Reposition to get home or cut off your rival.", MINT
        if state.carry[state.active] >= CAPACITY:
            return "FULL HAUL", "Bank your fish at your matching dock to free up space.", GOLD
        return "PICK A ROUTE", "Hover over lit ice to preview the move. Click to skate.", MINT

    def apply(self, move):
        old = self.state
        self.state, report = advance(old, move)
        bump = move.kind == "bump"
        piece = (1-old.active if bump else old.active)
        origin = old.positions[piece]
        self.arena.slide(piece*2, display_cell(origin), display_cell(move.target), bump, .34 if bump else .30)
        self.delay = .45 if bump else .36
        self.flash = None
        self.key_cursor = None
        self.sounds.play("strike" if bump else "move")
        if report.banked or report.rival_banked:
            self.flash = f"+{report.banked or report.rival_banked} BANKED", GOLD
            self.sounds.play("result")
        elif report.spilled:
            self.flash = "FISH SPILLED", CORAL
        elif report.caught:
            self.flash = f"+{report.caught} CARRIED", MINT
            self.sounds.play("bait")
        self.flash_time = 1.16
        self.sync_art()

    def advance_turn(self):
        state = self.state
        if state.over:
            self.hud.focus = -1
            self.page = "result"
            return
        opponent = self.players[state.active]
        if opponent == "Human":
            return
        if self.future is None:
            self.cancel = Event()
            self.future = self.pool.submit(search_heist, state, opponent, self.cancel.is_set)
        elif self.future.done():
            decision = self.future.result()
            self.future = None
            self.apply(decision.action)

    def fit_camera(self, w, h):
        key = (w, h, self.overhead)
        if key == self.camera_key:
            return
        self.camera_key = key
        compact = w/h < 1.36
        s = max(.53, min(1.32, h/900, w/(680 if compact else 1140)))
        room_w = max(1, w - (44 if compact else 368)*s)
        room_h = max(1, h - (353 if compact else 149)*s)
        pixels = min(room_w/8.35, room_h/(7.62 if self.overhead else 7.33))
        fw, fh = w/pixels, h/pixels
        middle_x = .5 if compact else .5 + 163*s/w
        middle_y = .46 if compact else .52
        self.camera.setPos(0, -.24, 28) if self.overhead else self.camera.setPos(3.2, -14.5, 20.5)
        self.camera.lookAt(0, 0, 0)
        self.lens.setFilmSize(fw, fh)
        self.lens.setFilmOffset((.5-middle_x)*fw, (middle_y-.5)*fh)
        self.arena.root.setShaderInput("eye", self.camera.getPos())

    def update(self, dt):
        w, h = self.viewport_size()
        self.fit_camera(w, h)
        self.arena.animate(dt if self.page != "pause" else 0, self.art, True)
        if self.page == "match":
            self.delay = max(0, self.delay - dt)
            self.flash_time -= dt
            if self.flash_time <= 0:
                self.flash = None
            if self.delay <= 0:
                self.advance_turn()
        mouse, pixels = self.mouse_position()
        if mouse != self.prev_mouse and mouse is not None:
            self.key_cursor = None
        self.prev_mouse = mouse
        cell = self.hit_cell(mouse) if mouse and not self.hud.contains(pixels) else None
        self.hover = self.key_cursor if self.key_cursor is not None else cell
        legal_here = self.targets()
        key = (self.state, self.hover, self.can_move, self.key_cursor)
        if key != self.art_key:
            self.art_key = key
            active = 2 * self.state.active
            ice_hover = display_cell(self.hover) if self.hover is not None else None
            lit = {display_cell(cell): Action("rescue" if move.kind == "bump" else "move", active, display_cell(cell))
                   for cell, move in legal_here.items()}
            self.arena.show_options(self.art, active if self.can_move else None, lit, ice_hover)
            self.arena.focus_tile(ice_hover if self.can_move and self.key_cursor is not None else None)
        hud_key = (w, h, self.page, self.state, self.players, self.delay > 0, self.hover, self.flash)
        if hud_key != self.hud_key:
            self.hud_key = hud_key
            self.hud.draw_heist(self, w, h)
        self.hud.focus_buttons(pixels)

