"""kioku.mainsplit: a side panel beside Anki's main view, as the AMBOSS
add-on makes one (desktop minimum widths 400 and 624 px)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QSplitter, QVBoxLayout, QWidget

from kioku.mainsplit import MainSplit

app = QApplication.instance() or QApplication([])


windows: list[QWidget] = []


def resize(splitter: QSplitter, width: int) -> None:
    splitter.window().setFixedSize(width, 800)
    app.processEvents()


def make(width: int) -> tuple[QSplitter, MainSplit, QWidget, QWidget]:
    # inside a window, as in Anki: a top-level QSplitter sizes itself
    window = QWidget()
    windows.append(window)
    splitter = QSplitter()
    QVBoxLayout(window).addWidget(splitter)
    split = MainSplit(splitter)
    main, panel = QWidget(), QWidget()
    main.setMinimumWidth(400)
    panel.setMinimumWidth(624)
    splitter.addWidget(main)
    splitter.addWidget(panel)
    window.show()
    resize(splitter, width)
    split.adapt()
    return splitter, split, main, panel


def test_phone_stacks_with_expand_button() -> None:
    splitter, split, main, panel = make(430)
    assert splitter.orientation() == Qt.Orientation.Vertical
    assert main.minimumWidth() == panel.minimumWidth() == 0
    assert split.button.isVisible() and split.button.text() == "▲"
    a, b = splitter.sizes()
    assert abs(a - b) <= 1

    split.button.click()
    assert splitter.sizes()[0] == 0 and split.button.text() == "▼"
    split.button.click()
    a, b = splitter.sizes()
    assert abs(a - b) <= 1 and split.button.text() == "▲"


def test_wide_screen_side_by_side_and_back() -> None:
    splitter, split, main, panel = make(900)
    assert splitter.orientation() == Qt.Orientation.Horizontal
    third = splitter.width() // 3
    assert main.minimumWidth() == panel.minimumWidth() == third
    assert not split.button.isVisible()

    resize(splitter, 430)
    split.adapt()
    assert splitter.orientation() == Qt.Orientation.Vertical
    resize(splitter, 1400)
    split.adapt()
    assert splitter.orientation() == Qt.Orientation.Horizontal
    assert (main.minimumWidth(), panel.minimumWidth()) == (400, splitter.width() // 3)
