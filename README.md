# Halloween Slots

A trick-or-treat slot machine for a Raspberry Pi. Kids press a big button and
three reels of Halloween icons spin. The result tells you how many treats to
hand out. An LED strip glows between spins, flashes during spins and wins,
and can pulse to the background music.

Built on [Kivy](https://kivy.org) (Python), adapted from the original
kivySlots project.

---

## Quick start (once a year)

1. Plug in the Pi, screen, speakers, button and LED strip, then boot.
2. Update the code: `cd ~/Halloween_Slots && git pull`
3. **Check the odds** in `config.py`. `win_odds` may still be on a test
   setting. Normal odds are listed right above it.
4. Start the game: `~/Halloween_Slots/launch.sh`
5. Press **H** in the game for the keyboard shortcuts.

---

## What's in the folder

```
Halloween_Slots/
├── main.py            the game
├── config.py          all the settings you might want to change
├── launch.sh          starts the game on the Pi (use this for autostart)
├── piHardware.py      button + LED strip on the Pi
├── nullHardware.py    stand-in used on a Mac/PC (no button or LEDs)
├── viewport.py        scales the 1920x1080 layout to any screen
├── assets/
│   ├── images/
│   │   ├── stripbig1.png      the reel strip (12 icons, top to bottom)
│   │   ├── icons/             icons used for falling-icon celebrations
│   │   └── background/        background pictures (B key cycles)
│   └── audio/
│       ├── roll.mp3, win.mp3  spin and generic win sounds
│       ├── reels/             reel-stop sounds and per-icon win sounds
│       └── background/        music playlist + .lights.json beat maps
├── scripts/
│   ├── setup_pi.sh    one-time install on a fresh Pi
│   ├── stop_game.sh   force-quit the game (e.g. over SSH)
│   ├── setup_mac.sh   one-time install for testing on a Mac
│   └── run_mac.sh     run on a Mac
├── tools/
│   ├── make_light_maps.py   builds beat maps so the LEDs follow the music
│   └── led_test.py          checks the LED strip on its own
└── logs/              one CSV per night of every spin (created automatically)
```

---

## Hardware

| Part | Connection |
|---|---|
| Spin button | Between **GPIO17** (physical pin 11) and any **GND** pin. Set with `gpio_button`. |
| LED strip (WS2812B) | Data to **GPIO21** (physical pin 40); 5V and GND from a separate 5V supply, with its GND also tied to the Pi's GND. |
| Screen | HDMI, 1920x1080 works best. |
| Speakers | 3.5 mm jack or HDMI audio. |

LED tips:
- Keep the strip on GPIO21 / channel 0. GPIO18/19 clash with the Pi's
  audio, and GPIO10 (SPI) garbled the colors on this Pi.
- The LED library needs root, which is why `launch.sh` starts the game with
  `sudo`. To skip the password prompt, add a sudo rule for just the game:
  `sudo visudo -f /etc/sudoers.d/halloween-slots`, then add the line
  `admin ALL=(root) NOPASSWD: /usr/bin/python3 /home/admin/Halloween_Slots/main.py`.
  That lets anything running as `admin` start the game as root, so only do
  it on a Pi nobody else uses. To undo it:
  `sudo rm /etc/sudoers.d/halloween-slots`.
- If the strip flickers at full brightness, lower `led_brightness`. If that
  doesn't help, the power supply is usually the cause: add a bigger 5V
  supply, inject power at both ends of the strip, or add a 300-500 Ω
  resistor in the data line.

---

## First-time setup on a Pi

```bash
cd ~
git clone https://github.com/sgallen85/Halloween_Slots.git
cd Halloween_Slots
./scripts/setup_pi.sh
```

This installs Kivy, the GPIO and LED libraries (system-wide, so they work
under sudo), plus ffmpeg and numpy for the music-lights tool.

To test the LED strip on its own: `sudo python3 tools/led_test.py`

### Starting the game

```bash
~/Halloween_Slots/launch.sh
```

To start it automatically at boot, point your desktop's autostart at
`/home/<you>/Halloween_Slots/launch.sh`.

To quit, press **Esc**. If the screen is frozen, SSH in and run
`~/Halloween_Slots/scripts/stop_game.sh`.

---

## Keyboard shortcuts

Press **H** in the game to see these on screen, along with the current music
and light settings.

| Key | Does |
|---|---|
| Space | Spin (same as the button) |
| M | Music play / pause |
| S | Skip to the next song |
| Left / Right arrows | Song back / forward 15 seconds |
| P | Music: in order / shuffle |
| B | Next background picture |
| L | LEDs: follow the music / normal loop |
| K | Music light style: meter / halloween meter / party / halloween party / ripples / pulse |
| [ and ] | Shift the music lights earlier / later by 0.02 s |
| H | Show / hide help |
| Esc | Quit |

Most keys show a short message in the top-left corner. Changes made with
keys last until the game restarts. To keep one, copy the value into
`config.py`, for example `led_music_offset`.

---

## How the game plays

- Each spin's result is picked up front using `win_odds`. The reels then
  land on it.
- Payouts (in treats): any spin 2, double 4, three of a kind 12,
  jackpot (3 pumpkins) 20.
  One pumpkin doubles a payout and two pumpkins triple it.
- Wins show a banner. A triple sets off fireworks of that icon bursting
  out of the three reels (`win_animation = 'rain'` rains it down
  instead). A jackpot fires bursts out of the three reel pumpkins for the
  length of its song, alternating pumpkins with the other icons
  (`jackpot_animation`: `'combo'`, `'fireworks'` for pumpkins only, or
  `'rain'`).
- Every spin is saved to `logs/spins_YYYY-MM-DD.csv`, so you can count
  treats afterwards.

## Music and lights

- Songs go in `assets/audio/background/` (mp3, ogg or wav). They play
  (in order, or shuffled with **P**) after `idle_music_timeout` seconds
  without a spin, or as soon as you press **M** (which also pauses and
  plays). Spinning pauses it, and it picks up where it left off once
  nobody has spun for `idle_music_timeout` seconds.
- **LEDs when idle:** orange pulse, green pulse, purple runner over green,
  then the same with orange, on repeat.
- **LEDs with music:** if a song has a beat map, the strip turns into a
  level meter that bounces out from the middle with the beat, with peak
  dots at each end. Strong beats push it further, and the brightness
  flares on each beat and dims in between. The color fades to the
  next one every 16 beats. Press **L** to switch back to the normal loop,
  and **K** to try the other styles. Set the starting style with
  `led_music_style` in `config.py`.
- **Halloween Meter** (K) is the meter using only orange, purple and
  green (`led_halloween_colors`). The bar is one solid color with peak
  dots in the next color, and color changes dim out and back in, so no
  in-between shades show up.
- **Party style** (K again) is a full light show built from each song's map:
  colors follow the harmony (chord changes shift the color), quiet parts
  drift in slow waves, grooves bounce the meter, choruses chase color
  blocks one step per beat (switching direction each bar), cymbals
  sparkle, every bar flashes the ends, and drops set off a white burst and
  confetti.
- **Halloween Party** (K again) is the same show using only orange,
  purple and green (`led_halloween_colors`).
- **After adding songs**, build their beat maps (on the Pi or a Mac with
  ffmpeg and numpy):
  ```bash
  python3 tools/make_light_maps.py
  ```
  Songs without a map just use the normal light loop.
- If the beat flashes land early or late, use **[** and **]** while a song
  plays, then copy the number into `led_music_offset`.

## Customizing

Everything adjustable is in `config.py`, with a comment on each line. The
most common changes:

| Setting | What it changes |
|---|---|
| `win_odds` | How often each result comes up |
| `background_file` | The starting background picture |
| `win_banner_hold_seconds` | How long the win banner stays up |
| `win_sound_delay` | Pause after the reels stop before the win sound (default 2 s) |
| `win_volume`, `spin_sounds_volume`, `music_volume` | Sound mix: wins at 1.0; spin sounds and music at 0.8 so wins stand out. The jackpot sound starts as soon as the spin sound ends. |
| `start_with_music`, `idle_music_timeout` | When music starts |
| `led_brightness`, `led_count` | LED strip brightness and length |
| `led_pulse_seconds`, `led_runner_seconds` | Speed of the idle light loop |

To add **backgrounds**, drop 1920x1080 images into
`assets/images/background/`.

To change **sounds**, replace files in `assets/audio/`, keeping the names
(any of .mp3, .ogg or .wav):
- `roll`: plays during a spin
- `reel-stop`: plays as each reel stops (a `reels/reel-icon-<N>` file, if
  present, plays instead for that icon)
- `cash`: after a spin with no match and no pumpkins
- `win`: after a pumpkin bonus, and first for a double or triple
- `reels/win-<icon>`: plays right after `win` for a double or triple of
  that icon, for example `win-vampire`
- `reels/jackpot`: for 3 pumpkins; falls back to `win`

---

## Testing on a Mac

```bash
./scripts/setup_mac.sh   # once
./scripts/run_mac.sh
```

On a Mac there's no button or LED strip. Use Space to spin. To run in a
window, set `window_size = (1920, 1080)` in `config.py`.

## Troubleshooting

| Problem | Try |
|---|---|
| Button does nothing | Check that `gpio_button` uses the **GPIO** number, not the physical pin number. The button goes between that pin and GND. Watch the log for `Button Pressed`. |
| LEDs stay dark | Run with `sudo` (`launch.sh` does). Check `led_pin = 21` and `led_count`, then try `sudo python3 tools/led_test.py`. |
| LEDs flicker | Lower `led_brightness` and check the power supply (see LED tips above). |
| `ALSA ... underrun occurred` in the log | Harmless if the sound has no clicks or skips. |
| Music lights out of sync | Use **[** and **]** while a song plays, then save the value in `led_music_offset`. |
| A song's lights don't follow the music | Run `python3 tools/make_light_maps.py` to build its map. |
