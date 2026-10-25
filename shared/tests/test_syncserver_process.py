"""The sync server as a child process (kioku.syncserver._ServerProcess): what
Anki builds without Kioku's rsbridge patch use, such as the Termux variant's."""

from __future__ import annotations

import os
import socket
import types
import urllib.request

import pytest

from kioku import syncserver
from test_syncserver import NORMAL, Required, add_note, fronts, login, new_col, settings, sync, url


@pytest.fixture(autouse=True)
def upstream_rsbridge(monkeypatch):  # type: ignore[no-untyped-def]
    # only upstream's blocking syncserver(): no syncserver_start/_stop
    monkeypatch.setattr(syncserver, "_rsbridge", lambda: types.SimpleNamespace())
    yield
    syncserver.stop()


def test_start_stop_restart(platform) -> None:
    s = settings()
    st = syncserver.start(s)
    assert st.running and st.port == s.port, st
    child = syncserver._process._child
    assert child is not None and child.poll() is None
    assert syncserver.answers()
    assert not any(k.startswith("SYNC_USER") for k in os.environ)

    syncserver.stop()
    assert child.poll() is not None
    assert not syncserver.status().running
    with pytest.raises(OSError):
        urllib.request.urlopen(f"{url(st)}health", timeout=2)

    # starting again while running replaces the child on the same port
    assert syncserver.start(s).running
    first = syncserver._process._child
    assert syncserver.start(s).running and syncserver.answers()
    assert first.poll() is not None


def test_port_in_use(platform) -> None:
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        st = syncserver.start(settings(port=busy.getsockname()[1]))
    assert not st.running
    assert "already in use" in st.error, st.error
    assert syncserver._process._child is None


def test_round_trip(platform, tmp_path) -> None:
    s = settings()
    st = syncserver.start(s)
    a = new_col(tmp_path / "a" / "collection.anki2")
    b = new_col(tmp_path / "b" / "collection.anki2")
    try:
        add_note(a, "from a")
        auth_a = login(a, s, url(st))
        auth_b = login(b, s, url(st))
        assert sync(a, auth_a, upload=True) in (Required.FULL_SYNC, Required.FULL_UPLOAD)
        assert sync(b, auth_b, upload=False) in (Required.FULL_SYNC, Required.FULL_DOWNLOAD)
        assert fronts(b) == {"from a"}
        add_note(b, "from b")
        assert sync(b, auth_b) in NORMAL
        assert sync(a, auth_a) in NORMAL
        assert fronts(a) == {"from a", "from b"}
        assert syncserver.has_data(s)
    finally:
        a.close()
        b.close()
