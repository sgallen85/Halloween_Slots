import RPi.GPIO as GPIO
import config

from kivy.app import App
from kivy.uix.widget import Widget
from kivy.graphics import Rectangle, Color
from kivy.core.image import Image as CoreImage


print(">>> Initializing GPIO (matches hardwareButton.__init__)...")
GPIO.setmode(GPIO.BCM)
GPIO.setup(config.gpio_button, GPIO.IN, pull_up_down=GPIO.PUD_UP)
print(">>> GPIO initialized successfully.")


class FullWidget(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print(">>> Loading background...")
        with self.canvas:
            bg = Rectangle()
            bg.source = 'test_image.png'
            bg.pos = (0, 0)
            bg.size = (1920, 1080)
        print(">>> Background done. Loading 3 strip textures...")

        for n in range(3):
            print(">>> Loading strip #{}...".format(n))
            img = CoreImage('test_strip.png')
            img.texture.wrap = 'repeat'
            with self.canvas:
                rect = Rectangle()
                rect.texture = img.texture
                rect.pos = (n * 300, 0)
                rect.size = (300, 1080)
            u, v, w, h = 0, 1.18, 1, -0.85
            rect.tex_coords = [u, v, u + w, v, u + w, v + h, u, v + h]
            print(">>> Strip #{} done.".format(n))

        print(">>> All strips loaded. Adding payline...")
        with self.canvas:
            Color(1, 0, 0)
            payline = Rectangle()
            payline.pos = (50, 540)
            payline.size = (1820, 10)
        print(">>> Everything done, returning to Kivy...")


class MinimalTest9(App):
    def build(self):
        return FullWidget()


if __name__ == '__main__':
    MinimalTest9().run()
