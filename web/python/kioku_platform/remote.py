"""Server mode (docs/server.md): the collection is on the Kioku server
(server/kioku_server.py), the browser only runs the interface.

Calls to Anki's Rust core go to the server, except translations and the
card-rendering helpers that only transform text (LOCAL); those run here, so
most of the reviewer's calls never leave the browser. Paths in calls are
translated: /home/web_user is the server's home folder, other files (a
picked .apkg, an export) are uploaded before the call or fetched after it.

Each thread has its own socket to `kioku-backend:1`, which the app page
sends to the server's relay (shell/kioku-web.js). shell/storage.js sets
KIOKU_SERVER_HOME and KIOKU_CLIENT (one per browser) when
the page was served by a Kioku server.
"""

from __future__ import annotations

import importlib
import inspect
import json
import logging
import os
import re
import socket
import struct
import threading
import urllib.parse
import zlib
from typing import Any, Callable

logger = logging.getLogger("kioku.remote")

LOCAL_HOME = "/home/web_user"
SERVER_HOME = os.environ.get("KIOKU_SERVER_HOME", "")
CLIENT = os.environ.get("KIOKU_CLIENT", "")
TARGET = ("kioku-backend", 1)

# no collection data needed: translations, and text transforms (which
# Anki's core has on the collection, so a scratch one is opened here)
LOCAL = {"translate_string", "format_timespan", "i18n_resources"}
LOCAL_WITH_COLLECTION = {
    "extract_av_tags",
    "extract_latex",
    "encode_iri_paths",
    "decode_iri_paths",
    "strip_html",
    "html_to_text_line",
    "render_markdown",
    "compare_answer",
    "extract_cloze_for_typing",
}
# reads repeated many times per card; kept until the next other call
# (only this device changes the collection while it holds the lease)
CACHED = {
    "get_config_json",
    "get_config_bool",
    "get_config_string",
    "get_deck_legacy",
    "get_deck_config_legacy",
    "get_notetype_legacy",
    "get_current_deck",
}
# fetched ahead in one round trip, used once (Browse's rows)
PREFETCHED = {"browser_row_for_id"}
PREFETCH_ROWS = 30
# reads that leave the cache alone
READS = CACHED | {
    "browser_row_for_id",
    "get_card",
    "get_note",
    "get_queued_cards",
    "describe_next_states",
    "get_undo_status",
    "latest_progress",
    "deck_tree",
    "get_deck_names",
    "note_fields_check",
    "get_cloze_field_ords",
    "studied_today",
    "search_cards",
    "search_notes",
    "render_existing_card",
    "state_is_leech",
    "congrats_info",
    "get_notetype_names",
    "tag_tree",
}

OK, ERROR, FAILED, BUSY, TAKEN = range(5)
COMPRESSED = 0x80
COMPRESS_OVER = 4096


class LeaseLost(Exception):
    """Kioku was opened on another device."""


def enabled() -> bool:
    return bool(SERVER_HOME)


def install() -> None:
    """Route Anki's backend calls; runs before Anki opens a collection."""
    from anki import _backend_generated
    from anki._backend import RustBackend

    methods = _methods(_backend_generated)
    original = RustBackend._run_command
    cache = _cache

    def run_command(self: Any, service: int, method: int, input: bytes) -> bytes:
        name, message_type = methods.get((service, method), ("", None))
        if name in LOCAL:
            return original(self, service, method, input)
        if name in LOCAL_WITH_COLLECTION:
            _open_scratch_collection(self, methods)
            return original(self, service, method, input)
        key = (service, method, input)
        if name in CACHED and key in cache:
            return cache[key]
        if name in PREFETCHED and (ahead := cache.pop(key, None)) is not None:
            return ahead
        if name not in READS:
            cache.clear()
        output = _call(service, method, input, message_type if name in _PATH_METHODS else None)
        if name in CACHED:
            cache[key] = output
        elif name not in READS:
            cache.clear()
        return output

    def db_command(self: Any, input: dict[str, Any]) -> Any:
        from anki.utils import from_json_bytes, to_json_bytes

        if input.get("kind") != "query" or not str(input.get("sql", "")).lstrip().lower().startswith("select"):
            cache.clear()
        return from_json_bytes(_result(*_send("D", to_json_bytes(input))))

    _PATH_METHODS.update(name for name, message_type in methods.values() if message_type and _has_paths(message_type.DESCRIPTOR))
    RustBackend._run_command = run_command  # type: ignore[method-assign]
    RustBackend._db_command = db_command  # type: ignore[method-assign]
    _patch_media()
    _patch_browse(methods)
    logger.info("server mode: collection on the server, home %s", SERVER_HOME)


_PATH_METHODS: set[str] = set()
# (service, method, request) -> response: CACHED reads and PREFETCHED rows,
# dropped by any other call
_cache: dict[tuple[int, int, bytes], bytes] = {}


def _methods(module: Any) -> dict[tuple[int, int], tuple[str, Any]]:
    """(service, method) -> (name, request message class), from Anki's
    generated backend (server/kioku_server.py reads it the same way)."""
    found: dict[tuple[int, int], tuple[str, Any]] = {}
    for block in inspect.getsource(module).split("\n    def ")[1:]:
        call = re.search(r"self\._run_command\((\d+), (\d+)", block)
        if not call:
            continue
        name = re.match(r"\w+", block)[0]  # type: ignore[index]
        key = (int(call[1]), int(call[2]))
        message = re.search(r"message = (anki\.\w+)\.([\w.]+)\(", block)
        if message:
            cls: Any = importlib.import_module(message[1])
            for part in message[2].split("."):
                cls = getattr(cls, part)
            found[key] = (name, cls)
        elif key not in found:
            found[key] = (name.removesuffix("_raw"), None)
    return found


def _path_field(name: str) -> bool:
    return "path" in name or "folder" in name


def _has_paths(descriptor: Any, depth: int = 0) -> bool:
    for field in descriptor.fields:
        if field.type == field.TYPE_STRING and _path_field(field.name):
            return True
        if field.type == field.TYPE_MESSAGE and depth < 3 and _has_paths(field.message_type, depth + 1):
            return True
    return False


def _repeated(field: Any) -> bool:
    # protobuf 6 dropped `label`
    if hasattr(field, "is_repeated"):
        return bool(field.is_repeated)
    return field.label == field.LABEL_REPEATED


def _walk(message: Any, fix: Callable[[str], str | None]) -> None:
    for field, value in message.ListFields():
        if field.type == field.TYPE_STRING and _path_field(field.name):
            if _repeated(field):
                for i, item in enumerate(value):
                    if (new := fix(item)) is not None:
                        value[i] = new
            elif (new := fix(value)) is not None:
                setattr(message, field.name, new)
        elif field.type == field.TYPE_MESSAGE and not field.message_type.GetOptions().map_entry:
            for item in value if _repeated(field) else [value]:
                _walk(item, fix)


def server_path(path: str) -> str | None:
    if path == LOCAL_HOME or path.startswith(LOCAL_HOME + "/"):
        return SERVER_HOME + path[len(LOCAL_HOME) :]
    return None


def _call(service: int, method: int, input: bytes, message_type: Any) -> bytes:
    fetch: list[tuple[str, str]] = []
    if message_type is not None:
        message = message_type.FromString(input)

        def fix(path: str) -> str | None:
            if not path.startswith("/"):
                return None
            if (on_server := server_path(path)) is not None:
                if os.path.isdir(path):
                    # made here by Anki (pm.backupFolder()): there too
                    _request("M", on_server.encode())
                return on_server
            name = os.path.basename(path).encode()
            if os.path.isfile(path):
                with open(path, "rb") as f:
                    return _request("U", struct.pack(">H", len(name)) + name + f.read()).decode()
            if os.path.isdir(os.path.dirname(path)):
                # written by the call: fetched afterwards
                remote = _request("T", struct.pack(">H", len(name)) + name).decode()
                fetch.append((path, remote))
                return remote
            return None

        _walk(message, fix)
        input = message.SerializeToString()
    status, output = _send("C", struct.pack(">HHB", service, method, 0) + input)
    if status == BUSY:
        if not _take_over():
            _lease_lost()
        status, output = _send("C", struct.pack(">HHB", service, method, 1) + input)
    output = _result(status, output)
    for local, remote in fetch:
        with open(local, "wb") as f:
            f.write(_request("G", remote.encode()))
    return output


def _result(status: int, output: bytes) -> bytes:
    if status == TAKEN:
        _lease_lost()
    if status == ERROR:
        from anki import backend_pb2
        from anki._backend import backend_exception_to_pylib

        raise backend_exception_to_pylib(backend_pb2.BackendError.FromString(output))
    if status != OK:
        raise Exception(f"Kioku server: {output.decode(errors='replace')}")
    return output


def _take_over() -> bool:
    if threading.current_thread() is not threading.main_thread():
        return False
    from aqt.utils import askUser

    return askUser("Kioku is open on another device. Use it here instead? The other device will stop using it.")


def _lease_lost() -> None:
    """The page says so (shell/server.js; its button reloads) and the GUI
    thread stops there, rather than Anki showing errors for every call."""
    if threading.current_thread() is threading.main_thread():
        _park()
    from aqt import mw

    mw.taskman.run_on_main(_park)
    raise LeaseLost("Kioku is open on another device.")


def _park() -> None:
    import _kioku_web

    from . import web

    web.js("takenOver")
    while True:
        # yields to the browser, so the page and its button keep working
        _kioku_web.sleep(1000)


# transport
##########################################################################

_local = threading.local()


def _langs() -> list[str]:
    import anki.lang

    return [getattr(anki.lang, "current_lang", "") or "en"]


def _connect() -> socket.socket:
    # a timeout makes Python wait with poll(), which yields to the browser
    # on the main thread (src/main.cpp) so the WebSocket's data arrives
    sock = socket.create_connection(TARGET, timeout=3600)
    _write(sock, "H", json.dumps({"client": CLIENT, "langs": _langs()}).encode())
    _read(sock)
    return sock


def _send(kind: str, payload: bytes) -> tuple[int, bytes]:
    sock = getattr(_local, "sock", None)
    if sock is not None:
        try:
            _write(sock, kind, payload)
        except OSError:
            # closed meanwhile (server restart, network): nothing was sent
            sock.close()
            sock = None
    if sock is None:
        sock = _local.sock = _connect()
        _write(sock, kind, payload)
    try:
        return _read(sock)
    except OSError:
        _local.sock = None
        sock.close()
        raise


def _send_many(kind: str, payloads: list[bytes]) -> list[tuple[int, bytes]]:
    """Requests sent together and answered in order: one round trip."""
    sock = getattr(_local, "sock", None) or _connect()
    _local.sock = sock
    try:
        for payload in payloads:
            _write(sock, kind, payload)
        return [_read(sock) for _ in payloads]
    except OSError:
        _local.sock = None
        sock.close()
        raise


def _request(kind: str, payload: bytes) -> bytes:
    status, output = _send(kind, payload)
    if status != OK:
        raise Exception(f"Kioku server: {output.decode(errors='replace')}")
    return output


def _write(sock: socket.socket, kind: str, payload: bytes) -> None:
    code = ord(kind)
    if len(payload) > COMPRESS_OVER:
        code, payload = code | COMPRESSED, zlib.compress(payload, 1)
    sock.sendall(struct.pack(">IB", len(payload) + 1, code) + payload)


def _read_exact(sock: socket.socket, n: int) -> bytes:
    parts, left = [], n
    while left:
        part = sock.recv(min(left, 1 << 20))
        if not part:
            raise ConnectionError("Kioku server closed the connection")
        parts.append(part)
        left -= len(part)
    return b"".join(parts)


def _read(sock: socket.socket) -> tuple[int, bytes]:
    (n,) = struct.unpack(">I", _read_exact(sock, 4))
    body = _read_exact(sock, n)
    status, output = body[0], body[1:]
    if status & COMPRESSED:
        status, output = status & ~COMPRESSED, zlib.decompress(output)
    return status, output


# the scratch collection for LOCAL_WITH_COLLECTION, media
##########################################################################

_scratch = threading.Lock()


def _open_scratch_collection(backend: Any, methods: dict) -> None:
    if getattr(backend, "_kioku_scratch", False):
        return
    with _scratch:
        if getattr(backend, "_kioku_scratch", False):
            return
        from anki import collection_pb2

        key = next(k for k, (name, _) in methods.items() if name == "open_collection")
        folder = "/tmp/kioku-scratch"
        os.makedirs(folder, exist_ok=True)
        request = collection_pb2.OpenCollectionRequest(
            collection_path=f"{folder}/collection.anki2",
            media_folder_path=f"{folder}/media",
            media_db_path=f"{folder}/media.db",
        )
        backend._backend.command(*key, request.SerializeToString())
        backend._kioku_scratch = True


def _patch_browse(methods: dict) -> None:
    """Browse asks for its rows one call each: on a miss, the next rows
    that need fetching are asked for together."""
    from aqt.browser.table.model import DataModel

    key, request = next((k, cls) for k, (name, cls) in methods.items() if name == "browser_row_for_id" and cls)
    original = DataModel._fetch_row_and_update_cache

    def fetch_row(self: Any, index: Any, item: int, old_row: Any) -> Any:
        if (*key, request(val=item).SerializeToString()) not in _cache:
            ids = [
                i
                for i in self._items[index.row() : index.row() + PREFETCH_ROWS]
                if i == item or (row := self._rows.get(i)) is None or row.is_stale(self._stale_cutoff)
            ]
            inputs = [request(val=i).SerializeToString() for i in ids]
            if len(inputs) > 1:
                try:
                    replies = _send_many("C", [struct.pack(">HHB", *key, 0) + i for i in inputs])
                except OSError:
                    replies = []
                for input, (status, output) in zip(inputs, replies):
                    if status == OK:
                        _cache[(*key, input)] = output
        return original(self, index, item, old_row)

    DataModel._fetch_row_and_update_cache = fetch_row  # type: ignore[method-assign]


def media_url(filename: str) -> str:
    return "/__kioku/media/" + urllib.parse.quote(filename)


def _patch_media() -> None:
    """Media files are on the server: Anki's check for one."""
    import anki.collection  # noqa: F401 (anki.media can't be imported first)
    from anki.media import MediaManager

    def have(self: MediaManager, fname: str) -> bool:
        path = server_path(os.path.join(self.dir(), fname))
        return path is not None and _request("E", path.encode()) == b"1"

    MediaManager.have = have  # type: ignore[method-assign]


def audio_player(taskman: Any, media_folder: str) -> Any:
    """Plays media files from the server's URL, not the wasm file system."""
    from . import audio, web

    class ServerAudioPlayer(audio.WebAudioPlayer):
        def play(self, tag: Any, on_done: Any) -> None:
            token = self._done.start(on_done)
            web.js("play", media_url(tag.filename), token)
            audio.gui_hooks.av_player_did_begin_playing(self, tag)

    return ServerAudioPlayer(taskman, media_folder)
