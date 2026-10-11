#!/usr/bin/env python3
"""
Builds a "light map" for each background music track, so the LED strip can
flash along with the music while the game is idle.

The game can't analyze audio while it plays (Kivy's audio player doesn't
expose the sound data, or even a reliable playback position), so the work is
done ahead of time here. Each track is decoded and measured:
  - bass and treble energy, 50 times a second
  - beats (with how hard each one hits) and which beat starts each bar
  - harmony, as a color that drifts with the chords (circle of fifths, so
    related chords get neighbouring colors)
  - intensity over time (quiet verse vs. big chorus) and "drops", where
    the song suddenly kicks in
The result is saved next to the track:

    assets/audio/background/3_time_warp.mp3
    assets/audio/background/3_time_warp.lights.json   <- this

The game picks the map up automatically. Tracks without one fall back to the
normal idle light loop.

Usage (needs numpy and ffmpeg):
    python3 tools/make_light_maps.py            # maps any track that's new or changed
    python3 tools/make_light_maps.py --force    # rebuild every map

On the Pi:  sudo apt-get install -y ffmpeg python3-numpy
On a Mac:   brew install ffmpeg && pip3 install numpy
"""
import argparse
import glob
import json
import os
import subprocess
import sys

try:
    import numpy as np
except ImportError:
    sys.exit("numpy isn't installed - see the top of this file for how to install it.")

SAMPLE_RATE = 11025   # plenty for bass and beats, and fast to process
FPS = 50              # map frames per second
WINDOW = 1024         # FFT window (~93 ms)
EXTENSIONS = ('.mp3', '.ogg', '.wav')


MAP_VERSION = 3   # bump when maps gain new data, so old ones get rebuilt


def map_version(path):
    try:
        with open(path) as f:
            return json.load(f).get('version', 1)
    except Exception:
        return 0


def map_path(track_path):
    return os.path.splitext(track_path)[0] + '.lights.json'


def decode(path):
    """Decodes any audio file to mono float samples via ffmpeg."""
    try:
        raw = subprocess.run(
            ['ffmpeg', '-v', 'error', '-i', path, '-ac', '1', '-ar', str(SAMPLE_RATE),
             '-f', 's16le', '-'],
            check=True, stdout=subprocess.PIPE).stdout
    except FileNotFoundError:
        sys.exit("ffmpeg isn't installed - see the top of this file for how to install it.")
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def spectrogram(samples):
    """Magnitude spectrum of each FPS frame, shape (frames, bins)."""
    hop = SAMPLE_RATE / FPS
    n_frames = int(len(samples) / hop)
    padded = np.concatenate([np.zeros(WINDOW // 2, np.float32), samples,
                             np.zeros(WINDOW, np.float32)])
    starts = (np.arange(n_frames) * hop).astype(int)
    frames = padded[starts[:, None] + np.arange(WINDOW)[None, :]]
    return np.abs(np.fft.rfft(frames * np.hanning(WINDOW), axis=1))


def band(spec, lo_hz, hi_hz):
    freqs = np.fft.rfftfreq(WINDOW, 1.0 / SAMPLE_RATE)
    return spec[:, (freqs >= lo_hz) & (freqs < hi_hz)]


def bass_energy(spec):
    """0-1 bass loudness per frame - jumps up instantly on a hit, eases down
    afterwards, so the lights punch rather than flicker."""
    db = 10 * np.log10(np.sum(band(spec, 30, 160) ** 2, axis=1) + 1e-9)
    lo, hi = np.percentile(db, 10), np.percentile(db, 98)
    level = np.clip((db - lo) / max(hi - lo, 1e-6), 0, 1)
    smoothed = np.empty_like(level)
    current = 0.0
    for i, v in enumerate(level):
        current = v if v > current else current * 0.88 + v * 0.12
        smoothed[i] = current
    return smoothed


def onset_strength(spec):
    """How much new low/mid energy arrives each frame - spikes on drum hits."""
    low = np.log1p(100 * band(spec, 30, 2000))
    flux = np.maximum(0, np.diff(low, axis=0, prepend=low[:1])).sum(axis=1)
    # Remove slow loudness changes so only sudden hits stand out
    kernel = np.ones(FPS) / FPS
    flux = np.maximum(0, flux - np.convolve(flux, kernel, mode='same'))
    return flux / (flux.std() + 1e-9)


def estimate_period(onsets):
    """Beat length in frames, from the onset curve's autocorrelation, leaning
    toward typical song tempos (~120 BPM)."""
    min_lag, max_lag = int(FPS * 60 / 190), int(FPS * 60 / 60)
    o = onsets - onsets.mean()
    ac = np.correlate(o, o, mode='full')[len(o) - 1:]
    lags = np.arange(min_lag, max_lag + 1)
    bpm = 60.0 * FPS / lags
    weight = np.exp(-0.5 * (np.log2(bpm / 120.0) / 0.9) ** 2)
    return int(lags[np.argmax(ac[lags] * weight)])


def track_beats(onsets, period):
    """Places beats on strong onsets while keeping a steady tempo (dynamic
    programming beat tracker, after Ellis 2007)."""
    n = len(onsets)
    score = onsets.astype(np.float64).copy()
    back = np.full(n, -1)
    tightness = 100.0
    for t in range(n):
        lo, hi = t - 2 * period, t - period // 2
        if hi <= 0:
            continue
        prev = np.arange(max(0, lo), hi)
        penalty = -tightness * np.log((t - prev) / period) ** 2
        candidates = score[prev] + penalty
        best = np.argmax(candidates)
        score[t] += candidates[best]
        back[t] = prev[best]
    # Start from the best-scoring frame in the last beat period and walk back
    t = n - period + int(np.argmax(score[n - period:])) if n > period else int(np.argmax(score))
    beats = []
    while t >= 0:
        beats.append(t)
        t = back[t]
    return beats[::-1]


def smooth(x, seconds):
    """Moving average over `seconds`."""
    n = max(1, int(seconds * FPS))
    return np.convolve(x, np.ones(n) / n, mode='same')


def normalize(x, lo_pct=10, hi_pct=98):
    lo, hi = np.percentile(x, lo_pct), np.percentile(x, hi_pct)
    return np.clip((x - lo) / max(hi - lo, 1e-9), 0, 1)


def treble_energy(spec):
    """0-1 hi-hat / cymbal level per frame, quick to rise and fall."""
    db = 10 * np.log10(np.sum(band(spec, 2500, 5500) ** 2, axis=1) + 1e-9)
    return normalize(db)


def harmony_hue(spec):
    """A color (hue, 0-360) per frame that follows the harmony. Each FFT bin
    between 110 Hz and 2 kHz votes for its musical note; notes are placed
    around the circle of fifths, so the average direction drifts smoothly as
    chords change, and closely related chords land on nearby colors."""
    freqs = np.fft.rfftfreq(WINDOW, 1.0 / SAMPLE_RATE)
    sel = (freqs >= 110) & (freqs < 2000)
    pitch_class = (np.round(12 * np.log2(freqs[sel] / 440.0)).astype(int) + 9) % 12
    angle = 2 * np.pi * ((pitch_class * 7) % 12) / 12.0     # circle of fifths
    weights = spec[:, sel] ** 2
    z = (weights * np.exp(1j * angle)[None, :]).sum(axis=1)
    z = smooth(z.real, 8.0) + 1j * smooth(z.imag, 8.0)     # follow the progression, not each chord
    return (np.degrees(np.angle(z)) + 360) % 360


def loudness(samples, n_frames):
    """0-1 smoothed loudness per frame."""
    hop = SAMPLE_RATE / FPS
    starts = (np.arange(n_frames) * hop).astype(int)
    win = int(hop)
    rms = np.array([np.sqrt(np.mean(samples[s:s + win] ** 2) + 1e-12) for s in starts])
    return normalize(smooth(20 * np.log10(rms + 1e-9), 3.0), 5, 95)


def intensity_curve(loud, treble, onsets):
    """0-1 how big the song feels at each moment. Loudness alone can't tell
    a verse from a chorus in a loud modern mix, so cymbals (treble) and drum
    activity count too. Ranked within the song, so every track spends some
    time calm, some grooving and some at its peak."""
    busy = normalize(smooth(onsets, 3.0))
    feel = smooth(0.5 * loud + 0.25 * smooth(treble, 3.0) + 0.25 * busy, 2.0)
    ranks = np.argsort(np.argsort(feel))
    return ranks / max(1, len(ranks) - 1)


def find_drops(loud):
    """Times where the song jumps from quieter to much louder (skipping the
    first few seconds, where every song 'jumps' from silence)."""
    after = smooth(loud, 1.0)
    before = np.concatenate([np.zeros(2 * FPS), smooth(loud, 4.0)[:-2 * FPS]])
    jump = after - before
    drops, last = [], -1e9
    for i in range(6 * FPS, len(jump)):
        if jump[i] > 0.3 and after[i] > 0.6 and i - last > 15 * FPS:
            # step forward to the steepest point of the rise
            j = i + int(np.argmax(np.diff(after[i:i + FPS]))) if i + FPS < len(after) else i
            drops.append(round(j / FPS, 2))
            last = i
    return drops


def bar_phase(strengths):
    """Which beat (0-3) of each group of four starts the bar: the phase whose
    beats hit hardest on average."""
    if len(strengths) < 8:
        return 0
    return int(np.argmax([strengths[p::4].mean() for p in range(4)]))


def build_map(path):
    samples = decode(path)
    if len(samples) < SAMPLE_RATE:
        raise ValueError('track is under a second long')
    spec = spectrogram(samples)
    energy = bass_energy(spec)
    onsets = onset_strength(spec)
    period = estimate_period(onsets)
    beats = track_beats(onsets, period)
    # How hard each beat hits (0-1), so quiet passages get gentle flashes
    strengths = np.array([onsets[max(0, b - 2):b + 3].max() for b in beats])
    strengths = np.clip(strengths / (np.percentile(strengths, 90) + 1e-9), 0, 1)
    treble = treble_energy(spec)
    hue = harmony_hue(spec)
    loud = loudness(samples, len(spec))
    intensity = intensity_curve(loud, treble, onsets)
    slow = FPS // 10   # the slow-changing curves are stored at 10 per second
    return {
        'version': MAP_VERSION,
        'fps': FPS,
        'duration': round(len(samples) / SAMPLE_RATE, 2),
        'bpm': round(60.0 * FPS / period, 1),
        'energy': [int(round(v * 100)) for v in energy],
        'beats': [[round(b / FPS, 3), int(round(s * 100))] for b, s in zip(beats, strengths)],
        'bar_phase': bar_phase(strengths),
        'treble': [int(round(v * 100)) for v in treble],
        'slow_fps': FPS // slow,
        'hue': [int(round(v)) for v in hue[::slow]],
        'intensity': [int(round(v * 100)) for v in intensity[::slow]],
        'drops': find_drops(loud),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--force', action='store_true', help='rebuild every map')
    args = parser.parse_args()

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # project folder
    tracks = sorted(p for ext in EXTENSIONS
                    for p in glob.glob(os.path.join(here, 'assets', 'audio', 'background', '*' + ext)))
    if not tracks:
        print('No tracks found in assets/audio/background/')
        return
    for path in tracks:
        out = map_path(path)
        name = os.path.relpath(path, here)
        if not args.force and os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(path) \
                and map_version(out) >= MAP_VERSION:
            print('up to date  {}'.format(name))
            continue
        try:
            light_map = build_map(path)
        except Exception as e:
            print('FAILED      {}: {}'.format(name, e))
            continue
        with open(out, 'w') as f:
            json.dump(light_map, f, separators=(',', ':'))
        print('mapped      {}  ({} BPM, {} beats, {} drops)'.format(
            name, light_map['bpm'], len(light_map['beats']), len(light_map['drops'])))


if __name__ == '__main__':
    main()
