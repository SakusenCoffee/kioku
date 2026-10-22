"""Syncing when Kioku goes to the background and comes back
(kioku.switchsync), against the real sync server, with a second collection
standing in for AnkiDroid."""

from __future__ import annotations

import threading
import time
from concurrent.futures import Future

import aqt
import pytest
from anki.sync import SyncAuth

from kioku import ankidroid, background, switchsync, syncserver
from test_syncserver import add_note, fronts, login, new_col, settings, sync, url


class TaskMan:
    """A background thread, like Anki's; on_done waits for pump(), the main
    thread."""

    def __init__(self) -> None:
        self.done: list = []
        self.threads: list[threading.Thread] = []

    def run_in_background(self, task, on_done=None, args=None, uses_collection=True):  # type: ignore[no-untyped-def]
        fut: Future = Future()

        def run() -> None:
            try:
                fut.set_result(task(**(args or {})))
            except Exception as err:
                fut.set_exception(err)
            if on_done:
                self.done.append(lambda: on_done(fut))

        thread = threading.Thread(target=run)
        self.threads.append(thread)
        thread.start()
        return fut

    def pump(self) -> None:
        for thread in self.threads:
            thread.join(60)
        while self.done:
            self.done.pop(0)()


class PM:
    def __init__(self, profile: dict) -> None:
        self.profile = profile

    def sync_auth(self):  # type: ignore[no-untyped-def]
        if not (hkey := self.profile.get("syncKey")):
            return None
        return SyncAuth(hkey=hkey, endpoint=self.profile.get("currentSyncUrl"))

    def custom_sync_url(self):  # type: ignore[no-untyped-def]
        return self.profile.get("customSyncUrl")

    def auto_syncing_enabled(self) -> bool:
        return self.profile.get("autoSync", True)

    def set_host_number(self, n) -> None:  # type: ignore[no-untyped-def]
        self.profile["hostNum"] = n

    def set_current_sync_url(self, u) -> None:  # type: ignore[no-untyped-def]
        self.profile["currentSyncUrl"] = u


class MW:
    def __init__(self, col, profile: dict) -> None:  # type: ignore[no-untyped-def]
        self.col = col
        self.pm = PM(profile)
        self.taskman = TaskMan()
        self.busy = 0
        self.progress = type("P", (), {"busy": lambda _s: self.busy})()
        self.media_syncer = type("M", (), {"is_syncing": lambda _s: False})()
        self._background_op_count = 0
        self.anki_syncs = 0

    def can_auto_sync(self) -> bool:
        return bool(self.pm.sync_auth()) and self.pm.auto_syncing_enabled()

    def _increase_background_ops(self) -> None:
        self._background_op_count += 1

    def _decrease_background_ops(self) -> None:
        self._background_op_count -= 1

    def _sync_collection_and_media(self, after) -> None:  # type: ignore[no-untyped-def]
        # Anki's own sync, with its questions: recorded only
        self.anki_syncs += 1

    def _refresh_after_sync(self) -> None:
        pass


@pytest.fixture
def phones(platform, tmp_path, monkeypatch):
    """Kioku's profile and "AnkiDroid", both synced with the phone's server."""
    s = settings()
    st = syncserver.start(s)
    assert st.running, st
    endpoint = url(st)
    kioku = new_col(tmp_path / "kioku" / "collection.anki2")
    droid = new_col(tmp_path / "droid" / "collection.anki2")
    auth_k = login(kioku, s, endpoint)
    auth_d = login(droid, s, endpoint)
    add_note(kioku, "first")
    sync(kioku, auth_k, upload=True, media=False)
    sync(droid, auth_d, media=False)
    profile = {"syncKey": auth_k.hkey, "customSyncUrl": endpoint, "currentSyncUrl": endpoint}
    mw = MW(kioku, profile)
    monkeypatch.setattr(aqt, "mw", mw, raising=False)
    monkeypatch.setattr(ankidroid, "_when_active", lambda run: run())
    switchsync._running[0] = False
    switchsync._attention[0] = False
    switchsync._back_while_running[0] = False
    mw.droid, mw.auth_d = droid, auth_d
    yield mw
    mw.taskman.pump()
    kioku.close()
    droid.close()
    syncserver.stop()


def leave(mw, wait_s: float = 10) -> list[str]:  # type: ignore[no-untyped-def]
    """What Kioku's activity does: ask at onPause until the answer isn't
    "wait", then at onStop."""
    answers = [switchsync.on_background(mw, "pause")]
    deadline = time.time() + wait_s
    while answers[-1] == "wait" and time.time() < deadline:
        time.sleep(0.02)
        answers.append(switchsync.on_background(mw, "pause"))
    answers.append(switchsync.on_background(mw, "stop"))
    return answers


def test_wanted(phones) -> None:
    mw = phones
    assert switchsync.wanted(mw)
    mw.pm.profile["autoSync"] = False
    assert not switchsync.wanted(mw)
    mw.pm.profile["autoSync"] = True
    mw.pm.profile["customSyncUrl"] = "https://sync.example.com/"
    assert not switchsync.wanted(mw)
    mw.pm.profile["customSyncUrl"] = syncserver.own_url()
    mw.pm.profile.pop("syncKey")
    assert not switchsync.wanted(mw)


def test_leaving_sends_changes_before_ankidroid_syncs(phones) -> None:
    mw = phones
    add_note(mw.col, "made in Kioku")
    answers = leave(mw)
    # waited for the sync, then nothing left to do at onStop
    assert answers[0] == "wait" and answers[-2:] == ["none", "none"], answers
    sync(mw.droid, mw.auth_d, media=False)
    assert "made in Kioku" in fronts(mw.droid)
    mw.taskman.pump()
    assert not switchsync._attention[0] and mw.anki_syncs == 0
    assert not switchsync.has_local_changes(mw.col)


def test_leaving_without_changes_doesnt_sync(phones) -> None:
    mw = phones
    sync(mw.col, login(mw.col, settings_of(), syncserver.own_url()), media=False)
    assert leave(mw) == ["none", "none"]
    assert not mw.taskman.threads


def settings_of() -> syncserver.Settings:
    return syncserver._running_settings  # type: ignore[return-value]


def test_busy_leaves_it_for_later(phones) -> None:
    mw = phones
    add_note(mw.col, "made while busy")
    mw._background_op_count = 1
    assert leave(mw) == ["none", "none"]
    assert not mw.taskman.threads


def test_full_sync_is_never_done_unasked(phones) -> None:
    mw = phones
    add_note(mw.col, "before the schema change")
    mw.col.mod_schema(check=False)
    leave(mw)
    mw.taskman.pump()
    # nothing uploaded: AnkiDroid's copy is untouched
    sync(mw.droid, mw.auth_d, media=False)
    assert "before the schema change" not in fronts(mw.droid)
    assert switchsync._attention[0]
    # back after a moment: Anki's own sync, which asks
    switchsync.on_foreground(mw, 100)
    assert mw.anki_syncs == 1 and not switchsync._attention[0]


def test_failure_is_left_for_anki_to_show(phones) -> None:
    mw = phones
    add_note(mw.col, "won't get through")
    mw.pm.profile["syncKey"] = "wrong"
    leave(mw)
    mw.taskman.pump()
    assert switchsync._attention[0]
    mw.pm.profile["syncKey"] = "wrong-but-set"
    switchsync.on_foreground(mw, 100)
    assert mw.anki_syncs == 1


def test_coming_back_syncs_after_a_while(phones) -> None:
    mw = phones
    switchsync.on_foreground(mw, 500)
    assert mw.anki_syncs == 0
    switchsync.on_foreground(mw, 5000)
    assert mw.anki_syncs == 1
    mw.busy = 1
    switchsync.on_foreground(mw, 5000)
    assert mw.anki_syncs == 1


def test_back_before_the_background_sync_finished(phones) -> None:
    mw = phones
    add_note(mw.col, "made in Kioku")
    assert switchsync.on_background(mw, "pause") == "wait"
    switchsync.on_foreground(mw, 5000)
    assert mw.anki_syncs == 0
    mw.taskman.pump()
    # once it finished: Anki's own sync, for AnkiDroid's changes
    assert mw.anki_syncs == 1


def test_background_watch(phones, platform) -> None:
    mw = phones
    mw.pm.profile[ankidroid.PROFILE_KEY] = {"mode": ankidroid.MEDIA}
    background.refresh(mw)
    assert platform.watching is not None
    on_background, on_foreground = platform.watching
    add_note(mw.col, "made in Kioku")
    assert on_background("pause") == "wait"
    mw.taskman.pump()
    mw.pm.profile["autoSync"] = False
    background.refresh(mw)
    assert platform.watching is None
