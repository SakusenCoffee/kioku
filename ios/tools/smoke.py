# Quick crash sweep inside the running app (sent by smoke.sh through devcmd):
# opens Anki's windows one after another, studies a card, switches profile
# and goes back, closing each window the way Back does. Every step logs
# "SWEEP <n> <name>: ..." to kioku.log first, so a crash shows where it
# happened; "SWEEP done" at the end.
import sys
import traceback

import aqt
from aqt.qt import QApplication, QMessageBox, QTimer
from kioku import windows

mw = aqt.mw
STEP_MS = 2500


def log(text: str) -> None:
    print(f"SWEEP {text}", flush=True)


def ensure_card() -> None:
    col = mw.col
    if col.card_count() == 0:
        note = col.new_note(col.models.by_name("Basic"))
        note["Front"], note["Back"] = "smoke front", "smoke back"
        col.add_note(note, col.decks.id("Default"))
    mw.reset()


def study() -> None:
    mw.col.decks.select(mw.col.decks.id("Default"))
    mw.moveToState("overview")
    QTimer.singleShot(800, lambda: mw.moveToState("review"))


def answer() -> None:
    mw.reviewer._showAnswer()
    QTimer.singleShot(800, lambda: mw.reviewer._answerCard(3))


def deck_options() -> None:
    import aqt.deckoptions

    aqt.deckoptions.display_options_for_deck_id(mw.col.decks.get_current_id())


def switch_profile() -> None:
    mw.unloadProfileAndShowProfileManager()


def back_from_profiles() -> None:
    windows._back(mw.profileDiag)


STEPS = [
    ("card", ensure_card),
    ("about", mw.onAbout),
    ("browse", mw.onBrowse),
    ("add", mw.onAddCard),
    ("stats", mw.onStats),
    ("prefs", mw.onPrefs),
    ("notetypes", mw.onNoteTypes),
    ("filtered", mw.onCram),
    ("studydeck", mw.onStudyDeck),
    ("emptycards", mw.onEmptyCards),
    ("export", mw.onExport),
    ("addons", mw.addonManager.onAddonsDialog),
    ("deckoptions", deck_options),
    ("checkdb", mw.onCheckDB),
    ("checkmedia", mw.on_check_media_db),
    ("sync-login", mw.on_sync_button_clicked),
    ("study", study),
    ("answer", answer),
    ("undo", mw.undo),
    ("decks", lambda: mw.moveToState("deckBrowser")),
    ("switch-profile", switch_profile),
    ("profiles-back", back_from_profiles),
]


def close_others() -> list[str]:
    """Close what the last step left open, like Back; report message boxes."""
    seen = []
    for w in QApplication.topLevelWidgets():
        if w is mw or not w.isVisible() or not w.isWindow():
            continue
        name = type(w).__name__
        if isinstance(w, QMessageBox):
            seen.append(f"box: {w.text()[:80]!r}")
            w.done(0)
        elif name == "ProfileManager":
            seen.append("ProfileManager left open")
        else:
            seen.append(name)
            windows._back(w)
    return seen


def run(i: int = 0) -> None:
    if i:
        left = close_others()
        log(f"{i - 1} {STEPS[i - 1][0]}: ok" + (f" (closed {', '.join(left)})" if left else ""))
    if i == len(STEPS):
        log(f"done; state={mw.state} profile={mw.pm.name}")
        return
    name, action = STEPS[i]
    log(f"{i} {name}: start")
    # scheduled first: many actions open a modal window and only return
    # once it is closed
    QTimer.singleShot(STEP_MS, lambda: run(i + 1))
    try:
        action()
    except Exception:
        log(f"{i} {name}: EXCEPTION")
        traceback.print_exc(file=sys.stdout)


QTimer.singleShot(100, run)
print("sweep started")
