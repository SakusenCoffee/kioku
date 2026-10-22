"""The phone's sync server (kioku.syncserver) against real Anki clients."""

from __future__ import annotations

import os
import socket
import threading
import time
import urllib.request

import pytest
from anki.collection import Collection
from anki.errors import SyncError
from anki.sync import SyncAuth
from anki.sync_pb2 import SyncCollectionResponse

from kioku import syncserver

Required = SyncCollectionResponse.ChangesRequired
# what a finished normal sync reports (no full sync needed)
NORMAL = (Required.NO_CHANGES, Required.NORMAL_SYNC)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def settings(**kw) -> syncserver.Settings:
    values = dict(enabled=True, port=free_port(), username="kioku", password="secret-pass")
    values.update(kw)
    return syncserver.Settings(**values)


def url(st: syncserver.Status) -> str:
    return f"http://127.0.0.1:{st.port}/"


def login(col: Collection, s: syncserver.Settings, endpoint: str) -> SyncAuth:
    auth = col.sync_login(username=s.username, password=s.password, endpoint=endpoint)
    return SyncAuth(hkey=auth.hkey, endpoint=endpoint)


def wait_media(col: Collection) -> None:
    deadline = time.time() + 60
    while col.media_sync_status().active:
        assert time.time() < deadline, "media sync did not finish"
        time.sleep(0.05)


def sync(col: Collection, auth: SyncAuth, *, upload: bool = False, media: bool = True) -> int:
    out = col.sync_collection(auth, sync_media=False)
    if out.required in (Required.FULL_SYNC, Required.FULL_UPLOAD, Required.FULL_DOWNLOAD):
        up = out.required == Required.FULL_UPLOAD or (out.required == Required.FULL_SYNC and upload)
        col.close_for_full_sync()
        # like aqt.sync: a media USN starts a media sync afterwards
        server_usn = out.server_media_usn if media else None
        col.full_upload_or_download(auth=auth, server_usn=server_usn, upload=up)
        col.reopen(after_full_sync=True)
    if media:
        col.sync_media(auth)
        wait_media(col)
    return out.required


def new_col(path) -> Collection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return Collection(str(path))


def add_note(col: Collection, front: str, back: str = "back") -> int:
    # note ids are creation times in ms: notes made in the same millisecond
    # in different collections would be the same note to a sync
    time.sleep(0.002)
    note = col.new_note(col.models.by_name("Basic"))
    note["Front"] = front
    note["Back"] = back
    col.add_note(note, col.decks.id("Default"))
    return note.id


def fronts(col: Collection) -> set[str]:
    return {col.get_note(nid)["Front"] for nid in col.find_notes("")}


# Settings
######################################################################


def test_settings_problems() -> None:
    ok = settings()
    assert ok.problem() is None
    assert settings(port=80).problem()
    assert settings(port=70000).problem()
    assert settings(username="").problem()
    assert settings(username="a:b").problem()
    assert settings(username="../x").problem()
    assert settings(username="..").problem()
    assert settings(password="short").problem()
    assert settings(listen="moon").problem()
    assert len(syncserver.new_password()) >= 12


def test_settings_saved_in_global_profile(tmp_path) -> None:
    from anki.db import DB
    from aqt.profiles import ProfileManager

    db = DB(str(tmp_path / "prefs21.db"))
    db.execute("create table profiles (name text primary key, data blob not null)")
    pm = type("PM", (), {})()
    pm.db = db
    pm.meta = {"other": 1}
    pm._pickle = lambda obj: ProfileManager._pickle(pm, obj)
    db.execute("insert into profiles values ('_global', ?)", pm._pickle(pm.meta))

    s = settings(listen=syncserver.TAILSCALE, port=9123)
    syncserver.save_settings(pm, s)
    data = db.scalar("select cast(data as blob) from profiles where name = '_global'")
    meta = ProfileManager._unpickle(pm, data)
    assert meta["other"] == 1
    assert syncserver.load_settings(meta) == s
    # unknown keys and wrong types fall back to defaults
    meta[syncserver.META_KEY].update(port="8080", bogus=True)
    assert syncserver.load_settings(meta).port == 8080
    assert syncserver.load_settings({}) == syncserver.Settings()


# Running
######################################################################


def test_start_stop_restart(platform) -> None:
    s = settings()
    st = syncserver.start(s)
    assert st.running and st.port == s.port and st.host == "127.0.0.1", st
    assert syncserver.answers()
    assert platform.service_calls[-1][0] is True
    # the password is not left in the environment
    assert not any(k.startswith("SYNC_USER") for k in os.environ)

    syncserver.stop()
    assert not syncserver.status().running
    assert not syncserver.answers()
    assert platform.service_calls[-1] == (False, "")
    with pytest.raises(OSError):
        urllib.request.urlopen(f"{url(st)}health", timeout=2)

    st = syncserver.start(s)
    assert st.running and syncserver.answers()
    # starting again while running replaces the server on the same port
    st = syncserver.start(s)
    assert st.running and syncserver.answers()


def test_port_in_use(platform) -> None:
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        st = syncserver.start(settings(port=busy.getsockname()[1]))
    assert not st.running
    assert "already in use" in st.error
    assert platform.service_calls[-1] == (False, "")


def test_bad_settings_dont_start(platform) -> None:
    st = syncserver.start(settings(password="x"))
    assert not st.running and "8 characters" in st.error


def test_tailscale_not_connected(platform, monkeypatch) -> None:
    monkeypatch.setattr(syncserver, "tailscale_address", lambda: None)
    st = syncserver.start(settings(listen=syncserver.TAILSCALE))
    assert not st.running and "Tailscale" in st.error
    assert syncserver.urls(settings(listen=syncserver.TAILSCALE)) == []


def test_all_networks_listens_everywhere(platform) -> None:
    s = settings(listen=syncserver.ALL)
    st = syncserver.start(s)
    assert st.host == "0.0.0.0"
    assert syncserver.answers()
    assert syncserver.urls(s)[0][1] == f"http://127.0.0.1:{s.port}/"


def test_many_restarts_leave_no_threads(platform) -> None:
    s = settings()
    syncserver.start(s)
    syncserver.stop()
    before = threading.active_count()
    for _ in range(25):
        assert syncserver.start(s).running
        assert syncserver.answers()
        syncserver.stop()
    time.sleep(0.5)
    assert threading.active_count() <= before + 1


# Syncing through it
######################################################################


def test_two_clients_round_trip(platform, tmp_path) -> None:
    s = settings()
    st = syncserver.start(s)
    a = new_col(tmp_path / "a" / "collection.anki2")
    b = new_col(tmp_path / "b" / "collection.anki2")
    try:
        add_note(a, "from a")
        a.media.write_data("a.txt", b"media from a")
        auth_a = login(a, s, url(st))
        auth_b = login(b, s, url(st))

        # an empty server: the first client uploads, the second downloads
        assert sync(a, auth_a, upload=True) in (Required.FULL_SYNC, Required.FULL_UPLOAD)
        assert sync(b, auth_b, upload=False) in (Required.FULL_SYNC, Required.FULL_DOWNLOAD)
        assert fronts(b) == {"from a"}
        assert b.media.have("a.txt")

        # changes both ways, as normal syncs
        add_note(b, "from b")
        b.media.write_data("b.txt", b"media from b")
        assert sync(b, auth_b) in NORMAL
        assert sync(a, auth_a) in NORMAL
        assert fronts(a) == {"from a", "from b"}
        assert a.media.have("b.txt")
        with open(os.path.join(a.media.dir(), "b.txt"), "rb") as f:
            assert f.read() == b"media from b"
        assert sync(a, auth_a) in NORMAL

        # the server's copy lives in the app's private folder
        assert syncserver.has_data(s)
        assert syncserver.storage_used() > 0
    finally:
        a.close()
        b.close()


def test_wrong_password_is_refused(platform, tmp_path) -> None:
    s = settings()
    st = syncserver.start(s)
    col = new_col(tmp_path / "c" / "collection.anki2")
    try:
        with pytest.raises(SyncError):
            col.sync_login(username=s.username, password="wrong-password", endpoint=url(st))
        with pytest.raises(SyncError):
            col.sync_login(username="someone", password=s.password, endpoint=url(st))
    finally:
        col.close()


def test_restart_keeps_data_and_logins(platform, tmp_path) -> None:
    s = settings()
    st = syncserver.start(s)
    a = new_col(tmp_path / "a" / "collection.anki2")
    try:
        add_note(a, "one")
        auth = login(a, s, url(st))
        sync(a, auth, upload=True)
        syncserver.stop()
        syncserver.start(s)
        add_note(a, "two")
        # same login, no full sync after the restart
        assert sync(a, auth) in NORMAL
        b = new_col(tmp_path / "b" / "collection.anki2")
        try:
            sync(b, login(b, s, url(st)))
            assert fronts(b) == {"one", "two"}
        finally:
            b.close()
    finally:
        a.close()


def test_new_password_needs_new_login(platform, tmp_path) -> None:
    s = settings()
    st = syncserver.start(s)
    a = new_col(tmp_path / "a" / "collection.anki2")
    try:
        auth = login(a, s, url(st))
        sync(a, auth, upload=True)
        s2 = syncserver.Settings(**{**vars(s), "password": "another-pass"})
        syncserver.start(s2)
        with pytest.raises(SyncError):
            a.sync_collection(auth, sync_media=False)
        auth2 = login(a, s2, url(st))
        # same user name: same folder, the data is still there
        assert sync(a, auth2) in NORMAL
    finally:
        a.close()


def test_delete_data_means_full_upload(platform, tmp_path) -> None:
    s = settings()
    st = syncserver.start(s)
    a = new_col(tmp_path / "a" / "collection.anki2")
    try:
        add_note(a, "kept on the phone")
        auth = login(a, s, url(st))
        sync(a, auth, upload=True)
        syncserver.stop()
        syncserver.delete_data()
        assert not syncserver.has_data(s)
        assert syncserver.storage_used() == 0
        syncserver.start(s)
        auth = login(a, s, url(st))
        required = sync(a, auth, upload=True)
        assert required in (Required.FULL_SYNC, Required.FULL_UPLOAD)
        # the client's own data was not touched
        assert fronts(a) == {"kept on the phone"}
    finally:
        a.close()


def test_stop_during_media_upload(platform, tmp_path) -> None:
    s = settings()
    st = syncserver.start(s)
    a = new_col(tmp_path / "a" / "collection.anki2")
    try:
        auth = login(a, s, url(st))
        sync(a, auth, upload=True, media=False)
        for i in range(300):
            a.media.write_data(f"file{i}.bin", os.urandom(64 * 1024))
        a.sync_media(auth)
        time.sleep(0.3)
        started = time.time()
        syncserver.stop()
        assert time.time() - started < 15
        # the client's media sync fails or finishes; it must not hang
        deadline = time.time() + 60
        while True:
            try:
                if not a.media_sync_status().active:
                    break
            except Exception:
                break
            assert time.time() < deadline
            time.sleep(0.1)
        syncserver.start(s)
        a.sync_media(auth)
        wait_media(a)
        b = new_col(tmp_path / "b" / "collection.anki2")
        try:
            auth_b = login(b, s, url(st))
            sync(b, auth_b)
            assert all(b.media.have(f"file{i}.bin") for i in range(300))
        finally:
            b.close()
    finally:
        a.close()


def _try(fn, *args) -> None:  # type: ignore[no-untyped-def]
    try:
        fn(*args)
    except AssertionError:
        pass


def test_simultaneous_clients(platform, tmp_path) -> None:
    s = settings()
    st = syncserver.start(s)
    cols = [new_col(tmp_path / f"c{i}" / "collection.anki2") for i in range(3)]
    try:
        auths = [login(c, s, url(st)) for c in cols]
        # an empty collection needs no first full sync; start from cards
        add_note(cols[0], "seed")
        sync(cols[0], auths[0], upload=True)
        for c, auth in zip(cols[1:], auths[1:]):
            sync(c, auth)
        for i, c in enumerate(cols):
            add_note(c, f"note {i}")
        errors: list[Exception] = []

        def run(c: Collection, auth: SyncAuth) -> None:
            for attempt in range(10):
                try:
                    sync(c, auth, media=False)
                    return
                except Exception as err:  # another client holds the server
                    errors.append(err)
                    time.sleep(0.2 * (attempt + 1))
            raise AssertionError("never synced")

        # syncing at the same moment fails with Anki's "only one copy of Anki
        # can sync" error (each start aborts the other's sync) and must lose
        # nothing; clients may give up
        threads = [threading.Thread(target=lambda c=c, a=a: _try(run, c, a)) for c, a in zip(cols, auths)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(120)
        assert all("one copy of Anki" in str(e) for e in errors), errors
        # one more round each, one at a time, brings everyone up to date
        for c, auth in zip(cols, auths):
            sync(c, auth, media=False)
        for c, auth in zip(cols, auths):
            sync(c, auth, media=False)
        expected = {"seed", "note 0", "note 1", "note 2"}
        assert all(fronts(c) == expected for c in cols), [fronts(c) for c in cols]
    finally:
        for c in cols:
            c.close()
