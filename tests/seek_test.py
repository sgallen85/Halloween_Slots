from kivy.app import App
from kivy.core.audio import SoundLoader
from kivy.clock import Clock


class SeekTest(App):
    def build(self):
        self.snd = SoundLoader.load('test_track.ogg')
        if self.snd is None:
            print(">>> FAILED to load test_track.ogg")
            return None
        print(">>> Loaded OK, length: {} sec".format(self.snd.length))
        self.snd.play()
        Clock.schedule_once(self.check_pos, 3)
        return None

    def check_pos(self, dt):
        pos = self.snd.get_pos()
        print(">>> After 3 sec of playback, get_pos() reports: {}".format(pos))
        print(">>> Stopping, then seeking to 3.0...")
        self.snd.stop()
        self.snd.play()
        self.snd.seek(3.0)
        Clock.schedule_once(self.check_after_seek, 1)

    def check_after_seek(self, dt):
        pos = self.snd.get_pos()
        print(">>> 1 sec after seek(3.0) + play(), get_pos() reports: {}".format(pos))
        print(">>> (If this says ~4.0, seek worked. If it says ~1.0, seek was ignored.)")
        App.get_running_app().stop()


if __name__ == '__main__':
    SeekTest().run()
