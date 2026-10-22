"""A profile on AnkiDroid's folder (kioku.ankidroid): settings, media sharing,
locking against a second process (standing in for AnkiDroid) and falling
back to the profile's own collection."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time

import anki.collection
import anki.media
import pytest
from anki.collection import Collection

from kioku import ankidroid, syncserver
from test_syncserver import add_note, fronts, login, new_col, settings, sync, url


@pytest.fixture
def droid(platform, tmp_path):
    """An AnkiDroid folder with a collection and some media."""
    folder = tmp_path / "AnkiDroid"
    col = new_col(folder / "collection.anki2")
    add_note(col, "made in AnkiDroid", '<img src="droid.png">')
    col.media.write_data("droid.png", b"image from AnkiDroid")
    col.close()
    # AnkiDroid's own media database name; Kioku must never open it
    open(folder / "collection.media.db", "wb").close()
    yield folder
    ankidroid.set_override("", None, None)


# Settings
######################################################################


def test_load_and_store() -> None:
    profile: dict = {}
    assert ankidroid.load(profile) == ankidroid.Source()
    source = ankidroid.Source(mode=ankidroid.MEDIA, folder="/x", allow_delete_unused=True)
    ankidroid.store(profile, source)
    assert ankidroid.load(profile) == source
    profile[ankidroid.PROFILE_KEY]["mode"] = "bogus"
    assert ankidroid.load(profile).mode == ankidroid.OFF
    assert ankidroid.load(None) == ankidroid.Source()


def test_problems(droid, platform) -> None:
    ok = ankidroid.Source(mode=ankidroid.FOLDER, folder=str(droid))
    assert ankidroid.problems(ok) == []
    assert ankidroid.problems(ankidroid.Source(mode=ankidroid.OFF, folder="/nowhere")) == []
    assert "no folder" in ankidroid.problems(
        ankidroid.Source(mode=ankidroid.MEDIA, folder=str(droid / "missing"))
    )[0]
    os.rename(droid / "collection.anki2", droid / "moved.anki2")
    assert any("collection.anki2" in p for p in ankidroid.problems(ok))
    # MEDIA mode doesn't need AnkiDroid's collection
    assert ankidroid.problems(ankidroid.Source(mode=ankidroid.MEDIA, folder=str(droid))) == []
    platform.files_access = False
    assert "All files access" in ankidroid.problems(ok)[0]


def test_find_folders(droid, tmp_path) -> None:
    nested = tmp_path / "Documents" / "Old AnkiDroid"
    os.makedirs(nested)
    open(nested / "collection.anki2", "wb").close()
    os.makedirs(tmp_path / "Android" / "data")
    found = ankidroid.find_folders(str(tmp_path))
    assert found[0] == str(droid)
    assert str(nested) in found


def test_versions() -> None:
    assert ankidroid.parse_version("2.26.0alpha6") == (2, 26, 0)
    assert ankidroid.parse_version("2.25.3") == (2, 25, 3)
    assert ankidroid.parse_version("2.21beta1") == (2, 21)
    assert ankidroid.parse_version("") == ()
    assert not ankidroid.version_too_old("2.25.3")
    assert not ankidroid.version_too_old("2.22.0")
    assert ankidroid.version_too_old("2.21.1")
    assert ankidroid.version_too_old("2.16alpha1")
    assert not ankidroid.version_too_old("weird")


# MEDIA: own collection, AnkiDroid's media folder
######################################################################


def open_with_media(collection: str, media: str, media_db: str) -> Collection:
    ankidroid.set_override(collection, media, media_db)
    return Collection(collection)


@pytest.fixture
def media_paths_patched(monkeypatch):
    patched = ankidroid.media_paths(anki.media.media_paths_from_col_path)
    monkeypatch.setattr(anki.collection, "media_paths_from_col_path", patched)
    monkeypatch.setattr(anki.media, "media_paths_from_col_path", patched)


def test_media_folder_override(droid, tmp_path, media_paths_patched) -> None:
    profile = tmp_path / "Kioku" / "Profile"
    os.makedirs(profile)
    col_path = str(profile / "collection.anki2")
    media_db = str(profile / ankidroid.MEDIA_DB[ankidroid.MEDIA])
    col = open_with_media(col_path, str(droid / "collection.media"), media_db)
    try:
        assert col.media.dir() == str(droid / "collection.media")
        assert col.media.have("droid.png")
        name = col.media.write_data("kioku.png", b"image from Kioku")
        assert os.path.exists(droid / "collection.media" / name)
        # Kioku's media database is its own; AnkiDroid's is untouched
        assert os.path.exists(media_db)
        assert os.path.getsize(droid / "collection.media.db") == 0
        assert not os.path.exists(profile / "collection.media")
        # a reopen (after a full sync) keeps the override
        col.close_for_full_sync()
        col._backend.close_collection(downgrade_to_schema11=False)
        col.reopen()
        assert col.media.dir() == str(droid / "collection.media")
    finally:
        col.close()
    # other collections are not affected
    other = new_col(tmp_path / "other" / "collection.anki2")
    try:
        assert other.media.dir() == str(tmp_path / "other" / "collection.media")
    finally:
        other.close()


def test_media_mode_with_sync_server(droid, tmp_path, media_paths_patched) -> None:
    """Both "apps" open at once: AnkiDroid's collection with its media, and
    Kioku's own collection on the same media folder, synced through the
    phone's server with media sync off."""
    s = settings()
    st = syncserver.start(s)
    droid_col = Collection(str(droid / "collection.anki2"))
    profile = tmp_path / "Kioku" / "Profile"
    os.makedirs(profile)
    kioku_col = open_with_media(
        str(profile / "collection.anki2"),
        str(droid / "collection.media"),
        str(profile / ankidroid.MEDIA_DB[ankidroid.MEDIA]),
    )
    try:
        auth_d = login(droid_col, s, url(st))
        auth_k = login(kioku_col, s, url(st))
        sync(droid_col, auth_d, upload=True, media=False)
        sync(kioku_col, auth_k, media=False)
        assert fronts(kioku_col) == {"made in AnkiDroid"}
        assert kioku_col.media.have("droid.png")

        name = kioku_col.media.write_data("kioku.png", b"from Kioku")
        add_note(kioku_col, "made in Kioku", f'<img src="{name}">')
        sync(kioku_col, auth_k, media=False)
        sync(droid_col, auth_d, media=False)
        assert "made in Kioku" in fronts(droid_col)
        assert droid_col.media.have(name)
        # no media went through the server
        assert not os.listdir(os.path.join(syncserver.user_folder(s), "media"))

        # media check in Kioku sees AnkiDroid's file as used once synced
        out = kioku_col.media.check()
        assert "droid.png" not in out.unused and name not in out.unused
    finally:
        droid_col.close()
        kioku_col.close()


# FOLDER: AnkiDroid's own collection, locked while open
######################################################################

HOLDER = textwrap.dedent(
    """
    import sys, time
    from anki.collection import Collection
    col = Collection(sys.argv[1])
    col.db.scalar("select count() from notes")
    print("open", flush=True)
    sys.stdin.readline()
    col.close()
    print("closed", flush=True)
    """
)


def hold(path: str) -> subprocess.Popen:
    """Another process (AnkiDroid) with the collection open."""
    proc = subprocess.Popen(
        [sys.executable, "-c", HOLDER, path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout.readline().strip() == "open"
    return proc


def release(proc: subprocess.Popen) -> None:
    proc.stdin.write("\n")
    proc.stdin.flush()
    assert proc.stdout.readline().strip() == "closed"
    proc.wait(30)


def test_locked_while_ankidroid_has_it(droid) -> None:
    path = str(droid / "collection.anki2")
    proc = hold(path)
    try:
        with pytest.raises(Exception) as err:
            Collection(path)
        assert ankidroid.explain(err.value) == ankidroid.LOCKED_HELP
    finally:
        release(proc)
    col = Collection(path)
    try:
        assert fronts(col) == {"made in AnkiDroid"}
        # and now the other way round: Kioku has it, AnkiDroid can't open it
        with pytest.raises(subprocess.CalledProcessError):
            subprocess.run(
                [sys.executable, "-c", HOLDER, path],
                input="\n",
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
            )
    finally:
        col.close()


def test_close_for_background_and_reopen(droid) -> None:
    """What Kioku does when it goes to the background, and back."""
    path = str(droid / "collection.anki2")
    col = Collection(path)
    add_note(col, "made in Kioku")
    col.close_for_full_sync()
    col._backend.close_collection(downgrade_to_schema11=False)

    # AnkiDroid opens it meanwhile, sees Kioku's note and adds its own
    proc = hold(path)
    with pytest.raises(Exception) as err:
        col.reopen()
    assert ankidroid.explain(err.value) == ankidroid.LOCKED_HELP
    release(proc)
    other = Collection(path)
    add_note(other, "added while Kioku was away")
    other.close()

    col.reopen()
    try:
        assert fronts(col) == {"made in AnkiDroid", "made in Kioku", "added while Kioku was away"}
    finally:
        col.close()


# Opening a profile (the patched AnkiQt._loadCollection)
######################################################################


class FakePM:
    def __init__(self, folder: str, profile: dict) -> None:
        self.folder = folder
        self.profile = profile
        self.saved = 0

    def profileFolder(self) -> str:
        return self.folder

    def collectionPath(self) -> str:
        source = ankidroid.load(self.profile)
        if source.mode == ankidroid.FOLDER:
            return source.collection
        return os.path.join(self.folder, "collection.anki2")

    def save(self) -> None:
        self.saved += 1


class FakeMW:
    def __init__(self, pm: FakePM) -> None:
        from anki._backend import RustBackend

        self.pm = pm
        self.backend = RustBackend()
        self.col = None
        self.messages: list = []
        self.busy = 0
        self.resets = 0
        self.progress = type(
            "P",
            (),
            {
                "single_shot": lambda _s, ms, fn, _r: self.messages.append(fn),
                "busy": lambda _s: self.busy,
            },
        )()
        self.media_syncer = type("M", (), {"is_syncing": lambda _s: False})()
        self._background_op_count = 0

    def setEnabled(self, on: bool) -> None:
        pass

    def update_undo_actions(self) -> None:
        pass

    def reset(self) -> None:
        self.resets += 1


@pytest.fixture
def load_collection(monkeypatch, media_paths_patched):
    """The patched AnkiQt._loadCollection, with Anki's own as its fallback."""
    import aqt.main

    def original(self):  # type: ignore[no-untyped-def]
        self.col = Collection(self.pm.collectionPath(), backend=self.backend)

    monkeypatch.setattr(aqt.main.AnkiQt, "_loadCollection", original)
    monkeypatch.setattr(aqt.main.AnkiQt, "_loadCollection", original)
    # install() only patches what it needs here when the rest is in place
    import aqt
    from aqt.profiles import ProfileManager

    monkeypatch.setattr(ProfileManager, "collectionPath", ProfileManager.collectionPath)
    monkeypatch.setattr(aqt.AnkiApp, "__init__", aqt.AnkiApp.__init__)
    from aqt import mediacheck
    from aqt.import_export import importing

    monkeypatch.setattr(mediacheck.MediaChecker, "_on_trash_files", mediacheck.MediaChecker._on_trash_files)
    monkeypatch.setattr(importing.ColpkgImporter, "do_import", importing.ColpkgImporter.do_import)
    monkeypatch.setattr(aqt.main.AnkiQt, "_unloadCollection", aqt.main.AnkiQt._unloadCollection)
    from aqt.operations import CollectionOp, QueryOp

    monkeypatch.setattr(CollectionOp, "run_in_background", CollectionOp.run_in_background)
    monkeypatch.setattr(QueryOp, "run_in_background", QueryOp.run_in_background)
    from aqt import gui_hooks

    hooks_before = list(gui_hooks.main_window_did_init._hooks)
    ankidroid.install()
    yield aqt.main.AnkiQt._loadCollection
    gui_hooks.main_window_did_init._hooks[:] = hooks_before


def make_mw(tmp_path, source: ankidroid.Source) -> FakeMW:
    folder = tmp_path / "Kioku" / "Profile"
    os.makedirs(folder, exist_ok=True)
    profile: dict = {}
    ankidroid.store(profile, source)
    return FakeMW(FakePM(str(folder), profile))


def test_profile_opens_ankidroid_collection(droid, tmp_path, load_collection, monkeypatch) -> None:
    monkeypatch.setattr(ankidroid, "FOLDER_READY", True)
    mw = make_mw(tmp_path, ankidroid.Source(mode=ankidroid.FOLDER, folder=str(droid)))
    load_collection(mw)
    try:
        assert mw.col.path == str(droid / "collection.anki2")
        assert mw.col.media.dir() == str(droid / "collection.media")
        mw.col.media.check()  # the media database is made on first use
        assert os.path.exists(os.path.join(mw.pm.folder, ankidroid.MEDIA_DB[ankidroid.FOLDER]))
        assert os.path.getsize(droid / "collection.media.db") == 0
        assert not mw.messages
    finally:
        mw.col.close()


def test_profile_falls_back_when_locked(droid, tmp_path, load_collection, monkeypatch) -> None:
    monkeypatch.setattr(ankidroid, "FOLDER_READY", True)
    mw = make_mw(tmp_path, ankidroid.Source(mode=ankidroid.FOLDER, folder=str(droid)))
    proc = hold(str(droid / "collection.anki2"))
    try:
        load_collection(mw)
    finally:
        release(proc)
    try:
        # its own collection, the setting turned off and saved, and a message
        assert mw.col.path == os.path.join(mw.pm.folder, "collection.anki2")
        assert mw.col.media.dir() == os.path.join(mw.pm.folder, "collection.media")
        assert ankidroid.load(mw.pm.profile).mode == ankidroid.OFF
        assert mw.pm.saved == 1
        assert len(mw.messages) == 1
    finally:
        mw.col.close()


def test_profile_falls_back_when_folder_missing(droid, tmp_path, load_collection, platform) -> None:
    platform.files_access = False
    mw = make_mw(tmp_path, ankidroid.Source(mode=ankidroid.MEDIA, folder=str(droid)))
    load_collection(mw)
    try:
        assert mw.col.media.dir() == os.path.join(mw.pm.folder, "collection.media")
        assert ankidroid.load(mw.pm.profile).mode == ankidroid.OFF
    finally:
        mw.col.close()


def test_profile_with_media_mode(droid, tmp_path, load_collection) -> None:
    mw = make_mw(tmp_path, ankidroid.Source(mode=ankidroid.MEDIA, folder=str(droid)))
    load_collection(mw)
    try:
        assert mw.col.path == os.path.join(mw.pm.folder, "collection.anki2")
        assert mw.col.media.dir() == str(droid / "collection.media")
    finally:
        mw.col.close()
    # back to Kioku's own: the override is gone
    ankidroid.store(mw.pm.profile, ankidroid.Source())
    load_collection(mw)
    try:
        assert mw.col.media.dir() == os.path.join(mw.pm.folder, "collection.media")
    finally:
        mw.col.close()
    time.sleep(0)


# Going to the background and back (FOLDER)
######################################################################


@pytest.fixture
def folder_mw(droid, tmp_path, load_collection, platform, monkeypatch):
    """A profile on AnkiDroid's collection, open; the retry dialog recorded."""
    retries: list = []
    monkeypatch.setattr(ankidroid, "FOLDER_READY", True)
    monkeypatch.setattr(ankidroid, "_show_retry", lambda mw, err: retries.append(err))
    monkeypatch.setattr(ankidroid, "_close_retry", lambda: None)
    # what runs once Qt has seen the app active runs later, as on a phone
    later: list = []
    monkeypatch.setattr(ankidroid, "_when_active", later.append)
    mw = make_mw(tmp_path, ankidroid.Source(mode=ankidroid.FOLDER, folder=str(droid)))
    mw.retries = retries
    load_collection(mw)
    _, on_foreground = platform.watching

    def foreground() -> None:
        on_foreground(5000)
        while later:
            later.pop(0)()

    mw.foreground = foreground
    yield mw
    col = ankidroid._held[0] or mw.col
    ankidroid._held[0] = None
    ankidroid._deferred.clear()
    if col is not None and col.db is not None:
        col.close()


def test_folder_profile_falls_back_until_ready(droid, tmp_path, load_collection, platform) -> None:
    mw = make_mw(tmp_path, ankidroid.Source(mode=ankidroid.FOLDER, folder=str(droid)))
    load_collection(mw)
    try:
        assert mw.col.path == os.path.join(mw.pm.folder, "collection.anki2")
        assert ankidroid.load(mw.pm.profile).mode == ankidroid.OFF
        assert len(mw.messages) == 1
        assert platform.watching is None
    finally:
        mw.col.close()


def test_watches_background_only_for_folder(droid, tmp_path, load_collection, platform, monkeypatch) -> None:
    monkeypatch.setattr(ankidroid, "FOLDER_READY", True)
    mw = make_mw(tmp_path, ankidroid.Source(mode=ankidroid.FOLDER, folder=str(droid)))
    load_collection(mw)
    assert platform.watching is not None
    mw.col.close()
    ankidroid.store(mw.pm.profile, ankidroid.Source(mode=ankidroid.MEDIA, folder=str(droid)))
    load_collection(mw)
    assert platform.watching is None
    mw.col.close()


def test_background_closes_and_foreground_reopens(folder_mw, droid, platform) -> None:
    mw = folder_mw
    on_background, _ = platform.watching
    add_note(mw.col, "made in Kioku")
    col = mw.col

    assert on_background("pause") == "closed"
    assert mw.col is None and ankidroid.is_closed()
    # onStop asks again
    assert on_background("stop") == "closed"

    # AnkiDroid opens it, sees Kioku's note and adds its own
    other = Collection(str(droid / "collection.anki2"))
    assert "made in Kioku" in fronts(other)
    add_note(other, "added while Kioku was away")
    other.close()

    mw.foreground()
    assert mw.col is col and not ankidroid.is_closed()
    assert "added while Kioku was away" in fronts(mw.col)
    # AnkiDroid changed it: every screen refreshed
    assert mw.resets == 1
    assert not mw.retries


def test_foreground_without_changes_keeps_screens(folder_mw, platform) -> None:
    mw = folder_mw
    on_background, _ = platform.watching
    assert on_background("pause") == "closed"
    mw.foreground()
    assert mw.col is not None and mw.resets == 0
    # a second resume (activity result, then onResume) does nothing
    mw.foreground()
    assert mw.resets == 0


def test_busy_collection_stays_open(folder_mw, platform) -> None:
    mw = folder_mw
    on_background, _ = platform.watching
    mw._background_op_count = 1
    assert on_background("pause") == "busy"
    assert mw.col is not None and mw.col.db is not None
    mw._background_op_count = 0
    mw.busy = 1
    assert on_background("stop") == "busy"
    mw.busy = 0
    assert on_background("stop") == "closed"


def test_nothing_to_close() -> None:
    mw = type("MW", (), {"col": None, "pm": type("PM", (), {"profile": {}})()})()
    assert ankidroid.close_for_ankidroid(mw) == "none"


def test_reopen_while_ankidroid_has_it(folder_mw, droid, platform) -> None:
    mw = folder_mw
    on_background, _ = platform.watching
    assert on_background("stop") == "closed"
    proc = hold(str(droid / "collection.anki2"))
    try:
        mw.foreground()
        assert mw.col is None and ankidroid.is_closed()
        assert len(mw.retries) == 1
        assert ankidroid.explain(mw.retries[0]) == ankidroid.LOCKED_HELP
        # back from Android's settings without force-stopping it
        mw.foreground()
        assert len(mw.retries) == 2 and mw.col is None
    finally:
        release(proc)
    mw.foreground()
    assert mw.col is not None and fronts(mw.col) == {"made in AnkiDroid"}


def test_operations_wait_while_closed(folder_mw, platform) -> None:
    from aqt.operations import CollectionOp, QueryOp

    mw = folder_mw
    on_background, _ = platform.watching
    assert on_background("pause") == "closed"
    # the editor saving a field as Kioku goes to the background
    CollectionOp(parent=None, op=lambda col: col.add_note).run_in_background()
    QueryOp(parent=None, op=lambda col: None, success=lambda _: None).run_in_background()
    assert len(ankidroid._deferred) == 2
    ran: list = []
    ankidroid._deferred[:] = [lambda: ran.append(mw.col is not None)]
    mw.foreground()
    assert ran == [True] and not ankidroid._deferred


def test_anki_backup_drops_the_lock(droid, tmp_path) -> None:
    """Why FOLDER is not offered: Anki's backup reads collection.anki2
    through a second file descriptor (rslib's read_locked_db_file) while
    SQLite has it open, and closing that descriptor drops the process's
    POSIX locks on the file, SQLite's exclusive lock included. AnkiDroid's
    core does the same, so after one of its backups Kioku can open the
    collection while AnkiDroid still has it open. If this test fails, Anki
    fixed it: check AnkiDroid's core and revisit FOLDER_READY."""
    path = str(droid / "collection.anki2")
    col = Collection(path)
    try:
        add_note(col, "changed since the last backup")
        with pytest.raises(subprocess.CalledProcessError):
            subprocess.run(
                [sys.executable, "-c", HOLDER, path], input="\n", capture_output=True,
                text=True, check=True, timeout=60,
            )
        backups = tmp_path / "backups"
        backups.mkdir()
        col.create_backup(backup_folder=str(backups), force=True, wait_for_completion=True)
        # a second process now opens it although this one still has it open
        release(hold(path))
    finally:
        col.close()
