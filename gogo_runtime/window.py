"""Panda3D window and input support for Go Go 3D."""

from concurrent.futures import ThreadPoolExecutor

from direct.filter.FilterManager import FilterManager
from direct.showbase.ShowBase import ShowBase
from panda3d.core import Shader, Texture

from .hud import load_fonts
from .shaders import EDGE_SMOOTH, SCREEN_VERTEX


class BoardWindow(ShowBase):
    def __init__(self, window_type, audio_enabled, *, hud_type, sounds_type, smoothing_strength):
        super().__init__(windowType=window_type)
        if not self.win or not self.win.isValid():
            raise RuntimeError("Frostfall Arena Go Go 3D could not open a Panda3D graphics window.")
        self.disableMouse()
        self.setBackgroundColor(.028, .054, .096)
        self.fonts = load_fonts()
        self.filter = FilterManager(self.win, self.cam)
        self.filter_screen = self.filter.renderSceneInto()
        if self.filter_screen is not None:
            texture = self.filter_screen.getTexture()
            texture.setMinfilter(Texture.FTLinear)
            texture.setMagfilter(Texture.FTLinear)
            self.filter_screen.setShader(Shader.make(Shader.SL_GLSL, SCREEN_VERTEX, EDGE_SMOOTH))
            self.filter_screen.setShaderInput("scene", texture)
            self.filter_screen.setShaderInput("smoothing_strength", smoothing_strength)
        self.hud = hud_type(self, self.fonts)
        self.sounds = sounds_type(self.loader, audio_enabled)
        self.sound = audio_enabled
        self.fullscreen = False
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gogo-3d-ai")
        self.future = None
        self.size = (0, 0)
        self.global_clock = self.taskMgr.globalClock

    def viewport_size(self):
        width, height = max(1, self.win.getXSize()), max(1, self.win.getYSize())
        if (width, height) != self.size:
            self.size = (width, height)
            self.pixel2d.setScale(2 / width, 1, 2 / height)
            if self.filter_screen is not None:
                self.filter_screen.setShaderInput("viewport_size", float(width), float(height))
        return width, height

    def mouse_position(self):
        if self.mouseWatcherNode and self.mouseWatcherNode.hasMouse():
            cursor = self.mouseWatcherNode.getMouse()
            w, h = self.size
            return (cursor.x, cursor.y), ((1 + cursor.x)*w/2, (1 - cursor.y)*h/2)
        return None, (-100, -100)

    def stop_search(self):
        if self.future is not None:
            self.future.cancel()
        self.future = None

    def destroy(self):
        if hasattr(self, "pool"):
            self.stop_search()
            self.pool.shutdown(wait=True, cancel_futures=True)
        if hasattr(self, "sounds"):
            self.sounds.close()
        if hasattr(self, "filter"):
            self.filter.cleanup()
            self.filter.ignoreAll()
        super().destroy()
