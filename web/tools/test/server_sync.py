"""Sync in server mode (docs/server.md): the server's Anki core syncs, not
the browser. Starts Anki's own sync server and tools/serve.py with fresh
data, then in headless Chrome: full upload, a normal sync with a new note,
media sync. With ANKIWEB=1 a second browser then logs in to AnkiWeb with
`email` and `password` from the Kioku repo's .env (a test account) and
does a full download over that collection; it never uploads there.

Needs a Python with Anki's core (`pip install anki==<ANKI_PY_VERSION>`),
a build (tools/build.sh) and `npm install` in tools/test.
Usage: python tools/test/server_sync.py"""

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server as harness  # noqa: E402  (reuses its runner, not its test)

WORK = harness.WORK
SYNC_PORT = 8790
SYNC_BASE = os.path.join(WORK, "syncserver")
ENDPOINT = f"http://127.0.0.1:{SYNC_PORT}/"
check, run = harness.check, harness.run


def sync_server_notes() -> int:
    path = os.path.join(SYNC_BASE, "test", "collection.anki2")
    if not os.path.exists(path):
        return -1
    # the sync server keeps it locked: read a copy
    copy = tempfile.mkdtemp()
    for suffix in ("", "-wal"):
        if os.path.exists(path + suffix):
            shutil.copy(path + suffix, os.path.join(copy, "c.anki2" + suffix))
    with sqlite3.connect(os.path.join(copy, "c.anki2")) as db:
        return db.execute("select count() from notes").fetchone()[0]


def wait_for(cond, seconds: int = 30) -> bool:
    for _ in range(seconds):
        if cond():
            return True
        time.sleep(1)
    return False


ADD_NOTE = """import aqt
mw = aqt.mw
n = mw.col.new_note(mw.col.models.by_name("Basic"))
n["Front"] = "{front}"
n["Back"] = '<img src="{media}">'
mw.col.add_note(n, mw.col.decks.id("Default"))
mw.col.media.write_data("{media}", b"\\x89PNG kioku sync test {front}")"""

sync = subprocess.Popen(
    [sys.executable, "-m", "anki.syncserver"],
    env=dict(os.environ, SYNC_USER1="test:test", SYNC_HOST="127.0.0.1", SYNC_PORT=str(SYNC_PORT), SYNC_BASE=SYNC_BASE),
    stdout=open(os.path.join(WORK, "syncserver.log"), "w"),
    stderr=subprocess.STDOUT,
)
server = harness.start_server()
try:
    time.sleep(3)
    run(
        [
            ["wait", 9000],
            ["py", ADD_NOTE.format(front="one", media="sync-one.png"), 0, 1000],
            ["py", f"""import aqt
mw = aqt.mw
auth = mw.col.sync_login("test", "test", {ENDPOINT!r})
mw.pm.set_custom_sync_url({ENDPOINT!r})
mw.pm.set_sync_key(auth.hkey)
mw.pm.set_sync_username("test")
aqt._out = mw.col.sync_collection(mw.pm.sync_auth(), False)""", 0, 3000],
            check("sync: login and first sync from the server ask for a full sync", "(aqt._out.required != aqt._out.NO_CHANGES, aqt._out.required)"),
            ["py", "import aqt, aqt.sync\naqt.sync.full_upload(aqt.mw, aqt._out.server_media_usn, lambda: None)", 0, 10000],
            check("sync: collection open again after the full upload", "(mw.col is not None and mw.col.note_count() == 1, mw.col.note_count() if mw.col else None)"),
            ["py", ADD_NOTE.format(front="two", media="sync-two.png"), 0, 1000],
            ["py", "import aqt\naqt.mw.on_sync_button_clicked()", 0, 15000],
            check("sync: normal sync through Anki's sync button", "(mw.col.note_count() == 2, mw.col.note_count())"),
        ],
        "chromeSync",
        first_run=True,
    )
    harness.server_check("sync server: both notes", wait_for(lambda: sync_server_notes() == 2), sync_server_notes())
    media = os.path.join(SYNC_BASE, "test", "media")
    harness.server_check(
        "sync server: media synced from the server",
        wait_for(lambda: os.path.isdir(media) and {"sync-one.png", "sync-two.png"} <= set(os.listdir(media))),
        sorted(os.listdir(media)) if os.path.isdir(media) else None,
    )

    if os.environ.get("ANKIWEB"):
        env = dict(
            line.strip().split("=", 1)
            for line in open(os.path.join(harness.WEB, "..", ".env"), encoding="utf8")
            if "=" in line and not line.startswith("#")
        )
        email, password = env["email"].strip("'\""), env["password"].strip("'\"")
        run(
            [
                ["wait", 9000],
                ["py", "import aqt\naqt.mw.pm.set_media_syncing_enabled(False)", 0, 500],
                ["py", f"""import aqt
mw = aqt.mw
mw.pm.set_custom_sync_url(None)
auth = mw.col.sync_login({email!r}, {password!r}, None)
mw.pm.set_sync_key(auth.hkey)
mw.pm.set_sync_username({email!r})
aqt._out = mw.col.sync_collection(mw.pm.sync_auth(), False)
# as aqt.sync.sync_collection does: AnkiWeb names the host to use
if aqt._out.new_endpoint:
    mw.pm.set_current_sync_url(aqt._out.new_endpoint)""", 0, 8000],
                check("AnkiWeb: login from the server", "(aqt._out.required in (aqt._out.FULL_DOWNLOAD, aqt._out.FULL_SYNC), aqt._out.required)"),
                ["py", "import aqt, aqt.sync\naqt.sync.full_download(aqt.mw, aqt._out.server_media_usn, lambda: None)", 0, 60000],
                ["shot", os.path.join(WORK, "ankiweb")],
                check("AnkiWeb: full download into the server's collection", "(mw.col is not None and mw.col.note_count() > 100, mw.col.note_count() if mw.col else None)"),
            ],
            "chromeAnkiWeb",
        )
finally:
    server.terminate()
    sync.terminate()
harness.finish()
