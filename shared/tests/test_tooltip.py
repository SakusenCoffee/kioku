"""Anki's tooltip() on a phone: Qt sizes a window to at most 2/3 of the
screen, which cut longer tooltips off (kioku.patches)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import aqt
import aqt.utils
from aqt.qt import QApplication, QWidget

from kioku import patches

app = QApplication.instance() or QApplication([])


class Progress:
    def timer(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        return None


def test_tooltip_fits_the_screen() -> None:
    patches.apply()
    mw = QWidget()
    mw.progress = Progress()  # type: ignore[attr-defined]
    aqt.mw = mw  # type: ignore[assignment]
    try:
        screen = app.primaryScreen().availableGeometry()
        aqt.utils.tooltip("word " * 200, parent=mw)
        label = aqt.utils._tooltipLabel
        assert label.wordWrap()
        assert screen.left() + 8 <= label.x()
        assert label.x() + label.width() <= screen.left() + screen.width() - 8

        aqt.utils.tooltip("short", parent=mw)
        label = aqt.utils._tooltipLabel
        assert not label.wordWrap()
        assert label.width() == label.sizeHint().width()
    finally:
        aqt.utils.closeTooltip()
        aqt.mw = None  # type: ignore[assignment]
