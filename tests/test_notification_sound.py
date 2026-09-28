"""Notification cues are bundled and driven by authority transitions."""

import wave

import numpy as np

from core import sound


def test_bundled_wav_cues_are_playable_files():
    for name in ("boot", "engage", "warning", "disengage", "auto_off"):
        path = sound._find(name)
        assert path.endswith(".wav")
        with wave.open(path, "rb") as stream:
            assert stream.getnchannels() == 2
            assert stream.getframerate() == 44100
            assert stream.getnframes() > 1000


def test_cues_have_soft_level_and_no_harsh_high_frequency_band():
    for name in ("boot", "engage", "warning", "disengage", "auto_off"):
        with wave.open(sound._find(name), "rb") as stream:
            samples = np.frombuffer(
                stream.readframes(stream.getnframes()), dtype="<i2")
        mono = samples.astype(np.float64).reshape(-1, 2).mean(axis=1) / 32768
        assert np.max(np.abs(mono)) < 0.31
        power = np.abs(np.fft.rfft(mono)) ** 2
        frequencies = np.fft.rfftfreq(len(mono), 1 / 44100)
        assert power[frequencies > 3000].sum() / power.sum() < 0.001
        assert abs(mono[0]) < 0.0001
        assert abs(mono[-1]) < 0.0001
        blocks = mono[:len(mono) // 441 * 441].reshape(-1, 441)
        level = np.sqrt(np.mean(blocks ** 2, axis=1))
        assert np.max(np.abs(np.diff(level))) < 0.04


def test_autopilot_transition_uses_one_appropriate_cue():
    assert sound.autopilot_event(False, True, "", "") == "engage"
    assert sound.autopilot_event(True, False, "", "manual hotkey") == "disengage"
    assert sound.autopilot_event(True, False, "", "steering packet stale") == "auto_off"
    assert sound.autopilot_event(False, False, "", "map heartbeat stale") == "warning"
    assert sound.autopilot_event(False, False, "map heartbeat stale",
                                  "map heartbeat stale") is None
