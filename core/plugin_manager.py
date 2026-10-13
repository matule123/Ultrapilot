import multiprocessing as mp
import os
import logging
import time
import importlib
import inspect
import threading
from typing import Any, Type, Dict

from sdk.base_plugin import BasePlugin
from sdk.plugin_sdk import PluginSDK


def _shutdown_transport_error(error):
    """Return whether Manager/pipe IPC disappeared during normal shutdown."""
    text = f"{type(error).__name__}: {error}".lower()
    return any(marker in text for marker in (
        "brokenpipe", "broken pipe", "eoferror", "pipe has been ended",
        "pipe is being closed", "winerror 109", "winerror 232",
    ))


def _revoke_producer(state, name, *, required):
    fields={
        'drivepolicy': {'longitudinal_policy':None,'longitudinal_policy_active':required,
            'planned_speed_ms':None,'aux_brake_request':None},
        'acc': {'longitudinal_acc':None,'longitudinal_acc_active':required,
            'acc_throttle':None,'acc_brake':None},
    }
    if name in fields: state.update(fields[name])


def plugin_worker(plugin_class: Type[BasePlugin], plugin_name: str,
                  shared_dict: Dict[str, Any], stop_event):
    """
    Entrypoint for a plugin running in its own process.

    The PluginSDK is built *inside* the new process from the shared managed
    dict, so the plugin gets a fully wired SDK (telemetry / controller proxy /
    tags / settings) without anything unpicklable crossing the process boundary.
    """
    # Each plugin process is a fresh Python interpreter, so it has NO logging
    # setup inherited from the parent — without this, every ``logging.info`` call
    # inside a plugin (e.g. the autopilot diagnostics) is silently dropped and
    # never reaches ultrapilot.log. Configure a file handler that appends to the
    # same log the engine uses, tagged with the plugin name.
    try:
        from core.logger import setup
        setup(plugin_name=plugin_name)
    except Exception:
        logging.basicConfig(level=logging.INFO)

    plugin=None;first_failure=None;reason='stopped';last_time=0.
    try:
        if stop_event.is_set() or shared_dict.get('app_shutdown_requested',False):
            return
        if shared_dict.get(f'plugin_enabled.{plugin_name}') is False:
            return
        sdk = PluginSDK(shared_dict, plugin_name)
        plugin = plugin_class(sdk)
        plugin.on_start()
        start_control_worker = getattr(plugin, "start_control_worker", None)
        if callable(start_control_worker):
            start_control_worker()

        # Once after initialization, outside the recurring control tick.
        # RSS is the whole worker process, not exclusive plugin allocations.
        from core.logger import log_plugin_ready
        from core.process_memory import resident_mb
        log_plugin_ready(plugin_name, resident_mb())

        tick_dt = 0.01  # 100 Hz
        last_time = time.monotonic()
        failures=0
        while not stop_event.is_set():
            current_time = time.monotonic()
            delta_time = current_time - last_time
            last_time = current_time

            # Allow the UI to enable/disable plugins live via shared state.
            live_enabled = shared_dict.get(f"plugin_enabled.{plugin_name}", None)
            if live_enabled is False:
                reason='disabled';break

            if plugin.enabled:
                try:
                    plugin.on_tick(delta_time)
                    failures=0
                except Exception as e:
                    if stop_event.is_set() or shared_dict.get('app_shutdown_requested',False):
                        reason='shutdown'
                        break
                    # Include the failing source line. A message-only exception
                    # made route failures look like a frozen progress indicator.
                    if first_failure is None:
                        first_failure=dict(type=type(e).__name__,message=str(e)[:240],
                                           observed_at=current_time)
                        logging.exception(f"[plugin:{plugin_name}] on_tick error: {e}")
                    _revoke_producer(shared_dict,plugin_name,required=True)
                    failures+=1
                    if failures>=3 or _shutdown_transport_error(e):
                        reason='tick_failure';break

            if plugin_name == "map":
                # A navigation tick already spends its period localizing a
                # real SDK frame. Adding a full sleep afterwards unnecessarily
                # spaces fresh targets apart (Windows can round 10 ms up).
                # Wait only the remainder, with no catch-up queue after an
                # overrun. FrameGate still prevents duplicate calculations.
                stop_event.wait(max(0.0, tick_dt - (
                    time.monotonic() - current_time)))
            else:
                time.sleep(tick_dt)

    except BaseException as e:
        if stop_event.is_set():
            reason='shutdown'
            logging.info("[plugin:%s] stopped during application shutdown.",
                         plugin_name)
        else:
            reason='crashed'
            if first_failure is None:
                first_failure=dict(type=type(e).__name__,message=str(e)[:240],observed_at=last_time)
            logging.exception("[plugin:%s] process crashed: %s", plugin_name, e)
    finally:
        if plugin is not None:
            try: plugin.on_stop()
            except Exception as e:
                if not stop_event.is_set():
                    reason='cleanup_failure'
                    if first_failure is None:
                        first_failure=dict(type=type(e).__name__,message=str(e)[:240],observed_at=last_time)
                    logging.exception('[plugin:%s] cleanup failed',plugin_name)
        try:
            failed=reason in ('tick_failure','crashed','cleanup_failure')
            _revoke_producer(shared_dict,plugin_name,required=failed)
            shared_dict[f'plugin_exit.{plugin_name}']=dict(reason=reason,
                first_failure=first_failure,observed_at=last_time)
        except Exception:
            pass  # Manager may already be gone during shutdown.
    if reason in ('tick_failure','crashed','cleanup_failure'):
        raise SystemExit(1)


def plugin_version(plugin_class):
    """Validate independent MAJOR.MINOR.PATCH metadata before loading a plugin."""
    import re
    version = getattr(plugin_class, "VERSION", "0.0.0")
    if not isinstance(version, str) or not re.fullmatch(
            r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version):
        raise ValueError("Plugin VERSION must use MAJOR.MINOR.PATCH")
    return version


class PluginManager:
    """
    Multiprocessing plugin manager with crash supervision.

    Each plugin runs in its own process.  If a plugin process dies unexpectedly
    while the engine is still running, it is automatically restarted, so a
    single misbehaving plugin can never permanently break the autopilot.
    """

    def __init__(self, engine):
        self.engine = engine
        from core.paths import app_dir
        self.plugin_dir = os.path.join(app_dir(), "plugins")
        # folder -> {class, process, stop_event}
        self.plugins: Dict[str, Dict[str, Any]] = {}
        self._published_processes = None
        self._closing = False
        self._lifecycle_lock = threading.RLock()
        self._deferred_plugins = set()

    def _may_spawn(self, folder):
        return (not self._closing and getattr(self.engine,'running',True)
            and not self.engine.shared_state.get('app_shutdown_requested',False)
            and self.engine.shared_state.get(f'plugin_enabled.{folder}') is not False)

    def begin_shutdown(self):
        self._closing=True
        for entry in tuple(self.plugins.values()):
            if entry.get('stop_event') is not None: entry['stop_event'].set()
        self._deferred_plugins = set()

    # --- Discovery ------------------------------------------------------------
    def _find_plugin_class(self, folder: str) -> Type[BasePlugin]:
        """Import plugins.<folder>.main and return its plugin class.

        Accepts a class literally named ``Plugin`` or any BasePlugin subclass
        (so e.g. ``DiscordPlugin`` is found too)."""
        module = importlib.import_module(f"plugins.{folder}.main")
        if hasattr(module, "Plugin"):
            return getattr(module, "Plugin")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, BasePlugin) and obj is not BasePlugin:
                return obj
        raise ImportError(f"No BasePlugin subclass found in plugins.{folder}.main")

    def _enabled_in_settings(self, folder: str) -> bool:
        plugins_cfg = self.engine.settings.get("plugins", {}) or {}
        # Default: enabled unless explicitly turned off in settings.json.
        return bool(plugins_cfg.get(folder, True))

    def discover_and_load(self):
        logging.info("Discovering plugins...")
        if not os.path.isdir(self.plugin_dir):
            logging.error(f"Plugin directory not found: {self.plugin_dir}")
            return

        for folder in sorted(os.listdir(self.plugin_dir)):
            full = os.path.join(self.plugin_dir, folder)
            if not os.path.isdir(full) or folder.startswith("__"):
                continue
            if not os.path.exists(os.path.join(full, "main.py")):
                continue
            if not self._enabled_in_settings(folder):
                self._deferred_plugins.add(folder)
                logging.info(f"Plugin '{folder}' disabled in settings, skipping.")
                continue
            try:
                plugin_class = self._find_plugin_class(folder)
                version = plugin_version(plugin_class)
                self.plugins[folder] = {"class": plugin_class, "version": version,
                                        "process": None, "stop_event": None}
                self.engine.shared_state.set("plugin_versions", {
                    name: entry["version"] for name, entry in self.plugins.items()})
                self._spawn(folder)
                logging.info(f"Loaded plugin: {folder} v{version} ({plugin_class.__name__})")
            except Exception as e:
                logging.error(f"Failed to load plugin '{folder}': {e}")

    # --- Process management ----------------------------------------------------
    def _spawn(self, folder: str):
        with self._lifecycle_lock:
            return self._spawn_locked(folder)

    def _spawn_locked(self, folder):
        if not self._may_spawn(folder): return
        entry = self.plugins[folder]
        stop_event = mp.Event()
        proc = mp.Process(
            target=plugin_worker,
            args=(entry["class"], folder, self.engine.shared_state.raw, stop_event),
            name=f"Plugin-{folder}",
            daemon=True,
        )
        entry["process"] = proc
        entry["stop_event"] = stop_event
        if not self._may_spawn(folder):
            stop_event.set()
            entry['process']=None
            return
        self.engine.shared_state.set(f'plugin_exit.{folder}',None)
        proc.start()
        entry['started_at']=time.monotonic()
        self._publish_processes()

    def _publish_processes(self):
        """Expose exact plugin PIDs for the Performance UI on Windows."""
        processes = {}
        for name, entry in self.plugins.items():
            proc = entry.get("process")
            if proc is not None and proc.pid and proc.is_alive():
                processes[name] = int(proc.pid)
        if processes != self._published_processes:
            self._published_processes = dict(processes)
            self.engine.shared_state.set("plugin_processes", processes)

    def tick(self, delta_time: float):
        """Supervise plugin processes; restart any that died unexpectedly."""
        if (self._closing or not self.engine.running
                or self.engine.shared_state.get('app_shutdown_requested',False)):
            return
        with self._lifecycle_lock:
            self._tick_locked(delta_time)

    def _tick_locked(self, delta_time):
        # A UI enable must also start a plugin skipped during discovery. Do not
        # rescan/import every tick or create duplicate processes on repeated UI
        # updates. Disabled loaded workers retain the existing live flag path.
        for folder in tuple(self._deferred_plugins):
            if self.engine.shared_state.get(f"plugin_enabled.{folder}") is not True:
                continue
            self._deferred_plugins.remove(folder)
            try:
                plugin_class = self._find_plugin_class(folder)
                version = plugin_version(plugin_class)
                self.plugins[folder] = {"class": plugin_class, "version": version,
                                        "process": None, "stop_event": None}
                self.engine.shared_state.set("plugin_versions", {
                    name: entry["version"] for name, entry in self.plugins.items()})
                self._spawn(folder)
                logging.info("Loaded enabled plugin: %s v%s", folder, version)
            except Exception:
                self.plugins.pop(folder, None)
                logging.exception("Could not start newly enabled plugin '%s'", folder)
        for folder, entry in tuple(self.plugins.items()):
            proc = entry["process"]
            stop_event = entry["stop_event"]
            if proc is not None and proc.is_alive():
                if entry.get('health',{}).get('state') in ('restart_wait','failed'):
                    health=dict(state='running',attempts=entry.get('attempts',0),
                        first_failure=entry.get('first_failure'),next_restart=None)
                    entry['health']=health
                    self.engine.shared_state.set(f'plugin_health.{folder}',health)
                if time.monotonic()-entry.get('started_at',time.monotonic())>=60.:
                    entry['attempts']=0
                    entry.pop('first_failure',None)
                    entry.pop('failure_noted',None)
                continue
            # Healthy workers already consume the live flag. Read it here
            # only after exit, before deciding whether any restart is allowed.
            enabled=self.engine.shared_state.get(f'plugin_enabled.{folder}') is not False
            if not enabled:
                if stop_event is not None: stop_event.set()
                entry['disabled']=True
                continue
            exit_record=self.engine.shared_state.get(f'plugin_exit.{folder}') or {}
            if (proc is not None and exit_record.get('reason')=='disabled'
                    and self.engine.shared_state.get(f'plugin_enabled.{folder}') is True):
                proc.join(timeout=0)
                entry.update(disabled=False,attempts=0,next_restart=0.)
                entry.pop('first_failure',None)
                self._spawn(folder);continue
            if proc is not None and not proc.is_alive() and stop_event is not None \
                    and stop_event.is_set() and entry.get('disabled'):
                entry.update(disabled=False,attempts=0,next_restart=0.)
                entry.pop('first_failure',None)
                proc.join(timeout=0)
                self._spawn(folder);continue
            if proc is None or stop_event is None or stop_event.is_set(): continue
            now=time.monotonic()
            if 'first_failure' not in entry:
                entry['first_failure']=dict(exitcode=proc.exitcode,
                    worker=exit_record.get('first_failure'),reason=exit_record.get('reason','unexpected_exit'))
                logging.warning("Plugin '%s' exited: %s",folder,entry['first_failure'])
            if not entry.get('failure_noted'):
                values={}
                _revoke_producer(values,folder,required=True)
                self.engine.shared_state.update_batch(values)
                entry['failure_noted']=True
                entry['next_restart']=now+min(4.,.5*2**entry.get('attempts',0))
            attempts=entry.get('attempts',0)
            exhausted=attempts>=3
            health=dict(state='failed' if exhausted else 'restart_wait',attempts=attempts,
                first_failure=entry['first_failure'],next_restart=None if exhausted else entry['next_restart'])
            if entry.get('health')!=health:
                entry['health']=health
                self.engine.shared_state.set(f'plugin_health.{folder}',health)
            if exhausted or now<entry['next_restart'] or not self._may_spawn(folder): continue
            proc.join(timeout=0)
            entry.update(attempts=attempts+1,failure_noted=False)
            self._spawn(folder)
        self._publish_processes()

    def stop_all(self):
        self.begin_shutdown()
        with self._lifecycle_lock:
            self._stop_all_locked()

    def _stop_all_locked(self):
        for folder, entry in self.plugins.items():
            logging.info("Stopping plugin '%s'...", folder)
            if entry["stop_event"]:
                entry["stop_event"].set()
        for folder, entry in self.plugins.items():
            proc = entry["process"]
            if proc:
                proc.join(timeout=1)
                if proc.is_alive():
                    logging.warning(
                        "Plugin '%s' did not stop within 1 second; terminating.",
                        folder)
                    proc.terminate()
                    proc.join(timeout=1)
                if proc.is_alive():
                    logging.error("Plugin '%s' could not be terminated cleanly.",
                                  folder)
                else:
                    logging.info("Plugin '%s' stopped.", folder)
        self.engine.shared_state.set("plugin_processes", {})
