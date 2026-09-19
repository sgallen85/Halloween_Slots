from kivy.app import App
from kivy.uix.widget import Widget
from kivy.graphics import Rectangle


class BgWidget(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print(">>> About to load image via Rectangle.source...")
        with self.canvas:
            bg = Rectangle()
            bg.source = 'test_image.png'
            bg.pos = (0, 0)
            bg.size = (1920, 1080)
        print(">>> Rectangle created, returning to Kivy...")


class MinimalTest2(App):
    def build(self):
        return BgWidget()


if __name__ == '__main__':
    MinimalTest2().run()
