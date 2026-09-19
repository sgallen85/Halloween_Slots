from kivy.app import App
from kivy.uix.image import Image


class MinimalTest(App):
    def build(self):
        print(">>> About to load image...")
        img = Image(source='test_image.png')
        print(">>> Image widget created, returning to Kivy...")
        return img


if __name__ == '__main__':
    MinimalTest().run()