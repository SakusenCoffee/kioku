"""Stacking a side panel under Anki's main view on narrow screens.

Add-ons such as AMBOSS put the main view into a QSplitter beside their side
panel; kioku.patches gives such a splitter a MainSplit.
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtWidgets import QSplitter, QToolButton, QWidget


class MainSplit(QObject):
    """Side by side when the splitter is at least NARROW points wide
    (tablets, phones in landscape), with each pane's minimum width capped
    at a third; stacked otherwise (main view above the panel), with a
    button on the handle that expands the panel or splits again."""

    NARROW = 600
    HANDLE = 28

    def __init__(self, splitter: QSplitter) -> None:
        super().__init__(splitter)
        self.splitter = splitter
        self.min_widths: dict[int, int] = {}
        self.handle_width = splitter.handleWidth()
        self.stacked: bool | None = None
        self.expanded = False
        self.button = QToolButton()
        self.button.setAutoRaise(True)
        self.button.clicked.connect(self.toggle_expanded)
        splitter.installEventFilter(self)

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        if event is None:
            return False
        if obj is self.splitter and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.ChildAdded,
        ):
            QTimer.singleShot(0, self.adapt)
        elif event.type() == QEvent.Type.Resize and obj is self.button.parent():
            self.place_button()
        return False

    def panes(self) -> list[QWidget]:
        s = self.splitter
        return [s.widget(i) for i in range(s.count())]

    def adapt(self) -> None:
        s = self.splitter
        if s.count() < 2 or s.width() <= 0:
            return
        for w in self.panes():
            self.min_widths.setdefault(id(w), w.minimumWidth())
        stacked = s.width() < self.NARROW
        for w in self.panes():
            original = self.min_widths[id(w)]
            w.setMinimumWidth(0 if stacked else min(original, s.width() // 3))
        if stacked == self.stacked:
            return
        self.stacked = stacked
        self.expanded = False
        s.setOrientation(
            Qt.Orientation.Vertical if stacked else Qt.Orientation.Horizontal
        )
        s.setHandleWidth(self.HANDLE if stacked else self.handle_width)
        handle = s.handle(s.count() - 1)
        if stacked and handle is not None:
            if self.button.parent() is not handle:
                self.button.setParent(handle)
                handle.installEventFilter(self)
            self.button.show()
            self.place_button()
        else:
            self.button.hide()
        self.split_evenly()

    def split_evenly(self) -> None:
        n = self.splitter.count()
        self.splitter.setSizes([10000] * n)
        self.button.setText("▲")
        self.button.setToolTip("Expand")

    def toggle_expanded(self) -> None:
        self.expanded = not self.expanded
        if self.expanded:
            n = self.splitter.count()
            self.splitter.setSizes([0] * (n - 1) + [10000])
            self.button.setText("▼")
            self.button.setToolTip("Split")
        else:
            self.split_evenly()

    def place_button(self) -> None:
        handle = self.button.parent()
        if handle is None:
            return
        h = handle.height()
        self.button.setFixedSize(h * 3, h)
        self.button.move((handle.width() - h * 3) // 2, 0)
