#!/usr/bin/env python3
from __future__ import division

import random
import os, sys, time, math, logging, argparse, glob, csv, atexit, json, bisect, colorsys, re

import config

# All game art and sound lives in assets/ next to this file.
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')


def asset(*parts):
    return os.path.join(ASSETS, *parts)

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
from kivy.animation import Animation, AnimationTransition

from kivy.app import App
from kivy.uix.screenmanager import Screen
from kivy.uix.floatlayout import FloatLayout
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.lang import Builder
from kivy.core.image import Image
from kivy.core.window import Window
from kivy.uix.widget import Widget
from kivy.properties import NumericProperty
from kivy.graphics import *
from kivy.utils import get_color_from_hex


import viewport

Builder.load_string('''
<GameScreen>:
    slots: _id_slots
    win_label: _win_label
    win_banner: _win_banner
    win_icon_left: _win_icon_left
    win_icon_right: _win_icon_right
    win_celebration: _win_celebration
    status_label: _status_label
    help_label: _help_label
    name: "Game Screen"
    FloatLayout:
        Slots:
            id: _id_slots
            canvas:
        # Drawn after the reels but before the banner, so win animations
        # fly over the reels and behind the banner
        JackpotCelebration:
            id: _win_celebration
        FloatLayout:
            id: _win_banner
            size_hint: (1, None)
            height: 300
            pos_hint: {'center_x': .5, 'y': .2}
            opacity: 0
            canvas.before:
                Color:
                    rgba: 0.12, 0.12, 0.12, app.banner_opacity
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
        Label:
            id: _status_label
            text: ""
            font_size: '36sp'
            bold: True
            color: 1, 1, 1, 1
            opacity: 0
            size_hint: (None, None)
            size: self.texture_size
            padding: (20, 10)
            pos_hint: {'x': .01, 'top': .99}
            canvas.before:
                Color:
                    rgba: 0, 0, 0, 0.6
                Rectangle:
                    pos: self.pos
                    size: self.size
        Label:
            id: _help_label
            text: ""
            markup: True
            font_name: 'RobotoMono-Regular'
            font_size: '30sp'
            line_height: 1.25
            color: 1, 1, 1, 1
            opacity: 0
            size_hint: (None, None)
            size: self.texture_size
            padding: (60, 40)
            pos_hint: {'center_x': .5, 'center_y': .5}
            canvas.before:
                Color:
                    rgba: 0, 0, 0, 0.92
                Rectangle:
                    pos: self.pos
                    size: self.size
''')

# 

# should this be global?
ledStrip = Hardware.ledStrip()

def _led_off_at_exit():
    try:
        ledStrip.off()
    except Exception:
        pass

# Covers normal exits and uncaught exceptions. Escape uses os._exit, which
# skips atexit, so clean_exit() also shuts the strip off explicitly.
atexit.register(_led_off_at_exit)

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

    FIELDS = ['timestamp', 'reel1', 'reel2', 'reel3',
              'result', 'pumpkin_count', 'payout']

    def __init__(self, log_dir='logs'):
        self.path = None
        try:
            os.makedirs(log_dir, exist_ok=True)
            date_str = time.strftime('%Y-%m-%d')
            self.path = os.path.join(log_dir, 'spins_{}.csv'.format(date_str))
            n = 2
            while os.path.exists(self.path) and not self._header_matches(self.path):
                # Today's file was written with different columns (an older
                # version of the game) - start a new one rather than mix them.
                self.path = os.path.join(log_dir, 'spins_{}_{}.csv'.format(date_str, n))
                n += 1
            if not os.path.exists(self.path):
                with open(self.path, 'w', newline='') as f:
                    csv.writer(f).writerow(self.FIELDS)
        except Exception as e:
            logging.warning('game log disabled - could not set up {}: {}'.format(log_dir, e))
            self.path = None

    def _header_matches(self, path):
        with open(path, newline='') as f:
            return next(csv.reader(f), None) == self.FIELDS

    def log_spin(self, landed, match_type, pumpkin_count, payout):
        if self.path is None:
            return
        row = [
            time.strftime('%Y-%m-%d %H:%M:%S'),
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


##  [1.100, .942, .759, .598, .444, .273]

TIER_STYLE = {
    'spin':        {'color': (1, 1, 1, 1),      'size_frac': 0.20, 'hold': 0.3, 'text': '{} treats'},
    'double':      {'color': (213/255, 135/255, 49/255, 1),  'size_frac': 0.24, 'hold': 0.7, 'text': 'DOUBLE!\n{} treats'},
    '3 of a kind': {'color': (1, 0.55, 0.1, 1),  'size_frac': 0.28, 'hold': 1.0, 'text': '3 OF A KIND!\n{} treats'},
    'jackpot':     {'color': (1, 0.25, 0.05, 1), 'size_frac': 0.34, 'hold': 2.0, 'text': 'JACKPOT!!!'},
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


class JackpotCelebration(Widget):
    """Full-screen overlay of icons falling from above the screen under
    gravity, bouncing softly off the bottom, and drifting off the left/right
    edges to disappear - the classic 'cascade' win-screen effect, built from
    scratch using this game's own icon art. All the physics knobs below can
    be overridden from config.py (see the matching config_* names in
    __init__) without touching this class.

    The icons are drawn as plain textured rectangles on this widget's canvas
    (one shared texture per icon image) rather than as 50 Image widgets:
    moving a rectangle is just a number change, where moving a widget sets
    off property events and layout passes - slow enough on a Pi to make the
    animation stutter, and creating the widgets froze the start of the win."""

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
        self._bodies = []  # list of [Rectangle, x, y, vx, vy]
        self._textures = {}  # icon path -> texture, loaded once
        self.run_seconds = 0.0
        self._rain_until = 0.0
        self._update_ev = None
        self._stop_ev = None

        self.duration = getattr(config, 'jackpot_duration', self.DURATION)
        self.icon_count = getattr(config, 'jackpot_icon_count', self.ICON_COUNT)
        self.icon_size = getattr(config, 'jackpot_icon_size', self.ICON_SIZE)
        self.drift_speed_range = getattr(config, 'jackpot_drift_speed_range', self.DRIFT_SPEED_RANGE)
        self.spawn_height_range = getattr(config, 'jackpot_spawn_height_range', self.SPAWN_HEIGHT_RANGE)
        self.gravity = getattr(config, 'jackpot_gravity', self.GRAVITY)
        self.bottom_restitution = getattr(config, 'jackpot_bottom_restitution', self.BOTTOM_RESTITUTION)

    RAIN_TAIL = 3.0   # seconds before the end when re-dropping stops, so the screen clears

    def start(self, icon_paths, icon_size=None, count=None, duration=None):
        """Starts the rain. With a `duration` longer than usual (the
        jackpot, matched to its music), icons that fall off the screen
        are dropped back in from the top until shortly before the end."""
        self.stop()
        if not icon_paths:
            return
        self.run_seconds = max(self.duration, duration or 0)
        # Only a stretched run (the jackpot) keeps re-dropping icons; a
        # triple's rain falls once and drifts off, as it always did.
        self._rain_until = (time.time() + self.run_seconds - self.RAIN_TAIL) if duration else 0.0
        self._spawn_rain(icon_paths,
                         icon_size if icon_size is not None else self.icon_size,
                         count if count is not None else self.icon_count)
        self.opacity = 1
        self._update_ev = Clock.schedule_interval(self._update, 0)
        self._stop_ev = Clock.schedule_once(self.stop, self.run_seconds)

    def _spawn_rain(self, icon_paths, size, n):
        """Adds `n` icons above the top of the screen, ready to fall."""
        self.icon_size_now = size
        with self.canvas:
            Color(1, 1, 1, 1)
            for i in range(n):
                path = random.choice(icon_paths)
                texture = self._textures.get(path)
                if texture is None:
                    texture = self._textures[path] = Image(path).texture
                # Start above the screen (staggered height = staggered fall
                # timing) at a random x. Icons spawned on the left half drift
                # right as they fall, and vice versa, so they cross the screen
                # rather than drifting randomly.
                x = random.uniform(0, 1920 - size)
                y = 1080 + random.uniform(*self.spawn_height_range)
                direction = 1 if x < (1920 - size) / 2 else -1
                vx = direction * random.uniform(*self.drift_speed_range)
                rect = Rectangle(texture=texture, pos=(x, y), size=(size, size))
                self._bodies.append([rect, x, y, vx, 0.0])

    MAX_FALL_SPEED = 1200   # px/s - icons dropped from high up would otherwise hit
                            # the bottom so fast they bounce back over the top of
                            # the screen, looking like they came from the bottom

    def _update(self, dt):
        dt = min(dt, 0.05)  # a slow frame mustn't fling icons across the screen
        size = self.icon_size_now
        margin = size + 50  # fully off-screen before we despawn
        gravity, restitution = self.gravity, self.bottom_restitution
        max_fall = self.MAX_FALL_SPEED
        surviving = []
        for body in self._bodies:
            rect, x, y, vx, vy = body
            vy = max(vy + gravity * dt, -max_fall)
            x += vx * dt
            y += vy * dt

            if y <= 0:
                y = 0
                vy = abs(vy) * restitution

            # No side walls - icons that drift past either edge just keep
            # going and get removed once they're fully out of view.
            if x + size < -margin or x > 1920 + margin:
                if time.time() < self._rain_until:
                    # Still going - drop it back in from the top
                    x = random.uniform(0, 1920 - size)
                    y = 1080 + random.uniform(0, 600)
                    vx = (1 if x < (1920 - size) / 2 else -1) * random.uniform(*self.drift_speed_range)
                    rect.pos = (x, y)
                    body[1], body[2], body[3], body[4] = x, y, vx, 0.0
                    surviving.append(body)
                else:
                    self.canvas.remove(rect)
                continue

            rect.pos = (x, y)
            body[1], body[2], body[4] = x, y, vy
            surviving.append(body)
        self._bodies = surviving

    # Fireworks (the jackpot): pumpkins bursting out of the reel pumpkins
    FW_GRAVITY = -520            # px/s^2 - bends each burst into arcs
    FW_SPEED = (420, 1050)       # launch speed range, px/s
    FW_LIFE = (1.3, 2.0)         # seconds each pumpkin flies before fading out
    FW_PER_BURST = (9, 14)       # pumpkins per burst
    FW_GAP = (0.3, 0.85)         # seconds between bursts
    FW_SCALE = (0.45, 0.95)      # pumpkin size vs. the reel icons
    FW_ROCKET_SPEED = (880, 1000) # rockets: launch speed, px/s (bursts ~300-480 px above the reels)
    FW_ROCKET_FUSE = (0.6, 0.8)  # rockets: seconds of flight before they explode
    FW_ROCKET_SPREAD = 0.6       # rockets: max lean from straight up, radians (~35 deg)

    def _texture(self, path):
        texture = self._textures.get(path)
        if texture is None:
            texture = self._textures[path] = Image(path).texture
        return texture

    def start_fireworks(self, icon_path, origins, size, duration=None, alt_paths=None):
        """Fireworks: every icon on the payline bursts at once, then they
        take turns firing bursts of icons in all directions at random
        moments until shortly before `duration` is up (or the usual
        celebration length), so the last burst fades out on time. With
        `alt_paths`, every other burst uses one of those icons instead,
        picked at random (the jackpot: pumpkin, vampire, pumpkin, ...)."""
        self.stop()
        if not origins or not os.path.exists(icon_path):
            return
        self.run_seconds = max(self.duration, duration or 0)
        # Share of launches that are rockets: one icon shooting up with a
        # trail, exploding into a burst up in the air
        self.rocket_chance = getattr(config, 'fireworks_rocket_chance', 0.67)
        now = time.time()
        alt = [p for p in (alt_paths or []) if os.path.exists(p)]
        self._fw = {'main': self._texture(icon_path),
                    'alt': [self._texture(p) for p in alt],
                    'count': 0, 'origins': origins, 'size': size,
                    'next': now + random.uniform(*self.FW_GAP),
                    'last_launch': now + self.run_seconds - self.FW_LIFE[1]}
        self._sparks = []
        self.opacity = 1
        for origin in origins:                      # the opening volley
            self._fw_burst(origin, now, big=True)
        self._update_ev = Clock.schedule_interval(self._fw_update, 0)
        self._stop_ev = Clock.schedule_once(self.stop, self.run_seconds)

    def _fw_next_texture(self):
        """Main icon for even bursts; with alternates, a random one of
        those for odd bursts."""
        fw = self._fw
        fw['count'] += 1
        if fw['alt'] and fw['count'] % 2 == 0:
            return random.choice(fw['alt'])
        return fw['main']

    def _fw_add(self, texture, x, y, vx, vy, scale, life, now, kind='spark'):
        """kind: 'spark' (a flying piece of a burst), 'pop' (the flash at a
        burst's centre), 'rocket' (one icon climbing before it explodes)
        or 'trail' (a fading copy left behind a rocket)."""
        fw = self._fw
        s = fw['size'] * scale
        group = InstructionGroup()
        color = Color(1, 1, 1, 1)
        rect = Rectangle(texture=texture, pos=(x - s / 2, y - s / 2), size=(s, s))
        group.add(color)
        group.add(rect)
        self.canvas.add(group)
        self._sparks.append([group, color, rect, x, y, vx, vy, now, life, s, kind, now])

    def _fw_rocket(self, origin, now):
        """One icon shooting up from the reel at a slight angle; it
        explodes into a burst of the same icon when its fuse runs out."""
        ox, oy = origin
        texture = self._fw_next_texture()
        angle = math.pi / 2 + random.uniform(-self.FW_ROCKET_SPREAD, self.FW_ROCKET_SPREAD)
        speed = random.uniform(*self.FW_ROCKET_SPEED)
        self._fw_add(texture, ox, oy, math.cos(angle) * speed, math.sin(angle) * speed,
                     1.0, random.uniform(*self.FW_ROCKET_FUSE), now, kind='rocket')

    def _fw_burst(self, origin, now, big=False, texture=None):
        ox, oy = origin
        if texture is None:
            texture = self._fw_next_texture()
        # the "pop": the icon swelling up and fading at the launch point
        self._fw_add(texture, ox, oy, 0, 0, 1.0, 0.35, now, kind='pop')
        count = random.randint(*self.FW_PER_BURST) + (4 if big else 0)
        spin = random.uniform(0, 2 * math.pi)
        for i in range(count):
            angle = spin + 2 * math.pi * i / count + random.uniform(-0.15, 0.15)
            speed = random.uniform(*self.FW_SPEED) * (1.15 if big else 1.0)
            self._fw_add(texture, ox, oy, math.cos(angle) * speed, math.sin(angle) * speed,
                         random.uniform(*self.FW_SCALE), random.uniform(*self.FW_LIFE), now)

    def _fw_update(self, dt):
        dt = min(dt, 0.05)
        fw = self._fw
        now = time.time()
        if fw['next'] <= now < fw['last_launch']:
            for _ in range(2 if random.random() < 0.2 else 1):   # now and then, two at once
                if random.random() < self.rocket_chance:
                    self._fw_rocket(random.choice(fw['origins']), now)
                else:
                    self._fw_burst(random.choice(fw['origins']), now)
            fw['next'] = now + random.uniform(*self.FW_GAP)
        drag = 0.6 ** dt                                # air resistance
        alive = []
        explode = []
        trails = []
        for spark in self._sparks:
            group, color, rect, x, y, vx, vy, born, life, s0, kind = spark[:11]
            age = (now - born) / life
            if age >= 1.0:
                self.canvas.remove(group)
                if kind == 'rocket':
                    explode.append((x, y, rect.texture))
                continue
            if kind == 'pop':                           # the flash at a burst's centre
                s = s0 * (1.0 + 0.9 * age)
                color.a = 1.0 - age
            elif kind == 'trail':                       # fading copy behind a rocket
                s = s0 * (1.0 - 0.5 * age)
                color.a = 0.7 * (1.0 - age)
            elif kind == 'rocket':                      # climbing, full size, until the fuse ends
                vx *= drag
                vy = vy * drag + self.FW_GRAVITY * dt
                x += vx * dt
                y += vy * dt
                s = s0
                spark[3], spark[4], spark[5], spark[6] = x, y, vx, vy
                if now - spark[11] > 0.03:              # drop a trail copy every few frames
                    spark[11] = now
                    trails.append((x, y, rect.texture))
            else:
                vx *= drag
                vy = vy * drag + self.FW_GRAVITY * dt
                x += vx * dt
                y += vy * dt
                s = s0 * (1.0 - 0.45 * age)
                color.a = 1.0 - age * age
                spark[3], spark[4], spark[5], spark[6] = x, y, vx, vy
            rect.pos = (x - s / 2, y - s / 2)
            rect.size = (s, s)
            alive.append(spark)
        self._sparks = alive
        for x, y, texture in trails:
            self._fw_add(texture, x, y, 0, 0, 0.45, 0.4, now, kind='trail')
        for x, y, texture in explode:
            self._fw_burst((x, y), now, texture=texture)

    def stop(self, *args):
        if self._update_ev:
            self._update_ev.cancel()
            self._update_ev = None
        if self._stop_ev:
            self._stop_ev.cancel()
            self._stop_ev = None
        self.canvas.clear()
        self._bodies = []
        self._sparks = []
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

    # Default background image filename, in assets/images/background/. Override
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
        self.game_logger = GameLogger()
        self.background_file = getattr(config, 'background_file', self.BACKGROUND_FILE)
        # Only draw bars automatically when NOT using the original default
        # background (which already has them baked in) - unless config.py
        # explicitly says otherwise via `background_bars`.
        self.background_bars = getattr(config, 'background_bars',
                                        self.background_file != self.BACKGROUND_FILE)
        self.bar_rects = []
        self.bg_gif_textures = []
        self.bg_gif_index = 0
        self.bg_anim_event = None

        # LED strip has three modes:
        #   idle     - slow pulse, one color at a time (see below)
        #   spinning - every other LED green/orange, swapping back and forth
        #   win      - flashes the matching tier color (reusing TIER_STYLE's
        #              own colors, so the LEDs and the on-screen banner agree)
        self._led_flash_event = None
        self._led_flash_state = None
        # Idle effect, repeating:
        #   orange pulse, green pulse, purple runner over steady green,
        #   orange pulse, green pulse, purple runner over steady orange
        # Each pulse fades up from fully dark and back down. The runner
        # sweeps down the strip and back once over a steady background that
        # fades in and out with it; the background color alternates through
        # the idle colors each round. All optional in config.py:
        #   led_idle_colors     - list of (r, g, b) 0-255 colors to alternate through
        #   led_pulse_seconds   - seconds for one color's full fade up and back down
        #   led_pulse_gap       - seconds the strip stays dark between effects
        #   led_runner_color    - (r, g, b) of the runner
        #   led_runner_seconds  - seconds for the runner's trip there and back
        #                         (0 turns the runner off)
        #   led_runner_background_level - background brightness under the
        #                         runner, 0-1 (lower makes the purple stand out)
        self.led_idle_colors = getattr(config, 'led_idle_colors',
                                       [(255, 50, 0), (0, 200, 15)])
        self.led_pulse_seconds = getattr(config, 'led_pulse_seconds', 4.0)
        self.led_pulse_gap = getattr(config, 'led_pulse_gap', 0.1)
        self.led_runner_color = getattr(config, 'led_runner_color', (140, 0, 255))
        self.led_runner_seconds = getattr(config, 'led_runner_seconds', 3.0)
        self.led_runner_background_level = getattr(config, 'led_runner_background_level', 0.6)
        self.led_count = getattr(config, 'led_count', 60)
        self._led_idle_event = None
        self._led_idle_phase_start = 0.0
        self._led_last_rgb = None
        # Spinning effect, also optional in config.py:
        #   led_spin_colors   - colors laid out every other LED (default orange, green)
        #   led_spin_interval - seconds between the colors swapping places
        self.led_spin_colors = getattr(config, 'led_spin_colors',
                                       [(255, 50, 0), (0, 200, 15)])
        self.led_spin_interval = getattr(config, 'led_spin_interval', 0.2)
        self._led_spin_event = None
        self._led_spin_offset = 0
        # Win light show. It lasts exactly as long as the on-screen win
        # animation (banner, plus falling icons on a triple/jackpot), and
        # alternates between strobing through these colors and chasing them
        # along the strip in blocks. Optional in config.py:
        #   led_win_colors - list of (r, g, b) 0-255 colors
        # White is kept a bit below full: all 200 LEDs at full white draw the
        # most current of any color and can brown out the strip's supply.
        self.led_win_colors = getattr(config, 'led_win_colors', [
            (0, 200, 15),     # green
            (140, 0, 255),    # purple
            (255, 50, 0),     # orange
            (170, 170, 170),  # white
        ])

        # Idle background music - starts after IDLE_MUSIC_TIMEOUT seconds of
        # no spins, pauses (and remembers position) the moment a spin starts,
        # and resumes right where it left off next time it goes idle again -
        # by muting instead of stopping (see _pause_background_music), since
        # Kivy's SDL2 provider get_pos()/seek() are known to always report 0.
        self.music_enabled = getattr(config, 'start_with_music', True)

        # Sound mix. Volume can't go above 1.0 (the file's own level), so
        # wins stand out by keeping the spin sounds a little lower.
        #   win_sound_delay     - seconds after the reels stop before the win
        #                         sound plays, so it doesn't run into the
        #                         tail of the spin sound
        #   win_volume          - win/jackpot sounds, 0-1
        #   spin_sounds_volume  - the spin (roll) and reel-stop sounds, 0-1
        #   music_volume        - background music, 0-1 (defaults to the same
        #                         level as the spin sounds)
        # The jackpot sound skips the delay: it starts the moment the spin
        # sound finishes (or right away, if it already has).
        self.win_sound_delay = getattr(config, 'win_sound_delay', 2.0)
        self.win_volume = getattr(config, 'win_volume', 1.0)
        self.spin_sounds_volume = getattr(config, 'spin_sounds_volume', 0.8)
        self.music_volume = getattr(config, 'music_volume', self.spin_sounds_volume)
        self._win_sound_event = None
        self._roll_ends_at = 0.0   # when the current spin sound finishes
        self._jackpot_sound = None # music waits while this is due or playing
        self._jackpot_show_seconds = 0.0   # jackpot animation length (its music's length)
        self.music_muted = False
        self.idle_music_timeout = getattr(config, 'idle_music_timeout', self.IDLE_MUSIC_TIMEOUT)
        self.music_playlist = []
        self.music_index = 0
        self.music_sound = None
        self.last_activity_time = time.time()
        # 'order': by the number at the start of each file name (1, 2 ... 12);
        # 'shuffle': every song once in random order before any repeats.
        # The P key switches between them.
        self.music_playback = getattr(config, 'music_playback', 'order')

        # Music lights: while background music is audible and idle, the
        # strip follows that track's light map (built ahead of time by
        # make_light_maps.py) instead of the pulse/runner loop. Optional in
        # config.py:
        #   led_music_lights - False to start with the normal idle loop
        #                      (the L key toggles this while running)
        #   led_music_colors - colors the lights step through
        #   led_music_beats_per_color - beats before moving to the next color
        #   led_music_style  - 'meter'   (default) a level meter bouncing out
        #                                  from the middle with peak dots
        #                      'party'   a full light show that follows the
        #                                  song's harmony, sections, bars,
        #                                  cymbals and drops
        #                      'halloween_party'  the party show in Halloween
        #                                  colors only (led_halloween_colors)
        #                      'ripples' each beat ripples out from the middle
        #                      'pulse'   the whole strip flashes on each beat
        #   led_music_meter_dim - ('meter' only) bar brightness between beats,
        #                      0-1; it flares to full on each beat. 1 = no pulsing
        #   led_music_accent_threshold - ('ripples' only) how hard a beat
        #                      must hit (0-100) to ripple in the accent color
        #   led_music_offset - seconds to shift the lights vs the music;
        #                      positive = lights later, negative = earlier
        #                      ([ and ] keys adjust this while running)
        self.led_music_lights = getattr(config, 'led_music_lights', True)
        self.led_music_colors = getattr(config, 'led_music_colors', [
            (255, 50, 0),    # orange
            (0, 200, 15),    # green
            (140, 0, 255),   # purple
        ])
        self.led_music_beats_per_color = getattr(config, 'led_music_beats_per_color', 16)
        self.led_music_style = getattr(config, 'led_music_style', 'meter')
        self.led_music_meter_dim = getattr(config, 'led_music_meter_dim', 0.45)
        self.led_halloween_colors = getattr(config, 'led_halloween_colors', [
            (255, 70, 0),     # orange
            (130, 0, 255),    # purple
            (60, 255, 0),     # green
        ])
        self._meter = None            # level meter state, reset per track
        self._party = None            # party show state, reset per track
        self.led_music_accent_threshold = getattr(config, 'led_music_accent_threshold', 95)
        self.led_music_offset = getattr(config, 'led_music_offset', 0.04)
        self._music_started_at = 0.0
        self._music_map = None        # light map for the current track, or None
        self._led_music_mode = False  # whether the idle tick is following music

    def setup(self):
        for strip in self.strips:
            del strip
        self.canvas.clear()
        self.start_time = time.time()
        self.strips = []

        self._load_background_cycle()
        start_bg_path = self._resolve_start_background()

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
                core_img = Image(asset("images", "stripbig1.png"))
                strip = Strip(core_img, num_symbols=self.num_symbols)
                strip.set_uv(self, strip.slot_to_uv(0))
                self.strips.append(strip)
            Color(*TIER_STYLE['jackpot']['color'])
            self.payline = Rectangle()
        self.last_time = time.time()

        self.sounds = {}
        # Sound effects: assets/audio/ and assets/audio/reels/, any mix of
        # .wav/.ogg/.mp3 (Kivy's SDL2 audio plays all three). Each is keyed
        # by filename without extension. audio/background/ is the music
        # playlist - loaded separately, one song at a time.
        files = []
        for folder in (asset('audio'), asset('audio', 'reels')):
            for ext in ('.wav', '.ogg', '.mp3'):
                files += glob.glob(os.path.join(folder, '*' + ext))
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

        self._load_background_music()
        self._led_set_idle()

    def _led_to_rgb255(self, float_color):
        """Converts one of TIER_STYLE's 0-1 float colors (Kivy's format) to
        the 0-255 integers the LED strip wants."""
        return tuple(int(max(0, min(1, c)) * 255) for c in float_color[:3])

    def _led_set_idle(self):
        if self._led_flash_event:
            return  # a flash is mid-sequence - it'll restore idle itself when done
        if self._led_idle_event:
            return  # already pulsing - leave the phase alone
        if self._led_spin_event:
            return  # reels are spinning - idle resumes once they stop
        self._led_idle_phase_start = time.time()
        self._led_last_rgb = None
        # ~30 updates/sec keeps the fade smooth and the main loop light
        self._led_idle_event = Clock.schedule_interval(self._led_idle_tick, 1 / 30.)

    def _led_idle_stop(self):
        if self._led_idle_event:
            self._led_idle_event.cancel()
            self._led_idle_event = None

    def _music_lights_active(self):
        snd = self.music_sound
        return (self.led_music_lights and self._music_map is not None and snd is not None
                and snd.state == 'play' and snd.volume > 0 and self.state == 'idle')

    def _led_idle_tick(self, dt):
        if self._music_lights_active():
            self._led_music_mode = True
            self._led_music_frame()
            return
        if self._led_music_mode:
            # Music just stopped or was muted - restart the loop from the
            # top (fades up from dark) rather than jumping in mid-pulse.
            self._led_music_mode = False
            self._led_idle_phase_start = time.time()
            self._led_last_rgb = None
        colors = self.led_idle_colors
        if not colors:
            return
        pulse = max(0.5, self.led_pulse_seconds)
        gap = max(0.0, self.led_pulse_gap)
        runner = max(0.0, self.led_runner_seconds)
        n = len(colors)
        # One round = a pulse of each color, then a runner over a background
        # color; the background steps backwards through the colors each
        # round (green, then orange). Each step is followed by a short gap.
        # The full pattern repeats after n rounds.
        steps = []
        for rnd in range(n):
            steps += [('pulse', c) for c in colors]
            if runner > 0:
                steps.append(('runner', colors[(-1 - rnd) % n]))
        def step_len(kind):
            return (pulse if kind == 'pulse' else runner) + gap
        elapsed = time.time() - self._led_idle_phase_start
        pos = elapsed % sum(step_len(k) for k, _ in steps)
        for kind, base in steps:
            if pos < step_len(kind):
                break
            pos -= step_len(kind)
        if kind == 'runner' and pos < runner:
            self._led_runner_frame(pos / runner, base)
            self._led_last_rgb = None   # strip no longer matches any solid color
            return
        if kind == 'runner' or pos >= pulse:
            level = 0.0   # dark pause between effects
        else:
            # Smooth 0 -> 1 -> 0 that starts and ends fully dark, so the color
            # change always happens while the strip is off. The 1.5 power
            # suits how LED brightness looks to the eye without leaving the
            # strip near-black for long at either end.
            wave = 0.5 - 0.5 * math.cos(2 * math.pi * (pos / pulse))
            level = wave ** 1.5
        rgb = (int(round(base[0] * level)), int(round(base[1] * level)),
               int(round(base[2] * level)))
        if rgb != self._led_last_rgb:   # skip redundant strip refreshes
            self._led_last_rgb = rgb
            ledStrip.set_all(*rgb)

    # Music light timing
    LED_MUSIC_FADE_SECONDS = 1.5     # crossfade between base colors
    LED_RIPPLE_SECONDS = 0.9         # how long a beat's ripple lives
    LED_RIPPLE_REACH_SECONDS = 0.55  # time for a ripple to reach the strip ends
    LED_RIPPLE_WIDTH = 4.0           # LEDs either side of a ripple's crest

    def _led_music_frame(self):
        """One frame of the music lights. Every style shares a base color
        that changes every `led_music_beats_per_color` beats, crossfading
        over a second or so, plus an accent (the next color).
          meter:   see _led_meter_frame
          ripples: bass glow + soft beat flash, and each beat sends a ring
                   of light from the middle out to both ends; strong beats
                   ripple in the accent color
          pulse:   bass glow + a whole-strip flash on every beat
        """
        light_map = self._music_map
        colors = self.led_music_colors
        n = self.led_count
        if not colors or n <= 0:
            return
        t = time.time() - self._music_started_at - self.led_music_offset
        energy = light_map['energy']
        idx = int(t * light_map['fps'])
        e = energy[idx] / 100.0 if 0 <= idx < len(energy) else 0.0
        beats = light_map['beats']
        beat_times = light_map['beat_times']
        k = bisect.bisect_right(beat_times, t) - 1   # most recent beat

        # Base color, crossfading from the previous phrase's color
        per = max(1, self.led_music_beats_per_color)
        phrase = k // per if k >= 0 else 0
        def lerp(a, b, f):
            return tuple(x + (y - x) * f for x, y in zip(a, b))
        base = colors[phrase % len(colors)]
        accent = colors[(phrase + 1) % len(colors)]
        if phrase > 0:
            since = t - beat_times[phrase * per]
            mix = min(1.0, since / self.LED_MUSIC_FADE_SECONDS)
            base = lerp(colors[(phrase - 1) % len(colors)], base, mix)
            accent = lerp(colors[phrase % len(colors)], accent, mix)

        if self.led_music_style == 'party' and 'intensity' in light_map:
            self._led_party_frame(t, e, k)
            return
        if self.led_music_style == 'halloween_party' and 'intensity' in light_map:
            self._led_party_frame(t, e, k, palette=self.led_halloween_colors)
            return
        if self.led_music_style in ('meter', 'party', 'halloween_party'):   # old maps fall back to meter
            self._led_meter_frame(t, e, k, base, accent)
            return

        # Whole-strip level: bass glow, plus a quick flash on each beat
        level = 0.08 + 0.32 * e
        if k >= 0:
            beat_time, strength = beats[k]
            flash_size = 0.35 if self.led_music_style == 'ripples' else 1.0
            flash = flash_size * (0.45 + 0.55 * strength / 100.0) * math.exp(-(t - beat_time) / 0.22)
            level = max(level, flash)
        r0, g0, b0 = base[0] * level, base[1] * level, base[2] * level

        if self.led_music_style != 'ripples':
            ledStrip.set_all(int(r0), int(g0), int(b0))
            return

        # Ripples from the last few beats still in flight
        ripples = []
        for j in range(max(0, k - 3), k + 1):
            beat_time, strength = beats[j]
            age = t - beat_time
            if age < 0 or age > self.LED_RIPPLE_SECONDS:
                continue
            amp = (0.4 + 0.6 * strength / 100.0) * (1 - age / self.LED_RIPPLE_SECONDS) ** 1.5
            color = accent if strength >= self.led_music_accent_threshold else base
            radius = (age / self.LED_RIPPLE_REACH_SECONDS) * (n / 2.0)
            ripples.append((radius, amp, color))

        center = (n - 1) / 2.0
        width = self.LED_RIPPLE_WIDTH
        pixels = []
        for i in range(n):
            r, g, b = r0, g0, b0
            d = abs(i - center)
            for radius, amp, color in ripples:
                near = 1.0 - abs(d - radius) / width
                if near > 0:
                    a = amp * near
                    r += color[0] * a
                    g += color[1] * a
                    b += color[2] * a
            pixels.append((min(255, int(r)), min(255, int(g)), min(255, int(b))))
        ledStrip.set_pixels(pixels)

    # Level meter feel
    LED_METER_FALL = 1.4        # how fast the bar drops back (fraction of full width per second)
    LED_METER_PEAK_HOLD = 0.35  # seconds the peak dots wait before falling
    LED_METER_PEAK_GRAVITY = 3.0  # how fast the peak dots accelerate back in

    def _led_meter_frame(self, t, e, k, base, accent):
        """Music lights as a level meter, mirrored from the middle of the
        strip: the bar jumps out on each beat (further on strong beats, with
        the bass setting how big it stays between beats), then falls back
        in. A peak dot at each end holds the furthest point for a moment,
        then drops. The bar is the base color in the middle, blending to
        the accent color at the tips. Brightness pulses with the beat on
        top of the movement (see led_music_meter_dim)."""
        n = self.led_count
        level, peak, flash = self._meter_step(t, e, k)

        # Brightness pulses with the music too: the bar glows at a medium
        # level between beats (a bit brighter with more bass) and flares on
        # each beat; the strip outside the bar flickers with the beat.
        bar_bright = min(1.0, self.led_music_meter_dim + 0.15 * e
                         + (1.0 - self.led_music_meter_dim) * flash)
        outside_bright = 0.03 + 0.22 * flash
        half = n / 2.0
        center = (n - 1) / 2.0
        bar = level * half
        peak = peak * half
        pixels = []
        for i in range(n):
            d = abs(i - center) + 0.5          # distance from the middle, in LEDs
            frac = min(1.0, d / half)
            # base color in the middle, blending to the accent at the tips
            mix = frac ** 1.5
            color = [b + (a - b) * mix for b, a in zip(base, accent)]
            inside = max(0.0, min(1.0, bar - d + 1.0))   # soft edge on the bar
            level = outside_bright + (bar_bright - outside_bright) * inside
            if abs(d - peak) < 1.0 and peak > 1.0:       # peak dot
                level = 1.0
                color = [min(255, c * 0.6 + 100) for c in accent]  # brighter, whiter
            pixels.append((int(color[0] * level), int(color[1] * level), int(color[2] * level)))
        ledStrip.set_pixels(pixels)

    def _meter_step(self, t, e, k):
        """Advances the level meter's bounce one frame. Returns (level,
        peak, flash): bar and peak-dot reach (0-1 of half the strip) and the
        current beat's brightness flare (0-1)."""
        now = time.time()
        m = self._meter
        if m is None:
            m = self._meter = {'level': 0.0, 'peak': 0.0, 'peak_vel': 0.0,
                               'peak_at': now, 'last': now}
        dt = min(0.1, max(0.0, now - m['last']))
        m['last'] = now

        # Where the music wants the bar: bass level plus a kick on each beat.
        # `flash` is the same beat, decaying a little slower, for brightness.
        target = 0.12 + 0.45 * e
        flash = 0.0
        if k >= 0:
            beat_time, strength = self._music_map['beats'][k]
            hit = 0.25 + 0.75 * strength / 100.0
            kick = hit * math.exp(-(t - beat_time) / 0.10)
            flash = hit * math.exp(-(t - beat_time) / 0.22)
            target += 0.55 * kick
        target = min(1.0, target)

        # Jump up instantly, fall back steadily - that's the bounce
        if target > m['level']:
            m['level'] = target
        else:
            m['level'] = max(target, m['level'] - self.LED_METER_FALL * dt)

        # Peak dots: pushed out by the bar, hold, then fall with gravity
        if m['level'] >= m['peak']:
            m['peak'], m['peak_vel'], m['peak_at'] = m['level'], 0.0, now
        elif now - m['peak_at'] > self.LED_METER_PEAK_HOLD:
            m['peak_vel'] += self.LED_METER_PEAK_GRAVITY * dt
            m['peak'] = max(m['level'], m['peak'] - m['peak_vel'] * dt)

        return m['level'], m['peak'], flash

    # Party show tuning
    PARTY_HUE_RATE = 0.6          # how quickly colors follow the harmony (per second)
    PARTY_SEGMENT = 6             # LEDs per color block in the chorus chase
    PARTY_WHITE = 210             # cap on white flashes (full white on every LED draws a lot of power)

    def _led_party_frame(self, t, e, k, palette=None):
        """The party show. Reads the whole light map, not just the beat:
          color      follows the song's harmony (see make_light_maps.py) -
                     the main color, plus a contrasting second color
          intensity  blends three moods as the song builds and relaxes:
                       calm   slow waves of color drifting across the strip
                       groove the bouncing meter
                       peak   blocks of both colors chasing along the strip,
                              one step per beat, changing direction each bar,
                              with a white flash on strong bar-start beats
          bars       a flash at both ends of the strip on every bar
          treble     white sparkles on hi-hats and cymbals
          drops      a white burst from the middle, then colored confetti
        With a `palette` (the Halloween Party style), the harmony picks from
        those colors instead of the full rainbow.
        """
        light_map = self._music_map
        n = self.led_count
        now = time.time()
        p = self._party
        if p is None:
            p = self._party = {'hue': None, 'last': now, 'sparks': []}
        dt = min(0.1, max(0.0, now - p['last']))
        p['last'] = now

        # --- read the map at time t
        fps, slow_fps = light_map['fps'], light_map['slow_fps']
        idx = int(t * fps)
        treble = light_map['treble'][idx] / 100.0 if 0 <= idx < len(light_map['treble']) else 0.0
        sidx = min(max(0, int(t * slow_fps)), len(light_map['intensity']) - 1)
        intensity = light_map['intensity'][sidx] / 100.0
        target_hue = light_map['hue'][sidx]

        # Ease toward the harmony's color along the shorter way round the wheel
        if p['hue'] is None:
            p['hue'] = target_hue
        diff = (target_hue - p['hue'] + 540) % 360 - 180
        p['hue'] = (p['hue'] + diff * min(1.0, self.PARTY_HUE_RATE * dt)) % 360
        hue = p['hue'] / 360.0

        if palette:
            def hsv(h, v, sat=1.0):
                # The color wheel is split evenly between the palette colors.
                # Each holds solid for most of its share; near the border the
                # old color dims out and the next dims in, rather than mixing
                # (orange + purple would make pink).
                pos = (h % 1.0) * len(palette)
                frac = pos - int(pos)
                i = int(pos) % len(palette)
                color = palette[i] if frac < 0.5 else palette[(i + 1) % len(palette)]
                dip = min(1.0, abs(frac - 0.5) / 0.1)        # 0 right at the border
                v = max(0.0, min(1.0, v)) * (0.15 + 0.85 * dip)
                return tuple(c * v for c in color)
            second_offset = 1.0 / len(palette)   # the next palette color
        else:
            def hsv(h, v, sat=1.0):
                r, g, b = colorsys.hsv_to_rgb(h % 1.0, sat, max(0.0, min(1.0, v)))
                return (r * 255, g * 255, b * 255)
            second_offset = 0.42                 # contrasting, not quite opposite

        main_h, second_h = hue, hue + second_offset

        # --- beat, bar and drop timing
        beat_period = 60.0 / max(40.0, light_map.get('bpm', 120))
        age, strength, downbeat, bar = 99.0, 0, False, 0
        if k >= 0:
            beat_time, strength = light_map['beats'][k]
            age = t - beat_time
            beat_in_bar = (k - light_map.get('bar_phase', 0)) % 4
            downbeat = beat_in_bar == 0
            bar = (k - light_map.get('bar_phase', 0)) // 4
        flash = (0.3 + 0.7 * strength / 100.0) * math.exp(-age / 0.2)
        drops = light_map.get('drops', [])
        di = bisect.bisect_right(drops, t) - 1
        drop_age = t - drops[di] if di >= 0 else 99.0

        # --- mood weights: calm -> groove -> peak, blended so nothing snaps
        def ramp(x, a, b):
            x = max(0.0, min(1.0, (x - a) / (b - a)))
            return x * x * (3 - 2 * x)
        w_peak = ramp(intensity, 0.62, 0.8)
        w_calm = 1.0 - ramp(intensity, 0.22, 0.4)
        w_groove = max(0.0, 1.0 - w_peak - w_calm)

        meter_level, meter_peak, _ = self._meter_step(t, e, k)   # keep the meter bouncing
        center = (n - 1) / 2.0
        half = n / 2.0

        # Chorus chase: moves one block per beat (snappy ease), reverses each bar
        step = 0.0
        if k >= 0:
            step = k + min(1.0, age / (beat_period * 0.35)) ** 0.5
        chase_pos = step * self.PARTY_SEGMENT
        chase_dir = 1 if bar % 2 == 0 else -1
        chase_white = 0.0
        if downbeat and strength >= 60:
            chase_white = 0.7 * math.exp(-age / 0.07)

        pixels = []
        for i in range(n):
            d = abs(i - center) + 0.5
            r = g = b = 0.0

            if w_calm > 0.01:    # slow drifting waves, swelling with the bass
                w1 = 0.5 + 0.5 * math.sin(i * 0.11 - t * 1.3)
                w2 = 0.5 + 0.5 * math.sin(i * 0.07 + t * 0.7)
                c = hsv(main_h + 0.08 * w2, 0.08 + 0.3 * w1 * (0.5 + e) + 0.25 * flash)
                r += c[0] * w_calm; g += c[1] * w_calm; b += c[2] * w_calm

            if w_groove > 0.01:  # the bouncing meter, main color in the middle
                inside = max(0.0, min(1.0, meter_level * half - d + 1.0))
                mix = min(1.0, d / half) ** 1.5
                v = 0.04 + (0.35 + 0.65 * flash) * inside
                if abs(d - meter_peak * half) < 1.0 and meter_peak > 0.05:
                    v = 1.0
                c = hsv(main_h + (second_h - main_h) * mix, v)
                r += c[0] * w_groove; g += c[1] * w_groove; b += c[2] * w_groove

            if w_peak > 0.01:    # color blocks chasing to the beat
                seg = int((i * chase_dir + chase_pos) // self.PARTY_SEGMENT)
                c = hsv(main_h if seg % 2 == 0 else second_h, 0.35 + 0.35 * e + 0.3 * flash)
                wv = chase_white * self.PARTY_WHITE
                r += (c[0] + wv) * w_peak; g += (c[1] + wv) * w_peak; b += (c[2] + wv) * w_peak

            pixels.append([r, g, b])

        # Bar starts: both ends flash the second color, fading toward the middle
        if downbeat and age < 0.35:
            amt = math.exp(-age / 0.12)
            c = hsv(second_h, 1.0)
            reach = n * 0.18
            for i in range(n):
                edge = min(i, n - 1 - i)
                if edge < reach:
                    # take over rather than add, so purple over orange stays
                    # purple instead of turning pink
                    a = amt * (1 - edge / reach) ** 2
                    px = pixels[i]
                    px[0] += (c[0] - px[0]) * a; px[1] += (c[1] - px[1]) * a; px[2] += (c[2] - px[2]) * a

        # Drops: a white burst racing out from the middle, then confetti
        if drop_age < 0.6:
            radius = drop_age / 0.35 * half
            fill = 0.5 * (1 - drop_age / 0.6)
            for i in range(n):
                d = abs(i - center)
                ring = max(0.0, 1 - abs(d - radius) / 5.0) * (1 - drop_age / 0.6)
                wv = min(1.0, ring + fill) * self.PARTY_WHITE
                px = pixels[i]
                px[0] += wv; px[1] += wv; px[2] += wv

        # Sparkles: hi-hats and cymbals (white), confetti after a drop (any color)
        sparks = p['sparks']
        rate = 50.0 * treble ** 2 * (0.4 + intensity)          # per second
        confetti = 0.0
        if 0.4 < drop_age < 4.0:
            confetti = 120.0 * (1 - (drop_age - 0.4) / 3.6)
        for want, kind in ((rate * dt, 'white'), (confetti * dt, 'confetti')):
            count = int(want) + (1 if random.random() < want - int(want) else 0)
            for _ in range(count):
                if kind == 'white':
                    color = (self.PARTY_WHITE,) * 3
                elif palette:
                    color = random.choice(palette)
                else:
                    color = hsv(random.random(), 1.0)
                sparks.append([random.randrange(n), now, color, 0.12 if kind == 'white' else 0.3])
        alive = []
        for pos, born, color, life in sparks:
            a = 1 - (now - born) / life
            if a > 0:
                px = pixels[pos]
                px[0] = max(px[0], color[0] * a); px[1] = max(px[1], color[1] * a); px[2] = max(px[2], color[2] * a)
                alive.append([pos, born, color, life])
        p['sparks'] = alive[-200:]

        ledStrip.set_pixels([(min(255, int(r)), min(255, int(g)), min(255, int(b))) for r, g, b in pixels])

    LED_MUSIC_STYLES = ['meter', 'party', 'halloween_party', 'ripples', 'pulse']
    LED_MUSIC_STYLE_NAMES = {'meter': 'Meter', 'party': 'Party', 'halloween_party': 'Halloween Party',
                             'ripples': 'Ripples', 'pulse': 'Pulse'}

    def music_style_name(self):
        return self.LED_MUSIC_STYLE_NAMES.get(self.led_music_style, self.led_music_style)

    def cycle_music_style(self):
        """K key: meter -> party -> halloween party -> ripples -> pulse. Returns a short
        description for the notification."""
        styles = self.LED_MUSIC_STYLES
        i = styles.index(self.led_music_style) if self.led_music_style in styles else -1
        self.led_music_style = styles[(i + 1) % len(styles)]
        self._meter = None   # start the meter fresh rather than mid-bounce
        self._party = None
        message = "Music light style: " + self.music_style_name()
        if not self.led_music_lights:
            message += " (music lights are OFF - press L)"
        return message

    def toggle_music_lights(self):
        """L key: switch between music lights and the normal idle loop."""
        self.led_music_lights = not self.led_music_lights
        return self.led_music_lights

    def nudge_music_offset(self, seconds):
        """[ and ] keys: shift the music lights earlier/later."""
        self.led_music_offset = round(max(-1.0, min(1.0, self.led_music_offset + seconds)), 3)
        return self.led_music_offset

    def _led_runner_frame(self, u, background=(0, 0, 0)):
        """Draws the runner at progress `u` (0-1) through its trip: down the
        strip for the first half, back for the second, over a steady
        `background` color. It eases in and out
        at each end, and its tail stretches with speed, so it shrinks to a
        dot as it turns around instead of jumping."""
        n = self.led_count
        if n <= 0:
            return
        leg_u = (u * 2) % 1.0 if u < 1.0 else 1.0
        going_out = u < 0.5
        eased = leg_u * leg_u * (3 - 2 * leg_u)     # smoothstep
        speed = 4 * leg_u * (1 - leg_u)            # 0 at the ends, 1 mid-leg
        head = eased * (n - 1) if going_out else (1 - eased) * (n - 1)
        direction = 1 if going_out else -1
        tail = 1 + 14 * speed                      # LEDs of fading trail
        # Fade the whole runner in at the start and out at the end of the trip
        envelope = min(1.0, u / 0.08, (1.0 - u) / 0.08)
        r0, g0, b0 = self.led_runner_color
        bg_level = envelope * max(0.0, min(1.0, self.led_runner_background_level))
        br, bgr, bb = (background[0] * bg_level, background[1] * bg_level,
                       background[2] * bg_level)
        bg_pixel = (int(br), int(bgr), int(bb))
        pixels = []
        for i in range(n):
            d = (head - i) * direction   # > 0 means behind the head
            if d < 0:
                b = max(0.0, 1 + d / 1.5)          # soft leading edge
            elif d <= 1:
                b = 1.0
            else:
                b = max(0.0, 1 - (d - 1) / tail)  # fading trail
            if b > 0:
                # Blend from the background toward purple
                b = (b ** 1.5) * envelope
                pixels.append((int(br + (r0 - br) * b), int(bgr + (g0 - bgr) * b),
                               int(bb + (b0 - bb) * b)))
            else:
                pixels.append(bg_pixel)
        ledStrip.set_pixels(pixels)

    def led_shutdown(self):
        """Stops every LED effect and turns the strip off. Used on exit."""
        self._led_idle_stop()
        self._led_spin_stop()
        self._led_flash_stop()
        try:
            ledStrip.off()
        except Exception:
            pass

    def _led_flash_stop(self):
        if self._led_flash_event:
            self._led_flash_event.cancel()
            self._led_flash_event = None

    def _led_spin_start(self):
        """Every other LED orange/green, swapping places each interval so
        the colors appear to flash back and forth while the reels spin."""
        self._led_idle_stop()
        self._led_flash_stop()   # a new spin cuts off the last win's flash
        if self._led_spin_event:
            return
        self._led_spin_offset = 0
        self._led_spin_tick(0)   # light up immediately, not one interval late
        self._led_spin_event = Clock.schedule_interval(self._led_spin_tick,
                                                       max(0.05, self.led_spin_interval))

    def _led_spin_stop(self):
        if self._led_spin_event:
            self._led_spin_event.cancel()
            self._led_spin_event = None

    def _led_spin_tick(self, dt):
        if not self.led_spin_colors:
            return
        ledStrip.set_pattern(self.led_spin_colors, self._led_spin_offset)
        self._led_spin_offset = (self._led_spin_offset + 1) % len(self.led_spin_colors)

    # Win light show timing
    LED_WIN_SEGMENT_SECONDS = 1.5   # time in each mode before switching
    LED_WIN_CHASE_BLOCK = 5         # LEDs per color block in the chase
    LED_WIN_CHASE_SPEED = 40        # LEDs per second the chase moves

    def _led_flash(self, colors, seconds, interval=0.15):
        """Win light show for `seconds`: alternates between strobing through
        `colors` (one color per flash, `interval` seconds on then off) and
        chasing blocks of those colors along the strip. Timed by the clock
        rather than by counting ticks, so a busy frame (Kivy can run ticks
        late) can't cut it short."""
        self._led_idle_stop()   # the pulse and the flash would fight over the strip
        self._led_spin_stop()
        self._led_flash_stop()
        if not colors or seconds <= 0:
            self._led_set_idle()
            return
        block = max(1, self.LED_WIN_CHASE_BLOCK)
        self._led_flash_state = {
            'start': time.time(), 'seconds': seconds, 'interval': interval,
            'colors': colors, 'last': None,
            # e.g. 5 green, 5 purple, 5 orange, 5 white, repeated down the strip
            'chase': [c for c in colors for _ in range(block)],
        }
        self._led_flash_tick(0)   # light up immediately
        # Check often so each change lands close to on time.
        self._led_flash_event = Clock.schedule_interval(self._led_flash_tick, 1 / 30.)

    def _led_flash_tick(self, dt):
        st = self._led_flash_state
        elapsed = time.time() - st['start']
        if elapsed >= st['seconds']:
            self._led_flash_stop()
            self._led_set_idle()
            return
        colors = st['colors']
        if int(elapsed / self.LED_WIN_SEGMENT_SECONDS) % 2 == 0:
            # Strobe: color 1 on, off, color 2 on, off, ...
            step = int(elapsed / st['interval'])
            frame = ('strobe', step)
            if frame != st['last']:   # only touch the strip when it changes
                st['last'] = frame
                if step % 2 == 0:
                    ledStrip.set_all(*colors[(step // 2) % len(colors)])
                else:
                    ledStrip.off()
        else:
            # Chase: color blocks marching along the strip
            offset = int(elapsed * self.LED_WIN_CHASE_SPEED) % len(st['chase'])
            frame = ('chase', offset)
            if frame != st['last']:
                st['last'] = frame
                ledStrip.set_pattern(st['chase'], offset)

    def _load_background_cycle(self):
        """Finds all images in assets/images/background/ for the B key to
        cycle through."""
        extensions = ('.png', '.jpg', '.jpeg')
        files = []
        for ext in extensions:
            files += glob.glob(asset("images", "background", "*" + ext))
        files.sort()
        self.bg_cycle_files = files

    def _find_cycle_index(self, path):
        norm = os.path.normpath(path)
        for i, f in enumerate(self.bg_cycle_files):
            if os.path.normpath(f) == norm:
                return i
        return -1

    def _resolve_start_background(self):
        """The starting background: config.background_file from
        assets/images/background/, or the first image there if that file
        isn't found."""
        path = asset("images", "background", self.background_file)
        if os.path.exists(path):
            self.bg_cycle_index = self._find_cycle_index(path)
            return path

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
        return path

    def cycle_background(self):
        """B key. Returns a short description for the notification."""
        if not self.bg_cycle_files:
            return "No backgrounds found in images/background/"
        self.bg_cycle_index = (self.bg_cycle_index + 1) % len(self.bg_cycle_files)
        self.bg_rect.source = self.bg_cycle_files[self.bg_cycle_index]
        name = os.path.splitext(os.path.basename(self.bg_rect.source))[0].replace('_', ' ')
        if len(name) > 40:
            name = name[:38].rstrip() + '...'
        return "Background {}/{} - {}".format(self.bg_cycle_index + 1,
                                               len(self.bg_cycle_files), name)

    def _load_background_music(self):
        """Scans assets/audio/background/ for music files and builds the
        playlist in the current playback mode. The playlist is always built
        regardless of music_enabled, so M can still start it manually even
        when start_with_music is False in config.py - music_enabled only
        controls whether it starts on its own after the idle timeout."""
        self.music_playlist = []
        self.music_index = 0
        self.music_sound = None
        self.last_activity_time = time.time()

        files = []
        for ext in ('.wav', '.ogg', '.mp3'):
            files += glob.glob(asset('audio', 'background', '*' + ext))
        self._all_songs = sorted(files, key=self._song_sort_key)
        self.music_playlist = self._playlist_round()

    @staticmethod
    def _song_sort_key(path):
        """Sorts by the number at the start of the file name (so 2 comes
        before 10), then by name."""
        name = os.path.basename(path)
        m = re.match(r'\s*(\d+)', name)
        return (int(m.group(1)) if m else float('inf'), name.lower())

    def _playlist_round(self, avoid_first=None):
        """One pass through every song in the current mode. In shuffle, the
        round won't start with `avoid_first` (the song that just played)."""
        songs = list(self._all_songs)
        if self.music_playback == 'shuffle':
            random.shuffle(songs)
            if avoid_first and len(songs) > 1 and songs[0] == avoid_first:
                songs.append(songs.pop(0))
        return songs

    def toggle_music_playback(self):
        """P key: in order <-> shuffle. The current song keeps playing; the
        new order takes over after it. Returns a notification message."""
        self.music_playback = 'shuffle' if self.music_playback == 'order' else 'order'
        if self.music_playlist:
            current = self.music_playlist[self.music_index]
            songs = self._playlist_round()
            if self.music_playback == 'shuffle':
                songs.remove(current)
                songs.insert(0, current)        # then every other song once
            self.music_playlist = songs
            self.music_index = songs.index(current)
        return "Music: " + self.music_playback_name()

    def music_playback_name(self):
        return 'shuffle' if self.music_playback == 'shuffle' else 'in order'

    def toggle_music_mute(self):
        """M key. Returns a short description of the result for the
        on-screen notification."""
        if not self.music_playlist:
            return "No background music found"
        if self.music_sound is None:
            # Nothing loaded yet - most likely start_with_music is False in
            # config.py, or the idle timeout just hasn't fired yet. Either
            # way, start a fresh track now rather than muting nothing.
            self.start_music_now()
            return "Music ON - " + self.current_track_name()
        self.music_muted = not self.music_muted
        # If music is currently audible (idle, not already spin-muted),
        # apply the change immediately rather than waiting for the next
        # idle/spin transition.
        if self.state == 'idle':
            self.music_sound.volume = 0 if self.music_muted else self.music_volume
        if self.music_muted:
            return "Music muted"
        return "Music ON - " + self.current_track_name()

    def current_track_name(self):
        """Readable name of the current track, without its number:
        "4 - Thriller - Michael Jackson.mp3" -> "Thriller - Michael Jackson",
        "4_Thriller.mp3" -> "Thriller"."""
        if not self.music_playlist:
            return ""
        name = os.path.splitext(os.path.basename(self.music_playlist[self.music_index]))[0]
        name = re.sub(r'^\s*\d+\s*[-_.]*\s*', '', name) or name
        return name.replace('_', ' ')

    def start_music_now(self):
        if not self.music_playlist:
            return
        self.music_enabled = True
        self.music_muted = False
        self._start_music_track()
        self.last_activity_time = time.time()

    def skip_music_track(self):
        """S key. Returns a short description for the notification."""
        if not self.music_playlist:
            return "No background music found"
        if self.music_sound is not None:
            self.music_sound.stop()
        self._advance_music_track()
        if self.music_muted:
            return "Next track (muted) - " + self.current_track_name()
        return "Now playing - " + self.current_track_name()

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
        self._music_map = self._load_light_map(path)
        snd.volume = 0 if self._music_should_be_silent() else self.music_volume
        snd.play()
        # Kivy can't report playback position here, so the lights keep their
        # own clock from the moment the track starts. The track keeps playing
        # (muted) through spins, so this stays in step with it.
        self._music_started_at = time.time()
        self._meter = None
        self._party = None

    def _load_light_map(self, track_path):
        """Loads `<track>.lights.json` from make_light_maps.py, or returns
        None if there isn't one (those tracks just use the idle loop)."""
        path = os.path.splitext(track_path)[0] + '.lights.json'
        if not os.path.exists(path):
            logging.info('no light map for {} - run tools/make_light_maps.py'.format(track_path))
            return None
        try:
            with open(path) as f:
                light_map = json.load(f)
            light_map['beat_times'] = [b[0] for b in light_map['beats']]
            return light_map
        except Exception as e:
            logging.warning('could not load light map {}: {}'.format(path, e))
            return None

    def _advance_music_track(self):
        self.music_index += 1
        if self.music_index >= len(self.music_playlist):
            # End of the round: start again (a fresh shuffle in shuffle mode)
            last = self.music_playlist[-1]
            self.music_playlist = self._playlist_round(avoid_first=last)
            self.music_index = 0
        self._start_music_track()

    def _jackpot_sound_running(self):
        snd = self._jackpot_sound
        if snd is None:
            return False
        if self._win_sound_event is not None or snd.state == 'play':
            return True        # still waiting to start, or playing
        self._jackpot_sound = None
        return False

    def _update_background_music(self):
        if not self.music_enabled or not self.music_playlist or self.state != 'idle':
            return
        if self._jackpot_sound_running():
            return   # let the jackpot sound finish before the music comes back
        if time.time() - self.last_activity_time < self.idle_music_timeout:
            return
        if self.music_sound is None:
            self._start_music_track()
        elif self.music_sound.volume == 0:
            if not self.music_muted:
                self.music_sound.volume = self.music_volume  # was muted during a spin - it never stopped, just unmute it
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
        self.payline.pos = (0, self.size[1]/2)
        self.payline.size = (self.size[0], 7.5)

    def start_spin(self):
        if self.state == 'idle':
            self.state = 'STATE_SPINNING'
            self.stopped = 0
            if self._win_sound_event:   # a new spin before the last win sound started
                self._win_sound_event.cancel()
                self._win_sound_event = None
            self._jackpot_sound = None
            snd = self.sounds.get('roll')
            self._roll_ends_at = time.time()
            if snd:
                snd.volume = self.spin_sounds_volume
                snd.play()
                self._roll_ends_at += max(0.0, getattr(snd, 'length', 0) or 0)
            self.start_time = time.time()
            self.last_time = time.time()
            self.landed = []
            self.cancel_win_banner()
            self.target_symbols = self.pick_outcome()
            self._pause_background_music()
            self._led_spin_start()
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

    def start_jackpot_celebration(self, seconds=0.0):
        """The jackpot animation, lasting `seconds` (its song's length).
        config.jackpot_animation picks:
          'combo'     (default) fireworks from the three reel pumpkins,
                      every other burst one of the other icons
          'fireworks' pumpkin fireworks only
          'rain'      every icon raining down for the whole song"""
        if self.game_screen is None:
            return
        style = getattr(config, 'jackpot_animation', 'combo')
        if style in ('combo', 'fireworks'):
            pumpkin_name = symbol_name(self.pumpkin_symbol)
            alt = None
            if style == 'combo':
                alt = [asset("images", "icons", name + ".png")
                       for name in SYMBOL_NAMES[:self.num_symbols] if name != pumpkin_name]
            self.game_screen.win_celebration.start_fireworks(
                asset("images", "icons", pumpkin_name + ".png"), self._payline_origins(),
                self.reel_icon_pixel_size(), duration=seconds, alt_paths=alt)
            return
        icon_dir = asset("images", "icons")
        icon_paths = []
        for name in SYMBOL_NAMES[:self.num_symbols]:
            path = os.path.join(icon_dir, name + ".png")
            if os.path.exists(path):
                icon_paths.append(path)
        self.game_screen.win_celebration.start(icon_paths, icon_size=self.reel_icon_pixel_size(),
                                                duration=seconds)

    def _payline_origins(self):
        """Screen positions of the three icons on the payline."""
        payline_y = self.size[1] / 2
        return [(strip.pos[0] + strip.size[0] / 2, payline_y) for strip in self.strips]

    def start_triple_celebration(self, matched_symbol):
        """Three of a kind. config.win_animation picks 'rain' (the icon
        raining down, the default) or 'fireworks' (the icon bursting out
        of the three reels). Either way it lasts the usual celebration
        length, not the jackpot's."""
        if self.game_screen is None:
            return
        icon_path = os.path.join(asset("images", "icons"),
                                  symbol_name(matched_symbol) + ".png")
        if not os.path.exists(icon_path):
            return
        if getattr(config, 'win_animation', 'rain') == 'fireworks':
            self.game_screen.win_celebration.start_fireworks(
                icon_path, self._payline_origins(), self.reel_icon_pixel_size())
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

    def show_win(self, match_type, payout, pumpkin_count=0, min_seconds=0.0):
        """Shows the win banner. Returns how many seconds it stays on
        screen (fade in + hold + fade out), so the LEDs can match it.
        `min_seconds` stretches it (the jackpot banner stays up for its
        whole song)."""
        if self.game_screen is None:
            return 0.0
        style = TIER_STYLE[match_type]
        hold = getattr(config, 'win_banner_hold_seconds', style['hold'])
        hold = max(hold, (min_seconds or 0) - 0.6)
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
        if pumpkin_count >= 1:
            candidate = os.path.join(asset("images", "icons"),
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
        label.font_size = banner.height * style['size_frac']   # final size, rendered once
        banner.opacity = 0

        banner_anim = (Animation(opacity=1, duration=0.2)
                       + Animation(duration=hold)
                       + Animation(opacity=0, duration=0.4))
        banner_anim.start(banner)

        self._pop_in(label)
        return 0.2 + hold + 0.4

    POP_SECONDS = 0.25
    POP_START = 0.3   # starting size, as a fraction of the final size

    def _pop_in(self, label):
        """The banner text's springy pop-in. Zooms the already-rendered
        text up to full size (a cheap drawing transform) instead of
        animating its font size, which re-renders the big text every frame
        and made the start of each win stutter on the Pi."""
        if not hasattr(label, '_pop_scale'):
            with label.canvas.before:
                PushMatrix()
                label._pop_scale = Scale(1, 1, 1)
            with label.canvas.after:
                PopMatrix()
            label._pop_event = None
        if label._pop_event:
            label._pop_event.cancel()
        started = time.time()
        ease = AnimationTransition.out_back

        def step(dt):
            p = min(1.0, (time.time() - started) / self.POP_SECONDS)
            k = self.POP_START + (1 - self.POP_START) * ease(p)
            label._pop_scale.origin = label.center
            label._pop_scale.x = label._pop_scale.y = k
            if p >= 1.0:
                label._pop_event = None
                return False
        step(0)
        label._pop_event = Clock.schedule_interval(step, 0)

    def _celebration_seconds(self):
        """How long the falling-icons celebration will run, or 0 if none
        is running (no win, or its icon images weren't found)."""
        if self.game_screen is None:
            return 0.0
        celebration = self.game_screen.win_celebration
        return celebration.run_seconds if celebration._stop_ev else 0.0

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
                    snd.volume = self.spin_sounds_volume
                    snd.play()
                self.landed.append(slotnum)
                self.stopped += 1
                if self.stopped >= len(self.strips):
                    self.state = "FINAL"
        elif self.state == 'FINAL':
            match_type, payout, pumpkin_count = self.calculate_payout(self.landed)
            self.last_match_type = match_type
            self.last_payout = payout
            self.game_logger.log_spin(self.landed, match_type,
                                       pumpkin_count, payout)

            self.play_result_sound(match_type, pumpkin_count)

            if match_type == 'jackpot':
                self.start_jackpot_celebration(self._jackpot_show_seconds)
            elif match_type == '3 of a kind':
                counts = Counter(self.landed)
                matched_symbol = max(counts, key=counts.get)
                self.start_triple_celebration(matched_symbol)
            # The banner stays up as long as the animation (if there is one)
            banner_secs = self.show_win(match_type, payout, pumpkin_count,
                                        min_seconds=max(self._jackpot_show_seconds,
                                                        self._celebration_seconds()))

            # Reels have stopped - end the spin lights. A win light show
            # takes over the strip for as long as the win is on screen;
            # with no win, go straight back to idle.
            self._led_spin_stop()
            show_secs = max(banner_secs, self._celebration_seconds())
            if match_type == 'jackpot':
                self._led_flash(self.led_win_colors, show_secs, interval=0.1)
            elif match_type == '3 of a kind':
                self._led_flash(self.led_win_colors, show_secs, interval=0.12)
            elif match_type == 'double' or pumpkin_count >= 1:
                self._led_flash(self.led_win_colors, show_secs, interval=0.15)
            else:
                self._led_set_idle()
            self.state = 'idle'

    def play_result_sound(self, match_type, pumpkin_count):
        """Prefers an icon-specific sound for doubles/triples and a
        dedicated jackpot sound, falling back to the generic 'win' sound
        for anything not recorded yet, so missing audio never breaks a spin.

        Expected filenames in assets/audio/ or assets/audio/reels/ (any extension):
          jackpot            - plays on 3 pumpkins
          win-<icon name>    - e.g. win-vampire, win-pumpkin, win-skeleton;
                                used for BOTH a double and a triple of that icon
        Icon names come from SYMBOL_NAMES, lowercased.
        """
        snd = None
        self._jackpot_show_seconds = 0.0
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
            def play(dt):
                self._win_sound_event = None
                snd.volume = self.win_volume
                snd.play()
            if match_type == 'jackpot':
                # Straight in as soon as the spin sound is done, and hold
                # the background music until it has finished
                delay = self._roll_ends_at - time.time()
                self._jackpot_sound = snd
                length = getattr(snd, 'length', 0) or 0
                if length > 0:
                    # the jackpot animation and lights run until the music ends
                    self._jackpot_show_seconds = max(0.0, delay) + length
            else:
                # A short pause first, so it doesn't run into the end of the spin sound
                delay = self.win_sound_delay
            self._win_sound_event = Clock.schedule_once(play, max(0.0, delay))

class GameScreen(Screen):

    def start_game(self, hardware_button):
        self.hardware_button = hardware_button
        self.slots.setup()
        self.slots.game_screen = self
        self.slots.on_size()
        self.timer = Clock.schedule_interval(self.update_timer, 0)

    # Shown by the H key. Keep in step with on_keyboard_down below.
    SHORTCUTS = [
        ('Space', 'Spin (same as the big button)'),
        ('M',     'Music on / mute'),
        ('S',     'Skip to the next song'),
        ('P',     'Music: in order / shuffle'),
        ('B',     'Next background picture'),
        ('L',     'Lights: follow the music / normal loop'),
        ('K',     'Music light style: meter / party / halloween party / ...'),
        ('[  ]',  'Music lights earlier / later'),
        ('H',     'Show / hide this help'),
        ('Esc',   'Quit the game'),
    ]

    def on_keyboard_down(self, keyboard, keycode, text, modifiers):
        key = keycode[1]
        if key == "spacebar":
            self.hide_help()
            self.slots.start_spin()
        elif key == "h":
            self.toggle_help()
        elif key == "m":
            self.show_status(self.slots.toggle_music_mute())
        elif key == "s":
            self.show_status(self.slots.skip_music_track())
        elif key == "p":
            self.show_status(self.slots.toggle_music_playback())
        elif key == "b":
            self.show_status(self.slots.cycle_background())
        elif key == "l":
            on = self.slots.toggle_music_lights()
            self.show_status("Music lights: {}".format("ON" if on else "OFF (normal loop)"))
        elif key == "k":
            self.show_status(self.slots.cycle_music_style())
        elif text in ('[', ']'):
            offset = self.slots.nudge_music_offset(-0.02 if text == '[' else 0.02)
            self.show_status("Light timing: {:+.2f}s".format(offset))
        else:
            return
        if self.help_label.opacity:
            self.refresh_help()   # keep the "current settings" lines up to date

    def _help_text(self):
        slots = self.slots
        lines = ["[b][size=44sp]Keyboard shortcuts[/size][/b]", ""]
        for key, action in self.SHORTCUTS:
            lines.append("[b][color=ffa040]{:<6}[/color][/b]  {}".format(key, action))
        if slots.music_sound is None:
            music = "off"
        elif slots.music_muted:
            music = "muted"
        else:
            music = "on - " + slots.current_track_name()
        lines += [
            "",
            "[b]Right now[/b]",
            "Music:          " + music,
            "Playback:       " + slots.music_playback_name(),
            "Music lights:   " + ("ON" if slots.led_music_lights else "OFF (normal loop)"),
            "Light style:    " + slots.music_style_name(),
            "Light timing:   {:+.2f}s   (copy into config.py to keep)".format(slots.led_music_offset),
            "",
            "[color=aaaaaa]Press H to close[/color]",
        ]
        return "\n".join(lines)

    def refresh_help(self):
        self.help_label.text = self._help_text()

    def toggle_help(self):
        if self.help_label.opacity:
            self.hide_help()
        else:
            self.refresh_help()
            Animation.cancel_all(self.status_label)
            self.status_label.opacity = 0
            self.help_label.opacity = 1

    def hide_help(self):
        self.help_label.opacity = 0

    def show_status(self, message):
        """Shows a short message in the top-left corner for a few seconds."""
        if not message:
            return
        if self.help_label.opacity:
            logging.info(message)   # help is open and already shows current settings
            return
        label = self.status_label
        Animation.cancel_all(label)
        label.text = message
        label.opacity = 1
        (Animation(duration=2.5) + Animation(opacity=0, duration=0.5)).start(label)
        logging.info(message)

    def update_timer(self, dt):
        if self.hardware_button.checkButton():
            self.hide_help()
            self.slots.start_spin()
        self.slots.update()

class Slot(App):
    # Darkness of the win banner's band (0 = clear, 1 = solid)
    banner_opacity = NumericProperty(getattr(config, 'win_banner_opacity', 0.65))

    def build(self):
        self.root = viewport.Viewport(size=(1920, 1080), do_scale=True)
        self.game_screen = GameScreen()
        self.root.add_widget(self.game_screen)

        self._keyboard = Window.request_keyboard(self._keyboard_closed, self.game_screen, "text")
        self._keyboard.bind(on_key_down=self.on_keyboard_down)
        return self.root

    def on_start(self):
        self.game_screen.start_game(Hardware.hardwareButton())

    def _keyboard_closed(self):
        self._keyboard.unbind(on_key_down=self.on_keyboard_down)
        self._keyboard = None

    def on_keyboard_down(self, keyboard, keycode, text, modifiers):
        if keycode[1] == 'escape':
            self.clean_exit()
            return
        self.game_screen.on_keyboard_down(keyboard, keycode, text, modifiers)

    def clean_exit(self):
        logging.warning('clean exit requested (escape)')
        try:
            Clock.unschedule(self.game_screen.timer)
        except Exception:
            pass
        try:
            self.game_screen.slots.led_shutdown()
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


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Halloween Slots")
    parser.add_argument("--log-level", default="WARNING",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                        help="how much to print to the console")
    parser.add_argument("-d", "--debug", dest="log_level", action="store_const",
                        const="DEBUG", help="same as --log-level DEBUG")
    return parser.parse_args(argv[1:])


def main(argv):
    args = parse_args(argv)
    logging.basicConfig(format="[%(asctime)s] %(levelname)-8s %(message)s",
                        datefmt="%m/%d %H:%M:%S", level=args.log_level)
    Window.clearcolor = get_color_from_hex("000000")
    Hardware.setup()
    Slot().run()


if __name__ == '__main__':
    main(sys.argv)
