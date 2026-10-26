"""Test server mode (docs/server.md) in headless Chrome: starts
tools/serve.py with a fresh KIOKU_DATA, then device A goes through the
first-run dialogs, adds a note, studies it and imports a deck with media;
the collection must be on the server and not in the browser. A reload
keeps everything; device B (another browser profile) takes the collection
over, and A is told on its next action. Prints PASS/FAIL per check.

Needs Python with Anki's core (`pip install anki==<ANKI_PY_VERSION>` from
shared/versions.env) to run this, a build (tools/build.sh) and
`npm install` in tools/test.
Usage: python tools/test/server.py [deck.apkg with media]"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "..", "..")
DECK = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(WEB, "test-deck/Anki xiehanzi - HSK 1.apkg"))
PORT = 8767
URL = f"http://127.0.0.1:{PORT}/app.html"
WORK = tempfile.mkdtemp(prefix="kioku-server-test-")
DATA = os.path.join(WORK, "data")
PROFILE_DIR = os.path.join(DATA, "home/Documents/Anki2/User 1")
results = []
ADDON = 1771074083  # Review Heatmap


# counts round trips to the server from here on, and Browse rows asked
# for one at a time
COUNT_TRIPS = """import kioku_platform.remote as r, struct
r._trips = r._single_rows = 0
row = next(k for k, (n, _) in r._methods(__import__("anki._backend_generated", fromlist=["x"])).items() if n == "browser_row_for_id")
for name in ("_send", "_send_many"):
    def counted(kind, payload, _f=getattr(r, name), _single=name == "_send"):
        r._trips += 1
        if _single and kind == "C" and struct.unpack(">HH", payload[:4]) == row:
            r._single_rows += 1
        return _f(kind, payload)
    setattr(r, name, counted)"""


def check(name: str, expr: str, wait: int = 2000) -> list:
    code = f"""import aqt, os, traceback
mw = aqt.mw
try:
    r = ({expr})
    ok, detail = r if isinstance(r, tuple) else (r, "")
except Exception:
    ok, detail = False, traceback.format_exc()[-300:]
print("CHECK", {name!r}, "PASS" if ok else "FAIL", str(detail)[:200])"""
    return ["py", code, 0, wait]


def run(steps: list, profile: str, first_run: bool = False, background: bool = False):
    env = dict(os.environ, URL=URL, PROFILE=os.path.join(WORK, profile))
    if not first_run:
        env["NOFIRSTRUN"] = "1"
    proc = subprocess.Popen(
        ["node", "boot.mjs", json.dumps(steps)], cwd=HERE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    return proc if background else collect(proc)


def collect(proc) -> str:
    out = proc.communicate(timeout=900)[0]
    with open(os.path.join(WORK, f"run{len(os.listdir(WORK))}.log"), "w") as f:
        f.write(out)
    for line in out.splitlines():
        if "CHECK " in line:
            results.append(line.split("CHECK ", 1)[1])
            print(results[-1])
        elif "pageerror" in line or "devexec failed" in line:
            print(line[:300])
    return out


def server_check(name: str, ok: bool, detail: object = "") -> None:
    results.append(f"{name} {'PASS' if ok else 'FAIL'} {detail}")
    print(results[-1])


def start_server() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, os.path.join(WEB, "tools/serve.py"), os.path.join(WEB, "build/cmake"), str(PORT)],
        env=dict(os.environ, KIOKU_DATA=DATA, KIOKU_AUTH="none"),
        stderr=open(os.path.join(WORK, "server.log"), "w"),
    )


def finish() -> None:
    failed = [r for r in results if " FAIL" in r]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed; data in {WORK}")
    sys.exit(1 if failed else 0)


def main() -> None:
    server = start_server()
    try:
        test()
    finally:
        server.terminate()
        server.wait()
    finish()


def test() -> None:
    time.sleep(2)
    run(
        [
            ["wait", 9000],
            check("start: collection open from the server home", "(mw.col is not None and not os.path.exists(mw.col.path), mw.col.path)"),
            # Add: editor, two fields, Add, close
            ["click", 428, 37, 7000], ["click", 500, 173, 800], ["type", "Server front"],
            ["click", 500, 249, 800], ["type", "Server back"], ["click", 761, 674, 3000], ["click", 948, 674, 5000],
            check("add note through the editor", "(mw.col.note_count() == 1, mw.col.note_count())"),
            ["click", 307, 167, 4000], ["click", 603, 168, 5000], ["click", 500, 300, 500],
            ["key", "Space", 0, 3000], ["key", "3", 0, 3000],
            check("review: answer a card", "(mw.col.db.scalar('select count() from revlog') >= 1, mw.col.db.scalar('select count() from revlog'))"),
            ["py", "import aqt\naqt.mw.moveToState('deckBrowser')", 0, 3000],
            ["upload", DECK, [614, 666], 25000], ["click", 943, 66, 12000], ["click", 48, 21, 5000],
            check("import .apkg with media", "(mw.col.note_count() > 1, mw.col.note_count())"),
            ["py", COUNT_TRIPS, 0, 500],
            ["py", "import aqt\naqt._b = aqt.dialogs.open('Browser', aqt.mw)\naqt._b.search_for('')", 0, 10000],
            check("browse: rows fetched together", "(lambda m, r: (r._single_rows <= 3 and all(m.get_row(m.index(i, 0)).cells[0].text for i in range(5)), (r._trips, 'round trips', r._single_rows, 'single rows', m.len_rows(), 'rows')))(aqt._b.table._model, __import__('kioku_platform.remote', fromlist=['x']))"),
            ["py", "import aqt\naqt._b.close()", 0, 3000],
            ["py", "import aqt\nfrom aqt import gui_hooks\naqt._played = []\ngui_hooks.av_player_did_begin_playing.append(lambda p, t: aqt._played.append(type(p).__name__))", 0, 300],
            ["py", "import aqt\nfrom aqt.sound import av_player\nfrom anki.sound import SoundOrVideoTag\nav_player.play_tags([SoundOrVideoTag(filename='cmn-的.mp3')])", 0, 3000],
            check("audio: plays from the server", "('ServerAudioPlayer' in aqt._played, aqt._played)"),
            check("media: have() asks the server", "(lambda fs: (bool(fs) and mw.col.media.have(fs[0]) and not mw.col.media.have('no-such-file.png'), fs[:1]))([f for nid in mw.col.find_notes('')[:300] for n in [mw.col.get_note(nid)] for f in mw.col.media.files_in_str(n.mid, n.joined_fields())])"),
            # Get Add-ons' code path (Review Heatmap), through the relay
            ["py", f"import aqt\nfrom aqt.addons import download_addons\ndownload_addons(aqt.mw, aqt.mw.addonManager, [{ADDON}], lambda *a: None)", 0, 20000],
            ["py", "import aqt\naqt.mw.moveToState('deckBrowser')", 0, 12000],
        ],
        "chromeA",
        first_run=True,
    )
    on_server = sorted(os.listdir(PROFILE_DIR)) if os.path.isdir(PROFILE_DIR) else []
    server_check("server: collection and media there", "collection.anki2" in on_server and "collection.media" in on_server, on_server)
    media = os.listdir(os.path.join(PROFILE_DIR, "collection.media")) if "collection.media" in on_server else []
    server_check("server: imported media files", len(media) > 0, len(media))
    if media:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/__kioku/media/{urllib.request.quote(media[0])}") as r:
            server_check("server: /__kioku/media serves them", r.status == 200, r.status)
    server_check("server: add-on saved there", os.path.isfile(os.path.join(DATA, f"home/Documents/Anki2/addons21/{ADDON}/__init__.py")))
    server_check("server: profiles and preferences saved", os.path.exists(os.path.join(DATA, "home/Documents/Anki2/prefs21.db")))

    run(
        [
            ["wait", 9000],
            ["shot", os.path.join(WORK, "reload")],
            check("reload: same collection", "(mw.col.note_count() > 1 and mw.col.db.scalar('select count() from revlog') >= 1, mw.col.note_count())"),
            check("reload: add-on loaded from the server's copy", f"('{ADDON}' in __import__('sys').modules, [a.dir_name for a in mw.addonManager.all_addon_meta()])"),
            check("reload: no collection in the browser", "(not os.path.exists(mw.col.path), os.listdir(os.path.dirname(mw.col.path)))"),
        ],
        "chromeA",
    )

    # A works on; B opens meanwhile and says No (B stops, A goes on), then
    # opens again and takes over (Yes)
    a = run(
        [
            ["wait", 9000],
            ["py", "import aqt\naqt.mw.moveToState('overview')", 0, 30000],
            ["py", "import aqt\naqt.mw.moveToState('deckBrowser')", 0, 3000],
            check("device A: works on after B said No", "(mw.col.note_count() > 1, mw.col.note_count())"),
            ["dom", "String(!!document.getElementById('kioku-taken'))"],
        ],
        "chromeA",
        background=True,
    )
    time.sleep(15)
    out = run(
        [["wait", 9000], ["click", 886, 376, 4000], ["dom", "String(!!document.getElementById('kioku-taken'))"],
         check("device B: No leaves it closed", "(mw.col is None, mw.col)")],
        "chromeB",
    )
    server_check("device B: No shows 'open on another device'", "dom true" in out, [l for l in out.splitlines() if "dom " in l])
    out = collect(a)
    server_check("device A: not told anything", "dom false" in out, [l for l in out.splitlines() if "dom " in l])

    a = run(
        [
            ["wait", 9000],
            ["py", "import aqt\naqt.mw.moveToState('overview')", 0, 45000],
            ["py", "import aqt\naqt.mw.moveToState('deckBrowser')", 0, 3000],
            ["dom", "String(!!document.getElementById('kioku-taken'))"],
        ],
        "chromeA",
        background=True,
    )
    time.sleep(15)
    run([["wait", 9000], ["click", 950, 376, 6000], check("device B: took over", "(mw.col is not None, mw.col.note_count() if mw.col else None)")], "chromeB")
    out = collect(a)
    server_check("device A: told it was taken over", "dom true" in out, [l for l in out.splitlines() if "dom " in l])


if __name__ == "__main__":
    main()
