"""Syncing when Kioku goes to the background and comes back (Android).

Anki syncs automatically when a profile opens and closes, but a phone app is
rarely closed: it goes to the background, and is later killed there. So a
profile that syncs with the sync server on this phone (the way it shares
cards with AnkiDroid) also syncs:

- when Kioku goes to the background, if it has changes to send: a normal
  sync only, without media and without asking anything. Kioku's activity
  waits for it in onPause (and onStop) for a moment (kioku_platform.
  watch_background), so AnkiDroid, started next, usually finds Kioku's
  changes on the server. Anything else (a full sync is needed, an error) is
  left for when Kioku is back.
- when Kioku comes back after a while: Anki's own sync, the one behind the
  Sync button, which asks before any full sync and shows errors.

Only with Anki's "Automatically sync on profile open/close" on (Preferences
› Syncing), and only while the profile's sync server is the one in this app.
"""

from __future__ import annotations

import logging
import time

from kioku import syncserver

logger = logging.getLogger("kioku.switchsync")

# a shorter time away (a permission prompt, a quick look at a notification)
# doesn't sync when Kioku comes back
MIN_AWAY_MS = 2000

_running = [False]
# a background sync couldn't finish the job: run Anki's own once back
_attention = [False]
# came back while a background sync was still running
_back_while_running = [False]


def wanted(mw) -> bool:  # type: ignore[no-untyped-def]
    """The profile syncs with this app's server and syncs automatically."""
    if mw.col is None or mw.pm.profile is None:
        return False
    url = syncserver.own_url()
    return url is not None and mw.pm.custom_sync_url() == url and mw.can_auto_sync()


def has_local_changes(col) -> bool:  # type: ignore[no-untyped-def]
    # what Anki's offline sync status checks: modified since the last sync
    return bool(col.db.scalar("select mod > ls from col"))


def _busy(mw) -> bool:  # type: ignore[no-untyped-def]
    return bool(
        mw.progress.busy()
        or getattr(mw, "_background_op_count", 0)
        or mw.media_syncer.is_syncing()
    )


def on_background(mw, state: str) -> str:  # type: ignore[no-untyped-def]
    """From onPause/onStop: "wait" while a sync started here runs (the
    activity asks again until its time is up), else "none"."""
    if _running[0]:
        return "wait"
    if state != "pause" or not wanted(mw) or _busy(mw):
        return "none"
    if not has_local_changes(mw.col):
        return "none"
    _start_background_sync(mw)
    return "wait"


def _start_background_sync(mw) -> None:  # type: ignore[no-untyped-def]
    from aqt.operations import QueryOp

    auth = mw.pm.sync_auth()
    if auth is None:
        return
    _running[0] = True
    started = time.monotonic()

    def op(col):  # type: ignore[no-untyped-def]
        try:
            return col.sync_collection(auth, False)
        finally:
            # cleared here, not in success(): Android's UI thread is waiting
            # for it, and Qt's thread may not get to success() before onStop
            _running[0] = False
            logger.info("background sync took %d ms", (time.monotonic() - started) * 1000)

    def success(out) -> None:  # type: ignore[no-untyped-def]
        _after_sync(mw)
        mw.pm.set_host_number(out.host_number)
        if out.new_endpoint:
            mw.pm.set_current_sync_url(out.new_endpoint)
        if out.required != out.NO_CHANGES:
            # a full sync: never without asking
            logger.info("background sync: full sync needed, asking once back")
            _attention[0] = True
        _maybe_sync_after_return(mw)

    def failure(err: Exception) -> None:
        logger.warning("background sync failed: %s", err)
        _after_sync(mw)
        _attention[0] = True
        _maybe_sync_after_return(mw)

    QueryOp(parent=mw, op=op, success=success).failure(failure).run_in_background()


def _after_sync(mw) -> None:  # type: ignore[no-untyped-def]
    if mw.col is None:
        return
    # what Anki does after a sync: the scheduler and notetypes may have changed
    mw.col._load_scheduler()
    mw.col.models._clear_cache()


def _maybe_sync_after_return(mw) -> None:  # type: ignore[no-untyped-def]
    if _back_while_running[0]:
        _back_while_running[0] = False
        from kioku import ankidroid

        ankidroid._when_active(lambda: _sync_with_anki(mw))


def on_foreground(mw, away_ms: int) -> None:  # type: ignore[no-untyped-def]
    """From onResume: Anki's own sync, once Qt sees the app active."""
    if not wanted(mw):
        return
    if _running[0]:
        _back_while_running[0] = True
        return
    if away_ms < MIN_AWAY_MS and not _attention[0]:
        return
    from kioku import ankidroid

    ankidroid._when_active(lambda: _sync_with_anki(mw))


def _sync_with_anki(mw) -> None:  # type: ignore[no-untyped-def]
    if not wanted(mw) or _busy(mw) or _running[0]:
        # an import from the file picker, say: the next return syncs
        return
    _attention[0] = False
    mw._sync_collection_and_media(mw._refresh_after_sync)
