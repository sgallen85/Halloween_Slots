from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition
from kivy.uix.widget import Widget
from kivy.graphics import Rectangle, Color
from kivy.core.image import Image as CoreImage


class GameWidget(Widget):
    pass


class MinimalTest8(App):
    def build(self):
        print(">>> build() - setting up ScreenManager with 2 screens")
        self.manager = ScreenManager(transition=FadeTransition())

        start_screen = Screen(name="Start Screen")
        self.game_screen = Screen(name="Game Screen")
        self.game_widget = GameWidget()
        self.game_screen.add_widget(self.game_widget)

        self.manager.add_widget(start_screen)
        self.manager.add_widget(self.game_screen)
        self.manager.current = "Start Screen"

        return self.manager

    def on_start(self):
        print(">>> on_start() - switching to Game Screen (starts fade transition)")
        self.manager.current = "Game Screen"
        print(">>> Transition triggered. Loading textures RIGHT NOW, same instant...")

        with self.game_widget.canvas:
            bg = Rectangle()
            bg.source = 'test_image.png'
            bg.pos = (0, 0)
            bg.size = (1920, 1080)
        print(">>> Background done. Loading 3 strip textures...")

        for n in range(3):
            print(">>> Loading strip #{}...".format(n))
            img = CoreImage('test_strip.png')
            img.texture.wrap = 'repeat'
            with self.game_widget.canvas:
                rect = Rectangle()
                rect.texture = img.texture
                rect.pos = (n * 300, 0)
                rect.size = (300, 1080)
            u, v, w_, h = 0, 1.18, 1, -0.85
            rect.tex_coords = [u, v, u + w_, v, u + w_, v + h, u, v + h]
            print(">>> Strip #{} done.".format(n))

        print(">>> All strips loaded. Adding payline...")
        with self.game_widget.canvas:
            Color(1, 0, 0)
            payline = Rectangle()
            payline.pos = (50, 540)
            payline.size = (1820, 10)
        print(">>> Everything done.")


if __name__ == '__main__':
    MinimalTest8().run()
