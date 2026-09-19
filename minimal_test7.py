from kivy.app import App
from kivy.uix.widget import Widget
from kivy.graphics import Rectangle, Color
from kivy.core.image import Image as CoreImage


class FullWidget(Widget):
    pass


class MinimalTest7(App):
    def build(self):
        print(">>> build() called - returning empty widget, no images yet")
        self.w = FullWidget()
        return self.w

    def on_start(self):
        print(">>> on_start() called - window should be up now. Loading images...")
        with self.w.canvas:
            bg = Rectangle()
            bg.source = 'test_image.png'
            bg.pos = (0, 0)
            bg.size = (1920, 1080)
        print(">>> Background done. Loading 3 strip textures...")

        for n in range(3):
            print(">>> Loading strip #{}...".format(n))
            img = CoreImage('test_strip.png')
            img.texture.wrap = 'repeat'
            with self.w.canvas:
                rect = Rectangle()
                rect.texture = img.texture
                rect.pos = (n * 300, 0)
                rect.size = (300, 1080)
            u, v, w_, h = 0, 1.18, 1, -0.85
            rect.tex_coords = [u, v, u + w_, v, u + w_, v + h, u, v + h]
            print(">>> Strip #{} done.".format(n))

        print(">>> All strips loaded. Adding payline...")
        with self.w.canvas:
            Color(1, 0, 0)
            payline = Rectangle()
            payline.pos = (50, 540)
            payline.size = (1820, 10)
        print(">>> Everything done.")


if __name__ == '__main__':
    MinimalTest7().run()
