"""Feasibility probe: Anki's Rust core and PyQt6 inside a browser tab."""

import sys
import time

print("python", sys.version, sys.platform)

t = time.time()
from anki.collection import Collection

col = Collection("/tmp/probe.anki2")
deck = col.decks.id("Web probe")
note = col.new_note(col.models.by_name("Basic"))
note["Front"] = "Does Anki run in the browser?"
note["Back"] = "Its Rust core does."
col.add_note(note, deck)
counts = col.sched.counts()
print(f"anki: {col.card_count()} card(s), due counts {counts}, {time.time() - t:.2f}s")
card = col.get_card(col.find_cards("")[0])
question = card.question()
col.close()
print("anki question html:", question[:80])

from PyQt6.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget

print("qt", QT_VERSION_STR, "pyqt", PYQT_VERSION_STR)
app = QApplication(sys.argv)
w = QWidget()
w.setWindowTitle("Kioku web probe")
layout = QVBoxLayout(w)
label = QLabel(f"<h2>Kioku web probe</h2><p>Python {sys.version.split()[0]} · Qt {QT_VERSION_STR}</p>"
               f"<p>Anki collection: 1 card, due {counts}</p><p>{question}</p>")
label.setWordWrap(True)
layout.addWidget(label)
button = QPushButton("Click me")
clicks = 0


def clicked() -> None:
    global clicks
    clicks += 1
    button.setText(f"Clicked {clicks}×")
    print("clicked", clicks)


button.clicked.connect(clicked)
layout.addWidget(button)

from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox

dialog_button = QPushButton("Nested dialog")


def ask() -> None:
    # Anki uses blocking dialogs (QDialog.exec) in many places
    box = QMessageBox(QMessageBox.Icon.Question, "Kioku", "Keep going?",
                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, w)
    print("dialog: exec start")
    result = box.exec()
    print("dialog: exec returned", QMessageBox.StandardButton(result).name)
    dialog_button.setText(f"Dialog said {QMessageBox.StandardButton(result).name}")


dialog_button.clicked.connect(ask)
layout.addWidget(dialog_button)

bg_button = QPushButton("Background op")
pool = ThreadPoolExecutor(2)


def background() -> None:
    # like Anki's taskman: collection work on a worker thread, result on the GUI thread
    def work() -> str:
        import threading
        col = Collection("/tmp/probe.anki2")
        try:
            return f"{col.card_count()} card(s) on {threading.current_thread().name}"
        finally:
            col.close()

    fut = pool.submit(work)

    def poll() -> None:
        if fut.done():
            print("background:", fut.result())
            bg_button.setText(fut.result())
        else:
            QTimer.singleShot(50, poll)

    poll()


bg_button.clicked.connect(background)
layout.addWidget(bg_button)
w.resize(480, 320)
w.show()
print("probe: window shown")
app.exec()
