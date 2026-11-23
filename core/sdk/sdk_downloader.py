"""
SDK plugin installation for UltraPilot.

The UltraPilot SCS integration ships as three DLLs that go into the game's
``bin/win_x64/plugins/``
folder so the game exposes telemetry and accepts control input:

* ``scs-telemetry.dll``    — telemetry out of the game (truck state, position…).
* ``scs_sdk_controller.dll`` — control input back into the game (steering…).
* ``ets2la_plugin.dll`` — surrounding traffic, camera and GPS-route buffers.

The ETS2LA project keeps versioned copies of these DLLs in its repository, but
that repo is currently private, so we can't fetch new builds from it at runtime.
Legacy DLLs remain in ``assets/``. ETS2 1.61 uses a separate manifest-bound
bundle in ``assets/sdk/1.61/`` and accepts only the pinned game executable.
Unknown versions never fall back to a legacy native layout. Stationary
read-side validation is not a certificate for autonomous driving.
"""

import logging
import os
import shutil

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

from core.paths import app_dir, resource
from core.sdk import versioned_sdk

# All SDK DLLs required for telemetry, controls, GPS route and camera data.
SDK_FILES = ("scs-telemetry.dll", "scs_sdk_controller.dll", "ets2la_plugin.dll")

# Per-version sources.  ``bundled`` means the DLL is shipped in ``assets/`` and
# is used directly (no network).  ``urls`` (optional) would let us download a
# build for a version we don't bundle — left as a hook for the future.
SOURCES = {
    "1.61": {"bundled": True, "versioned": True},
    "1.60": {"bundled": True, "alias": "1.59"},
    "1.59": {
        "bundled": True,        # present in assets/scs-telemetry.dll etc.
        "urls": {},             # could be filled later with release URLs
    },
    # 1.58/1.57 ship the same SDK ABI in practice, so we reuse 1.59's DLLs.
    "1.58": {"bundled": True, "alias": "1.59"},
    "1.57": {"bundled": True, "alias": "1.59"},
}

def supported_versions() -> list:
    """Game versions we have a SDK source for (sorted, newest first)."""
    return sorted((v for v in SOURCES if is_supported(v)), reverse=True)


def _resolve(version: str) -> dict:
    """Follow ``alias`` chains to a concrete source entry."""
    version = versioned_sdk.major_minor(version)
    seen = set()
    cur = version
    while cur and cur in SOURCES and cur not in seen:
        seen.add(cur)
        entry = SOURCES[cur]
        nxt = entry.get("alias")
        if nxt and nxt != cur:
            cur = nxt
        else:
            return entry
    # Never install a legacy native layout into an unknown game version.
    return {}


def is_supported(version: str, assets_dir=None) -> bool:
    version = versioned_sdk.major_minor(version)
    if version in versioned_sdk.VERSIONED_VERSIONS:
        try:
            versioned_sdk.load_bundle(assets_dir or _dll_source_dir(),version)
            return True
        except versioned_sdk.BundleError:
            return False
    return version in SOURCES


def _dll_source_dir() -> str:
    """Where bundled DLLs live (assets/ next to the app)."""
    try:
        return resource("assets")
    except Exception:
        return os.path.join(app_dir(), "assets")


def _ensure_dlls_local(version: str, dest_dir: str, log=None, force: bool = False,
                       assets_dir=None) -> bool:
    """Get the SDK DLLs for ``version`` into ``dest_dir`` (no game install).

    Returns True if all required DLLs are present in ``dest_dir`` afterwards.
    """
    entry = _resolve(version)
    # Versioned bundles may only be installed through the exact-EXE gate.
    if not entry or entry.get('versioned'):
        return False
    os.makedirs(dest_dir, exist_ok=True)

    if entry.get("bundled"):
        src_dir = assets_dir or _dll_source_dir()
        ok = True
        for name in SDK_FILES:
            s = os.path.join(src_dir, name)
            d = os.path.join(dest_dir, name)
            if os.path.exists(d) and not force:
                continue
            if os.path.exists(s):
                try:
                    shutil.copy2(s, d)
                except Exception as e:
                    if log:
                        log("  " + name + ": " + str(e))
                    ok = False
            else:
                if log:
                    log("  chýba " + name + " v " + src_dir)
                ok = False
        return ok

    urls = entry.get("urls") or {}
    if not requests or not urls:
        return False
    ok = True
    for name in SDK_FILES:
        d = os.path.join(dest_dir, name)
        if os.path.exists(d) and not force:
            continue
        url = urls.get(name)
        if not url:
            ok = False
            continue
        try:
            r = requests.get(url, timeout=120, stream=True)
            if r.status_code != 200:
                ok = False
                continue
            with open(d, "wb") as f:
                for chunk in r.iter_content(65536):
                    if chunk:
                        f.write(chunk)
        except Exception as e:
            if log:
                log("  " + name + ": " + str(e))
            ok = False
    return ok


def is_sdk_installed(game_path: str, version=None, assets_dir=None) -> bool:
    """Versioned games require the exact EXE and DLL bytes, not just names."""
    if version is None:
        from core.sdk.game_utils import get_version_for_game
        version = get_version_for_game(game_path)
    if versioned_sdk.major_minor(version) in versioned_sdk.VERSIONED_VERSIONS:
        try:
            _,profile=versioned_sdk.load_bundle(assets_dir or _dll_source_dir(),version)
            versioned_sdk.verify_game(game_path,profile)
            return (not os.path.exists(os.path.join(game_path,'bin','win_x64','plugins',
                        'UltraPilot161ReadCandidate.dll'))
                    and versioned_sdk.installed_matches(game_path,profile))
        except versioned_sdk.BundleError:
            return False
    plugins_dir = os.path.join(game_path, "bin", "win_x64", "plugins")
    return all(os.path.exists(os.path.join(plugins_dir, n)) for n in SDK_FILES)


def ensure_installed(game_path: str, version: str, log=None, progress_cb=None,
                     force: bool = False, assets_dir=None) -> tuple:
    """Make sure the SDK DLLs are installed into ``game_path`` for ``version``.

    Returns ``(ok: bool, message: str)`` where ``message`` is a short status:
    ``"installed"``, ``"already"``, ``"unsupported:<version>"`` or
    ``"failed:<detail>"``.
    """
    if not game_path or not os.path.isdir(game_path):
        return False, "failed:no_game_path"

    from core.sdk.game_utils import get_version_for_game
    detected = get_version_for_game(game_path)
    if (detected not in ('Unknown','0.0')
            and versioned_sdk.major_minor(detected) != versioned_sdk.major_minor(version)):
        return False,'failed:game_version_mismatch'

    # DLL presence alone does not prove that its native layouts support this
    # game. In particular the installed 1.59 producer rejects ETS2 1.61.
    if not is_supported(version,assets_dir=assets_dir):
        return False, "unsupported:" + str(version)

    if versioned_sdk.major_minor(version) in versioned_sdk.VERSIONED_VERSIONS:
        try:
            result=versioned_sdk.install_bundle(game_path,assets_dir or _dll_source_dir(),
                version,force=force,log=log)
            if progress_cb:progress_cb(1.0)
            return result
        except (versioned_sdk.BundleError,OSError) as error:
            if log:log('SDK 1.61: '+str(error))
            return False,'failed:'+str(error)

    # Already there? Nothing to do.
    if is_sdk_installed(game_path,version=version,assets_dir=assets_dir) and not force:
        return True, "already"

    version = ".".join(str(version).strip().split(".")[:2])

    # Stage DLLs into the game's plugins folder.
    plugins_dir = os.path.join(game_path, "bin", "win_x64", "plugins")
    try:
        os.makedirs(plugins_dir, exist_ok=True)
    except Exception as e:
        logging.error("sdk_downloader: cannot create %s: %s", plugins_dir, e)
        return False, "failed:" + str(e)

    if progress_cb:
        progress_cb(0.2)
    if not _ensure_dlls_local(version, plugins_dir, log=log, force=force,assets_dir=assets_dir):
        return False, "failed:dll_missing"
    if progress_cb:
        progress_cb(1.0)

    return is_sdk_installed(game_path), "installed" if is_sdk_installed(game_path) else "failed:verify"


def repair(game_path: str, version: str, log=None, progress_cb=None) -> tuple:
    """Replace installed SDK DLLs with clean bundled copies."""
    return ensure_installed(game_path, version, log=log,
                            progress_cb=progress_cb, force=True)


def uninstall(game_path: str) -> tuple:
    """Remove UltraPilot/SCS SDK DLLs from the game's plugins directory."""
    if not game_path or not os.path.isdir(game_path):
        return False, "failed:no_game_path"
    plugins_dir = os.path.join(game_path, "bin", "win_x64", "plugins")
    try:
        for name in SDK_FILES:
            path = os.path.join(plugins_dir, name)
            if os.path.exists(path):
                os.remove(path)
    except Exception as e:
        logging.error("sdk_downloader: cannot uninstall SDK from %s: %s", plugins_dir, e)
        return False, "failed:" + str(e)
    return not is_sdk_installed(game_path), "uninstalled"
