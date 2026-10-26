"""Anki fitted to a phone's screen (ANKI_FIT_SCREEN=true; anki-session runs
this file instead of `anki`).

The screen is the size of the browser that shows it. When that is narrower
than Anki's desktop layout, its pages (deck list, study screen, editor,
statistics) are zoomed out until they fit, and windows bigger than the
screen fill it. Wider screens are left alone, and it follows the screen as
it changes (a phone turned sideways, another browser taking over).
"""

from __future__ import annotations

import aqt
from aqt.qt import QApplication, QEvent, QGuiApplication, QObject, QTimer, QWebEngineView, QWidget, Qt

# narrowest screen Anki's pages are laid out for, in screen pixels
DESKTOP_WIDTH = 800


def zoom() -> float:
    width = QGuiApplication.primaryScreen().availableGeometry().width()
    return min(1.0, width / DESKTOP_WIDTH)


def fit_page(web: QWebEngineView) -> None:
    # on a wide screen, only undo our own zoom (View > Zoom In stays)
    z = zoom()
    if z >= 1 and not web.property("kioku_zoomed"):
        return
    web.setProperty("kioku_zoomed", z < 1)
    if abs(web.zoomFactor() - z) > 0.01:
        web.setZoomFactor(z)


def fit_window(w: QWidget) -> None:
    avail = w.screen().availableGeometry()
    if w.isMaximized() or w.isFullScreen():
        return
    if w.frameGeometry().width() > avail.width() or w.frameGeometry().height() > avail.height():
        w.showMaximized()


def is_window(w: QWidget) -> bool:
    return w.isWindow() and w.windowType() in (Qt.WindowType.Window, Qt.WindowType.Dialog)


class Fit(QObject):
    def eventFilter(self, obj: QObject, evt: QEvent) -> bool:
        if evt.type() == QEvent.Type.Show and isinstance(obj, QWidget):
            if isinstance(obj, QWebEngineView):
                fit_page(obj)
                if not obj.property("kioku_fit"):
                    # a new page starts at the default zoom
                    obj.setProperty("kioku_fit", True)
                    obj.loadFinished.connect(lambda _ok, web=obj: fit_page(web))
            elif is_window(obj):
                QTimer.singleShot(0, lambda w=obj: fit_window(w))
        return False


def refit() -> None:
    for w in QApplication.allWidgets():
        if isinstance(w, QWebEngineView):
            fit_page(w)
        elif w.isVisible() and is_window(w):
            fit_window(w)


def install() -> None:
    fit = Fit()

    def started(mw: aqt.main.AnkiQt) -> None:
        app = QApplication.instance()
        fit.setParent(app)
        app.installEventFilter(fit)
        follow(QGuiApplication.primaryScreen())
        app.primaryScreenChanged.connect(follow)

    def follow(screen) -> None:  # type: ignore[no-untyped-def]
        screen.availableGeometryChanged.connect(lambda _rect: refit())
        refit()

    aqt.gui_hooks.main_window_did_init.append(lambda: started(aqt.mw))


if __name__ == "__main__":
    install()
    aqt.run()
