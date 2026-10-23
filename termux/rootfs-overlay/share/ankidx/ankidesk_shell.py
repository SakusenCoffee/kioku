"""The Kioku desktop: home screen, app launcher, software center and settings.

Looks like Cutefish/Deepin (see ankidesk_theme.py) and is built on the PyQt6
that Anki already needs, so it adds no size. It is the session's main process
(session.sh): it stays below every window, the dock's desktop button minimizes
the windows to show it, and the session ends when it exits ("Power off").
Anki is one of its apps; closing Anki returns here.

Pages (bottom bar in portrait, side rail in landscape):
  Apps      clock, search, Anki, Terminal and every installed desktop app
  Software  recommended apps and every Termux package: install / open / remove
  Settings  wallpaper, touch mode, keyboard, deck import, phone storage, power
  Remote    the remote desktop (ankidesk_remote.py), opened from Settings
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
import traceback
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtCore import (  # noqa: E402
    QFileSystemWatcher, QObject, QRect, QRectF, QSize, QSocketNotifier, Qt, QThread, QTimer, pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPainterPath, QPixmap  # noqa: E402
from PyQt6.QtNetwork import QLocalServer, QLocalSocket  # noqa: E402
from PyQt6.QtWidgets import (  # noqa: E402
    QAbstractButton,
    QApplication,
    QBoxLayout,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import ankidesk_keyboard as keyboard  # noqa: E402
import ankidesk_menu as menu  # noqa: E402
import ankidesk_pkg as pkg  # noqa: E402
import ankidesk_remote as remote  # noqa: E402
import ankidesk_theme as theme  # noqa: E402
import ankidesk_touch as touch  # noqa: E402
import ankidesk_x11 as x11  # noqa: E402

# Recommended apps. All use Qt or plain terminals, so they share the libraries
# the runtime already has and stay small.
CATALOG = [
    {"package": "pcmanfm-qt", "name": "Files", "desktop": "pcmanfm-qt", "glyph": "folder",
     "summary": "Browse and manage your files", "size": "10 MB", "extras": [pkg.ICON_THEME_PACKAGE]},
    {"package": "featherpad", "name": "Text Editor", "desktop": "featherpad", "glyph": "edit",
     "summary": "Lightweight text editor", "size": "4 MB"},
    {"package": "qterminal", "name": "QTerminal", "desktop": "qterminal", "glyph": "terminal",
     "summary": "Terminal with tabs", "size": "3 MB"},
    {"package": "falkon", "name": "Web Browser", "desktop": "org.kde.falkon", "glyph": "globe",
     "summary": "Falkon, on the same web engine as Anki", "size": "49 MB"},
    {"package": "lximage-qt", "name": "Image Viewer", "desktop": "lximage-qt", "glyph": "image",
     "summary": "View and convert images", "size": "8 MB", "extras": [pkg.ICON_THEME_PACKAGE]},
    {"package": "lxqt-archiver", "name": "Archives", "desktop": "lxqt-archiver", "glyph": "archive",
     "summary": "Open and create zip, tar and 7z files", "size": "9 MB", "extras": [pkg.ICON_THEME_PACKAGE]},
    {"package": "htop", "name": "System Monitor", "desktop": "htop", "glyph": "activity",
     "summary": "Processes and memory (htop)", "size": "1 MB", "exec": "htop", "terminal": True},
]
CATALOG_BY_DESKTOP = {e["desktop"]: e for e in CATALOG}
CATALOG_PACKAGES = {e["package"] for e in CATALOG}
TERMINAL = "st -f 'DejaVu Sans Mono:pixelsize=34'"
LAUNCH_ANKI = shlex.quote(sys.executable) + " " + shlex.quote(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "launch_anki.py"))
ANKI_KEY = os.environ.get("ANKI_SINGLE_INSTANCE_KEY", "kioku-anki")

# Written by the Android app (PickFileActivity, StorageActivity, AndroidBridge).
PICKED_WALLPAPER = os.path.join(theme.CONFIG_DIR, "picked-wallpaper")
PICKED_DECK = os.path.join(theme.CONFIG_DIR, "picked-deck")
TOUCH_MODE = os.path.join(theme.CONFIG_DIR, "touch-mode")
BATTERY_STATE = os.path.join(theme.CONFIG_DIR, "battery-unrestricted")
REMOTE_PAGE = 3
REMOTE_GRADIENT = ("#93C5FD", "#4F46E5")
# measured on a phone (2026-10-23): xfce4 + xfdesktop + fluent-gtk-theme
XFCE_SIZE, XFCE_DOWNLOAD = "about 245 MB", "40 MB"
STORAGE_STATE = menu.STORAGE_STATE
STORAGE_DIR = menu.STORAGE_DIR

SCALE = 3.0  # physical pixels per dp; set from the screen in main()
SEARCH_LIMIT = 40


def dp(n: float) -> int:
    return round(n * SCALE)


def stylesheet() -> str:
    return f"""
* {{ font-family: "DejaVu Sans"; }}
QWidget {{ background: transparent; color: {theme.TEXT}; font-size: {dp(14)}px; }}
QLabel#clock {{ font-size: {dp(64)}px; font-weight: 200; }}
QLabel#date {{ font-size: {dp(16)}px; color: {theme.TEXT_DIM}; }}
QLabel#title {{ font-size: {dp(24)}px; font-weight: bold; }}
QLabel#subtitle {{ font-size: {dp(13)}px; color: {theme.TEXT_DIM}; }}
QLabel#section {{ font-size: {dp(12)}px; font-weight: bold; color: {theme.TEXT_DIM}; padding-left: {dp(6)}px; }}
QLabel#name {{ font-size: {dp(15)}px; font-weight: bold; }}
QLabel#dim {{ font-size: {dp(12)}px; color: {theme.TEXT_DIM}; }}
QLabel#ok {{ font-size: {dp(12)}px; color: {theme.SUCCESS}; font-weight: bold; }}
QLabel#empty {{ font-size: {dp(15)}px; color: {theme.TEXT_DIM}; }}
QFrame#searchbox {{ background: {theme.CARD}; border: 1px solid {theme.BORDER}; border-radius: {dp(16)}px; }}
QFrame#field {{ background: {theme.SURFACE}; border: 1px solid {theme.SURFACE_BORDER}; border-radius: {dp(16)}px; }}
QLineEdit#search {{
    border: none; padding: {dp(10)}px 0; font-size: {dp(16)}px; selection-background-color: {theme.ACCENT};
}}
QFrame#card {{ background: {theme.SURFACE}; border: 1px solid {theme.SURFACE_BORDER}; border-radius: {dp(20)}px; }}
QFrame#sheet {{ background: {theme.SURFACE_RAISED}; border: 1px solid {theme.SURFACE_BORDER}; border-radius: {dp(26)}px; }}
QFrame#nav {{ background: {theme.BACKGROUND}; border: 1px solid {theme.SURFACE_BORDER}; border-radius: {dp(30)}px; }}
QFrame#line {{ background: {theme.SURFACE_BORDER}; max-height: 1px; min-height: 1px; border: none; }}
QToolButton#clear {{ border: none; border-radius: {dp(18)}px; }}
QToolButton#clear:pressed {{ background: {theme.SURFACE_PRESSED}; }}
QToolButton#navbtn {{
    border: none; border-radius: {dp(24)}px; padding: {dp(6)}px {dp(4)}px;
    font-size: {dp(12)}px; color: {theme.TEXT_DIM};
}}
QToolButton#navbtn:checked {{ background: rgba(46, 139, 255, 0.22); color: white; font-weight: bold; }}
QPushButton {{
    background: {theme.SURFACE_PRESSED}; border: none; border-radius: {dp(14)}px;
    padding: {dp(7)}px {dp(14)}px; font-size: {dp(14)}px; font-weight: bold; min-height: {dp(18)}px;
}}
QPushButton:pressed {{ background: #3A4770; }}
QPushButton:disabled {{ color: {theme.TEXT_DIM}; }}
QPushButton#primary {{ background: {theme.ACCENT}; color: white; }}
QPushButton#primary:pressed {{ background: {theme.ACCENT_PRESSED}; }}
QPushButton#primary:disabled {{ background: {theme.SURFACE_PRESSED}; color: {theme.TEXT_DIM}; }}
QPushButton#danger {{ background: {theme.DANGER}; color: white; }}
QToolButton#thumb {{
    border: {dp(2)}px solid transparent; border-radius: {dp(16)}px; padding: {dp(3)}px;
    font-size: {dp(12)}px; color: {theme.TEXT_DIM};
}}
QToolButton#thumb:checked {{ border: {dp(2)}px solid {theme.ACCENT}; color: white; font-weight: bold; }}
QLabel#brand {{ font-size: {dp(19)}px; font-weight: bold; }}
QPushButton#round {{
    border-radius: {dp(18)}px; padding: 0; min-width: {dp(36)}px; max-width: {dp(36)}px;
    min-height: {dp(36)}px; max-height: {dp(36)}px;
}}
QProgressBar {{
    background: rgba(255, 255, 255, 0.10); border: none; border-radius: {dp(4)}px;
    max-height: {dp(8)}px; min-height: {dp(8)}px; text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {theme.ACCENT}; border-radius: {dp(4)}px; }}
QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: {dp(4)}px; margin: 0; }}
QScrollBar::handle:vertical {{ background: rgba(255, 255, 255, 0.25); border-radius: {dp(2)}px; min-height: {dp(30)}px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    background: none; height: 0;
}}
"""


def launch(command: str, terminal: bool = False, app: bool = True) -> None:
    """Start `command` detached. Apps get the phone settings of
    theme.app_environment(); Anki (app=False) scales itself."""
    if terminal:
        command = f"{TERMINAL} -e {command}"
    subprocess.Popen(["sh", "-c", command], start_new_session=True,
                     env=theme.app_environment() if app else None,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    return lbl


def pixmap_label(pm: QPixmap) -> QLabel:
    lbl = QLabel()
    lbl.setPixmap(pm)
    lbl.setFixedSize(pm.size())
    return lbl


def card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(dp(8), dp(8), dp(8), dp(8))
    layout.setSpacing(0)
    return frame, layout


def hline() -> QFrame:
    line = QFrame()
    line.setObjectName("line")
    return line


def search_field(placeholder: str, frame_name: str, text: str = "") -> tuple[QFrame, QHBoxLayout, QLineEdit]:
    """A rounded search field with a finger-sized clear button (Qt's own is tiny)."""
    box = QFrame()
    box.setObjectName(frame_name)
    row = QHBoxLayout(box)
    row.setContentsMargins(dp(14), 0, dp(6), 0)
    row.setSpacing(dp(8))
    row.addWidget(pixmap_label(theme.render_svg(theme.glyph_svg("search", theme.TEXT_DIM), dp(20))))
    edit = QLineEdit(text)
    edit.setObjectName("search")
    edit.setPlaceholderText(placeholder)
    # Only a tap focuses it, so the keyboard never opens by itself.
    edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
    row.addWidget(edit, 1)
    clear = QToolButton()
    clear.setObjectName("clear")
    clear.setIcon(theme.line_icon("close", dp(18), theme.TEXT_DIM))
    clear.setIconSize(QSize(dp(18), dp(18)))
    clear.setFixedSize(dp(36), dp(36))
    clear.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    clear.setVisible(bool(text))
    def on_clear() -> None:
        typing = edit.hasFocus()
        edit.clear()
        if typing and keyboard.KEYBOARD:  # keep typing: the tap on the button closed the keyboard
            keyboard.KEYBOARD.want(True, force=True)

    clear.clicked.connect(on_clear)
    edit.textChanged.connect(lambda t: clear.setVisible(bool(t)))
    row.addWidget(clear)
    return box, row, edit


def no_focus(root: QWidget) -> None:
    """Buttons never take keyboard focus: on a touch screen a tapped button
    would otherwise keep it, and focus moving on when a page is hidden would
    land in a text field and open the keyboard."""
    for b in root.findChildren(QAbstractButton):
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)


def read_state(path: str, default: str = "") -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return default


class Worker(QObject):
    progress = pyqtSignal(str, float)
    finished = pyqtSignal(object, str)  # result, error message (empty on success)

    def __init__(self, fn: Callable) -> None:
        super().__init__()
        self.fn = fn

    def run(self) -> None:
        try:
            result = self.fn(lambda text, f: self.progress.emit(text, f))
            self.finished.emit(result, "")
        except Exception as e:  # noqa: BLE001 - shown to the user
            traceback.print_exc()
            self.finished.emit(None, str(e) or type(e).__name__)


class Tile(QAbstractButton):
    """An app on the home screen: icon over a name of up to two lines."""

    ICON = 60

    def __init__(self, pm: QPixmap, text: str, action) -> None:
        super().__init__()
        self.pm = pm
        self.setText(text)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        font = QFont(self.font())
        font.setPixelSize(dp(13))
        self.setFont(font)
        self.setFixedHeight(dp(self.ICON + 54))
        self.setMinimumWidth(dp(72))
        self.clicked.connect(action)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return QSize(dp(84), dp(self.ICON + 54))

    def _lines(self, fm: QFontMetrics, width: int) -> list[str]:
        words, first = self.text().split(), ""
        while words and fm.horizontalAdvance((first + " " + words[0]).strip()) <= width:
            first = (first + " " + words.pop(0)).strip()
        if not first:  # one long word
            return [fm.elidedText(self.text(), Qt.TextElideMode.ElideRight, width)]
        rest = " ".join(words)
        return [first] + ([fm.elidedText(rest, Qt.TextElideMode.ElideRight, width)] if rest else [])

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.isDown():
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), dp(18), dp(18))
            p.fillPath(path, QColor(255, 255, 255, 46))
        p.drawPixmap((self.width() - self.pm.width()) // 2, dp(6), self.pm)
        fm = QFontMetrics(self.font())
        p.setFont(self.font())
        y = dp(6) + self.pm.height() + dp(6)
        for line in self._lines(fm, self.width() - dp(6)):
            rect = QRect(0, y, self.width(), fm.height())
            # A soft shadow keeps the name readable on bright wallpapers.
            p.setPen(QColor(0, 0, 0, 150))
            p.drawText(rect.translated(0, max(1, dp(0.7))), Qt.AlignmentFlag.AlignHCenter, line)
            p.setPen(QColor(theme.TEXT))
            p.drawText(rect, Qt.AlignmentFlag.AlignHCenter, line)
            y += fm.height()


class Row(QFrame):
    """A tappable settings row that grows with its (wrapped) text, unlike a
    QPushButton, whose size ignores its layout."""

    clicked = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.down = False

    def _set_down(self, down: bool) -> None:
        self.down = down
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton:
            self._set_down(True)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        # A drag-scroll cancels the press with a release far outside.
        was = self.down
        self._set_down(False)
        if was and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self.down:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), dp(16), dp(16))
            p.fillPath(path, QColor(theme.SURFACE_PRESSED))


class Sheet(QWidget):
    """A bottom sheet over the dimmed shell, instead of separate dialog windows."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.on_ok = self.on_cancel = None
        self.panel = QFrame()
        self.panel.setObjectName("sheet")
        self.panel.setMaximumWidth(dp(520))
        box = QVBoxLayout(self.panel)
        box.setContentsMargins(dp(22), dp(22), dp(22), dp(18))
        box.setSpacing(dp(10))
        head = QHBoxLayout()
        head.setSpacing(dp(14))
        self.icon = QLabel()
        head.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(dp(4))
        self.title = label("", "name", wrap=True)
        self.text = label("", "dim", wrap=True)
        texts.addWidget(self.title)
        texts.addWidget(self.text)
        head.addLayout(texts, 1)
        box.addLayout(head)
        box.addSpacing(dp(8))
        buttons = QHBoxLayout()
        buttons.setSpacing(dp(10))
        self.cancel = QPushButton("Cancel")
        self.cancel.clicked.connect(self._cancel)
        self.ok = QPushButton("OK")
        self.ok.clicked.connect(self._accept)
        buttons.addWidget(self.cancel, 1)
        buttons.addWidget(self.ok, 1)
        box.addLayout(buttons)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(dp(12), dp(12), dp(12), dp(12))
        outer.addStretch(1)
        outer.addWidget(self.panel, 0, Qt.AlignmentFlag.AlignHCenter)
        no_focus(self)
        self.hide()

    def ask(self, icon: QPixmap, title: str, text: str, ok: str, on_ok=None, kind: str = "primary",
            cancel: str = "Cancel", on_cancel=None) -> None:
        self.icon.setPixmap(icon)
        self.title.setText(title)
        self.text.setText(text)
        self.ok.setText(ok)
        self.ok.setEnabled(True)
        self.ok.setObjectName(kind)
        self.ok.style().unpolish(self.ok)
        self.ok.style().polish(self.ok)
        self.cancel.setText(cancel)
        self.cancel.setVisible(on_ok is not None)
        self.on_ok, self.on_cancel = on_ok, on_cancel
        self.panel.setMinimumWidth(min(dp(520), self.parentWidget().width() - dp(24)))
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()

    def close_sheet(self) -> None:
        self.on_ok = self.on_cancel = None
        self.hide()

    def _accept(self) -> None:
        cb = self.on_ok
        self.close_sheet()
        if cb:
            cb()

    def _cancel(self) -> None:
        cb = self.on_cancel
        self.close_sheet()
        if cb:
            cb()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        QPainter(self).fillRect(self.rect(), QColor(0, 0, 0, 150))

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if not self.panel.geometry().contains(event.position().toPoint()):
            self._cancel()


class Shell(QWidget):
    resized = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Apps")
        # No title bar: the shell is the phone's home screen, above the dock.
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet(stylesheet())
        self.workers: set[tuple[QThread, Worker]] = set()
        self.busy: str | None = None  # package being installed or removed
        self._wallpaper: QPixmap | None = None
        self.tiles: list[tuple[str, Tile]] = []
        self.columns = 4
        self.landscape = False
        self.pkg_index: dict[str, dict[str, str]] | None = None
        self.pkg_loading = False
        self.base_packages = pkg.base_packages()  # part of the runtime

        self.pages = QStackedWidget()
        self.home = QWidget()
        self.software = QWidget()
        self.settings = QWidget()
        self.remote_page = QWidget()
        self.remote_busy = False
        for page in (self.home, self.software, self.settings, self.remote_page):
            self.pages.addWidget(self._scroll(page))

        self.layout_box = QBoxLayout(QBoxLayout.Direction.TopToBottom, self)
        self.layout_box.setContentsMargins(0, 0, 0, dp(10))
        self.layout_box.setSpacing(dp(8))
        self.layout_box.addWidget(self.pages, 1)
        self.nav = self._build_nav()
        self.layout_box.addWidget(self.nav, 0, Qt.AlignmentFlag.AlignCenter)

        self.sheet = Sheet(self)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(250)
        self.search_timer.timeout.connect(self._show_packages)
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._tick)
        self.clock_timer.start(10_000)
        self._build_settings()
        self.reload()
        self.show_page(0)

    # --- frame ----------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        p = QPainter(self)
        if self.pages.currentIndex() != 0:
            # Software and Settings sit on a solid background, not the wallpaper.
            p.fillRect(self.rect(), QColor(theme.BACKGROUND))
            return
        if self._wallpaper is None or self._wallpaper.size() != self.size():
            self._wallpaper = theme.wallpaper(self.width(), self.height(), dim=0.25)
        p.drawPixmap(0, 0, self._wallpaper)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._apply_orientation(self.width() > self.height())
        width = self.width() - (dp(120) if self.landscape else 0) - dp(28)
        columns = max(4, min(8, width // dp(86)))
        if columns != self.columns:
            self.columns = columns
            self._layout_tiles()
        if self.sheet.isVisible():
            self.sheet.setGeometry(self.rect())
        super().resizeEvent(event)
        self.resized.emit()

    def _apply_orientation(self, landscape: bool) -> None:
        """Bottom bar in portrait; in landscape a rail on the left, so the
        short screen height is left to the pages."""
        if landscape == self.landscape:
            return
        self.landscape = landscape
        D = QBoxLayout.Direction
        self.layout_box.setDirection(D.RightToLeft if landscape else D.TopToBottom)
        if landscape:
            self.layout_box.setContentsMargins(dp(10), dp(10), 0, dp(10))
        else:
            self.layout_box.setContentsMargins(0, 0, 0, dp(10))
        self.nav_row.setDirection(D.TopToBottom if landscape else D.LeftToRight)
        if hasattr(self, "wallpaper_grid"):
            self._build_wallpapers()

    @staticmethod
    def _scroll(w: QWidget) -> QScrollArea:
        s = QScrollArea()
        s.setWidgetResizable(True)
        s.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        s.setWidget(w)
        # The page takes the viewport's width, never its content's minimum.
        w.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        s.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        s.viewport().setAutoFillBackground(False)
        w.setAutoFillBackground(False)
        return s

    @staticmethod
    def _clear(w: QWidget) -> QVBoxLayout:
        old = w.layout()
        if old is not None:
            QWidget().setLayout(old)  # reparent to drop the old layout and its widgets
        layout = QVBoxLayout(w)
        layout.setContentsMargins(dp(18), dp(28), dp(18), dp(12))
        layout.setSpacing(dp(10))
        # Pages are as wide as the screen: the content wraps or shrinks
        # instead of making the page scroll sideways.
        layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetNoConstraint)
        return layout

    def _header(self, layout: QVBoxLayout, title: str, subtitle: str) -> None:
        layout.addWidget(label(title, "title"))
        layout.addWidget(label(subtitle, "subtitle", wrap=True))
        layout.addSpacing(dp(10))

    def _build_nav(self) -> QFrame:
        nav = QFrame()
        nav.setObjectName("nav")
        self.nav_row = QBoxLayout(QBoxLayout.Direction.LeftToRight, nav)
        self.nav_row.setContentsMargins(dp(6), dp(6), dp(6), dp(6))
        self.nav_row.setSpacing(dp(4))
        self.nav_buttons = []
        for i, (text, glyph) in enumerate((("Apps", "apps"), ("Software", "store"), ("Settings", "settings"))):
            b = QToolButton()
            b.setObjectName("navbtn")
            b.setText(text)
            b.setIcon(theme.line_icon(glyph, dp(24)))
            b.setIconSize(QSize(dp(24), dp(24)))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            b.setCheckable(True)
            b.setFixedSize(dp(96), dp(58))
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _=False, i=i: self.show_page(i))
            self.nav_row.addWidget(b)
            self.nav_buttons.append(b)
        return nav

    def show_page(self, i: int) -> None:
        if i == 2 and self.pages.currentIndex() != 2:
            self._build_settings()  # touch mode or storage may have changed
        if i == REMOTE_PAGE:
            # the battery setting may have changed in Android's settings
            menu.android_request("ankidesk:battery/state")
            self._build_remote()
        self.pages.setCurrentIndex(i)
        for j, b in enumerate(self.nav_buttons):
            b.setChecked(i == j)
        self.update()

    def reload(self) -> None:
        self._build_home()
        self._build_software()

    # --- apps -----------------------------------------------------------------

    def _app_pixmap(self, app: menu.App) -> QPixmap:
        size = dp(Tile.ICON)
        entry = CATALOG_BY_DESKTOP.get(app.id)
        if entry:
            return theme.app_tile(entry["glyph"], size)
        if app.icon:
            pm = theme.image_tile(app.icon, size)
            if pm is not None:
                return pm
        return theme.letter_tile(app.name, size)

    def _build_home(self) -> None:
        layout = self._clear(self.home)
        layout.setContentsMargins(dp(14), dp(36), dp(14), dp(12))
        self.clock = label("", "clock")
        self.date = label("", "date")
        for w in (self.clock, self.date):
            w.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            layout.addWidget(w)
        self._tick()
        layout.addSpacing(dp(18))
        if remote.is_active():
            frame, box = card()
            box.addWidget(self._row("monitor", REMOTE_GRADIENT, "Remote session active",
                                    lambda: self.show_page(REMOTE_PAGE),
                                    "Anki is on the remote screen. Tap to see the address or turn it off."))
            layout.addWidget(frame)
            layout.addSpacing(dp(14))

        box, _, self.search = search_field("Search apps", "searchbox")
        self.search.textChanged.connect(self._layout_tiles)
        self.search.returnPressed.connect(self._launch_first)
        outer = QHBoxLayout()
        outer.setContentsMargins(dp(6), 0, dp(6), 0)
        outer.addWidget(box)
        layout.addLayout(outer)
        layout.addSpacing(dp(14))

        size = dp(Tile.ICON)
        self.tiles = [
            ("Anki", Tile(theme.app_tile("anki", size), "Anki", self._open_anki)),
            ("Terminal", Tile(theme.app_tile("terminal", size), "Terminal", lambda: self._run(TERMINAL))),
        ]
        apps = menu.apps()
        for app in apps:
            name = CATALOG_BY_DESKTOP[app.id]["name"] if app.id in CATALOG_BY_DESKTOP else app.name
            self.tiles.append((name, Tile(self._app_pixmap(app), name,
                                          lambda _=False, a=app: self._launch_app(a))))
        # Installed catalog apps whose package has no .desktop file.
        have = {a.id for a in apps}
        installed = pkg.installed()
        for e in CATALOG:
            if e["package"] in installed and e["desktop"] not in have:
                self.tiles.append((e["name"], Tile(theme.app_tile(e["glyph"], size), e["name"],
                                                   lambda _=False, e=e: self._open(e))))
        self.tiles.append(("Get apps", Tile(theme.app_tile("plus", size), "Get apps",
                                            lambda: self.show_page(1))))
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(dp(4))
        self.grid.setVerticalSpacing(dp(10))
        self.no_match = label("No apps found", "empty")
        self.no_match.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.grid_host)
        layout.addWidget(self.no_match)
        layout.addStretch(1)
        self._layout_tiles()

    def _matches(self) -> list[tuple[str, Tile]]:
        q = self.search.text().strip().lower()
        return [(n, t) for n, t in self.tiles if q in n.lower()]

    def _layout_tiles(self) -> None:
        if not hasattr(self, "grid"):
            return
        for _, t in self.tiles:
            self.grid.removeWidget(t)
            t.hide()
        shown = self._matches()
        for i, (_, t) in enumerate(shown):
            self.grid.addWidget(t, i // self.columns, i % self.columns)
            t.show()
        for c in range(8):
            self.grid.setColumnStretch(c, 1 if c < self.columns else 0)
        self.no_match.setVisible(not shown)

    def _launch_first(self) -> None:
        shown = self._matches()
        if shown:
            shown[0][1].click()

    def _tick(self) -> None:
        if hasattr(self, "clock"):
            self.clock.setText(time.strftime("%H:%M"))
            self.date.setText(time.strftime("%A, %d %B"))

    # --- software -------------------------------------------------------------

    def _build_software(self) -> None:
        query = self.pkg_search.text() if hasattr(self, "pkg_search") else ""
        layout = self._clear(self.software)
        self._header(layout, "Software", "Apps and tools from the Termux repositories, "
                                         "downloaded when you install them.")

        self.progress_card, box = card()
        box.setContentsMargins(dp(16), dp(14), dp(16), dp(16))
        box.setSpacing(dp(10))
        self.progress_label = label("", "dim", wrap=True)
        self.progress_bar = QProgressBar()
        box.addWidget(self.progress_label)
        box.addWidget(self.progress_bar)
        self.progress_card.setVisible(self.busy is not None)
        layout.addWidget(self.progress_card)

        # Search over every package in the repositories.
        field, row, self.pkg_search = search_field("Search all Termux packages", "field", query)
        self.pkg_search.textChanged.connect(lambda _: self.search_timer.start())
        refresh = QPushButton()
        refresh.setObjectName("round")
        refresh.setIcon(theme.line_icon("refresh", dp(18)))
        refresh.setIconSize(QSize(dp(18), dp(18)))
        refresh.clicked.connect(self._refresh_packages)
        row.addWidget(refresh)
        layout.addWidget(field)
        self.pkg_results = QVBoxLayout()
        self.pkg_results.setSpacing(dp(10))
        layout.addLayout(self.pkg_results)

        layout.addSpacing(dp(6))
        layout.addWidget(label("RECOMMENDED", "section"))
        installed = pkg.installed()
        for entry in CATALOG:
            layout.addWidget(self._package_card(entry, entry["package"] in installed))
        layout.addStretch(1)
        no_focus(self.software)
        self._show_packages()

    def _package_card(self, entry: dict, is_installed: bool, version: str = "") -> QFrame:
        frame, box = card()
        row = QHBoxLayout()
        row.setContentsMargins(dp(8), dp(8), dp(8), dp(8))
        row.setSpacing(dp(14))
        row.addWidget(pixmap_label(theme.app_tile(entry["glyph"], dp(56))), 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(dp(2))
        texts.addWidget(label(entry["name"], "name", wrap=True))
        if entry.get("summary"):
            texts.addWidget(label(entry["summary"], "dim", wrap=True))
        if entry.get("builtin"):
            texts.addWidget(label("Part of Kioku", "ok"))
        elif is_installed:
            texts.addWidget(label("Installed", "ok"))
        else:
            texts.addWidget(label("  ·  ".join(x for x in (version, entry.get("size", "")) if x), "dim"))
        row.addLayout(texts, 1)
        buttons = QVBoxLayout() if self.width() < dp(420) else QHBoxLayout()
        buttons.setSpacing(dp(8))
        if is_installed:
            open_b = QPushButton("Open")
            open_b.setObjectName("primary")
            open_b.clicked.connect(lambda _=False, e=entry: self._open(e))
            remove_b = QPushButton()
            remove_b.setObjectName("round")
            remove_b.setIcon(theme.line_icon("trash", dp(20)))
            remove_b.setIconSize(QSize(dp(20), dp(20)))
            remove_b.clicked.connect(lambda _=False, e=entry: self._confirm("remove", e))
            buttons.addWidget(open_b)
            buttons.addWidget(remove_b, 0, Qt.AlignmentFlag.AlignRight)
        elif not entry.get("builtin"):
            get_b = QPushButton(" Get")
            get_b.setObjectName("primary")
            get_b.setIcon(theme.line_icon("download", dp(18), "#FFFFFF"))
            get_b.setIconSize(QSize(dp(18), dp(18)))
            get_b.clicked.connect(lambda _=False, e=entry: self._confirm("install", e))
            buttons.addWidget(get_b)
        buttons.addStretch(1)
        row.addLayout(buttons)
        box.addLayout(row)
        for b in frame.findChildren(QPushButton):
            b.setEnabled(self.busy is None)
        return frame

    def _package_entry(self, name: str) -> dict:
        fields = (self.pkg_index or {}).get(name, {})
        size = int(fields.get("Installed-Size", 0) or 0) * 1024
        return {"package": name, "name": name, "glyph": "package",
                "summary": fields.get("Description", ""),
                "size": f"{size / 2**20:.1f} MB" if size else "",
                "builtin": name in self.base_packages}

    def _show_packages(self) -> None:
        """Fill the results under the search field: matches for the query, or
        the packages the user installed besides the recommended apps."""
        layout = self.pkg_results
        while layout.count():
            w = layout.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        query = self.pkg_search.text().strip()
        installed = pkg.installed()
        if not query:
            mine = sorted(n for n, s in installed.items() if not s.get("auto") and n not in CATALOG_PACKAGES)
            if mine:
                layout.addWidget(label("INSTALLED BY YOU", "section"))
                for n in mine:
                    layout.addWidget(self._package_card(self._package_entry(n), True, installed[n]["version"]))
            return
        if self.pkg_index is None:
            layout.addWidget(label("Loading the package list…" if self.pkg_loading else
                                   "The package list could not be loaded. Tap ⟳ to try again.", "empty", wrap=True))
            if not self.pkg_loading:
                self._load_packages()
            return
        names, total = pkg.search(query, self.pkg_index, SEARCH_LIMIT)
        if not names:
            layout.addWidget(label(f"No package matches “{query}”.", "empty", wrap=True))
        for n in names:
            layout.addWidget(self._package_card(self._package_entry(n), n in installed,
                                                self.pkg_index[n].get("Version", "")))
        if total > len(names):
            layout.addWidget(label(f"{len(names)} of {total} matches shown. Type more to narrow it down.",
                                   "dim", wrap=True))
        no_focus(self.software)

    def _load_packages(self, refresh: bool = False) -> None:
        self.pkg_loading = True

        def load(progress):
            if refresh:
                pkg.update(progress)
            return pkg.index(progress)

        def done(result, error: str) -> None:
            self.pkg_loading = False
            self.pkg_index = result
            if error:
                print("package list:", error, file=sys.stderr)
            self._show_packages()

        self._run_async(load, done)

    def _refresh_packages(self) -> None:
        if not self.pkg_loading:
            self.pkg_index = None
            self._load_packages(refresh=True)
            self._show_packages()

    # --- settings -------------------------------------------------------------

    def _row(self, glyph: str, gradient: tuple[str, str], text: str, action, detail: str = "",
             checked: bool | None = None) -> Row:
        """A settings row. `checked` makes it one choice of a group (radio mark),
        `detail` is shown dimmed under the text."""
        b = Row()
        row = QHBoxLayout(b)
        row.setContentsMargins(dp(10), dp(8), dp(10), dp(8))
        row.setSpacing(dp(14))
        texts = QWidget()
        col = QVBoxLayout(texts)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(dp(2))
        col.addWidget(label(text, wrap=True))
        if detail:
            col.addWidget(label(detail, "dim", wrap=True))
        if checked is None:
            end = theme.render_svg(theme.glyph_svg("chevron", theme.TEXT_DIM), dp(20))
        else:
            end = theme.render_svg(theme.glyph_svg("check", theme.ACCENT if checked else "none", 3), dp(22))
        parts = ((pixmap_label(theme.app_tile(glyph, dp(38), gradient)), 0), (texts, 1), (pixmap_label(end), 0))
        for w, stretch in parts:
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            for c in w.findChildren(QWidget):
                c.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            row.addWidget(w, stretch)
        b.setMinimumHeight(dp(58))
        if isinstance(action, str):
            b.clicked.connect(lambda: menu.android_request(action))
        else:
            b.clicked.connect(action)
        return b

    def _group(self, layout: QVBoxLayout, title: str, rows: list[QWidget]) -> None:
        layout.addWidget(label(title, "section"))
        frame, box = card()
        for i, r in enumerate(rows):
            if i:
                box.addWidget(hline())
            box.addWidget(r)
        layout.addWidget(frame)
        layout.addSpacing(dp(12))

    def _build_settings(self) -> None:
        area = self.pages.widget(2)
        scroll = area.verticalScrollBar().value() if area else 0
        layout = self._clear(self.settings)
        self._header(layout, "Settings", f"Personalize {theme.DISTRO} and set up touch and keyboard.")
        layout.addWidget(label("WALLPAPER", "section"))
        frame, box = card()
        box.setContentsMargins(dp(10), dp(12), dp(10), dp(10))
        self.wallpaper_grid = QGridLayout()
        self.wallpaper_grid.setSpacing(dp(6))
        box.addLayout(self.wallpaper_grid)
        box.addSpacing(dp(8))
        pick = QHBoxLayout()
        pick.setSpacing(dp(8))
        for text, glyph, fn in (("Gallery", "image", lambda: menu.android_request("ankidesk:pick-wallpaper")),
                                ("Files", "folder", self._pick_wallpaper_file)):
            b = QPushButton("  " + text)
            b.setIcon(theme.line_icon(glyph, dp(18)))
            b.setIconSize(QSize(dp(18), dp(18)))
            b.clicked.connect(fn)
            pick.addWidget(b, 1)
        box.addLayout(pick)
        layout.addWidget(frame)
        layout.addSpacing(dp(12))
        self._build_wallpapers()

        trackpad = read_state(TOUCH_MODE, "touch") == "trackpad"
        self._group(layout, "TOUCH AND KEYBOARD", [
            self._row("pointer", ("#4FB3FF", "#1C6FE8"), "Touch screen", self._set_touch_mode("touch"),
                      "Tap to click, swipe to scroll", checked=not trackpad),
            self._row("touchpad", ("#A78BFA", "#6D28D9"), "Mouse pad", self._set_touch_mode("trackpad"),
                      "Move a pointer like a laptop; scroll with two fingers", checked=trackpad),
            self._row("keyboard", ("#2DD4BF", "#0F8F87"), "Show or hide keyboard", "ankidesk:keyboard/toggle"),
        ])
        storage = menu.storage_on()
        self._group(layout, "ANKI AND FILES", [
            self._row("upload", ("#6FC3FF", "#2457E6"), "Import a deck from the phone", self._import_from_phone,
                      "An .apkg or .colpkg file, e.g. from Downloads"),
            self._row("lock", ("#86EFAC", "#16A34A"), "Phone storage",
                      self._confirm_storage_off if storage else "ankidesk:storage",
                      "On: your phone's folders are in Home › storage" if storage else
                      "Off: let the Files app and Anki open your phone's folders"),
            self._row("folder", ("#7DD3FC", "#0284C7"), "Open Kioku's files in Android", "ankidesk:files"),
        ])
        self._group(layout, "REMOTE DESKTOP", [
            self._row("monitor", REMOTE_GRADIENT, "Remote desktop", lambda: self.show_page(REMOTE_PAGE),
                      "On: Anki is on the remote screen" if remote.is_active() else
                      "Use Anki from a computer, in a web browser or a VNC viewer"),
        ])
        self._group(layout, "DEVICE", [
            self._row("monitor", ("#FDBA74", "#EA580C"), "Display", "ankidesk:display-settings"),
            self._row("drive", ("#CBD5E1", "#64748B"), "Storage and app info", "ankidesk:app-settings"),
            self._row("phone", ("#F9A8D4", "#BE185D"), "Switch to Android", "ankidesk:phone-apps"),
        ])
        self._group(layout, "SYSTEM", [
            self._row("refresh", ("#93C5FD", "#2563EB"), "Restart desktop", self._restart_desktop),
            self._row("power", ("#FCA5A5", "#DC2626"), "Power off", self._confirm_power_off),
        ])

        about, box = card()
        box.setContentsMargins(dp(16), dp(16), dp(16), dp(16))
        row = QHBoxLayout()
        row.setSpacing(dp(14))
        row.addWidget(pixmap_label(theme.render_svg(open(theme.LOGO, encoding="utf-8").read(), dp(56))))
        texts = QVBoxLayout()
        texts.setSpacing(dp(2))
        texts.addWidget(label(f"{theme.DISTRO} {theme.VERSION}", "brand"))
        texts.addWidget(label("Anki desktop on Android. Built on Termux, Qt 6 and JWM.", "dim", wrap=True))
        row.addLayout(texts, 1)
        box.addLayout(row)
        layout.addWidget(about)
        layout.addStretch(1)
        no_focus(self.settings)
        if area:
            # Back to where the user was once the new page has its size.
            self.settings.layout().activate()
            self.settings.resize(self.settings.sizeHint().expandedTo(area.viewport().size()))
            area.verticalScrollBar().setValue(scroll)
            QTimer.singleShot(0, lambda: area.verticalScrollBar().setValue(scroll))

    def _set_touch_mode(self, mode: str):
        def apply() -> None:
            menu.android_request("ankidesk:input/" + mode)
            # Android writes the new mode back to TOUCH_MODE; show it right away.
            try:
                with open(TOUCH_MODE, "w", encoding="utf-8") as fh:
                    fh.write(mode)
            except OSError:
                pass
            self._build_settings()
        return apply

    def _build_wallpapers(self) -> None:
        grid = self.wallpaper_grid
        while grid.count():
            grid.takeAt(0).widget().deleteLater()
        current = theme.current_wallpaper()
        papers = theme.builtin_wallpapers()
        if os.path.exists(theme.CUSTOM_WALLPAPER):
            papers.append(("Yours", theme.CUSTOM_WALLPAPER))
        w, h = dp(88), dp(132)
        columns = 3 if not self.landscape else 6
        for i, (name, path) in enumerate(papers):
            b = QToolButton()
            b.setObjectName("thumb")
            b.setCheckable(True)
            b.setChecked(path == current)
            b.setText(name)
            b.setIcon(QIcon(self._thumbnail(path, w, h)))
            b.setIconSize(QSize(w, h))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _=False, p=path: self._apply_wallpaper(p))
            grid.addWidget(b, i // columns, i % columns, Qt.AlignmentFlag.AlignHCenter)

    @staticmethod
    def _thumbnail(path: str, w: int, h: int) -> QPixmap:
        src = theme.wallpaper(w, h, path=path)
        out = QPixmap(w, h)
        out.fill(Qt.GlobalColor.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, w, h), dp(12), dp(12))
        p.setClipPath(clip)
        p.drawPixmap(0, 0, src)
        p.end()
        return out

    def _apply_wallpaper(self, path: str) -> None:
        theme.set_wallpaper(path)
        self._wallpaper = None
        self._build_wallpapers()
        self.update()

    def _pick_wallpaper_file(self) -> None:
        start = os.path.join(STORAGE_DIR, "pictures")
        dialog = QFileDialog(self, "Choose a wallpaper", start if os.path.isdir(start) else theme.HOME,
                             "Pictures (*.png *.jpg *.jpeg *.webp *.svg *.bmp *.gif)")
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setStyleSheet(f"* {{ background: {theme.SURFACE}; color: {theme.TEXT}; font-size: {dp(15)}px; }}"
                             f"QPushButton {{ background: {theme.ACCENT}; border-radius: {dp(10)}px; "
                             f"padding: {dp(8)}px {dp(16)}px; }}")
        if dialog.exec() and dialog.selectedFiles():
            self._import_wallpaper(dialog.selectedFiles()[0])
        self.showMaximized()

    def _import_wallpaper(self, path: str) -> None:
        try:
            if path.endswith(".svg"):
                self._apply_wallpaper(path)
                return
            screen = self.screen().geometry()
            self._apply_wallpaper(theme.import_wallpaper(path, screen.width(), screen.height()))
        except (OSError, ValueError) as e:
            self.sheet.ask(theme.app_tile("image", dp(52)), "Cannot use this picture", str(e), "OK")

    def on_config_changed(self, _path: str = "") -> None:
        """Files the Android app leaves in ~/.config/kioku."""
        if os.path.exists(PICKED_WALLPAPER):  # picked in Android's gallery
            try:
                self._import_wallpaper(PICKED_WALLPAPER)
            finally:
                os.remove(PICKED_WALLPAPER)
            self.show_page(2)
            self.activateWindow()
        if os.path.exists(PICKED_DECK):  # picked or shared from another app
            path = read_state(PICKED_DECK)
            os.remove(PICKED_DECK)
            if path:
                self._import_into_anki(path)
        if self.pages.currentIndex() == 2:
            self._build_settings()  # touch mode, storage
        elif self.pages.currentIndex() == REMOTE_PAGE and not self.remote_busy:
            self._build_remote()  # the battery setting

    # --- anki and storage -------------------------------------------------------

    def _import_from_phone(self) -> None:
        menu.android_request("ankidesk:pick-deck")

    def _import_into_anki(self, path: str) -> None:
        """Hand a file to Anki, which imports it (its single-instance socket,
        AnkiQt.onAppMsg), or start Anki with it."""
        sock = QLocalSocket()
        sock.connectToServer(ANKI_KEY)
        if sock.waitForConnected(1000):
            sock.write(path.encode())
            sock.waitForBytesWritten(1000)
            sock.disconnectFromServer()
            self._open_anki()
        else:
            launch(f"{LAUNCH_ANKI} {shlex.quote(path)}", app=False)

    def _confirm_storage_off(self) -> None:
        def off() -> None:
            menu.storage_off()
            self._build_settings()

        self.sheet.ask(theme.app_tile("lock", dp(52), ("#86EFAC", "#16A34A")), "Turn off phone storage?",
                       "Home › storage goes away; the files on your phone stay where they are. "
                       "Android's permission stays until you remove it in app info.", "Turn off", off)

    def _ask_storage(self, then: Callable[[], None]) -> None:
        """Before the Files app opens for the first time: offer phone storage."""
        if read_state(STORAGE_STATE) or menu.storage_on():
            then()
            return

        def answer(allow: bool) -> None:
            if allow:
                menu.android_request("ankidesk:storage")
            else:
                with open(STORAGE_STATE, "w", encoding="utf-8") as fh:
                    fh.write("not-now")
            then()

        self.sheet.ask(theme.app_tile("lock", dp(52), ("#86EFAC", "#16A34A")), "Show your phone's files?",
                       "Kioku can put your phone's folders (Downloads, Pictures, Documents…) in "
                       "Home › storage. Android asks you to allow access to all files. "
                       "You can change this later in Settings.",
                       "Allow", lambda: answer(True), cancel="Not now", on_cancel=lambda: answer(False))

    # --- power ----------------------------------------------------------------

    def _restart_desktop(self) -> None:
        theme.write_jwmrc(self.landscape)
        restart_wm()

    def _confirm_power_off(self) -> None:
        self.sheet.ask(theme.app_tile("power", dp(52), ("#FCA5A5", "#DC2626")), "Power off?",
                       "Anki and all apps close; your collection is saved. Open the app again to start.",
                       "Power off", self._power_off, kind="danger")

    def _power_off(self) -> None:
        if remote.is_active():
            # Anki on the remote screen first: the session's end gives it only
            # a few seconds
            def done(result, error: str) -> None:
                if error:
                    self.sheet.ask(theme.app_tile("power", dp(52), ("#FCA5A5", "#DC2626")),
                                   "Couldn't power off", error, "OK")
                else:
                    menu.android_request("ankidesk:remote/off")
                    self._power_off()

            self.show_page(REMOTE_PAGE)
            self._run_remote(remote.end, done)
            return
        # Ask every window to close (Anki saves and syncs on close), then end
        # the session once Anki is gone or after a grace period.
        for w in x11.find(lambda w: w.wm_class != "ankidesk-shell"):
            x11.close_window(w.id)
        deadline = time.monotonic() + 30

        def check() -> None:
            if x11.find(lambda w: w.wm_class.lower() == "anki") and time.monotonic() < deadline:
                QTimer.singleShot(500, check)
            else:
                # not quit(): Qt 6 cancels it when a window refuses to close,
                # and this one always does (closeEvent)
                QApplication.exit(0)

        QTimer.singleShot(500, check)

    # --- remote desktop -------------------------------------------------------

    def _build_remote(self) -> None:
        layout = self._clear(self.remote_page)
        self._header(layout, "Remote desktop",
                     "Anki on a desktop-sized screen, used from a computer: a web browser or a "
                     "VNC viewer. The phone does the work, so keep it charged and connected.")
        self.remote_progress = label("", "dim", wrap=True)
        self.remote_progress.setVisible(self.remote_busy)
        layout.addWidget(self.remote_progress)
        if remote.is_active():
            self._build_remote_active(layout)
        else:
            self._build_remote_off(layout)
        battery = read_state(BATTERY_STATE, "no") == "yes"
        self._group(layout, "PHONE", [
            self._row("power", ("#86EFAC", "#16A34A"), "Run without battery limits", "ankidesk:battery",
                      "Allowed: the session keeps going with the screen off" if battery else
                      "Recommended: else Android may cut the network once the screen is off"),
        ])
        layout.addStretch(1)
        no_focus(self.remote_page)

    def _build_remote_active(self, layout: QVBoxLayout) -> None:
        info = remote.state()
        frame, box = card()
        box.setContentsMargins(dp(16), dp(16), dp(16), dp(16))
        box.setSpacing(dp(6))
        box.addWidget(label("Remote session active", "name"))
        box.addWidget(label(f"Anki is on the remote screen ({info.get('resolution', '')}); it comes "
                            "back here when you turn this off.", "dim", wrap=True))
        for who, address in info.get("addresses", []):
            box.addSpacing(dp(4))
            box.addWidget(label(who, "dim"))
            text = label(address, wrap=True)
            text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            box.addWidget(text)
        box.addSpacing(dp(4))
        box.addWidget(label("Password", "dim"))
        box.addWidget(label(info.get("password", "")))
        box.addSpacing(dp(10))
        off = QPushButton("Turn off")
        off.setObjectName("danger")
        off.setEnabled(not self.remote_busy)
        off.clicked.connect(self._remote_off)
        box.addWidget(off)
        layout.addWidget(frame)
        layout.addSpacing(dp(12))

    def _build_remote_off(self, layout: QVBoxLayout) -> None:
        s = remote.load_settings()
        on = QPushButton("Turn on")
        on.setObjectName("primary")
        on.setEnabled(not self.remote_busy)
        on.clicked.connect(self._confirm_remote_on)
        layout.addWidget(on)
        layout.addSpacing(dp(12))
        self._group(layout, "LISTEN ON", [
            self._row("lock", ("#86EFAC", "#16A34A"), "Tailscale", self._set_remote("listen", remote.TAILSCALE),
                      "Your own devices, from anywhere, encrypted by Tailscale (the Tailscale app "
                      "must be connected)", checked=s.listen == remote.TAILSCALE),
            self._row("globe", ("#FDBA74", "#EA580C"), "All networks", self._set_remote("listen", remote.ALL),
                      "Any device on this Wi-Fi. Not encrypted: only on networks you trust",
                      checked=s.listen == remote.ALL),
            self._row("smartphone", ("#CBD5E1", "#64748B"), "This phone only",
                      self._set_remote("listen", remote.LOCAL),
                      "For a USB connection (adb forward) or testing", checked=s.listen == remote.LOCAL),
        ])
        xfce = remote.xfce_installed()
        desktop = [
            self._row("monitor", REMOTE_GRADIENT, "Simple", self._set_remote("desktop", remote.SIMPLE),
                      "Anki with a taskbar. Nothing to install", checked=s.desktop == remote.SIMPLE),
            self._row("apps", ("#7DD3FC", "#0284C7"), "XFCE", self._choose_xfce,
                      "A full Linux desktop: menu, panel, file manager, terminal" +
                      ("" if xfce else f". Installs {XFCE_SIZE}"), checked=s.desktop == remote.XFCE),
        ]
        if xfce:
            desktop.append(self._row("trash", ("#FCA5A5", "#DC2626"), "Remove XFCE", self._confirm_remove_xfce,
                                     f"Frees about {XFCE_SIZE}"))
        self._group(layout, "DESKTOP", desktop)
        self._group(layout, "SCREEN SIZE", [
            self._row("monitor", REMOTE_GRADIENT, size.replace("x", " × "), self._set_remote("resolution", size),
                      checked=s.resolution == size)
            for size in remote.RESOLUTIONS
        ])
        self._group(layout, "PASSWORD", [
            self._row("lock", ("#A78BFA", "#6D28D9"), s.password, self._new_remote_password,
                      f"Tap for a new one. Ports: {s.vnc_port} (VNC), {s.web_port} (web)"),
        ])

    def _choose_xfce(self) -> None:
        if remote.xfce_installed():
            self._set_remote("desktop", remote.XFCE)()
            return
        self.sheet.ask(theme.app_tile("apps", dp(52), ("#7DD3FC", "#0284C7")), "Install XFCE?",
                       f"A full Linux desktop for the remote screen, with the Fluent theme. It downloads "
                       f"about {XFCE_DOWNLOAD} and uses {XFCE_SIZE} on the phone. The phone keeps its "
                       "own desktop.", "Install", self._install_xfce)

    def _install_xfce(self) -> None:
        def done(result, error: str) -> None:
            if error:
                self.sheet.ask(theme.app_tile("apps", dp(52), ("#7DD3FC", "#0284C7")),
                               "XFCE wasn't installed", error, "OK")
            elif remote.xfce_installed():
                self._set_remote("desktop", remote.XFCE)()
                return
            self._build_remote()

        self._run_remote(remote.install_xfce, done)

    def _confirm_remove_xfce(self) -> None:
        self.sheet.ask(theme.app_tile("trash", dp(52), ("#FCA5A5", "#DC2626")), "Remove XFCE?",
                       f"Frees about {XFCE_SIZE}. The remote screen goes back to the simple desktop; "
                       "XFCE's settings are kept for next time.", "Remove",
                       lambda: self._run_remote(remote.remove_xfce, lambda result, error: self._build_remote()),
                       kind="danger")

    def _set_remote(self, key: str, value):
        def apply() -> None:
            s = remote.load_settings()
            setattr(s, key, value)
            remote.save_settings(s)
            self._build_remote()
        return apply

    def _new_remote_password(self) -> None:
        s = remote.load_settings()
        s.password = remote.new_password()
        remote.save_settings(s)
        self._build_remote()

    def _confirm_remote_on(self) -> None:
        self.sheet.ask(theme.app_tile("monitor", dp(52), REMOTE_GRADIENT), "Turn on the remote desktop?",
                       "Anki closes here (it saves first) and opens on the remote screen. Then open the "
                       "address shown on this page on your computer.", "Turn on", self._remote_on)

    def _remote_on(self) -> None:
        def done(result, error: str) -> None:
            if not error:
                menu.android_request("ankidesk:remote/on")
            self.reload()
            self._build_remote()
            if error:
                self.sheet.ask(theme.app_tile("monitor", dp(52), REMOTE_GRADIENT),
                               "The remote desktop didn't start", error, "OK")

        self._run_remote(remote.start, done)

    def _remote_off(self) -> None:
        def done(result, error: str) -> None:
            if not remote.is_active():
                menu.android_request("ankidesk:remote/off")
            self.reload()
            self._build_remote()
            if error:
                self.sheet.ask(theme.app_tile("monitor", dp(52), REMOTE_GRADIENT),
                               "The remote desktop is still on", error, "OK")

        self._run_remote(remote.stop, done)

    def _run_remote(self, fn: Callable, done: Callable) -> None:
        if self.remote_busy:
            return
        self.remote_busy = True
        self.show_page(REMOTE_PAGE)

        def finished(result, error: str) -> None:
            self.remote_busy = False
            done(result, error)

        def progress(text: str, fraction: float) -> None:
            self.remote_progress.setText(text)
            self.remote_progress.show()

        self._run_async(fn, finished, progress)

    # --- actions --------------------------------------------------------------

    def _run(self, command: str, terminal: bool = False) -> None:
        launch(command, terminal)

    def _launch_app(self, app: menu.App) -> None:
        entry = CATALOG_BY_DESKTOP.get(app.id)
        if entry and entry["package"] == "pcmanfm-qt":
            self._ask_storage(lambda: self._run(app.exec, app.terminal))
        else:
            self._run(app.exec, app.terminal)

    def _open_anki(self) -> None:
        if remote.is_active():
            # Anki is on the remote screen
            self.show_page(REMOTE_PAGE)
            return
        # Switch to Anki's main window if it is open, otherwise start it.
        wins = x11.find(lambda w: w.wm_class.lower() == "anki")
        main = [w for w in wins if w.title.endswith("- Anki")] or wins
        if not (main and x11.activate(main[0].id)):
            launch(LAUNCH_ANKI, app=False)

    def _open(self, entry: dict) -> None:
        """Open an installed package: its desktop app, else its command in a terminal."""
        name = entry["package"]
        files = pkg.installed().get(name, {}).get("files", [])
        desktops = [os.path.basename(f)[:-len(".desktop")] for f in files
                    if f.startswith("share/applications/") and f.endswith(".desktop")]
        for app in menu.apps():
            if app.id == entry.get("desktop") or app.id in desktops:
                self._launch_app(app)
                return
        if "exec" in entry:
            self._run(entry["exec"], entry.get("terminal", False))
            return
        commands = sorted(os.path.basename(f) for f in files if f.startswith("bin/"))
        if name in commands:
            # Run it, then stay in a shell for more.
            script = f"{shlex.quote(name)}; echo; exec sh"
        else:
            hint = (f"{name} is installed. Commands: {' '.join(commands)}" if commands
                    else f"{name} is installed (no commands of its own).")
            script = f"echo {shlex.quote(hint)}; echo; exec sh"
        self._run(f"sh -c {shlex.quote(script)}", terminal=True)

    def _confirm(self, action: str, entry: dict) -> None:
        if self.busy is not None:
            return
        icon = theme.app_tile(entry["glyph"], dp(52))
        if action == "remove":
            self.sheet.ask(icon, f"Remove {entry['name']}?", "You can install it again at any time.",
                           "Remove", lambda: self._start("remove", entry), kind="danger")
            return
        # Size the download in the background; the server can be slow.
        self.sheet.ask(icon, f"Install {entry['name']}?", "Checking download size…", "Install",
                       lambda: self._start("install", entry))
        self.sheet.ok.setEnabled(False)
        note = "" if entry["package"] in CATALOG_PACKAGES else (
            " Setup scripts of packages are not run, so a few command-line tools may need extra steps.")

        def done(result, error: str) -> None:
            if not self.sheet.isVisible() or self.sheet.title.text() != f"Install {entry['name']}?":
                return
            if error:
                self.sheet.ask(icon, "Cannot reach the package server", error, "OK")
                return
            dl, size = result
            self.sheet.text.setText(f"Downloads {dl / 2**20:.1f} MB and uses {size / 2**20:.0f} MB." + note)
            self.sheet.ok.setEnabled(True)

        self._run_async(lambda progress: pkg.download_size([entry["package"]] + entry.get("extras", []),
                                                           pkg.index(max_age=24 * 3600)), done)

    def _start(self, action: str, entry: dict) -> None:
        if self.busy is not None:
            return
        self.busy = entry["package"]
        self._build_software()
        self.progress_label.setText(("Installing " if action == "install" else "Removing ") + entry["name"])
        self.progress_bar.setValue(0)
        extras = entry.get("extras", [])
        fn = (lambda names, progress: pkg.install(names, progress, extras)) if action == "install" else pkg.remove

        def done(result, error: str) -> None:
            self.busy = None
            if error:
                self.sheet.ask(theme.app_tile(entry["glyph"], dp(52)), "Something went wrong", error, "OK")
            elif action == "install":
                files = pkg.installed().get(entry["package"], {}).get("files", [])
                has_app = "desktop" in entry or any(f.startswith("share/applications/") for f in files)
                where = ("Find it in Apps, or open it now." if has_app else
                         "It is a command-line tool: open it in a terminal, or type its name in Terminal.")
                self.sheet.ask(theme.app_tile(entry["glyph"], dp(52)), f"{entry['name']} is installed",
                               where, "Open", lambda: self._open(entry), cancel="Done")
            self.reload()
            self.show_page(1)

        self._run_async(lambda progress: fn([entry["package"]], progress), done, self._on_progress)

    def _run_async(self, fn: Callable, done: Callable, progress: Callable | None = None) -> None:
        """Run fn(progress) on a thread; done(result, error) back on this one."""
        thread = QThread()
        worker = Worker(fn)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        if progress:
            worker.progress.connect(progress)
        job = (thread, worker)
        self.workers.add(job)

        def finished(result, error: str) -> None:
            thread.quit()
            thread.wait()
            self.workers.discard(job)
            done(result, error)

        worker.finished.connect(finished)
        thread.start()

    def _on_progress(self, text: str, fraction: float) -> None:
        self.progress_label.setText(text)
        self.progress_bar.setValue(int(fraction * 100))

    # --- visibility -----------------------------------------------------------

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Back):
            if self.sheet.isVisible():
                self.sheet.close_sheet()
            else:
                self.show_home()
            return
        super().keyPressEvent(event)

    def show_home(self) -> None:
        self.sheet.close_sheet()
        if hasattr(self, "search"):
            self.search.clear()
            self.search.clearFocus()
        self._tick()
        self.show_page(0)
        self.showMaximized()
        x11.ensure_maximized(int(self.winId()))
        self.activateWindow()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        # The desktop is not closed with a gesture or Alt+F4; see "Power off".
        event.ignore()


# Windows that show and hide the keyboard themselves (ankidesk_keyboard.py).
OWN_KEYBOARD = {"anki", "ankidesk-shell"}


def watch_taps(kbd: keyboard.Keyboard) -> None:
    """Keyboard for other apps (terminals, installed apps): after a tap on one
    of their windows, open it if the pointer is a text cursor, else close it."""
    try:
        watcher = x11.TapWatcher()
    except OSError as e:
        print("no tap watcher:", e, file=sys.stderr)
        return

    def check() -> None:
        client = watcher.client_under_pointer()
        if client is None or client.wm_class.lower() in OWN_KEYBOARD:
            return
        kbd.want(watcher.text_cursor(), force=True)

    def on_readable() -> None:
        if watcher.taps():
            # Give the app a moment to update the cursor for the new position.
            QTimer.singleShot(120, check)

    notifier = QSocketNotifier(watcher.fileno(), QSocketNotifier.Type.Read)
    notifier.activated.connect(on_readable)
    kbd.tap_watcher = (watcher, notifier)  # kept alive with the keyboard
    on_readable()


# Apps that turn a finger drag into scrolling themselves (ankidesk_touch.py).
OWN_TOUCH = {"anki", "ankidesk-shell"}


def follow_touch_mode() -> None:
    """In touch-screen mode, give every other app the display's direct touch
    mode while it is the active window. Otherwise a finger drag arrives as a
    held mouse button, so a web browser selects text instead of scrolling; with
    real touch events browsers and GTK/Qt apps scroll with a drag and select
    with a long press, as on a phone."""
    try:
        display = x11.Display()
    except OSError as e:
        print("no touch mode switching:", e, file=sys.stderr)
        return
    state = {"mode": ""}

    def check() -> None:
        if read_state(TOUCH_MODE, "touch") != "touch":
            state["mode"] = ""  # mouse pad: leave it alone
            return
        win = display.active()
        cls = display.wm_class(win).lower() if win else ""
        mode = "direct" if cls and cls not in OWN_TOUCH else "touch"
        if mode != state["mode"]:
            state["mode"] = mode
            menu.android_request("ankidesk:input/" + mode)

    timer = QTimer(QApplication.instance())
    timer.setInterval(300)
    timer.timeout.connect(check)
    timer.start()
    check()


def restart_wm(states: tuple[list[int], list[int]] | None = None) -> None:
    """jwm -restart, keeping maximized and minimized windows so (JWM forgets).
    `states` (x11.window_states()) defaults to the current ones."""
    states = states or x11.window_states()
    subprocess.run(["jwm", "-restart"], check=False)
    # JWM takes a moment to come back; minimize only once the sizes are right.
    for delay in (1000, 2500):
        QTimer.singleShot(delay, lambda: x11.restore_states(*states, minimize=False))
    QTimer.singleShot(3500, lambda: x11.restore_states([], states[1]))


def follow_rotation(shell: Shell) -> None:
    """Move the dock to the side in landscape (theme.write_jwmrc) when the
    phone turns; the shell lays itself out in resizeEvent. Also corrects the
    dock written at session start, before the X screen had the display's size.
    The X screen size is read directly: Qt's screen geometry can lag behind.

    JWM restores minimized windows when the screen size changes, so the
    window states are sampled regularly and the ones from before the turn
    are put back."""
    states = {"last": x11.window_states()}
    sample = QTimer(shell)
    sample.setInterval(1500)
    sample.timeout.connect(lambda: states.update(last=x11.window_states()))
    sample.start()
    timer = QTimer(shell)
    timer.setSingleShot(True)
    timer.setInterval(400)

    def changed() -> None:
        sample.stop()  # keep the states from before the change
        timer.start()

    def check() -> None:
        try:
            width, height = x11.screen_size()
        except OSError:
            width = height = 0
        landscape = width > height
        if width and landscape != theme.jwmrc_landscape():
            theme.write_jwmrc(landscape)
            restart_wm(states["last"])
        # The shell may not have been maximized yet when the states were
        # sampled (the first resize comes right after the session starts).
        for delay in (1200, 2700):
            QTimer.singleShot(delay, lambda: x11.ensure_maximized(int(shell.winId())))
        QTimer.singleShot(2000, sample.start)

    timer.timeout.connect(check)
    QApplication.primaryScreen().geometryChanged.connect(lambda _: changed())
    shell.resized.connect(changed)
    timer.start()


def main() -> int:
    global SCALE
    remote.reset_stale()
    app = QApplication(sys.argv)
    app.setApplicationName("ankidesk-shell")
    screen = app.primaryScreen().geometry()
    SCALE = max(min(screen.width(), screen.height()) / 360, 1.0)
    font = QFont("DejaVu Sans")
    font.setPixelSize(dp(15))
    app.setFont(font)
    shell = Shell()
    kbd = keyboard.install(app)
    watch_taps(kbd)
    filters = (touch.DragScroll(lambda area: isinstance(area, QScrollArea), slop=dp(8), horizontal=False),
               touch.FitToScreen(skip=lambda w: w is shell))
    for f in filters:
        app.installEventFilter(f)
    follow_rotation(shell)
    follow_touch_mode()
    os.makedirs(theme.CONFIG_DIR, exist_ok=True)
    theme.write_app_settings()
    watcher = QFileSystemWatcher([theme.CONFIG_DIR])
    watcher.directoryChanged.connect(shell.on_config_changed)

    server = QLocalServer()
    QLocalServer.removeServer(menu.SHELL_SOCKET)
    if not server.listen(menu.SHELL_SOCKET):
        print("cannot listen on", menu.SHELL_SOCKET, file=sys.stderr)
        return 1

    def on_connection() -> None:
        conn = server.nextPendingConnection()

        def on_ready() -> None:
            for line in bytes(conn.readAll()).decode().split():
                if line in ("show", "toggle"):
                    shell.show_home()
                elif line == "reload":
                    shell.reload()

        conn.readyRead.connect(on_ready)

    server.newConnection.connect(on_connection)
    shell.show_home()
    # A deck shared from another app while Kioku was not running.
    QTimer.singleShot(3000, shell.on_config_changed)
    ready = os.environ.get("ANKIDX_READY_FILE")
    if ready:
        # The desktop is up: the Android app swaps its splash for the display.
        QTimer.singleShot(300, lambda: open(ready, "w").close())
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
