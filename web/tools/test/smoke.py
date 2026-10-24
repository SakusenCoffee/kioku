"""Quick smoke test of the app in headless Chrome: a fresh browser profile
goes through the first-run dialogs, adds a note, studies it, imports a deck
with media, plays audio and TTS, opens Anki's windows, checks the database,
exports, then a reload checks that everything was kept. Prints one
PASS/FAIL line per check and the page errors.

Needs tools/serve.py on port 8765 and `npm install` in tools/test.
Usage: python3 tools/test/smoke.py [deck.apkg with media]"""

import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DECK = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "../../test-deck/Anki xiehanzi - HSK 1.apkg"))


def check(name: str, expr: str, wait: int = 2000) -> list:
    """A step that prints CHECK <name> PASS/FAIL; `expr` is Python with
    aqt and mw in scope, true for a pass (may be a tuple: (ok, detail))."""
    code = f"""import aqt, os, traceback
mw = aqt.mw
try:
    r = ({expr})
    ok, detail = r if isinstance(r, tuple) else (r, "")
except Exception:
    ok, detail = False, traceback.format_exc()[-300:]
print("CHECK", {name!r}, "PASS" if ok else "FAIL", str(detail)[:200])"""
    return ["py", code, 0, wait]


def py(code: str, wait: int = 2000) -> list:
    return ["py", code, 0, wait]


def window_open(cls: str) -> str:
    return f"""(lambda ws: (bool(ws), ws))([w.windowTitle() for w in aqt.qt.QApplication.topLevelWidgets() if type(w).__name__ == {cls!r} and w.isVisible()])"""


CLOSE_OTHERS = py(
    "import aqt\nfor w in aqt.qt.QApplication.topLevelWidgets():\n"
    "    if w.isVisible() and w is not aqt.mw: w.close()",
    3000,
)

AV_HOOK = py(
    "import aqt, aqt.sound\nfrom aqt import gui_hooks\n"
    "aqt._smoke_played = []\n"
    "gui_hooks.av_player_did_begin_playing.append(lambda p, t: aqt._smoke_played.append(type(p).__name__))",
    500,
)

first = [
    ["wait", 9000],
    check("start: profile and collection open", "mw.col is not None and mw.pm.name is not None"),
    AV_HOOK,
    # Add: editor, two fields, Add, close
    ["click", 428, 37, 7000], ["click", 500, 173, 800], ["type", "Smoke front"],
    ["click", 500, 249, 800], ["type", "Smoke back"], ["click", 761, 674, 3000], ["click", 948, 674, 5000],
    check("add note through the editor", "(mw.col.note_count() == 1, mw.col.note_count())"),
    # study: Default deck, Study Now, show answer, Good
    ["click", 307, 167, 4000], ["click", 603, 168, 5000], ["click", 500, 300, 500],
    ["key", "Space", 0, 3000], ["key", "3", 0, 3000],
    check("review: answer a card", "(mw.col.db.scalar('select count() from revlog') >= 1, mw.col.db.scalar('select count() from revlog'))"),
    py("import aqt\naqt.mw.moveToState('deckBrowser')", 3000),
    # import a deck with media through the browser's file picker
    ["upload", DECK, [614, 666], 25000], ["click", 943, 66, 12000], ["click", 48, 21, 5000],
    check("import .apkg with media", "(mw.col.note_count() > 1 and len(os.listdir(mw.col.media.dir())) > 0, (mw.col.note_count(), len(os.listdir(mw.col.media.dir()))))"),
    py("import aqt, os\nfrom aqt.sound import av_player\nfrom anki.sound import SoundOrVideoTag\n"
       "f = [x for x in os.listdir(aqt.mw.col.media.dir()) if x.endswith('.mp3')][:1]\n"
       "av_player.play_tags([SoundOrVideoTag(filename=f[0])] if f else [])", 3000),
    check("audio: media file plays", "('WebAudioPlayer' in aqt._smoke_played, aqt._smoke_played)"),
    py("from aqt.sound import av_player\nfrom anki.sound import TTSTag\n"
       "av_player.play_tags([TTSTag(field_text='hello', lang='en_US', voices=[], speed=1.0, other_args=[])])", 3000),
    check("tts: {{tts}} speaks", "('WebSpeechPlayer' in aqt._smoke_played, aqt._smoke_played)"),
    # windows
    ["click", 500, 37, 10000],
    check("browse opens", window_open("Browser")),
    CLOSE_OTHERS,
    ["click", 575, 37, 10000],
    check("stats opens", window_open("NewDeckStats")),
    CLOSE_OTHERS,
    py("import aqt.deckoptions\naqt.deckoptions.display_options_for_deck_id(aqt.mw.col.decks.current()['id'])", 8000),
    check("deck options opens", window_open("DeckOptionsDialog")),
    CLOSE_OTHERS,
    py("import aqt\naqt.dialogs.open('Preferences', aqt.mw)", 5000),
    check("preferences opens", window_open("Preferences")),
    CLOSE_OTHERS,
    py("import aqt\nfrom aqt.clayout import CardLayout\n"
       "n = aqt.mw.col.get_note(aqt.mw.col.find_notes('')[0])\nCardLayout(aqt.mw, n, ord=0)", 6000),
    check("card templates (CardLayout) opens", window_open("CardLayout")),
    CLOSE_OTHERS,
    check("check database", "(lambda r: (True, r[0][:80]))(mw.col.fix_integrity())", 4000),
    check("undo available after a change", "(lambda s: (True, s))(mw.col.undo_status())"),
    py("import aqt\nfrom anki.collection import ExportAnkiPackageOptions\nfrom kioku_platform.files import save_path\n"
       "aqt.mw.col.export_anki_package(out_path=save_path('smoke.apkg'), options=ExportAnkiPackageOptions("
       "with_scheduling=True, with_deck_configs=True, with_media=True, legacy=False), limit=None)", 10000),
    py("import aqt\naqt.mw.pm.save()", 500),
    ["dom", "__kiokuWeb.persist()"], ["wait", 8000],
]

second = [
    ["wait", 9000],
    check("reload: profile kept (no first-run dialogs)", "mw.pm.name is not None"),
    check("reload: notes, reviews and media kept",
          "(lambda n, r, m: (n > 1 and r >= 1 and m > 0, (n, r, m)))(mw.col.note_count(), mw.col.db.scalar('select count() from revlog'), len(os.listdir(mw.col.media.dir())))"),
]

# less-used windows and features, in the profile the first runs left
extra = [
    ["wait", 9000],
    py("import aqt\naqt.mw.onCram()", 6000),
    check("filtered deck dialog", window_open("FilteredDeckConfigDialog")),
    CLOSE_OTHERS,
    py("import aqt\nfrom aqt.customstudy import CustomStudy\nCustomStudy.fetch_data_and_show(aqt.mw)", 5000),
    check("custom study dialog", window_open("CustomStudy")),
    CLOSE_OTHERS,
    py("import aqt\nfrom aqt.models import Models\nModels(aqt.mw, aqt.mw)", 4000),
    check("note types window", window_open("Models")),
    CLOSE_OTHERS,
    py("import aqt\nfrom aqt.emptycards import show_empty_cards\nshow_empty_cards(aqt.mw)", 1500),
    check("empty cards report (or its 'none' tooltip)",
          "(lambda ws: (bool(ws) or aqt.utils._tooltipLabel is not None, ws))([w for w in aqt.qt.QApplication.topLevelWidgets() if type(w).__name__ == 'EmptyCardsDialog' and w.isVisible()])", 500),
    CLOSE_OTHERS,
    py("import aqt\nfrom aqt.mediacheck import check_media_db\ncheck_media_db(aqt.mw)", 10000),
    check("check media report", "(lambda ws: (bool(ws), ws))([w.windowTitle() for w in aqt.qt.QApplication.topLevelWidgets() if w.isVisible() and w is not mw])"),
    CLOSE_OTHERS,
    py("import aqt\nfrom aqt.browser.find_and_replace import FindAndReplaceDialog\n"
       "FindAndReplaceDialog(aqt.mw, mw=aqt.mw, note_ids=list(aqt.mw.col.find_notes(''))[:5])", 5000),
    check("find and replace dialog", window_open("FindAndReplaceDialog")),
    CLOSE_OTHERS,
    py("import aqt\nopen('/tmp/smoke.csv', 'w').write('front one;back one\\nfront two;back two\\n')\n"
       "from aqt.import_export.importing import import_file\nimport_file(aqt.mw, '/tmp/smoke.csv')", 10000),
    check("CSV import page opens", "(lambda ws: (bool(ws), ws))([w.windowTitle() for w in aqt.qt.QApplication.topLevelWidgets() if w.isVisible() and w is not mw])"),
    CLOSE_OTHERS,
    check("export .colpkg", "(lambda p: (mw.col.export_collection_package(p, include_media=False, legacy=False), (True, os.path.getsize(p)))[1])('/tmp/smoke.colpkg')", 8000),
    py("import aqt\nfrom aqt.theme import Theme\naqt.mw.set_theme(Theme.DARK)", 4000),
    check("dark theme", "(aqt.theme.theme_manager.night_mode, aqt.theme.theme_manager.night_mode)"),
    ["shot", "dark"],
    py("import aqt\nfrom aqt.theme import Theme\naqt.mw.set_theme(Theme.FOLLOW_SYSTEM)", 3000),
    check("follow system theme (browser is light)", "(not aqt.theme.theme_manager.night_mode, aqt.theme.theme_manager.night_mode)"),
    py("import aqt\naqt.mw.unloadProfileAndShowProfileManager()", 8000),
    check("switch profile: profile manager", "(lambda ws: (bool(ws), ws))([w.windowTitle() for w in aqt.qt.QApplication.topLevelWidgets() if w.isVisible() and w is not mw])"),
    ["shot", "profiles"],
]


def run(steps: list, profile: str, cwd: str, nofirstrun: bool) -> str:
    env = dict(os.environ, PROFILE=profile)
    if nofirstrun:
        env["NOFIRSTRUN"] = "1"
    out = subprocess.run(["node", os.path.join(HERE, "boot.mjs"), json.dumps(steps)],
                         cwd=cwd, env=env, capture_output=True, text=True, timeout=900)
    return out.stdout + out.stderr


def main() -> None:
    work = tempfile.mkdtemp(prefix="kioku-smoke-")
    profile = os.path.join(work, "chrome")
    logs = run(first, profile, work, False) + run(second, profile, work, True)
    logs += run(extra, profile, work, True)
    open(os.path.join(work, "smoke.log"), "w").write(logs)
    results = re.findall(r"CHECK '?(.+?)'? (PASS|FAIL) ?(.*)", logs)
    downloads = re.findall(r"download completed (\d+) bytes", logs)
    results.append(("export .apkg downloads", "PASS" if downloads else "FAIL", f"{downloads[0]} bytes" if downloads else ""))
    for name, status, detail in results:
        print(f"{status}  {name}  {detail}".rstrip())
    errors = sorted(set(re.findall(r"pageerror (.+)|JS error (.+)", logs)))
    for e in errors:
        print("page error:", (e[0] or e[1])[:160])
    failed = sum(1 for r in results if r[1] == "FAIL")
    print(f"\n{len(results) - failed}/{len(results)} passed; log and screenshots in {work}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
