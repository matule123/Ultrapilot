"""Coarse loading receipts, measured only on the map loader thread."""
import logging
import time

from core.process_memory import resident_mb

MAP_WAIT_TEXT = "Please wait for map to load the necessary data."


class MapLoadLog:
    def __init__(self, clock=time.perf_counter, memory=resident_mb):
        self.clock, self.memory = clock, memory
        self.started = clock()
        self.previous_ram = memory()
        logging.info(MAP_WAIT_TEXT, extra={"map_load_wait": True}, stacklevel=2)

    def loaded(self, kind, count):
        elapsed_cs = round((self.clock() - self.started) * 100)
        ram = self.memory()
        delta = (ram - self.previous_ram
                 if ram is not None and self.previous_ram is not None else None)
        self.previous_ram = ram
        usage = f"{delta:.0f}Mb of RAM" if delta is not None else "unknown RAM"
        logging.info("%dcs  | Loaded %d %s  used %s", elapsed_cs, count, kind, usage,
                     extra={"map_load_receipt": True, "load_elapsed_cs": elapsed_cs,
                            "load_count": count, "load_kind": kind,
                            "load_ram_mb": delta}, stacklevel=2)


def hud_map_loading_text(progress):
    return MAP_WAIT_TEXT if isinstance(progress, dict) and progress.get("active") else ""
