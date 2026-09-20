#!/usr/bin/env python3
from __future__ import division

import random
import os, sys, time, math, logging, argparse, glob, subprocess, csv

import string

import config
from functools import partial

# Must happen before ANY kivy.core.audio import (including indirectly, via
# kivy.app etc. below) - this is what makes Kivy use the SDL2 audio backend,
# which talks to ALSA directly and doesn't need PulseAudio running. Setting
# this later (e.g. in piHardware.setup(), which used to be the only place
# it was set) is too late to have any effect.
os.environ['KIVY_AUDIO'] = 'sdl2'

# Same idea for image loading: prefer PIL/SDL2 over ffpyplayer. A system
# ffmpeg/libav upgrade can leave the pip-installed ffpyplayer package
# (compiled against the old version) mismatched with the new one, which can
# hang indefinitely on the very first image load rather than erroring out.
os.environ['KIVY_IMAGE'] = 'sdl2'

# SDL2 has its own internal audio driver selection, separate from Kivy's
# provider system above. On the Pi it was defaulting to something (almost
# certainly PulseAudio) that hangs on the very first sound load. Forcing it
# onto ALSA directly - which we confirmed works via speaker-test - fixes
# that. This only applies on Linux (the Pi) - ALSA doesn't exist on macOS,
# and forcing it there would silently kill audio entirely during Mac testing.
if sys.platform.startswith('linux'):
    os.environ['SDL_AUDIODRIVER'] = 'alsa'

from kivy.config import Config
Config.set('graphics', 'maxfps', '60')
Config.set('graphics', 'multisamples', '0')  # AA isn't buying you much here and costs fill-rate
Config.set('graphics', 'show_cursor', '0')   # currently commented out in your code.
Config.set('kivy', 'exit_on_escape', '0')    # replaced with our own hard-exit handler below
if config.window_size is True:
    # fullscreen at the display's native resolution
    Config.set('graphics', 'fullscreen', 'auto')
elif isinstance(config.window_size, (tuple, list)) and len(config.window_size) == 2:
    # windowed at an explicit size - handy for testing on a laptop
    Config.set('graphics', 'fullscreen', '0')
    Config.set('graphics', 'width', str(config.window_size[0]))
    Config.set('graphics', 'height', str(config.window_size[1]))
else:
    # window_size = False (or unset) - plain windowed mode, Kivy's default size
    Config.set('graphics', 'fullscreen', '0')

try:
  import piHardware as Hardware
except ImportError as e:
  logging.warning("piHardware failed to import ({}) - falling back to nullHardware. "
                   "The physical button and any hardware output will NOT work. "
                   "Run: python3 -c \"import piHardware\"  to see the real error.".format(e))
  import nullHardware as Hardware

from collections import Counter
from kivy.animation import Animation

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition
from kivy.uix.floatlayout import FloatLayout
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.lang import Builder
from kivy.core.image import Image
from kivy.core.window import Window, Keyboard
from kivy.properties import (AliasProperty,
                             ListProperty,
                             NumericProperty,
                             ObjectProperty)
from kivy.uix.image import Image as ImageWidget
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.widget import Widget
from kivy.graphics import *
from kivy.utils import get_color_from_hex


import viewport

Builder.load_string('''
<StartScreen>:
    buttons: _buttons
    name: "Start Screen"
    canvas:
        Color:
            hsv: .5, .5, .3
        Rectangle:
            size: self.size
    Label:
        text: "Slots"
        font_size: '128sp'
        pos_hint: {'center_x': .5, 'center_y': .7}
    GridLayout:
        id: _buttons
        size_hint: .10, .40
        pos_hint: {'center_x': .5, 'center_y': .3}
        cols: 1

<GameScreen>:
    slots: _id_slots
    win_label: _win_label
    win_banner: _win_banner
    win_icon_left: _win_icon_left
    win_icon_right: _win_icon_right
    win_celebration: _win_celebration
    name: "Game Screen"
    FloatLayout:
        Slots:
            id: _id_slots
            canvas:
        FloatLayout:
            id: _win_banner
            size_hint: (1, None)
            height: 300
            pos_hint: {'center_x': .5, 'y': .2}
            opacity: 0
            canvas.before:
                Color:
                    rgba: 0.12, 0.12, 0.12, 0.85
                Rectangle:
                    pos: self.pos
                    size: self.size
            Image:
                id: _win_icon_left
                size_hint: (None, None)
                allow_stretch: True
                keep_ratio: True
                opacity: 0
                pos_hint: {'center_x': .15, 'center_y': .5}
            Label:
                id: _win_label
                text: ""
                font_size: '110sp'
                bold: True
                color: 1, 1, 1, 1
                size_hint: (1, 1)
                pos_hint: {'center_x': .5, 'center_y': .5}
                text_size: self.size
                halign: 'center'
                valign: 'middle'
            Image:
                id: _win_icon_right
                size_hint: (None, None)
                allow_stretch: True
                keep_ratio: True
                opacity: 0
                pos_hint: {'center_x': .85, 'center_y': .5}
        JackpotCelebration:
            id: _win_celebration
''')

# 

# should this be global?
coinDispense = Hardware.coinDispense()

# Human-readable names for each strip slot, in the same order as
# stripbig1.png (top to bottom). Used only for the CSV game log. If you add
# more icons later, extend this list to match, or the log just falls back
# to numeric indices for anything past the end.
SYMBOL_NAMES = getattr(config, 'symbol_names', [
    'Bat', 'Cat', 'Ghost', 'Mummy', 'Sickle', 'Pumpkin',
    'Vampire', 'Broom', 'Hat', 'Spiderweb', 'Coffin', 'Skeleton',
])


def symbol_name(index):
    if 0 <= index < len(SYMBOL_NAMES):
        return SYMBOL_NAMES[index]
    return str(index)


class GameLogger:
    """Appends one CSV row per spin to logs/spins_YYYY-MM-DD.csv, so each
    Halloween night ends up in its own dated file, ready to open in a
    spreadsheet. Never raises - a logging problem should never crash the game."""

    FIELDS = ['timestamp', 'theme', 'reel1', 'reel2', 'reel3',
              'result', 'pumpkin_count', 'payout']

    def __init__(self, log_dir='logs'):
        self.path = None
        try:
            os.makedirs(log_dir, exist_ok=True)
            date_str = time.strftime('%Y-%m-%d')
            self.path = os.path.join(log_dir, 'spins_{}.csv'.format(date_str))
            if not os.path.exists(self.path):
                with open(self.path, 'w', newline='') as f:
                    csv.writer(f).writerow(self.FIELDS)
        except Exception as e:
            logging.warning('game log disabled - could not set up {}: {}'.format(log_dir, e))
            self.path = None

    def log_spin(self, theme, landed, match_type, pumpkin_count, payout):
        if self.path is None:
            return
        row = [
            time.strftime('%Y-%m-%d %H:%M:%S'),
            theme,
            symbol_name(landed[0]), symbol_name(landed[1]), symbol_name(landed[2]),
            match_type,
            pumpkin_count,
            payout,
        ]
        try:
            with open(self.path, 'a', newline='') as f:
                csv.writer(f).writerow(row)
        except Exception as e:
            logging.warning('failed to write game log row: {}'.format(e))


class MultiAudio:
    _next = 0

    def __init__(self, filename, count):
        self.buf = [SoundLoader.load(filename)
                    for i in range(count)]

    def play(self):
        self.buf[self._next].play()
        self._next = (self._next + 1) % len(self.buf)


##  [1.100, .942, .759, .598, .444, .273]

TIER_STYLE = {
    'spin':        {'color': (1, 1, 1, 1),      'size_frac': 0.20, 'hold': 0.3, 'text': '{} treats'},
    'double':      {'color': (213/255, 135/255, 49/255, 1),  'size_frac': 0.24, 'hold': 0.7, 'text': 'DOUBLE!\n{} treats'},
    '3 of a kind': {'color': (1, 0.55, 0.1, 1),  'size_frac': 0.28, 'hold': 1.0, 'text': '3 OF A KIND!\n{} treats'},
    'jackpot':     {'color': (1, 0.25, 0.05, 1), 'size_frac': 0.34, 'hold': 2.0, 'text': 'JACKPOT!!!\n{} treats'},
}

# Text color used specifically for the "PUMPKIN BONUS!" banner (1 or 2
# pumpkins). The jackpot tier keeps its own fiery color above, unaffected.
PUMPKIN_BONUS_COLOR = (121/255, 128/255, 70/255, 1)

class Strip(Rectangle):
    # -.85 was tuned by eye for 6 symbols; WINDOW_REFERENCE_N is that 6. The
    # ratio between these two is also what one icon's on-screen pixel size
    # works out to (see Slots.reel_icon_pixel_size), so they're named
    # constants rather than inline magic numbers.
    WINDOW_FRACTION = 0.85
    WINDOW_REFERENCE_N = 6.0

    def __init__(self, img, num_symbols=6, **kwargs):
        super(Strip, self).__init__(**kwargs)
        self.texture = img.texture
        self.texture.wrap = 'repeat'
        self.num_symbols = num_symbols
        self.slot_frac = 1.0 / num_symbols

    def add_uv(self, canvas, val):
        self.set_uv(canvas, self.tex_coords[1] - val)

    def set_uv(self, canvas, val):
        u = 0
        v = val
        w = 1
        # Scaled so the same number of icon-heights show through the reel
        # window regardless of symbol count, keeping each icon the same
        # apparent size on screen no matter how many symbols are on the strip.
        h = -self.WINDOW_FRACTION * (self.WINDOW_REFERENCE_N / self.num_symbols)
        self.tex_coords = [u, v, u+w, v, u+w, v+h, u, v+h]

    def strip_pos(self):
        return int((1.18-self.tex_coords[1]) / self.slot_frac) % self.num_symbols

    def slot_to_uv(self, slot):
        return 1.18 - (slot * self.slot_frac)

    def get_uv(self):
        return (self.tex_coords[0], self.tex_coords[1])


class JackpotCelebration(FloatLayout):
    """Full-screen overlay of icons falling from above the screen under
    gravity, bouncing softly off the bottom, and drifting off the left/right
    edges to disappear - the classic 'cascade' win-screen effect, built from
    scratch using this game's own icon art. All the physics knobs below can
    be overridden from config.py (see the matching config_* names in
    __init__) without touching this class."""

    DURATION = 10.0
    ICON_COUNT = 50
    ICON_SIZE = 220
    DRIFT_SPEED_RANGE = (150, 300)    # sideways drift speed magnitude, px/sec
    SPAWN_HEIGHT_RANGE = (0, 2200)    # how far above the screen top icons start (staggers their fall)
    GRAVITY = -700                    # px/sec^2, pulls downward - lower = slower/floatier fall
    BOTTOM_RESTITUTION = 0.58         # energy kept per bottom bounce (<1 = settles over time; higher = bounces longer)

    def __init__(self, **kwargs):
        super(JackpotCelebration, self).__init__(**kwargs)
        self.size_hint = (None, None)
        self.size = (1920, 1080)
        self.pos = (0, 0)
        self.opacity = 0
        self._bodies = []  # list of [widget, vx, vy]
        self._update_ev = None
        self._stop_ev = None

        self.duration = getattr(config, 'jackpot_duration', self.DURATION)
        self.icon_count = getattr(config, 'jackpot_icon_count', self.ICON_COUNT)
        self.icon_size = getattr(config, 'jackpot_icon_size', self.ICON_SIZE)
        self.drift_speed_range = getattr(config, 'jackpot_drift_speed_range', self.DRIFT_SPEED_RANGE)
        self.spawn_height_range = getattr(config, 'jackpot_spawn_height_range', self.SPAWN_HEIGHT_RANGE)
        self.gravity = getattr(config, 'jackpot_gravity', self.GRAVITY)
        self.bottom_restitution = getattr(config, 'jackpot_bottom_restitution', self.BOTTOM_RESTITUTION)

    def start(self, icon_paths, icon_size=None, count=None):
        self.stop()
        if not icon_paths:
            return
        size = icon_size if icon_size is not None else self.icon_size
        n = count if count is not None else self.icon_count
        for i in range(n):
            path = random.choice(icon_paths)
            img = ImageWidget(source=path, size=(size, size),
                               size_hint=(None, None), allow_stretch=True, keep_ratio=True)
            # Start above the screen (staggered height = staggered fall
            # timing) at a random x. Icons spawned on the left half drift
            # right as they fall, and vice versa, so they cross the screen
            # rather than drifting randomly.
            spawn_x = random.uniform(0, 1920 - size)
            direction = 1 if spawn_x < (1920 - size) / 2 else -1
            speed = random.uniform(*self.drift_speed_range)
            vx = direction * speed
            vy = 0
            img.pos = (spawn_x, 1080 + random.uniform(*self.spawn_height_range))
            self.add_widget(img)
            self._bodies.append([img, vx, vy])
        self.opacity = 1
        self._update_ev = Clock.schedule_interval(self._update, 0)
        self._stop_ev = Clock.schedule_once(self.stop, self.duration)

    def _update(self, dt):
        size = self.icon_size
        margin = size + 50  # fully off-screen before we despawn
        surviving = []
        for body in self._bodies:
            img, vx, vy = body
            vy += self.gravity * dt
            x, y = img.pos
            x += vx * dt
            y += vy * dt

            if y <= 0:
                y = 0
                vy = abs(vy) * self.bottom_restitution

            # No side walls - icons that drift past either edge just keep
            # going and get removed once they're fully out of view.
            if x + size < -margin or x > 1920 + margin:
                self.remove_widget(img)
                continue

            img.pos = (x, y)
            body[1], body[2] = vx, vy
            surviving.append(body)
        self._bodies = surviving

    def stop(self, *args):
        if self._update_ev:
            self._update_ev.cancel()
            self._update_ev = None
        if self._stop_ev:
            self._stop_ev.cancel()
            self._stop_ev = None
        self.clear_widgets()
        self._bodies = []
        self.opacity = 0

class Slots(Widget):
    state = 'idle'
    first_stop_length = 3.5

    # payout amounts — tweak freely
    PAY_BASE = 2
    PAY_DOUBLE = 4
    PAY_TRIPLE = 12
    PAY_JACKPOT = 20  # 3 pumpkins

    # total icons on the strip — must match stripbig1.png's icon count
    NUM_SYMBOLS = 12

    # Default odds of each spin outcome, as decimal percentages (should add
    # up to 1.0, e.g. 0.43 = 43%). Override in config.py with a `win_odds`
    # dict to change these without touching this file. The payout amounts
    # above are completely separate and untouched by this.
    OUTCOME_WEIGHTS = {
        'none':    0.43,
        'double':  0.30,
        'triple':  0.25,
        'jackpot': 0.02,
    }

    # Seconds of no spins before idle background music starts. Override with
    # idle_music_timeout in config.py.
    IDLE_MUSIC_TIMEOUT = 30.0

    # Default background image filename, in themes/<theme>/images/. Override
    # with `background_file` in config.py to use a different image without
    # touching this file. The original 'background.png' already has its
    # reel-backing bars painted into the art; anything else gets them drawn
    # in automatically (see background_bars below) so new backgrounds don't
    # need to include them.
    BACKGROUND_FILE = 'background.png'

    # How wide the drawn-in bar extends past each reel's own edges, and how
    # opaque it is. Tweak to taste.
    BAR_PAD = 0
    BAR_COLOR = (1, 1, 1, 0.68)

    def __init__(self, **kwargs):
        super(Slots, self).__init__(**kwargs)
        self.strips = []
        self.landed = []
        self.last_payout = 0
        self.last_match_type = None
        self.num_symbols = getattr(config, 'num_symbols', self.NUM_SYMBOLS)
        self.pumpkin_symbol = getattr(config, 'pumpkin_symbol', 5)
        self.outcome_weights = getattr(config, 'win_odds', self.OUTCOME_WEIGHTS)
        self.target_symbols = [0, 0, 0]
        self.game_screen = None
        self.current_theme = None
        self.game_logger = GameLogger()
        self.background_file = getattr(config, 'background_file', self.BACKGROUND_FILE)
        # Only draw bars automatically when NOT using the original default
        # background (which already has them baked in) - unless config.py
        # explicitly says otherwise via `background_bars`.
        self.background_bars = getattr(config, 'background_bars',
                                        self.background_file != self.BACKGROUND_FILE)
        self.bar_rects = []

        # Idle background music - starts after IDLE_MUSIC_TIMEOUT seconds of
        # no spins, pauses (and remembers position) the moment a spin starts,
        # and resumes right where it left off next time it goes idle again -
        # by muting instead of stopping (see _pause_background_music), since
        # Kivy's SDL2 provider get_pos()/seek() are known to always report 0.
        self.music_enabled = getattr(config, 'start_with_music', True)
        self.music_muted = False
        self.idle_music_timeout = getattr(config, 'idle_music_timeout', self.IDLE_MUSIC_TIMEOUT)
        self.music_playlist = []
        self.music_index = 0
        self.music_sound = None
        self.last_activity_time = time.time()

    def setup(self, theme):
        self.current_theme = theme
        for strip in self.strips:
            del strip
        self.canvas.clear()
        self.start_time = time.time()
        self.strips = []

        self._load_background_cycle(theme)
        start_bg_path = self._resolve_start_background(theme)

        with self.canvas:
            self.bg_rect = Rectangle()
            self.bg_rect.source = start_bg_path
            self.bg_rect.pos = (0, 0)
            self.bg_rect.size = (1920, 1080)

            self.bar_rects = []
            if self.background_bars:
                Color(*self.BAR_COLOR)
                for n in range(3):
                    self.bar_rects.append(Rectangle())
                Color(1, 1, 1, 1)  # reset tint before drawing the reel textures below

            for n in range(3):
                core_img = Image(os.path.join("themes", theme, "images", "stripbig1.png"))
                strip = Strip(core_img, num_symbols=self.num_symbols)
                strip.set_uv(self, strip.slot_to_uv(0))
                self.strips.append(strip)
            Color(1, 0, 0)
            self.payline = Rectangle()
        self.last_time = time.time()

        self.sounds = {}
        # Load any mix of .wav/.ogg/.mp3 - Kivy's SDL2 audio backend plays
        # all three natively, so there's no need to standardize on one.
        # config.audio_extension (if set) is included too, for backward compatibility.
        extensions = {'.wav', '.ogg', '.mp3'}
        configured_ext = getattr(config, 'audio_extension', None)
        if configured_ext:
            extensions.add(configured_ext)
        files = []
        for ext in extensions:
            files += glob.glob(os.path.join("themes", theme, 'audio', "*" + ext))
            files += glob.glob(os.path.join("themes", theme, 'audio', "*/*" + ext))
        for fn in files:
            path, f = os.path.split(fn)
            f, ext = os.path.splitext(f)
            try:
                snd = SoundLoader.load(fn)
            except Exception as e:
                logging.warning('could not load sound {}: {}'.format(fn, e))
                snd = None
            if snd is None:
                logging.warning('sound failed to load (will play silently): {}'.format(fn))
            self.sounds[f] = snd

        self._load_background_music(theme)

    def _load_background_cycle(self, theme):
        """Finds all images in themes/<theme>/images/background/ for the B
        key to cycle through."""
        extensions = ('.png', '.jpg', '.jpeg')
        files = []
        for ext in extensions:
            files += glob.glob(os.path.join("themes", theme, "images", "background", "*" + ext))
        files.sort()
        self.bg_cycle_files = files

    def _find_cycle_index(self, path):
        norm = os.path.normpath(path)
        for i, f in enumerate(self.bg_cycle_files):
            if os.path.normpath(f) == norm:
                return i
        return -1

    def _resolve_start_background(self, theme):
        """Figures out the actual starting background path, trying a few
        places in order, so a config.py that still names an old location
        (e.g. after moving everything into images/background/) degrades
        gracefully instead of rendering blank:
          1. themes/<theme>/images/<background_file>  (the classic location)
          2. themes/<theme>/images/background/<background_file>  (same
             filename, but now inside the cycle folder)
          3. the first image found in images/background/, if any
        """
        direct = os.path.join("themes", theme, "images", self.background_file)
        if os.path.exists(direct):
            self.bg_cycle_index = self._find_cycle_index(direct)
            return direct

        in_cycle_folder = os.path.join("themes", theme, "images", "background", self.background_file)
        if os.path.exists(in_cycle_folder):
            self.bg_cycle_index = self._find_cycle_index(in_cycle_folder)
            return in_cycle_folder

        if self.bg_cycle_files:
            logging.warning(
                "background_file '{}' not found - using the first image in "
                "images/background/ instead".format(self.background_file))
            self.bg_cycle_index = 0
            return self.bg_cycle_files[0]

        logging.warning(
            "background_file '{}' not found, and images/background/ has no "
            "images either - background will likely render blank".format(self.background_file))
        self.bg_cycle_index = -1
        return direct

    def cycle_background(self):
        if not self.bg_cycle_files:
            return
        self.bg_cycle_index = (self.bg_cycle_index + 1) % len(self.bg_cycle_files)
        self.bg_rect.source = self.bg_cycle_files[self.bg_cycle_index]

    def _load_background_music(self, theme):
        """Scans themes/<theme>/audio/background/ for music files and builds
        a shuffled playlist. The playlist is always built regardless of
        music_enabled, so M can still start it manually even when
        start_with_music is False in config.py - music_enabled only
        controls whether it starts on its own after the idle timeout."""
        self.music_playlist = []
        self.music_index = 0
        self.music_sound = None
        self.last_activity_time = time.time()

        extensions = {'.wav', '.ogg', '.mp3'}
        configured_ext = getattr(config, 'audio_extension', None)
        if configured_ext:
            extensions.add(configured_ext)
        files = []
        for ext in extensions:
            files += glob.glob(os.path.join("themes", theme, 'audio', 'background', "*" + ext))
        random.shuffle(files)
        self.music_playlist = files

    def toggle_music_mute(self):
        if self.music_sound is None:
            # Nothing loaded yet - most likely start_with_music is False in
            # config.py, or the idle timeout just hasn't fired yet. Either
            # way, start a fresh track now rather than muting nothing.
            self.start_music_now()
            return
        self.music_muted = not self.music_muted
        # If music is currently audible (idle, not already spin-muted),
        # apply the change immediately rather than waiting for the next
        # idle/spin transition.
        if self.state == 'idle':
            self.music_sound.volume = 0 if self.music_muted else 1

    def start_music_now(self):
        if not self.music_playlist:
            return
        self.music_enabled = True
        self.music_muted = False
        self._start_music_track()
        self.last_activity_time = time.time()

    def skip_music_track(self):
        if not self.music_playlist:
            return
        if self.music_sound is not None:
            self.music_sound.stop()
        self._advance_music_track()

    def _music_should_be_silent(self):
        return self.music_muted or self.state != 'idle'

    def _pause_background_music(self):
        # Mute rather than stop: Kivy's SDL2 provider doesn't reliably
        # support seek()/get_pos() (confirmed - get_pos() always reports 0
        # on this setup), so instead of stopping and trying to seek back,
        # the track just keeps playing silently underneath a spin and picks
        # up exactly where a listener would expect once unmuted.
        if self.music_sound is not None and self.music_sound.state == 'play':
            self.music_sound.volume = 0

    def _start_music_track(self):
        if not self.music_playlist:
            return
        path = self.music_playlist[self.music_index]
        snd = SoundLoader.load(path)
        if snd is None:
            logging.warning('background music failed to load: {}'.format(path))
            self._advance_music_track()
            return
        self.music_sound = snd
        snd.volume = 0 if self._music_should_be_silent() else 1
        snd.play()

    def _advance_music_track(self):
        self.music_index = (self.music_index + 1) % len(self.music_playlist)
        self._start_music_track()

    def _update_background_music(self):
        if not self.music_enabled or not self.music_playlist or self.state != 'idle':
            return
        if time.time() - self.last_activity_time < self.idle_music_timeout:
            return
        if self.music_sound is None:
            self._start_music_track()
        elif self.music_sound.volume == 0:
            if not self.music_muted:
                self.music_sound.volume = 1  # was muted during a spin - it never stopped, just unmute it
        elif self.music_sound.state != 'play':
            self._advance_music_track()  # previous track finished naturally

    def on_size(self, *args):
        if len(self.strips) == 0: return
        cx = self.size[0]/2
        ns = len(self.strips)
        sw = self.size[0] / (ns*2)
        mw = 20
        sx = cx - (ns*sw+(ns-1)*mw)/2
        for n, strip in enumerate(self.strips):
            strip.pos = (sx + n*sw + (n-1)*mw, 0)
            strip.size = (sw, self.size[1])
            if self.background_bars and n < len(self.bar_rects):
                bar = self.bar_rects[n]
                bar.pos = (strip.pos[0] - self.BAR_PAD, 0)
                bar.size = (sw + self.BAR_PAD * 2, self.size[1])
        self.payline.pos = (50, self.size[1]/2)
        self.payline.size = (self.size[0]-100, 10)

    def start_spin(self):
        if self.state == 'idle':
            self.state = 'STATE_SPINNING'
            self.stopped = 0
            snd = self.sounds.get('roll')
            if snd:
                snd.play()
            self.start_time = time.time()
            self.last_time = time.time()
            self.landed = []
            self.cancel_win_banner()
            self.target_symbols = self.pick_outcome()
            self._pause_background_music()
            self.last_activity_time = time.time()
        if self.state == 'key':
            self.state = 'STATE_SPINNING'

    def pick_outcome(self):
        """Decide the spin's result up front (weighted), then figure out
        which 3 landed symbols realize that result. The reels still spin and
        stop with the same visual timing as before — they just land on this
        predetermined result instead of wherever the scroll happens to be."""
        outcomes = list(self.outcome_weights.keys())
        weights = list(self.outcome_weights.values())
        outcome = random.choices(outcomes, weights=weights, k=1)[0]

        all_symbols = list(range(self.num_symbols))
        non_pumpkin = [s for s in all_symbols if s != self.pumpkin_symbol]

        if outcome == 'jackpot':
            return [self.pumpkin_symbol] * 3
        elif outcome == 'triple':
            sym = random.choice(non_pumpkin)
            return [sym] * 3
        elif outcome == 'double':
            pair_sym = random.choice(all_symbols)
            odd_sym = random.choice([s for s in all_symbols if s != pair_sym])
            symbols = [pair_sym, pair_sym, odd_sym]
            random.shuffle(symbols)
            return symbols
        else:  # 'none' - guarantee 3 distinct symbols, i.e. no match at all
            while True:
                picks = [random.choice(all_symbols) for _ in range(3)]
                if len(set(picks)) == 3:
                    return picks

    def cancel_win_banner(self):
        if self.game_screen is None:
            return
        banner = self.game_screen.win_banner
        label = self.game_screen.win_label
        Animation.cancel_all(banner)
        Animation.cancel_all(label)
        banner.opacity = 0
        self.game_screen.win_icon_left.opacity = 0
        self.game_screen.win_icon_right.opacity = 0
        self.game_screen.win_celebration.stop()

    def reel_icon_pixel_size(self):
        """The on-screen pixel size of one icon as it appears on the reels -
        derived from Strip's own sizing math, so it stays correct even if
        that math or the screen size ever changes."""
        return self.size[1] / (Strip.WINDOW_FRACTION * Strip.WINDOW_REFERENCE_N)

    def start_jackpot_celebration(self):
        if self.game_screen is None or not self.current_theme:
            return
        icon_dir = os.path.join("themes", self.current_theme, "images", "128")
        icon_paths = []
        for name in SYMBOL_NAMES[:self.num_symbols]:
            path = os.path.join(icon_dir, name + ".png")
            if os.path.exists(path):
                icon_paths.append(path)
        self.game_screen.win_celebration.start(icon_paths, icon_size=self.reel_icon_pixel_size())

    def start_triple_celebration(self, matched_symbol):
        if self.game_screen is None or not self.current_theme:
            return
        icon_path = os.path.join("themes", self.current_theme, "images", "128",
                                  symbol_name(matched_symbol) + ".png")
        if not os.path.exists(icon_path):
            return
        self.game_screen.win_celebration.start([icon_path],
                                                icon_size=self.reel_icon_pixel_size(),
                                                count=20)

    def calculate_payout(self, symbols):
        pumpkin_count = symbols.count(self.pumpkin_symbol)

        if pumpkin_count == 3:
            return 'jackpot', self.PAY_JACKPOT, pumpkin_count

        counts = Counter(symbols)
        max_match = max(counts.values())

        if max_match == 3:
            match_type, base = '3 of a kind', self.PAY_TRIPLE
        elif max_match == 2:
            match_type, base = 'double', self.PAY_DOUBLE
        else:
            match_type, base = 'spin', self.PAY_BASE

        if pumpkin_count == 1:
            base *= 2
        elif pumpkin_count == 2:
            base *= 3

        return match_type, base, pumpkin_count

    def show_win(self, match_type, payout, pumpkin_count=0):
        if self.game_screen is None:
            return
        style = TIER_STYLE[match_type]
        hold = getattr(config, 'win_banner_hold_seconds', style['hold'])
        banner = self.game_screen.win_banner
        label = self.game_screen.win_label
        icon_left = self.game_screen.win_icon_left
        icon_right = self.game_screen.win_icon_right
        Animation.cancel_all(banner)
        Animation.cancel_all(label)
        # Jackpot already implies 3 pumpkins and has its own banner text, so
        # only call out the bonus separately for the 1- or 2-pumpkin case.
        if pumpkin_count in (1, 2) and match_type != 'jackpot':
            text = 'PUMPKIN BONUS!\n{} treats'.format(payout)
            label_color = PUMPKIN_BONUS_COLOR
        else:
            text = style['text'].format(payout)
            label_color = style['color']

        # Flank the text with the pumpkin icon whenever a pumpkin's involved
        # at all (bonus tiers and jackpot), if that icon file is available.
        # These Image widgets are children of `banner`, so its own fade
        # animation (below) automatically fades them in/out too - no
        # separate animation needed here.
        icon_path = None
        if pumpkin_count >= 1 and self.current_theme:
            candidate = os.path.join("themes", self.current_theme, "images", "128",
                                      symbol_name(self.pumpkin_symbol) + ".png")
            if os.path.exists(candidate):
                icon_path = candidate

        if icon_path:
            icon_size = banner.height * 0.75
            icon_left.source = icon_path
            icon_right.source = icon_path
            icon_left.size = (icon_size, icon_size)
            icon_right.size = (icon_size, icon_size)
            icon_left.opacity = 1
            icon_right.opacity = 1
        else:
            icon_left.opacity = 0
            icon_right.opacity = 0

        label.text = text
        label.color = label_color
        label.font_size = banner.height * 0.08  # small starting point for the pop-in animation
        banner.opacity = 0

        banner_anim = (Animation(opacity=1, duration=0.2)
                       + Animation(duration=hold)
                       + Animation(opacity=0, duration=0.4))
        banner_anim.start(banner)

        target_size = banner.height * style['size_frac']
        label_anim = Animation(font_size=target_size, duration=0.25, t='out_back')
        label_anim.start(label)

    def update(self):
        dt = time.time() - self.start_time
        dtt = time.time() - self.last_time
        self.last_time = time.time()
        if self.state == 'idle':
            self.state = 'idle'
            self._update_background_music()
        elif self.state == 'STATE_SPINNING':
            for n in range(self.stopped, len(self.strips)):
                v = .8 + (n*.1)
                self.strips[n].add_uv(self, v * dtt)
            if dt > self.first_stop_length + self.stopped + random.uniform(0, 0.8):
                slotnum = self.target_symbols[self.stopped]
                # Kivy/GL reads the strip texture's vertical axis in the
                # opposite direction from slot_to_uv's own numbering, so the
                # slot we *display* has to be mirrored to actually show
                # `slotnum`. Everything else (logging, payout, sound) keeps
                # using the un-mirrored `slotnum` - only this render call
                # needs the flip.
                display_slot = (self.strips[self.stopped].num_symbols - 1) - slotnum
                self.strips[self.stopped].set_uv(self, self.strips[self.stopped].slot_to_uv(display_slot))
                snd = self.sounds.get('reel-icon-%d' % (slotnum+1))
                if snd:
                    snd.play()
                self.landed.append(slotnum)
                self.stopped += 1
                if self.stopped >= len(self.strips):
                    self.state = "FINAL"
        elif self.state == 'FINAL':
            match_type, payout, pumpkin_count = self.calculate_payout(self.landed)
            self.last_match_type = match_type
            self.last_payout = payout
            self.game_logger.log_spin(self.current_theme, self.landed, match_type,
                                       pumpkin_count, payout)

            self.play_result_sound(match_type, pumpkin_count)

            self.show_win(match_type, payout, pumpkin_count)
            if match_type == 'jackpot':
                self.start_jackpot_celebration()
            elif match_type == '3 of a kind':
                counts = Counter(self.landed)
                matched_symbol = max(counts, key=counts.get)
                self.start_triple_celebration(matched_symbol)
            coinDispense.dispenseCoin(payout)
            self.state = 'idle'

    def play_result_sound(self, match_type, pumpkin_count):
        """Prefers an icon-specific sound for doubles/triples and a
        dedicated jackpot sound, falling back to the generic 'win' sound
        for anything not recorded yet, so missing audio never breaks a spin.

        Expected filenames in the theme's audio folder (any extension):
          jackpot            - plays on 3 pumpkins
          win-<icon name>    - e.g. win-vampire, win-pumpkin, win-skeleton;
                                used for BOTH a double and a triple of that icon
        Icon names come from SYMBOL_NAMES, lowercased.
        """
        snd = None
        if match_type == 'jackpot':
            snd = self.sounds.get('jackpot')
        elif match_type in ('double', '3 of a kind'):
            counts = Counter(self.landed)
            matched_symbol = max(counts, key=counts.get)
            key = 'win-{}'.format(symbol_name(matched_symbol).lower())
            snd = self.sounds.get(key)

        if snd is None and (match_type != 'spin' or pumpkin_count >= 1):
            snd = self.sounds.get('win')

        if snd:
            snd.play()

class GameScreen(Screen):
    playing = False

    def start_game(self, theme):
        self.slots.setup(theme)
        self.slots.game_screen = self
        self.slots.on_size()
        self.timer = Clock.schedule_interval(self.update_timer, 0)

    def on_keyboard_down(self, keyboard, keycode, text, modifiers):
        if keycode[1] == "spacebar":
            self.slots.start_spin()
        if keycode[1] == "q":
            self.manager.current = "Start Screen"
        if keycode[1] == "m":
            self.slots.toggle_music_mute()
        if keycode[1] == "s":
            self.slots.skip_music_track()
        if keycode[1] == "b":
            self.slots.cycle_background()

    def update_timer(self, i=None, val=None):
        if self.manager.hardwareButton.checkButton():
            self.slots.start_spin()

        self.slots.update()
        if not self.playing:
            return  # don't move bird or pipes

        if self.manager.test_game_over():
            snd_game_over.play()
            self.playing = False

class StartScreen(Screen):
  def __init__(self, **kwargs):
    super(Screen, self).__init__(**kwargs)


  def build(self):
    #manager = kwargs['manager']
    themepaths = glob.glob("themes/*")

    self.themes = []
    for themepath in themepaths:
      if not os.path.isdir(themepath): continue
      path, theme = os.path.split(themepath)
      self.themes.append(theme)

    gl = self.buttons
    gl.size_hint = (.2, .1*len(self.themes))

    for theme in self.themes:
      bl = BoxLayout(size_hint=(.3, .3))
      gl.add_widget(bl)
      b = Button(text=theme, font_size='64sp', size_hint=(.9, .9), 
                 on_press=partial(self.manager.start_game, theme))
      bl.add_widget(b)

  def on_gamepad_down(self, obj, gamepad, buttonid):
    i = buttonid
    if i < len(self.themes):
      theme = self.themes[i]
      self.manager.start_game(theme)
      
  def on_keyboard_down(self, keyboard, keycode, text, modifiers):
    if keycode[1] in string.digits:
      i = int(keycode[1])
      if i==0: i=10
      i = i - 1
      if i < len(self.themes):
        theme = self.themes[i]
        self.manager.start_game(theme)

class SlotScreenManager(ScreenManager):
  hardwareButton = Hardware.hardwareButton()

  def start_game(self, theme, *args):
    self.current = "Game Screen"

    self.game_screen.start_game(theme)

class Slot(App):

    def build(self):
      self.root = viewport.Viewport(size=(1920,1080), do_scale=True)
      self.manager = SlotScreenManager()
      self.root.add_widget(self.manager)

      self.manager.start_screen = StartScreen()
      self.manager.add_widget(self.manager.start_screen)

      self.manager.game_screen = GameScreen()
      self.manager.add_widget(self.manager.game_screen)

      self._keyboard = Window.request_keyboard(self._keyboard_closed, self.manager, "text")
      self._keyboard.bind(on_key_down=self.on_keyboard_down)

      self._gamepad = Window.bind(on_joy_button_down=self.on_gamepad_down)

      self.current = "Start Screen"

      return self.root

    def _keyboard_closed(self):
      self._keyboard.unbind(on_key_down=self._on_keyboard_down)
      self._keyboard = None

    def on_gamepad_down(self, obj, gamepad, buttonid):
      self.manager.current_screen.on_gamepad_down(obj, gamepad, buttonid)

    def on_keyboard_down(self, keyboard, keycode, text, modifiers):
      if keycode[1] == 'escape':
        self.clean_exit()
        return
      self.manager.current_screen.on_keyboard_down(keycode, keycode, text, modifiers)

    def clean_exit(self):
      logging.warning('clean exit requested (escape)')
      try:
        Clock.unschedule(self.manager.game_screen.timer)
      except Exception:
        pass
      try:
        import RPi.GPIO as GPIO
        GPIO.cleanup()
      except Exception:
        pass
      # Kivy's normal App.stop()/window teardown can occasionally hang on the
      # Pi's KMS/DRM fullscreen driver. Rather than wait on that, terminate the
      # process immediately once our own cleanup above has run.
      os._exit(0)

    def on_start(self):
        self.spacing = 0.5 * self.root.width
        self.manager.start_screen.build()
        # if we have config.theme set, let's jump right to that theme
        theme = getattr(config, 'theme', None)
        if not theme:
            logging.warning('no theme set in config.py - staying on the start screen')
        else:
            try:
                self.manager.start_game(theme)
            except Exception as e:
                logging.warning('failed to auto-start theme {!r}: {}'.format(theme, e))

        if 0:
          self.slots = self.root.ids.slots
          #self.bird = self.root.ids.bird
          Clock.schedule_interval(self.update, 0.004)

          Window.bind(on_key_down=self.on_key_down)
          self.slots.on_touch_down = self.user_action

    def update(self, nap):
        if self.hardwareButton.checkButton():
            self.user_action()

        self.slots.update()
        if not self.playing:
            return  # don't move bird or pipes

        if self.test_game_over():
            snd_game_over.play()
            self.playing = False


    def user_action(self, *args):
        self.slots.start_spin()

def parse_args(argv):
  parser = argparse.ArgumentParser(
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    description=__doc__)

  parser.add_argument("-t", "--test", dest="test_flag", 
                    default=False,
                    action="store_true",
                    help="Run test function")
  parser.add_argument("--log-level", type=str,
                      choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                      help="Desired console log level")
  parser.add_argument("-d", "--debug", dest="log_level", action="store_const",
                      const="DEBUG",
                      help="Activate debugging")
  parser.add_argument("-q", "--quiet", dest="log_level", action="store_const",
                      const="CRITICAL",
                      help="Quite mode")

  args = parser.parse_args(argv[1:])

  return parser, args


def main(argv, stdout, environ):
  if sys.version_info < (3, 0): reload(sys); sys.setdefaultencoding('utf8')

  parser, args = parse_args(argv)

  logging.basicConfig(format="[%(asctime)s] %(levelname)-8s %(message)s", 
                    datefmt="%m/%d %H:%M:%S", level=args.log_level)

  Window.clearcolor = get_color_from_hex("000000")
  
  Hardware.setup()

  Slot().run()
  

if __name__ == '__main__':
  main(sys.argv, sys.stdout, os.environ)
