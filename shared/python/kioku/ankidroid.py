"""A Kioku profile that uses AnkiDroid's folder (Preferences > Advanced, Android).

Two modes besides Kioku's own storage, both per profile and both needing All
files access (only AnkiDroid builds that keep their folder in shared storage,
such as the GitHub "full" build with /storage/emulated/0/AnkiDroid):

MEDIA   Kioku keeps its own collection and syncs it with AnkiDroid through
        the sync server on the phone (kioku.syncserver), but reads and
        writes AnkiDroid's collection.media folder, so media exists once.
        Both apps can be open at the same time: nothing locks a media
        folder. Media sync is turned off in both apps.
FOLDER  Kioku opens AnkiDroid's collection.anki2 itself. Anki's core locks a
        collection while it is open (SQLite exclusive locking), so only one
        of the two apps can have it open; Kioku closes it whenever it goes
        to the background and reopens it when it comes back.

In both modes the media database (which tracks the folder for media sync) is
Kioku's own, in the profile folder: AnkiDroid's collection.media.db is never
opened. A profile whose AnkiDroid folder can't be opened falls back to
Kioku's own collection and says why.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass

logger = logging.getLogger("kioku.ankidroid")

OFF = "off"
MEDIA = "media"
FOLDER = "folder"
MODES = (OFF, MEDIA, FOLDER)
# FOLDER is not offered in Preferences: Anki's backups drop the collection's
# lock, so both apps could have it open (test_anki_backup_drops_the_lock)
FOLDER_READY = False

PROFILE_KEY = "kioku_ankidroid"
DEFAULT_FOLDER = "/storage/emulated/0/AnkiDroid"
# Kioku's media databases for AnkiDroid's folder, in the profile folder
MEDIA_DB = {MEDIA: "ankidroid-media.db2", FOLDER: "ankidroid-folder-media.db2"}

# AnkiDroid's application ids: release, debug, and its parallel builds
PACKAGES = ("com.ichi2.anki", "com.ichi2.anki.debug") + tuple(
    f"com.ichi2.anki.{c}" for c in "ABCDE"
)
# Collections are shared with AnkiDroid's own core in FOLDER mode; older
# AnkiDroid releases run an older core than Kioku's
MIN_VERSION = (2, 22)


@dataclass
class Source:
    mode: str = OFF
    folder: str = DEFAULT_FOLDER
    allow_delete_unused: bool = False

    @property
    def collection(self) -> str:
        return os.path.join(self.folder, "collection.anki2")

    @property
    def media(self) -> str:
        return os.path.join(self.folder, "collection.media")


def load(profile: dict | None) -> Source:
    source = Source()
    for key, value in ((profile or {}).get(PROFILE_KEY) or {}).items():
        if hasattr(source, key) and isinstance(value, type(getattr(source, key))):
            setattr(source, key, value)
    if source.mode not in MODES:
        source.mode = OFF
    return source


def store(profile: dict, source: Source) -> None:
    profile[PROFILE_KEY] = asdict(source)


def problems(source: Source) -> list[str]:
    """Why `source` can't be used now, or []."""
    if source.mode == OFF:
        return []
    import kioku_platform as platform

    found = []
    if not platform.all_files_access():
        found.append("Kioku needs All files access to read AnkiDroid's folder.")
        return found
    if not os.path.isdir(source.folder):
        found.append(f"There is no folder {source.folder}.")
        return found
    if not os.path.isdir(source.media):
        found.append(f"{source.folder} has no collection.media folder.")
    elif not os.access(source.media, os.W_OK):
        found.append(f"Kioku can't write to {source.media}.")
    if source.mode == FOLDER:
        if not os.path.isfile(source.collection):
            found.append(f"{source.folder} has no collection.anki2.")
        elif not os.access(source.collection, os.R_OK | os.W_OK):
            found.append(f"Kioku can't read and write {source.collection}.")
    return found


def find_folders(root: str = "/storage/emulated/0") -> list[str]:
    """Folders in shared storage that hold an Anki collection."""
    found = []
    candidates = [os.path.join(root, "AnkiDroid")]
    try:
        for name in sorted(os.listdir(root)):
            path = os.path.join(root, name)
            if name not in ("Android", "AnkiDroid") and os.path.isdir(path):
                candidates.append(path)
                try:
                    candidates += [os.path.join(path, sub) for sub in sorted(os.listdir(path))]
                except OSError:
                    pass
    except OSError:
        pass
    for path in candidates:
        if os.path.isfile(os.path.join(path, "collection.anki2")):
            found.append(path)
    return found


def parse_version(name: str) -> tuple[int, ...]:
    parts = []
    for piece in name.split("."):
        digits = "".join(c for c in piece if c.isdigit()) if piece else ""
        if not digits or not piece[0].isdigit():
            break
        # "0alpha6": the numeric start only
        lead = ""
        for c in piece:
            if not c.isdigit():
                break
            lead += c
        parts.append(int(lead))
        if lead != piece:
            break
    return tuple(parts)


def version_too_old(name: str) -> bool:
    version = parse_version(name)
    return bool(version) and version[: len(MIN_VERSION)] < MIN_VERSION


# Paths
######################################################################

# collection path -> (media folder, media db) for the open profile
_overrides: dict[str, tuple[str, str]] = {}


def paths(profile_folder: str, default_collection: str, source: Source) -> tuple[str, str | None]:
    """(collection path, media folder override or None) for `source`; the
    media database override goes with the folder."""
    if source.mode == FOLDER:
        return source.collection, source.media
    if source.mode == MEDIA:
        return default_collection, source.media
    return default_collection, None


def set_override(collection: str, media: str | None, media_db: str | None) -> None:
    _overrides.clear()
    if media is not None and media_db is not None:
        _overrides[os.path.abspath(collection)] = (media, media_db)


def media_paths(original):  # type: ignore[no-untyped-def]
    def media_paths_from_col_path(col_path: str) -> tuple[str, str]:
        override = _overrides.get(os.path.abspath(col_path))
        return override if override else original(col_path)

    return media_paths_from_col_path


# App integration
######################################################################

LOCKED_HELP = (
    "AnkiDroid has this collection open. Close AnkiDroid completely (Android "
    "Settings › Apps › AnkiDroid › Force stop), then try again."
)


def explain(error: Exception | str) -> str:
    text = str(error)
    # Anki's DbErrorKind::Locked: "Anki already open, or media currently syncing."
    if "locked" in text.lower() or "already open" in text.lower():
        return LOCKED_HELP
    return text


def current(mw) -> Source:  # type: ignore[no-untyped-def]
    return load(getattr(mw.pm, "profile", None))


def install() -> None:
    """Opens profiles from AnkiDroid's folder when they are set up so; does
    nothing for profiles that aren't."""
    import anki.collection
    import anki.media
    import aqt
    import aqt.main
    from aqt import gui_hooks
    from aqt.profiles import ProfileManager

    # both modules imported it by name: Collection opens the backend with
    # it, MediaManager takes its folder (served to card pages) from it
    patched = media_paths(anki.media.media_paths_from_col_path)
    anki.collection.media_paths_from_col_path = patched
    anki.media.media_paths_from_col_path = patched

    original_collection_path = ProfileManager.collectionPath

    def collection_path(self) -> str:  # type: ignore[no-untyped-def]
        source = load(self.profile)
        if source.mode == FOLDER:
            return source.collection
        return original_collection_path(self)

    ProfileManager.collectionPath = collection_path

    original_load = aqt.main.AnkiQt._loadCollection

    def load_collection(self) -> None:  # type: ignore[no-untyped-def]
        source = current(self)
        _watch_background(self, False)
        if source.mode == OFF:
            set_override("", None, None)
            return original_load(self)
        try:
            if found := problems(source):
                raise Exception("\n".join(found))
            _open(self, source)
            if source.mode == FOLDER:
                _watch_background(self, True)
        except Exception as err:
            # never leave the profile unusable: fall back to Kioku's own
            # collection and say why
            logger.warning("opening AnkiDroid's folder failed: %s", err)
            self.col = None
            source.mode = OFF
            store(self.pm.profile, source)
            self.pm.save()
            set_override("", None, None)
            original_load(self)
            message = (
                "This profile couldn't use AnkiDroid's folder, so it opened "
                f"Kioku's own collection instead.\n\n{explain(err)}\n\n"
                "Turn it on again in Preferences › Advanced."
            )
            self.progress.single_shot(500, lambda: _warn(message), False)

    aqt.main.AnkiQt._loadCollection = load_collection

    original_unload = aqt.main.AnkiQt._unloadCollection

    def unload_collection(self) -> None:  # type: ignore[no-untyped-def]
        _watch_background(self, False)
        original_unload(self)

    aqt.main.AnkiQt._unloadCollection = unload_collection

    _patch_media_check()
    _patch_colpkg_import()
    _defer_while_closed()
    gui_hooks.main_window_did_init.append(lambda: _add_menu_action(aqt.mw))


def _open(mw, source: Source) -> None:  # type: ignore[no-untyped-def]
    from anki.collection import Collection

    collection = mw.pm.collectionPath()
    media_db = os.path.join(mw.pm.profileFolder(), MEDIA_DB[source.mode])
    set_override(collection, source.media, media_db)
    mw.col = Collection(collection, backend=mw.backend)
    mw.setEnabled(True)


def _warn(text: str) -> None:
    from aqt.utils import showWarning

    showWarning(text)


def _patch_media_check() -> None:
    """Check Media's Delete Unused: in AnkiDroid's media folder a file this
    collection doesn't use may belong to a note AnkiDroid hasn't synced yet."""
    import aqt
    from aqt import mediacheck

    original = mediacheck.MediaChecker._on_trash_files

    def on_trash_files(self, fnames):  # type: ignore[no-untyped-def]
        source = current(aqt.mw)
        if source.mode != OFF and not source.allow_delete_unused:
            _warn(
                "This profile uses AnkiDroid's media folder. A file this profile "
                "doesn't use may belong to a card AnkiDroid hasn't synced yet, so "
                "deleting unused media is turned off.\n\nSync both apps first, "
                "then allow it in Preferences › Advanced."
            )
            return
        return original(self, fnames)

    mediacheck.MediaChecker._on_trash_files = on_trash_files


def _patch_colpkg_import() -> None:
    """Importing a .colpkg replaces the collection and writes media to the
    profile's own folder: not with AnkiDroid's."""
    from aqt.import_export import importing

    original = importing.ColpkgImporter.do_import

    def do_import(mw, path: str) -> None:  # type: ignore[no-untyped-def]
        if current(mw).mode != OFF:
            _warn(
                "This profile uses AnkiDroid's folder. Restoring a whole "
                "collection (.colpkg) isn't possible here; use a profile with "
                "Kioku's own collection."
            )
            return
        original(mw, path)

    importing.ColpkgImporter.do_import = staticmethod(do_import)


# Closing while in the background (FOLDER)
######################################################################
#
# Android resumes AnkiDroid only after Kioku's onPause has returned, but
# Kioku's onStop comes later, and after it Qt's event loop doesn't run until
# Kioku is back. So Kioku's activity waits in onPause (and again in onStop,
# if an operation was still running) for close_for_ankidroid(), and asks for
# reopen_after_ankidroid() on resume, ahead of the activity results and
# input that come with it (kioku_platform.watch_background).
#
# While closed, mw.col is None, so Anki's timers skip, and the Collection
# waits in _held; operations started meanwhile (an editor saving a field as
# it loses focus) wait in _deferred and run once it's open again.

_held: list = [None]
_deferred: list = []
_mod_before_close = [0]


def is_closed() -> bool:
    return _held[0] is not None


def busy(mw) -> bool:  # type: ignore[no-untyped-def]
    return bool(
        mw.progress.busy()
        or getattr(mw, "_background_op_count", 0)
        or mw.media_syncer.is_syncing()
    )


def close_for_ankidroid(mw) -> str:  # type: ignore[no-untyped-def]
    """Closes the collection so AnkiDroid can open it: "closed", "busy"
    (an operation still uses it) or "none" (nothing to close)."""
    if is_closed():
        return "closed"
    if mw.col is None or current(mw).mode != FOLDER:
        return "none"
    # busy first: a full sync has the collection's db closed meanwhile
    if busy(mw):
        return "busy"
    if mw.col.db is None:
        return "none"
    col = mw.col
    _mod_before_close[0] = col.mod
    col.close_for_full_sync()
    mw.backend.close_collection(downgrade_to_schema11=False)
    _held[0] = col
    mw.col = None
    logger.info("closed AnkiDroid's collection")
    return "closed"


def reopen_after_ankidroid(mw) -> bool:  # type: ignore[no-untyped-def]
    """Opens the collection again (if closed); on failure, offers to retry."""
    col = _held[0]
    if col is None:
        return True
    try:
        col.reopen()
    except Exception as err:
        logger.warning("reopening AnkiDroid's collection failed: %s", err)
        _when_active(lambda error=err: _show_retry(mw, error))
        return False
    _held[0] = None
    mw.col = col
    logger.info("reopened AnkiDroid's collection")
    changed = col.mod != _mod_before_close[0]
    waiting = _deferred[:]
    _deferred.clear()

    def refresh() -> None:
        from aqt import gui_hooks

        _close_retry()
        gui_hooks.collection_did_temporarily_close(col)
        # closing dropped the undo queue
        mw.update_undo_actions()
        if changed:
            # AnkiDroid changed it: refresh every screen
            mw.reset()
        for run in waiting:
            run()

    _when_active(refresh)
    return True


def _when_active(run) -> None:  # type: ignore[no-untyped-def]
    """Runs `run` once Qt has seen the app become active. On resume, Kioku
    reopens the collection before Qt hears of it; showing or hiding a window
    then makes Qt paint without a surface (SIGSEGV in eglSwapBuffers)."""
    from aqt.qt import QGuiApplication, Qt, QTimer

    app = QGuiApplication.instance()
    if app is None or app.applicationState() == Qt.ApplicationState.ApplicationActive:
        if app is None:
            run()
        else:
            QTimer.singleShot(0, run)
        return

    def on_state(state: Qt.ApplicationState) -> None:
        if state == Qt.ApplicationState.ApplicationActive:
            app.applicationStateChanged.disconnect(on_state)
            QTimer.singleShot(0, run)

    app.applicationStateChanged.connect(on_state)


def _defer_while_closed() -> None:
    """Operations started while the collection is closed run after reopening."""
    from aqt.operations import CollectionOp, QueryOp

    collection_op = CollectionOp.run_in_background

    def run_collection_op(self, *, initiator: object | None = None) -> None:  # type: ignore[no-untyped-def]
        if is_closed():
            _deferred.append(lambda: collection_op(self, initiator=initiator))
            return
        collection_op(self, initiator=initiator)

    CollectionOp.run_in_background = run_collection_op

    query_op = QueryOp.run_in_background

    def run_query_op(self) -> None:  # type: ignore[no-untyped-def]
        if is_closed():
            _deferred.append(lambda: query_op(self))
            return
        query_op(self)

    QueryOp.run_in_background = run_query_op


# the retry dialog, while AnkiDroid keeps the collection
_retry: list = [None]


def _show_retry(mw, err: Exception) -> None:  # type: ignore[no-untyped-def]
    """Not modal in the event loop sense (no exec()): Kioku coming back from
    Android's settings retries by itself, and a second failure only updates
    the text."""
    from aqt.qt import QDialog, QDialogButtonBox, QLabel, Qt, QVBoxLayout, qconnect

    text = f"Kioku can't open AnkiDroid's collection again.\n\n{explain(err)}"
    if _retry[0] is not None:
        _retry[0].findChild(QLabel).setText(text)
        return

    class RetryDialog(QDialog):
        # only its buttons close it (Back, Escape)
        def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
            event.ignore()

        def reject(self) -> None:
            pass

    dialog = RetryDialog(mw)
    dialog.setWindowTitle("AnkiDroid's collection")
    dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
    layout = QVBoxLayout(dialog)
    label = QLabel(text)
    label.setWordWrap(True)
    layout.addWidget(label)
    # a button box: kioku.windows shows the dialog as a card, without a
    # title bar and its Back button
    buttons = QDialogButtonBox(Qt.Orientation.Vertical)
    layout.addWidget(buttons)
    role = QDialogButtonBox.ButtonRole.ActionRole
    qconnect(buttons.addButton("Try again", role).clicked, lambda: reopen_after_ankidroid(mw))
    qconnect(buttons.addButton("AnkiDroid app info…", role).clicked, _open_ankidroid_info)
    qconnect(buttons.addButton("Quit Kioku", role).clicked, lambda: _quit(mw))
    _retry[0] = dialog
    dialog.show()


def _close_retry() -> None:
    dialog, _retry[0] = _retry[0], None
    if dialog is not None:
        dialog.hide()
        dialog.deleteLater()


def _open_ankidroid_info() -> None:
    import kioku_platform as platform

    installed = platform.app_versions(list(PACKAGES))
    package = next((p for p in PACKAGES if p in installed), PACKAGES[0])
    platform.open_app_details(package)


def _quit(mw) -> None:  # type: ignore[no-untyped-def]
    # the collection is closed and saved; nothing else to write
    mw.pm.save()
    os._exit(0)


def _watch_background(mw, on: bool) -> None:  # type: ignore[no-untyped-def]
    import kioku_platform as platform

    watch = getattr(platform, "watch_background", None)
    if watch is None:
        return
    if on:
        watch(lambda _state: close_for_ankidroid(mw), lambda: reopen_after_ankidroid(mw))
    else:
        watch(None, None)


def _add_menu_action(mw) -> None:  # type: ignore[no-untyped-def]
    """Tools › Switch to AnkiDroid (FOLDER profiles only)."""
    from aqt.qt import QAction, qconnect

    action = QAction("Switch to AnkiDroid", mw)
    mw.form.menuTools.addAction(action)

    def switch() -> None:
        import kioku_platform as platform

        if close_for_ankidroid(mw) == "busy":
            _warn("Kioku is still busy with the collection; try again in a moment.")
            return
        try:
            platform.launch_ankidroid()
        except Exception as err:
            reopen_after_ankidroid(mw)
            _warn(f"Couldn't start AnkiDroid: {err}")

    qconnect(action.triggered, switch)

    def update() -> None:
        action.setVisible(current(mw).mode == FOLDER)

    qconnect(mw.form.menuTools.aboutToShow, update)
    update()
