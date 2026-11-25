"""Launch the real-time 3D edition of Frostfall Arena."""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--heist", action="store_true", help="Play the Fish Heist prototype.")
    args = parser.parse_args()
    try:
        from panda3d.core import loadPrcFileData
    except ModuleNotFoundError:
        print("Install Panda3D with: python -m pip install -r requirements-3d.txt", file=sys.stderr)
        return 1

    title = "Frostfall Arena - Fish Heist" if args.heist else "Frostfall Arena - 3D"
    loadPrcFileData("Frostfall Arena", f"""
win-title {title}
win-size 1440 900
window-type onscreen
load-display pandagl
sync-video 1
framebuffer-multisample 1
multisamples 4
textures-power-2 none
notify-level warning
""")
    if args.heist:
        from frostfall.heist3d import FishHeist3D
        app = FishHeist3D()
    else:
        from frostfall.client3d import Frostfall3D
        app = Frostfall3D()
    try:
        app.run()
    finally:
        app.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
