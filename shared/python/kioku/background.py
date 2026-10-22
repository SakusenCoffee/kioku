"""What the open profile does when Kioku goes to the background and comes
back (Android): close AnkiDroid's collection (kioku.ankidroid, FOLDER), or
sync with the server on this phone (kioku.switchsync).

Kioku's activity waits in onPause and onStop for on_background() only
while refresh() found something to do, so other profiles don't hold up
switching apps.
"""

from __future__ import annotations

from kioku import ankidroid, switchsync


def _closes_collection(mw) -> bool:  # type: ignore[no-untyped-def]
    return ankidroid.current(mw).mode == ankidroid.FOLDER and ankidroid.FOLDER_READY


def refresh(mw) -> None:  # type: ignore[no-untyped-def]
    """Call after the profile or its sync settings changed."""
    import kioku_platform as platform

    watch = getattr(platform, "watch_background", None)
    if watch is None:
        return
    if mw.col is not None and (_closes_collection(mw) or switchsync.wanted(mw)):
        watch(lambda state: on_background(mw, state), lambda away: on_foreground(mw, away))
    else:
        watch(None, None)


def stop() -> None:
    import kioku_platform as platform

    watch = getattr(platform, "watch_background", None)
    if watch is not None:
        watch(None, None)


def on_background(mw, state: str) -> str:  # type: ignore[no-untyped-def]
    """ "closed", "none", "busy" (can't close yet: asked again) or "wait"
    (a sync is running: asked again)."""
    if ankidroid.is_closed() or _closes_collection(mw):
        return ankidroid.close_for_ankidroid(mw)
    return switchsync.on_background(mw, state)


def on_foreground(mw, away_ms: int) -> None:  # type: ignore[no-untyped-def]
    if ankidroid.is_closed():
        ankidroid.reopen_after_ankidroid(mw)
        return
    switchsync.on_foreground(mw, away_ms)
