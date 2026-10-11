# Halloween Slots settings. Edit, save, and restart the game to apply.
# Anything commented out (#) uses the default shown.

# ----------------------------------------------------------------------------
# Screen
# ----------------------------------------------------------------------------
window_size = True              # True = fullscreen; (1920, 1080) = a window, handy on a laptop
background_file = 'halloween2.jpg'   # starting picture from assets/images/background/ (B key cycles)
#background_bars = True         # dark bars behind the reels (default: on, except for background.png)

# ----------------------------------------------------------------------------
# Spin button
# ----------------------------------------------------------------------------
gpio_button = 17                # GPIO number (not physical pin); wire the button between it and GND

# ----------------------------------------------------------------------------
# Game
# ----------------------------------------------------------------------------
pumpkin_symbol = 5              # which reel icon is the pumpkin (bonus + jackpot)
win_banner_hold_seconds = 5.0   # how long the win banner stays up

# Chance of each spin result (should add up to 1.0).
# Normal odds:  {'none': 0.43, 'double': 0.30, 'triple': 0.25, 'jackpot': 0.02}
win_odds = {
    'none':    0.0,
    'double':  0.0,
    'triple':  0.8,
    'jackpot': 0.2,
}

# ----------------------------------------------------------------------------
# Music
# ----------------------------------------------------------------------------
idle_music_timeout = 20.0       # seconds with no spins before music starts on its own
start_with_music = False        # False = music only starts when you press M

# ----------------------------------------------------------------------------
# LED strip
# ----------------------------------------------------------------------------
led_pin = 21                    # keep on GPIO21 (channel 0) - 18/19 clash with the audio
led_channel = 0
led_count = 100
led_brightness = 100            # overall brightness 0-255; lower if the strip flickers

# Idle loop: orange pulse, green pulse, purple runner over green, repeat with orange
#led_idle_colors = [(255, 50, 0), (0, 200, 15)]
led_pulse_seconds = 4.0         # one color's fade up and back down
led_pulse_gap = 0.0001          # dark pause between effects
#led_runner_color = (140, 0, 255)
led_runner_seconds = 8.0        # runner's trip down the strip and back (0 = no runner)
led_runner_background_level = 0.3   # brightness of the color under the runner, 0-1

# While the reels spin: alternating colors swapping places
#led_spin_colors = [(255, 50, 0), (0, 200, 15)]
led_spin_interval = 0.2

# Win light show (lasts as long as the win animation)
#led_win_colors = [(0, 200, 15), (140, 0, 255), (255, 50, 0), (170, 170, 170)]

# Music lights: while music plays, the strip flashes to the beat.
# Run tools/make_light_maps.py after adding songs to assets/audio/background/.
led_music_lights = True         # False = start with the normal idle loop (L key toggles)
led_music_offset = 0.12         # seconds; raise if lights run early, lower if late ([ and ] adjust live)
led_music_beats_per_color = 16  # beats before the base color fades to the next one
led_music_style = 'meter'       # 'meter', 'party', 'halloween_party', 'ripples' or 'pulse'; K cycles
led_music_meter_dim = 0.20      # 'meter': brightness between beats (0-1); flares to full on each beat. 1 = no pulsing
led_music_accent_threshold = 65 # 'ripples' only: strong beats (0-100) ripple in the next color
#led_music_colors = [(255, 50, 0), (0, 200, 15), (140, 0, 255)]
#led_halloween_colors = [(255, 70, 0), (130, 0, 255), (60, 255, 0)]   # 'halloween_party' colors: orange, purple, green
