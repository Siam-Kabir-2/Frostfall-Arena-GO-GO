"""Resolution-aware scenery behind the live 3D board."""

from pathlib import Path

from panda3d.core import CardMaker, Filename, MovieTexture, OmniBoundingVolume, Shader, Texture, Vec4

ASSETS = Path(__file__).resolve().parent / "assets"

VERTEX = """
#version 150
in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;
out vec2 uv;

void main() {
    uv = p3d_MultiTexCoord0;
    gl_Position = vec4(p3d_Vertex.x, p3d_Vertex.z, .999, 1.);
}
"""

FRAGMENT = """
#version 150
uniform sampler2D p3d_Texture0;
uniform vec4 crop;
in vec2 uv;
out vec4 p3d_FragColor;

void main() {
    p3d_FragColor = texture(p3d_Texture0, crop.xy + uv * crop.zw);
}
"""


class ArenaBackdrop:
    def __init__(self, game):
        self.image = game.loader.loadTexture(Filename.fromOsSpecific(str(ASSETS / "aurora-arena.png")))
        self.image.setMinfilter(Texture.FTLinearMipmapLinear)
        video = MovieTexture("Home background")
        self.video = None
        if video.read(Filename.fromOsSpecific(str(ASSETS / "home-background.mp4"))):
            video.setMinfilter(Texture.FTLinear)
            video.setLoop(True)
            self.video = video
        for texture in (self.image, self.video):
            if texture is not None:
                texture.setMagfilter(Texture.FTLinear)
                texture.setWrapU(Texture.WMClamp)
                texture.setWrapV(Texture.WMClamp)
        self.showing_video = False
        self.size = None

        quad = CardMaker("Arena background")
        quad.setFrameFullscreenQuad()
        self.quad = game.render.attachNewNode(quad.generate())
        # The shader draws in screen space, outside the normal 3D camera bounds.
        self.quad.node().setBounds(OmniBoundingVolume())
        self.quad.node().setFinal(True)
        self.quad.setShader(Shader.make(Shader.SL_GLSL, VERTEX, FRAGMENT))
        self.quad.setTexture(self.image)
        self.quad.setBin("background", 0)
        self.quad.setDepthTest(False)
        self.quad.setDepthWrite(False)
        self.quad.setTwoSided(True)

    def update(self, width, height, *, home):
        show_video = home and self.video is not None
        if show_video != self.showing_video:
            if show_video:
                self.quad.setTexture(self.video)
                self.video.play()
            else:
                self.quad.setTexture(self.image)
                self.video.stop()
            self.showing_video = show_video
            self.size = None
        if self.size == (width, height):
            return
        self.size = width, height

        if show_video:
            source_width, source_height = self.video.getVideoWidth(), self.video.getVideoHeight()
            u = source_width/self.video.getXSize()
            v = source_height/self.video.getYSize()
            vertical_anchor = .5
        else:
            source_width, source_height = self.image.getXSize(), self.image.getYSize()
            u = v = 1.
            # Keep more of the aurora when a wide match window crops the height.
            vertical_anchor = .78
        source_aspect = source_width/source_height
        aspect = width/height
        horizontal = min(1., aspect/source_aspect)
        vertical = min(1., source_aspect/aspect)
        self.quad.setShaderInput("crop", Vec4((1-horizontal)*u/2, (1-vertical)*v*vertical_anchor,
                                              horizontal*u, vertical*v))
