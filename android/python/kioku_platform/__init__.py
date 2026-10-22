"""Android platform layer for the shared kioku package: android.webkit
web views, MediaPlayer audio and the system file picker, all provided by
KiokuBridge.java."""

from __future__ import annotations

import os
from typing import Any

from .files import pick_files, save_path
from .webview import WebView

__all__ = [
    "WebView",
    "audio_player",
    "cache_dir",
    "config_dir",
    "dark_mode",
    "dev_allowed",
    "documents_dir",
    "keep_awake",
    "move_to_back",
    "open_folder",
    "pick_files",
    "prepare",
    "save_path",
    "screenshot",
    "tts_player",
]

HOME = os.path.expanduser("~")


# the system CA certificates; the APEX copy is updated with Conscrypt
# (Android 14+), the /system one is the fallback
CA_DIRS = ("/apex/com.android.conscrypt/cacerts", "/system/etc/security/cacerts")


def prepare() -> None:
    """Runs before Anki is imported."""
    _ca_bundle()
    # Qt turns QMenuBar into the activity's options menu, which has no
    # button without an action bar; draw Anki's menu bar as a widget instead
    from PyQt6.QtCore import QCoreApplication, Qt

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeMenuBar)


def _ca_bundle() -> None:
    """HTTPS: Python's OpenSSL has no certificate store configured on
    Android, and the system's folder cannot serve as SSL_CERT_DIR: its files
    are named with OpenSSL's old (MD5) subject hash, while OpenSSL 3 looks
    certificates up by the current one. Concatenate them into a bundle
    (truststore, which Anki uses, then picks it up through SSL_CERT_FILE)."""
    if "SSL_CERT_FILE" in os.environ:
        return
    folder = next((d for d in CA_DIRS if os.path.isdir(d)), None)
    if folder is None:
        return
    names = sorted(os.listdir(folder))
    bundle = os.path.join(cache_dir(), "cacerts.pem")
    stamp = f"{folder} {len(names)} {os.stat(folder).st_mtime_ns}\n"
    try:
        with open(bundle, encoding="ascii", errors="replace") as f:
            current = f.readline() == "# " + stamp
    except OSError:
        current = False
    if not current:
        os.makedirs(cache_dir(), exist_ok=True)
        with open(bundle + ".tmp", "w", encoding="ascii", errors="replace") as out:
            out.write("# " + stamp)
            for name in names:
                with open(os.path.join(folder, name), encoding="ascii", errors="replace") as f:
                    out.write(f.read() + "\n")
        os.replace(bundle + ".tmp", bundle)
    os.environ["SSL_CERT_FILE"] = bundle


def dev_allowed() -> bool:
    """The dev command channel runs code from the external files folder,
    which other apps can write on Android 9/10; only development builds
    (tools/run_device.sh) allow it."""
    home = os.environ.get("KIOKU_PYTHON_HOME", "")
    return bool(home) and os.path.exists(os.path.join(home, "dev-build"))


def documents_dir() -> str:
    # the app's external files folder: reachable over USB and by file managers
    return os.environ.get("KIOKU_DOCUMENTS") or os.path.join(HOME, "Documents")


def config_dir() -> str:
    return os.path.join(HOME, ".config")


def cache_dir() -> str:
    return os.environ.get("TMPDIR") or os.path.join(HOME, ".cache")


def dark_mode() -> bool:
    from . import bridge

    return bool(bridge.call("darkMode"))


def open_folder(path: str) -> None:
    # Android has no folder viewer for app-private folders; nothing to open
    from aqt.utils import tooltip

    tooltip(path)


def audio_player(taskman: Any, media_folder: str) -> Any:
    from .audio import MediaPlayerPlayer

    return MediaPlayerPlayer(taskman, media_folder)


def tts_player(taskman: Any) -> Any:
    from .tts import TextToSpeechPlayer

    return TextToSpeechPlayer()


def keep_awake() -> None:
    from . import bridge

    bridge.call("keepAwake")


def move_to_back() -> None:
    from . import bridge

    bridge.call("moveTaskToBack")


def screenshot(path: str) -> str:
    """The Qt surface and the web views are separate Android surfaces; take
    screenshots from the computer instead (adb exec-out screencap -p)."""
    raise NotImplementedError("use android/tools/devcmd.sh --shot")
