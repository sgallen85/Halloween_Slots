from kivy.app import App
from kivy.uix.widget import Widget
from kivy.graphics import Rectangle
from kivy.core.image import Image as CoreImage


class StripWidget(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print(">>> About to load stripbig1.png via kivy.core.image.Image...")
        img = CoreImage('test_strip.png')
        print(">>> CoreImage loaded, texture acquired, building Rectangle...")
        with self.canvas:
            rect = Rectangle()
            rect.texture = img.texture
            rect.pos = (0, 0)
            rect.size = (300, 1080)
        print(">>> Rectangle with strip texture created, returning to Kivy...")


class MinimalTest3(App):
    def build(self):
        return StripWidget()


if __name__ == '__main__':
    MinimalTest3().run()
