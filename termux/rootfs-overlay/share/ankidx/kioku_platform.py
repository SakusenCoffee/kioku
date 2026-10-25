"""What Kioku's shared Python code (kioku.advanced, kioku.syncserver,
kioku.ankidroid; shared/python in the repository) asks of the platform, for
the Termux variant: Preferences > Advanced in Anki on the phone's desktop.

Android is reached through ankidesk:<command> requests (ankidesk_menu,
handled by the app's AndroidBridge.java). Requests have no reply; the app
writes answers into files here instead.
"""

from __future__ import annotations

import json
import os
import time

from ankidesk_menu import android_request

HOME = os.environ.get("HOME", "")
CONFIG_DIR = os.path.join(HOME, ".config", "kioku")
# AndroidBridge.java writes its answers here: {package: versionName} of
# installed apps, and "yes"/"no" for All files access
APPS_FILE = os.path.join(CONFIG_DIR, "apps.json")
ALL_FILES_FILE = os.path.join(CONFIG_DIR, "all-files")
ANSWER_SECONDS = 2.0
# Preferences > Advanced, under the sync server's addresses
SERVER_NOTE = ("The server runs while Kioku's desktop is on; Android keeps it "
               "running in the background (Kioku's notification).")


def config_dir() -> str:
    return CONFIG_DIR


def sync_server_running(running: bool, text: str) -> None:
    # the desktop session's foreground service keeps Anki running already
    pass


def _ask(request: str, path: str) -> str | None:
    """Sends the request; the app's answer, once it rewrote the file."""
    try:
        before = os.stat(path).st_mtime_ns
    except OSError:
        before = None
    android_request(request)
    deadline = time.monotonic() + ANSWER_SECONDS
    while time.monotonic() < deadline:
        try:
            if os.stat(path).st_mtime_ns != before:
                with open(path, encoding="utf-8") as fh:
                    return fh.read()
        except OSError:
            pass
        time.sleep(0.05)
    return None


def all_files_access() -> bool:
    return (_ask("ankidesk:all-files/state", ALL_FILES_FILE) or "").strip() == "yes"


def request_all_files_access() -> None:
    # Settings > Phone storage: asks for All files access first
    android_request("ankidesk:storage")


def app_versions(packages: list[str]) -> dict[str, str]:
    """{package: versionName} of the installed ones."""
    answer = _ask("ankidesk:apps/" + ",".join(packages), APPS_FILE)
    try:
        found = json.loads(answer or "{}")
    except ValueError:
        return {}
    return {p: found[p] for p in packages if p in found}


def open_app_details(package: str) -> None:
    android_request("ankidesk:app-details/" + package)


def launch_ankidroid() -> None:
    from kioku.ankidroid import PACKAGES

    installed = app_versions(list(PACKAGES))
    if not installed:
        raise RuntimeError("AnkiDroid isn't installed")
    android_request("ankidesk:launch/" + next(p for p in PACKAGES if p in installed))
