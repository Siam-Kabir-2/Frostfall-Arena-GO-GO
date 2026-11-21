"""Frame layout shared by the atlas builder and the Panda3D sprite renderer."""

from dataclasses import dataclass
from json import loads
from pathlib import Path

FRAME_WIDTH, FRAME_HEIGHT = 320, 176
ANCHOR_X, ANCHOR_Y = 110, 151
ATLAS_COLS = 10
FRAMES_PER_POSE = 6
FRAMES_PER_ROLE = 5*FRAMES_PER_POSE
IDLE, WALK, ATTACK, HURT, DEFEAT = range(0, FRAMES_PER_ROLE, FRAMES_PER_POSE)
ASSETS = Path(__file__).resolve().parent / "assets"
STANDING_HEIGHT = .0098*87


@dataclass(frozen=True)
class SpriteAtlas:
    texture: object
    standing_pixels: tuple


def load_atlases(loader):
    from panda3d.core import Filename, Texture

    heights = loads((ASSETS/"sprite-heights.json").read_text(encoding="utf-8"))
    atlases = []
    for side, standing_pixels in enumerate(heights):
        texture = loader.loadTexture(Filename.fromOsSpecific(str(ASSETS/f"squad-{side}.png")))
        texture.setMagfilter(Texture.FTNearest)
        texture.setMinfilter(Texture.FTNearest)
        texture.setWrapU(Texture.WMClamp)
        texture.setWrapV(Texture.WMClamp)
        atlases.append(SpriteAtlas(texture, tuple(standing_pixels)))
    return atlases


def make_sprite(root, atlas, hero):
    from panda3d.core import CardMaker, TransparencyAttrib

    unit = STANDING_HEIGHT/atlas.standing_pixels[hero]
    pivot = root.attachNewNode("Penguin sprite billboard")
    pivot.setBillboardPointEye()
    maker = CardMaker("Penguin sprite")
    maker.setFrame(-ANCHOR_X*unit, (FRAME_WIDTH-ANCHOR_X)*unit,
                   -(FRAME_HEIGHT-ANCHOR_Y)*unit, ANCHOR_Y*unit)
    node = pivot.attachNewNode(maker.generate())
    node.setTexture(atlas.texture)
    node.setTwoSided(True)
    node.setTransparency(TransparencyAttrib.MAlpha)
    node.setDepthWrite(False)
    node.setBin("transparent", 3)
    return node


def set_frame(node, hero, pose):
    from panda3d.core import TextureStage

    index = hero*FRAMES_PER_ROLE+pose
    col, row = index % ATLAS_COLS, index//ATLAS_COLS
    texture = node.getTexture()
    width, height = texture.getXSize(), texture.getYSize()
    stage = TextureStage.getDefault()
    node.setTexScale(stage, (FRAME_WIDTH-1)/width, (FRAME_HEIGHT-1)/height)
    node.setTexOffset(stage, (col*FRAME_WIDTH+.5)/width, 1-((row+1)*FRAME_HEIGHT-.5)/height)
