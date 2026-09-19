from kivy.app import App
from kivy.uix.widget import Widget
from kivy.graphics import Rectangle
from kivy.core.image import Image as CoreImage


class StripWidget(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print(">>> Loading stripbig1.png...")
        img = CoreImage('test_strip.png')
        img.texture.wrap = 'repeat'
        print(">>> Texture ready. Building Rectangle...")
        with self.canvas:
            rect = Rectangle()
            rect.texture = img.texture
            rect.pos = (0, 0)
            rect.size = (300, 1080)
        print(">>> Rectangle created. Now setting custom out-of-range tex_coords...")
        # Mirrors Strip.set_uv(): v=1.18, well outside the normal 0-1 range,
        # relying on GL_REPEAT to wrap it back around.
        u, v, w, h = 0, 1.18, 1, -0.85
        rect.tex_coords = [u, v, u + w, v, u + w, v + h, u, v + h]
        print(">>> tex_coords set successfully, returning to Kivy...")


class MinimalTest5(App):
    def build(self):
        return StripWidget()


if __name__ == '__main__':
    MinimalTest5().run()
