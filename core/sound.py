"""Non-blocking playback of bundled UltraPilot notification sounds."""

import logging
import os
import threading

from core.paths import resource

_EXTS = (".wav", ".mp3")


def _find(name: str) -> str:
    """Resolve a sound name to a file path, or '' if none exists."""
    for ext in _EXTS:
        try:
            p = resource("assets", "sounds", name + ext)
        except Exception:
            p = os.path.join(resource("assets"), "sounds", name + ext)
        if p and os.path.exists(p):
            return p
    return ""


def _play_wav(path: str):
    try:
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC
                           | winsound.SND_NODEFAULT)
        return True
    except Exception:
        return False


def _play_mp3(path: str):
    # Try pygame first (common in this project's deps), then playsound.
    try:
        import pygame
        if not getattr(pygame, "_snd_init", False):
            try:
                pygame.mixer.init()
            except Exception:
                pass
            pygame._snd_init = True
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        return True
    except Exception:
        pass
    try:
        from playsound import playsound
        playsound(path, block=False)
        return True
    except Exception:
        return False


def play(name: str, volume: float = 1.0) -> bool:
    """Play ``assets/sounds/<name>.{mp3,wav}`` asynchronously.

    Returns True if playback started, False if the file is missing or no backend
    is available. Never raises."""
    path = _find(name)
    if not path:
        return False

    def _run():
        try:
            ok = False
            if path.lower().endswith(".wav"):
                ok = _play_wav(path)
            if not ok:
                ok = _play_mp3(path)
            if not ok:
                logging.debug("sound: no backend for %s", path)
        except Exception as e:
            logging.debug("sound: %s failed: %s", name, e)

    threading.Thread(target=_run, daemon=True).start()
    return True


def autopilot_event(previous_active, active, previous_reason, reason):
    """Choose one cue for a real authority transition or a new rejection."""
    if active and not previous_active:
        return "engage"
    if previous_active and not active:
        if str(reason or "").lower() in ("manual hotkey", "manual command"):
            return "disengage"
        return "auto_off"
    if not active and reason and reason != previous_reason:
        if str(reason).lower() not in ("manual hotkey", "manual command"):
            return "warning"
    return None
