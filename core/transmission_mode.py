"""Read-only, off-tick evidence for the selected ETS2 profile's gearbox mode."""

import re
import time
from datetime import datetime, timedelta
from pathlib import Path


_MODE = re.compile(r'^uset\s+g_trans\s+"([^"]+)"\s*$', re.MULTILINE)
_PROFILE = re.compile(r"Set profile finished:\s*'([^']+)'", re.MULTILINE)
_LOG_MODE = re.compile(r'^\d\d:\d\d:\d\d\.\d+\s*:\s*uset g_trans "([^"]+)"', re.MULTILINE)
_LOG_CREATED = re.compile(r'^\*+\s*:\s*log created on\s*:\s*(.+)$', re.MULTILINE)


def read_transmission_mode(root=None, *, now=None):
    """Require the active profile file and the current game log to agree.

    This performs bounded disk I/O and must only run on the dedicated observer
    worker, never from Engine's 60 Hz control or activation path.
    """
    now = time.monotonic() if now is None else now
    result = {"mode": None, "status": "unknown", "source": "active profile + game.log.txt",
              "observed_at": now, "profile": None, "generation": None,
              "reason": "active ETS2 profile is not confirmed"}
    root = Path(root or Path.home() / "Documents" / "Euro Truck Simulator 2")
    try:
        log_path = root / "game.log.txt"
        before = log_path.stat()
        if before.st_size > 4 * 1024 * 1024:
            result["reason"] = "game log exceeds bounded read size"
            return result
        log = log_path.read_text(encoding="utf-8", errors="replace")
        after = log_path.stat()
        if (before.st_ino, before.st_mtime_ns, before.st_size) != (
                after.st_ino, after.st_mtime_ns, after.st_size):
            result["reason"] = "game log changed during read"
            return result
        profiles = list(_PROFILE.finditer(log))
        if not profiles:
            return result
        name = profiles[-1].group(1)
        encoded = name.encode("utf-8").hex().upper()
        # Never enumerate profiles to guess the active one. The selected name
        # is supplied by this game session, and Steam Cloud has its own root.
        steam = f"/steam/profiles/{encoded.lower()}/" in log.lower().replace("\\", "/")
        directory = "steam_profiles" if steam else "profiles"
        path = root / directory / encoded / "config_local.cfg"
        result["profile"] = encoded
        before = path.stat()
        if before.st_size > 64 * 1024:
            result["reason"] = "profile config exceeds bounded read size"
            return result
        config = path.read_text(encoding="utf-8", errors="replace")
        after = path.stat()
        if (before.st_ino, before.st_mtime_ns, before.st_size) != (
                after.st_ino, after.st_mtime_ns, after.st_size):
            result["reason"] = "profile config changed during read"
            return result
        modes = _MODE.findall(config)
        previous_profile_end = profiles[-2].end() if len(profiles) > 1 else 0
        logged = list(_LOG_MODE.finditer(log[previous_profile_end:profiles[-1].end()]))
        if len(modes) != 1 or not logged:
            result["reason"] = "g_trans is missing or ambiguous"
            return result
        config_mode, log_mode = modes[0], logged[-1].group(1)
        if config_mode != log_mode:
            result["reason"] = "active profile g_trans disagrees with game log"
            return result
        if config_mode not in {"0", "1", "2", "3"}:
            result["reason"] = "invalid g_trans value"
            return result
        log_event = logged[-1].group(0)
        created = _LOG_CREATED.search(log)
        if not created:
            result["reason"] = "game log session time is unavailable"
            return result
        try:
            started = datetime.strptime(created.group(1).strip(),
                                        "%A %B %d %Y @ %H:%M:%S")
            clock = re.match(r"(\d\d):(\d\d):(\d\d)\.(\d+)", log_event)
            event_at = started + timedelta(
                hours=int(clock[1]), minutes=int(clock[2]),
                seconds=int(clock[3]),
                milliseconds=int(clock[4][:3].ljust(3, "0")))
            # Files written after ETS2 logged g_trans cannot be treated as
            # accepted by the game merely because the values still match.
            if after.st_mtime > event_at.timestamp() + 2.0:
                result["reason"] = "profile config is newer than game confirmation"
                return result
        except (TypeError, ValueError, OverflowError):
            result["reason"] = "game log transmission time is invalid"
            return result
        log_identity = (str(log_path.stat().st_ctime_ns) + ":"
                        + str(previous_profile_end + logged[-1].start())
                        + ":" + str(profiles[-1].start()) + ":" + encoded
                        + ":" + log_event)
        generation = (log_identity
                      + ":" + str(after.st_mtime_ns) + ":" + config_mode)
        result.update(mode=int(config_mode), status="confirmed",
                      source=f"{directory}/{encoded}/config_local.cfg + game.log.txt",
                      detected_wall_time=time.time(), generation=generation,
                      config_mtime_ns=after.st_mtime_ns,
                      log_event=log_event, log_identity=log_identity,
                      reason="")
        return result
    except (OSError, UnicodeError, ValueError) as error:
        result["reason"] = type(error).__name__
        return result


def confirmed_mode(snapshot, now=None):
    """Return an authorised mode only while the off-tick evidence is fresh."""
    now = time.monotonic() if now is None else now
    if not isinstance(snapshot, dict) or snapshot.get("status") != "confirmed":
        return None
    try:
        age = now - float(snapshot["observed_at"])
        mode = snapshot["mode"]
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    return mode if mode in (0, 1, 2, 3) and 0 <= age <= 2.0 else None


class TransmissionModeObserver:
    """Invalidate a changed config until ETS2 logs a new mode observation."""

    def __init__(self):
        self.previous = None
        self.blocked_log_identity = None

    def accept(self, evidence):
        evidence = dict(evidence)
        old = self.previous
        if (old and evidence.get("status") == "confirmed"
                and evidence.get("log_identity") == old.get("log_identity")
                and evidence.get("profile") == old.get("profile")
                and evidence.get("config_mtime_ns")
                != old.get("config_mtime_ns")):
            self.blocked_log_identity = evidence.get("log_identity")
        if (self.blocked_log_identity is not None
                and evidence.get("log_identity") == self.blocked_log_identity):
            evidence.update(mode=None, status="unknown",
                            reason="profile config changed without a new game-log confirmation")
        elif evidence.get("log_identity") != self.blocked_log_identity:
            self.blocked_log_identity = None
        self.previous = evidence
        return evidence
