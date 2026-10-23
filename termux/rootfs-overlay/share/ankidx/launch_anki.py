"""Start Anki with defaults suited to a phone.

Anki reads its UI scale, video driver and update-check flag from the profile
metadata, overriding any environment variable, so patch the ProfileManager
accessors before Anki starts. The UI scale only changes the default; a value
set later in Preferences still wins.
"""

import os
import sys


def provide_qtquick_stub() -> None:
    """Termux's pyqt6 is built without the QtQuick bindings. Anki imports them
    only to pick the Qt Quick graphics API, which QT_QUICK_BACKEND=software
    (set by session.sh) already does, so a stand-in is enough."""
    try:
        import PyQt6.QtQuick  # noqa: F401
        return
    except ImportError:
        pass
    import enum
    import types

    class QSGRendererInterface:
        class GraphicsApi(enum.Enum):
            Unknown = 0
            Software = 1
            OpenVG = 2
            OpenGL = 3
            Direct3D11 = 4
            Vulkan = 5
            Metal = 6
            Null = 7
            Direct3D12 = 8

    class QQuickWindow:
        @staticmethod
        def setGraphicsApi(api: "QSGRendererInterface.GraphicsApi") -> None:
            pass

    module = types.ModuleType("PyQt6.QtQuick")
    module.QQuickWindow = QQuickWindow
    module.QSGRendererInterface = QSGRendererInterface
    module.__all__ = ["QQuickWindow", "QSGRendererInterface"]
    sys.modules["PyQt6.QtQuick"] = module


def provide_opengl_placeholders() -> None:
    """Termux's pyqt6 is also built without Qt's OpenGL classes. Anki imports
    QOpenGLContext but only uses it on Qt 5, so a placeholder is enough."""
    from PyQt6 import QtGui

    for name in ("QOpenGLContext",):
        if not hasattr(QtGui, name):
            setattr(QtGui, name, type(name, (), {}))


provide_qtquick_stub()
provide_opengl_placeholders()

from aqt.profiles import ProfileManager, VideoDriver  # noqa: E402

DEFAULT_SCALE = float(os.environ.get("ANKIDX_SCALE", "2.0"))
# on the remote desktop's screen (ankidesk_remote.py): a computer's monitor
REMOTE = os.environ.get("ANKIDX_REMOTE") == "1"


def ui_scale(self: ProfileManager) -> float:
    if REMOTE:
        return DEFAULT_SCALE
    return max(self.meta.get("uiScale", DEFAULT_SCALE), 1)


def check_for_updates(self: ProfileManager) -> bool:
    # Updates ship with the Android app, not through Anki's own updater.
    return False


def video_driver(self: ProfileManager) -> VideoDriver:
    # No OpenGL stack is bundled.
    return VideoDriver.Software


def signal_ready() -> None:
    # Tells the Android app to swap its splash screen for the display.
    path = os.environ.get("ANKIDX_READY_FILE")
    if path:
        open(path, "w").close()


_setup_meta = ProfileManager.setupMeta


def setup_meta(self: ProfileManager):  # type: ignore[no-untyped-def]
    result = _setup_meta(self)
    # Anki 26.09 sets QT_SCALE_FACTOR only after creating the QApplication,
    # which Qt no longer reads then; set it as soon as the scale is known
    os.environ["QT_SCALE_FACTOR"] = str(self.uiScale())
    return result


ProfileManager.uiScale = ui_scale
ProfileManager.check_for_updates = check_for_updates
ProfileManager.video_driver = video_driver
ProfileManager.setupMeta = setup_meta

import aqt  # noqa: E402
from aqt import gui_hooks  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ankidesk_mobile  # noqa: E402

if REMOTE:
    import aqt.utils  # noqa: E402

    # window sizes, splitters and table columns: the remote screen's own, so
    # each screen keeps what suits it
    _qt_state_key = aqt.utils._qt_state_key
    aqt.utils._qt_state_key = lambda kind, key: "kioku_remote_" + _qt_state_key(kind, key)

    def maximize_first_time() -> None:
        # after loadProfile() restored the window: with no size saved for the
        # remote screen yet, it has the phone's, tiny on a monitor
        key = aqt.utils._qt_state_key(aqt.utils._QtStateKeyKind.GEOMETRY, "mainWindow")
        if aqt.mw.pm.profile is not None and key not in aqt.mw.pm.profile:
            aqt.mw.showMaximized()

    gui_hooks.profile_did_open.append(maximize_first_time)
else:
    ankidesk_mobile.setup()
gui_hooks.main_window_did_init.append(signal_ready)

aqt.run()
