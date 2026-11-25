"""Launch the standalone Frostfall side-view diving game."""

import argparse
from array import array
from math import sin, tau
from random import SystemRandom

import pygame as pg

from cave import HEIGHT, WIDTH
from dive import Dive
from modes import MENU_BUTTONS, MODES, Run, draw_run, menu
from scene import Scene


DEFAULT_SEED = 610830
SIM_STEP = 1/60


class Audio:
    def __init__(self):
        self.muted = False
        self.sounds = {}
        config = pg.mixer.get_init()
        if config is None:
            return
        rate, _, channels = config
        tones = {"dive": (160, .16, -.36), "catch": (545, .16, .58), "bank": (444, .27, .69),
                 "lost": (203, .38, -.48), "win": (473, .58, .82)}
        for name, (frequency, duration, offset) in tones.items():
            samples = array("h")
            for frame in range(round(rate*duration)):
                seconds = frame/rate
                progress = seconds/duration
                amplitude = (1-progress)**2 * min(1, seconds*115)
                tone = sin(tau*frequency*seconds*(1+offset*progress))
                samples.extend([round(3800*amplitude*tone)]*channels)
            self.sounds[name] = pg.mixer.Sound(buffer=samples)

    def flush(self, game):
        if not self.muted:
            for name in dict.fromkeys(game.events):
                if name in self.sounds:
                    self.sounds[name].play()
        game.events.clear()


def read_controls():
    keys = pg.key.get_pressed()
    x = int(keys[pg.K_RIGHT] or keys[pg.K_d])-int(keys[pg.K_LEFT] or keys[pg.K_a])
    y = int(keys[pg.K_DOWN] or keys[pg.K_s])-int(keys[pg.K_UP] or keys[pg.K_w])
    direction = pg.Vector2(x, y)
    return direction.normalize() if direction.length_squared() > 1 else direction


def fit_window(screen):
    w, h = screen.get_size()
    size = min(w/WIDTH, h/HEIGHT)
    width, height = max(1, round(WIDTH*size)), max(1, round(HEIGHT*size))
    return pg.Rect((w-width)//2, (h-height)//2, width, height)


def canvas_point(screen, point):
    view = fit_window(screen)
    return ((point[0]-view.x)*WIDTH/view.width, (point[1]-view.y)*HEIGHT/view.height)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Play a repeatable cave layout.")
    parser.add_argument("--mode", choices=tuple(mode for mode, _, _ in MODES), help="Open a mode directly.")
    args = parser.parse_args()
    pg.mixer.pre_init(44100, -16, 1, 512)
    pg.init()
    try:
        desktop_w, desktop_h = pg.display.get_desktop_sizes()[0]
        initial_scale = max(.25, min(1., (desktop_w-55)/WIDTH, (desktop_h-95)/HEIGHT))
        screen = pg.display.set_mode((round(WIDTH*initial_scale), round(HEIGHT*initial_scale)), pg.RESIZABLE)
        pg.display.set_caption("Frostfall - Under the Ice")
        buffer = pg.Surface((WIDTH, HEIGHT)).convert()
        feed = pg.Surface((WIDTH, HEIGHT)).convert()
        preview = Dive(args.seed)
        menu_scene = Scene(preview.cave)
        run = Run(args.mode, args.seed) if args.mode else None
        scenery = Scene(run.games[0].cave) if run is not None and run.mode == "race" else menu_scene
        audio = Audio()
        clock = pg.time.Clock()
        remaining = 0.
        running = True
        while running:
            dt = min(clock.tick(60)*.001, .05)
            before = run
            for event in pg.event.get():
                if event.type == pg.QUIT:
                    running = False
                elif event.type == pg.WINDOWFOCUSLOST and run is not None:
                    run.set_pause(True)
                elif event.type == pg.MOUSEBUTTONDOWN and event.button == 1 and run is None:
                    point = canvas_point(screen, event.pos)
                    mode = next((MODES[index][0] for index, bounds in enumerate(MENU_BUTTONS)
                                 if bounds.collidepoint(point)), None)
                    if mode:
                        run = Run(mode, args.seed)
                        scenery = Scene(run.games[0].cave) if mode == "race" else menu_scene
                elif event.type == pg.KEYDOWN:
                    if event.key == pg.K_ESCAPE:
                        if run is None:
                            running = False
                        else:
                            run = None
                    elif event.key == pg.K_m:
                        audio.muted = not audio.muted
                    elif run is None:
                        shortcuts = (pg.K_1, pg.K_2, pg.K_3)
                        if event.key in shortcuts:
                            run = Run(MODES[shortcuts.index(event.key)][0], args.seed)
                            scenery = Scene(run.games[0].cave) if run.mode == "race" else menu_scene
                    elif event.key == pg.K_p:
                        run.set_pause(not run.paused)
                    elif event.key == pg.K_TAB:
                        run.switch_search()
                    elif event.key == pg.K_g:
                        run.toggle_routes()
                    elif event.key in (pg.K_r, pg.K_n):
                        previous = run
                        seed = run.seed if event.key == pg.K_r else SystemRandom().randrange(1000000)
                        run = Run(previous.mode, seed)
                        for old, game in zip(previous.games, run.games):
                            game.show_route, game.greedy = old.show_route, old.greedy
                        if seed != previous.seed:
                            scenery = Scene(run.games[0].cave)
            if run is None:
                menu(buffer, menu_scene, preview, canvas_point(screen, pg.mouse.get_pos()))
            else:
                remaining = remaining+dt if run is before else 0.
                controls = read_controls()
                while remaining >= SIM_STEP:
                    run.step(SIM_STEP, controls)
                    remaining -= SIM_STEP
                for game in run.games:
                    audio.flush(game)
                draw_run(buffer, feed, scenery, run)
            view = fit_window(screen)
            screen.fill((4, 13, 22))
            image = buffer if view.size == buffer.get_size() else pg.transform.smoothscale(buffer, view.size)
            screen.blit(image, view)
            pg.display.flip()
    finally:
        pg.quit()


if __name__ == "__main__":
    main()
