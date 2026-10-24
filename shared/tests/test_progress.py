"""kioku.windows: Anki's progress window (sync, Check Media) gets a Cancel
button, so it shows as a small card instead of filling the screen; Cancel
asks the task to stop as the desktop window's close button does."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QProgressBar,
    QVBoxLayout,
)

from kioku.windows import _add_cancel, _is_small_dialog

app = QApplication.instance() or QApplication([])


class ProgressDialog(QDialog):
    """Anki's aqt.progress.ProgressDialog: a label and a bar; closing it
    only sets wantCancel."""

    def __init__(self) -> None:
        super().__init__()
        self.wantCancel = False
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Syncing..."))
        layout.addWidget(QProgressBar())

    def closeEvent(self, evt) -> None:  # type: ignore[no-untyped-def]
        self.wantCancel = True
        evt.ignore()


def test_progress_becomes_a_card_with_cancel() -> None:
    avail = QRect(0, 0, 430, 900)
    dialog = ProgressDialog()
    assert not _is_small_dialog(dialog, avail)
    _add_cancel(dialog)
    assert _is_small_dialog(dialog, avail)
    dialog.show()
    box = dialog.findChild(QDialogButtonBox)
    box.button(QDialogButtonBox.StandardButton.Cancel).click()
    assert dialog.wantCancel
    assert dialog.isVisible()  # stays until the task stops
