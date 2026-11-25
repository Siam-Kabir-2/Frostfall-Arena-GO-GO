"""Mode selection, autonomous runs, and a synchronized two-lane race."""

import pygame as pg

from cave import AIR, FLOOR, GOAL, HEIGHT, WIDTH, Cave
from dive import Dive
from pilot import Pilot
from scene import CORAL, EDGE, GOLD, INK, MINT, MUTED, NIGHT, Scene, card, label


MODES = (
    ("solo", "Solo Dive", "Swim and bring fish back yourself."),
    ("watch", "Watch AI Dive", "Watch a diver plan routes and evade Deepfin."),
    ("race", "AI vs AI", "Race A* against Greedy Best-First on the same cave seed."),
)
ALGORITHMS = ("A*", "Greedy Best-First")
RACE_LIMIT = 60
MENU_BUTTONS = tuple(pg.Rect(57, 337+76*index, 500, 64) for index in range(len(MODES)))


class Run:
    def __init__(self, mode, seed):
        self.mode = mode
        self.seed = seed
        cave = Cave(seed, race=mode == "race")
        self.games = [Dive(seed, cave=cave) for _ in range(2 if mode == "race" else 1)]
        if mode == "race":
            self.games[1].greedy = True
        self.pilots = [Pilot() for _ in self.games] if mode != "solo" else []
        for game in self.games:
            game.show_route = bool(self.pilots)
        self.paused = False
        self.result = None

    @property
    def finished(self):
        return bool(self.result if self.mode == "race" else self.games[0].finished)

    def step(self, dt, controls):
        if self.paused or self.finished:
            return
        for index, game in enumerate(self.games):
            if not game.finished:
                direction = self.pilots[index].direction(game, dt) if self.pilots else controls
                game.step(dt, direction)
        if self.mode == "race":
            self.check_race()

    def set_pause(self, paused):
        if not self.finished:
            self.paused = paused
            for game in self.games:
                game.paused = paused

    def switch_search(self):
        if self.mode != "race":
            self.games[0].cycle_search()
            if self.pilots:
                self.pilots[0].route_age = 0.

    def toggle_routes(self):
        for game in self.games:
            game.show_route = not game.show_route

    def check_race(self):
        winners = [index for index, game in enumerate(self.games) if game.finished == "win"]
        if len(winners) == 2:
            self.result = "Tie · both divers finished on the same frame"
        elif winners:
            self.result = f"{ALGORITHMS[winners[0]]} wins the race"
        elif all(game.finished == "lost" for game in self.games) or max(game.seconds for game in self.games) >= RACE_LIMIT:
            first, second = (game.banked for game in self.games)
            self.result = ("Tie · the divers banked the same number of fish" if first == second else
                           f"{ALGORITHMS[int(second>first)]} wins on banked fish")


def menu(canvas, scene, preview, mouse):
    scene.draw(canvas, preview, chrome=False)
    film = pg.Surface((WIDTH, HEIGHT), pg.SRCALPHA)
    film.fill((3, 23, 36, 92))
    canvas.blit(film, (0, 0))
    card(canvas, (35, 167, 544, 451))
    label(canvas, "FROSTFALL", 58, 185, 15, MINT, "bold")
    label(canvas, "UNDER THE ICE", 55, 200, 67, INK, "display")
    label(canvas, "Choose how to dive", 58, 286, 21, MUTED)
    for index, ((_, title, detail), button) in enumerate(zip(MODES, MENU_BUTTONS)):
        active = button.collidepoint(mouse)
        tone = MINT if active else EDGE
        pg.draw.rect(canvas, (20, 53, 65) if active else (14, 40, 54), button, border_radius=9)
        pg.draw.rect(canvas, tone, button, width=1, border_radius=9)
        label(canvas, f"{index+1}", button.x+15, button.y+12, 24, MINT, "display")
        label(canvas, title, button.x+45, button.y+7, 25, INK, "bold")
        label(canvas, detail, button.x+45, button.y+35, 15, MUTED)
    label(canvas, "ESC  Exit", 58, 579, 15, MUTED, "bold")


def draw_run(canvas, frame, scene, run):
    if run.mode != "race":
        pilot = run.pilots[0] if run.pilots else None
        scene.draw(canvas, run.games[0], pilot_route=pilot.route if pilot else None, automated=bool(pilot))
        if pilot:
            label(canvas, "WATCH AI", 480, 42, 13, MINT, "bold", "topright")
        return

    canvas.fill((8, 27, 40))
    label(canvas, "FROSTFALL / UNDER THE ICE", 32, 25, 14, MINT, "bold")
    label(canvas, "AI VS AI", 30, 47, 64, INK, "display")
    label(canvas, f"Same cave / First to bank {GOAL} fish", WIDTH-32, 55, 22, INK, "bold", "topright")
    label(canvas, f"Seed {run.seed}", WIDTH-32, 86, 15, MUTED, anchor="topright")
    for index, color in enumerate((MINT, GOLD)):
        x, y, w = 27+index*620, 143, 606
        card(canvas, (x, y, w, 465))
        game, pilot = run.games[index], run.pilots[index]
        label(canvas, ALGORITHMS[index], x+16, y+11, 36, color, "display")
        label(canvas, f"{game.banked} / {GOAL} fish banked", x+w-16, y+24, 19, INK, "bold", "topright")
        scene.draw(frame, game, chrome=False, pilot_route=pilot.route)
        section = frame.subsurface((0, 117, WIDTH, FLOOR-117))
        view = pg.transform.smoothscale(section, (w-24, 276))
        canvas.blit(view, (x+12, y+65))
        label(canvas, f"Carrying  {len(game.haul)}", x+16, y+356, 16, INK, "bold")
        label(canvas, f"Lives  {game.lives}", x+150, y+356, 16, INK, "bold")
        label(canvas, f"{game.air:.1f}s air", x+w-16, y+356, 16, color, "bold", "topright")
        pg.draw.rect(canvas, EDGE, (x+16, y+386, w-32, 7), border_radius=3)
        fill = round((w-32)*game.air/AIR)
        if fill:
            pg.draw.rect(canvas, CORAL if game.air < 4.5 else color, (x+16, y+386, fill, 7), border_radius=3)
        status = "Finished" if game.finished == "win" else "Out of lives" if game.finished == "lost" else (
            "Heading to an opening" if pilot.returning else "Looking for fish")
        label(canvas, f"{status}  /  {game.seconds:.1f}s", x+16, y+412, 17, INK, "bold")
        label(canvas, f"{pilot.explored} nodes explored", x+w-16, y+414, 15, MUTED, anchor="topright")
    remaining = max(0., RACE_LIMIT-max(game.seconds for game in run.games))
    title = run.result or ("Race paused" if run.paused else f"{remaining:.0f}s left")
    label(canvas, title, WIDTH/2, 650, 34, GOLD if run.result else INK, "display", "midtop")
    label(canvas, "G  Routes    /    P  Pause    /    R  Replay    /    N  New cave    /    ESC  Modes",
          WIDTH/2, 716, 16, MUTED, "bold", "midtop")
