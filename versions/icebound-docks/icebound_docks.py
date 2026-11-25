"""Launch the separate Frostfall Arena Icebound Docks game."""

import argparse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--play", action="store_true", help="Start a match against Minimax immediately.")
    args = parser.parse_args()

    from panda3d.core import loadPrcFileData

    loadPrcFileData("Icebound Docks", """
window-title Frostfall Arena - Icebound Docks
win-size 1440 900
load-display pandagl
sync-video 1
framebuffer-multisample 1
multisamples 4
textures-power-2 none
notify-level warning
""")
    from frostfall.docks3d import IceboundDocks3D

    game = IceboundDocks3D()
    try:
        if args.play:
            game.start_match(("Human", "Minimax"))
        game.run()
    finally:
        game.destroy()


if __name__ == "__main__":
    main()
