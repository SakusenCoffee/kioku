"""Web platform layer for the shared kioku package: Anki's pages in
<iframe>s served through a service worker (webview.py, http.py), files
through the browser (files.py), audio and TTS through the page (audio.py).
/home/web_user is kept in IndexedDB (src/main.cpp kioku_load_storage).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from . import web
from .files import pick_files, save_path
from .webview import WebView, delete_cookies, set_cookie

logger = logging.getLogger("kioku.platform")

HOME = os.path.expanduser("~")


def prepare() -> None:
    """Runs before Anki is imported."""
    from PyQt6.QtCore import QCoreApplication, Qt

    from . import http

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeMenuBar)
    # roots for rustls (reqwest with native roots, which reads this file):
    # the wasm file system has no system store
    os.environ.setdefault("SSL_CERT_FILE", "/site/certifi/cacert.pem")
    web.start()
    http.setup(int(web.js("port")))
    _fill_screen()
    _save_after_changes()
    if dev_allowed():
        web.listen("devexec", _devexec)


def _fill_screen() -> None:
    """Like on a phone, the main window fills the page, also when the
    browser window is resized. Qt for WebAssembly leaves it at its desktop
    size, Anki restores its saved geometry when a profile opens, and
    WindowMaximized left it taller than the page."""
    import aqt
    from aqt import gui_hooks
    from PyQt6.QtCore import QEvent, QObject, QTimer

    def fit() -> None:
        mw = aqt.mw
        if mw is None or mw.isFullScreen() or (screen := mw.screen()) is None:
            return
        if mw.geometry() != screen.availableGeometry():
            mw.setGeometry(screen.availableGeometry())

    def fit_soon() -> None:
        # Qt may still apply the stored geometry once the window is exposed
        for delay in (0, 300, 1000):
            QTimer.singleShot(delay, fit)

    class Watch(QObject):
        def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
            if event is not None and event.type() in (QEvent.Type.Show, QEvent.Type.Resize):
                fit_soon()
            return False

    def init() -> None:
        aqt.mw.installEventFilter(Watch(aqt.mw))
        fit_soon()
        if (screen := aqt.mw.screen()) is not None:
            screen.availableGeometryChanged.connect(lambda _: fit())

    gui_hooks.main_window_did_init.append(init)
    gui_hooks.profile_did_open.append(fit_soon)


def _save_after_changes() -> None:
    """Save the files to IndexedDB (shell/storage.js) after collection
    changes, besides the page's timer."""
    from aqt import gui_hooks

    gui_hooks.operation_did_execute.append(lambda *_: web.js("persist"))
    gui_hooks.profile_will_close.append(lambda: web.js("persist"))


def _devexec(event: dict) -> None:
    """Development: run Python sent from the page's console with
    __kiokuWeb.post({type: "devexec", code: "..."}); `result` is printed."""
    import traceback

    scope: dict[str, Any] = {}
    try:
        exec(event["code"], scope)
        print("devexec:", repr(scope.get("result")))
    except Exception:
        print("devexec failed:", traceback.format_exc())


def dev_allowed() -> bool:
    return True


def documents_dir() -> str:
    return "/home/web_user/Documents"


def config_dir() -> str:
    return "/home/web_user/.config"


def cache_dir() -> str:
    return "/home/web_user/.cache"


def dark_mode() -> bool:
    return False


def open_folder(path: str) -> None:
    logger.info("open_folder(%s): not available on the web", path)


def audio_player(taskman: Any, media_folder: str) -> Any:
    from .audio import WebAudioPlayer

    return WebAudioPlayer(taskman, media_folder)


def tts_player(taskman: Any) -> Any:
    from .audio import WebSpeechPlayer

    return WebSpeechPlayer()


def keep_awake() -> None:
    pass


def move_to_back() -> None:
    pass


def all_files_access() -> bool:
    return True


def request_all_files_access() -> None:
    pass


def app_versions(packages: list[str]) -> dict[str, str]:
    return {}


def open_app_details(package: str) -> None:
    pass


def launch_ankidroid() -> None:
    pass


def watch_background(on_background: Callable[[], None], on_foreground: Callable[[], None]) -> None:
    pass


def sync_server_running(running: bool, text: str) -> None:
    pass


def screenshot(path: str) -> str:
    return ""
