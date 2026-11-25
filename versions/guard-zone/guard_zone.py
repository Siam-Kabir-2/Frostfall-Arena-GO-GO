"""Launch the separate Frostfall Arena Guard Zone version."""

import argparse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--play", action="store_true", help="Start against Minimax immediately.")
    args = parser.parse_args()

    from panda3d.core import loadPrcFileData

    loadPrcFileData("Guard Zone", """
window-title Frostfall Arena - Guard Zone
win-size 1440 900
load-display pandagl
sync-video 1
framebuffer-multisample 1
multisamples 4
textures-power-2 none
notify-level warning
""")
    from frostfall.guard3d import GuardZone3D

    game = GuardZone3D()
    try:
        if args.play:
            game.start_match(("Human", "Minimax"))
        game.run()
    finally:
        game.destroy()


if __name__ == "__main__":
    main()
