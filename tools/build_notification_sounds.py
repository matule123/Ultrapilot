"""Build original, quiet notification cues with soft musical envelopes.

The locally installed ETS2LA sounds informed the short duration and warm,
low-frequency character. No audio or code is copied from that project.
"""

from pathlib import Path
import wave

import numpy as np


DESTINATION = Path(__file__).resolve().parents[1] / "assets" / "sounds"
RATE = 44100

# Event: (duration, (frequency Hz, start seconds, strength) notes).
# Separate phrases avoid copying another application's notes or recordings.
PHRASES = {
    "boot": (1.45, ((174.61, 0.00, 0.60), (220.00, 0.26, 0.48),
                    (261.63, 0.54, 0.40))),
    "engage": (0.68, ((174.61, 0.00, 0.72), (220.00, 0.18, 0.52))),
    "disengage": (0.63, ((196.00, 0.00, 0.64), (164.81, 0.17, 0.44))),
    "warning": (0.55, ((392.00, 0.00, 0.56), (349.23, 0.13, 0.36))),
    "auto_off": (0.74, ((246.94, 0.00, 0.55), (196.00, 0.16, 0.45))),
}


def _note(frequency, seconds):
    t = np.arange(round(seconds * RATE), dtype=np.float64) / RATE
    # Quiet harmonics give a soft struck timbre; they decay faster than the
    # fundamental rather than sustaining as a bare oscillator.
    fundamental = np.sin(2 * np.pi * frequency * t)
    second = 0.075 * np.exp(-t / 0.14) * np.sin(4 * np.pi * frequency * t)
    third = 0.015 * np.exp(-t / 0.09) * np.sin(6 * np.pi * frequency * t)
    attack = np.sin(np.minimum(t / 0.055, 1) * np.pi / 2) ** 2
    tail = np.exp(-t / 0.23)
    return (fundamental + second + third) * attack * tail


def _render(duration, notes):
    count = round(duration * RATE)
    mono = np.zeros(count, dtype=np.float64)
    for frequency, start, strength in notes:
        offset = round(start * RATE)
        note = _note(frequency, (count - offset) / RATE)
        mono[offset:offset + len(note)] += strength * note
    release = min(count, round(0.18 * RATE))
    mono[-release:] *= np.cos(np.linspace(0, np.pi / 2, release)) ** 2
    mono *= 0.11 / max(np.max(np.abs(mono)), 1e-12)
    stereo = np.repeat(mono[:, None], 2, axis=1)
    return (np.clip(stereo, -1, 1) * 32767).astype("<i2").tobytes()


def main():
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for name, (duration, notes) in PHRASES.items():
        with wave.open(str(DESTINATION / f"{name}.wav"), "wb") as output:
            output.setnchannels(2)
            output.setsampwidth(2)
            output.setframerate(RATE)
            output.writeframes(_render(duration, notes))


if __name__ == "__main__":
    main()
