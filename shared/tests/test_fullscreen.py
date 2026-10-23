"""kioku.fullscreen: a swipe to the right asks whether to exit full screen."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import aqt
from aqt.qt import QApplication, QWidget

from kioku import fullscreen

app = QApplication.instance() or QApplication([])


class Content:
    head = ""


class MainWindow(QWidget):
    def __init__(self, full: bool) -> None:
        super().__init__()
        self.fullscreen = full


def test_script_in_pages() -> None:
    content = Content()
    fullscreen._add_swipe(content, object())
    assert fullscreen.COMMAND in content.head


def test_other_messages_pass_through(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(aqt, "mw", MainWindow(True), raising=False)
    assert fullscreen._on_message((False, None), "ans", None) == (False, None)


def test_menu_only_in_full_screen(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    shown: list = []
    monkeypatch.setattr(fullscreen, "_confirm", shown.append)

    monkeypatch.setattr(aqt, "mw", MainWindow(False), raising=False)
    assert fullscreen._on_message((False, None), fullscreen.COMMAND, None) == (True, None)
    assert shown == []

    monkeypatch.setattr(aqt, "mw", MainWindow(True), raising=False)
    fullscreen._on_message((False, None), fullscreen.COMMAND, None)
    assert shown == [aqt.mw]


def test_confirm_exits_or_stays(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    left: list = []
    monkeypatch.setattr(fullscreen, "_exit", left.append)
    mw = MainWindow(True)

    fullscreen._confirm(mw)
    box = mw._kioku_full_screen_box
    fullscreen._confirm(mw)  # a second swipe while it is open
    assert mw._kioku_full_screen_box is box
    box.button(box.StandardButton.Cancel).click()
    assert left == [] and mw._kioku_full_screen_box is None

    fullscreen._confirm(mw)
    box = mw._kioku_full_screen_box
    next(b for b in box.buttons() if b.text() == "Exit Full Screen").click()
    assert left == [mw]
