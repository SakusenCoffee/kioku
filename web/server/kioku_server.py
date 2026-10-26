"""Kioku server mode: one copy of the collection on the server, the browser
only runs Kioku's interface (docs/server.md).

tools/serve.py loads this module when KIOKU_DATA is set. It runs Anki's
Rust core natively (the `anki` package from PyPI, the same version as the
wasm build) and answers:

- backend calls from the app (python/kioku_platform/remote.py), over a
  socket that Emscripten turns into a WebSocket to the relay target
  `kioku-backend:1`, handled here instead of being passed on over TCP;
- /__kioku/server.json, /__kioku/home/... (the app's small files: profiles,
  preferences, add-ons; shell/server.js), /__kioku/media/<file> (the open
  collection's media) and the login page.

One device at a time uses the collection (the lease): opening it on a
second device asks to take over, and the first one is told on its next
call. Every call goes to the one backend, so there is nothing to merge.

Environment: KIOKU_DATA (folder for everything), KIOKU_AUTH (`password`,
the default, or `none` when the reverse proxy does it), KIOKU_PASSWORD
(or KIOKU_PASSWORD_FILE), KIOKU_LEASE_SECONDS (60), KIOKU_IDLE_MINUTES
(10: the collection is closed after this long without calls and opened
again on the next one).
"""

from __future__ import annotations

import hashlib
import hmac
import inspect
import json
import logging
import mimetypes
import os
import re
import secrets
import shutil
import socket
import struct
import threading
import time
import urllib.parse
import uuid
import zlib
from typing import Any

logger = logging.getLogger("kioku.server")

TARGET = "kioku-backend:1"
DATA = os.path.realpath(os.environ["KIOKU_DATA"])
HOME = os.path.join(DATA, "home")
TMP = os.path.join(DATA, "tmp")
LEASE_SECONDS = float(os.environ.get("KIOKU_LEASE_SECONDS", "60"))
IDLE_SECONDS = float(os.environ.get("KIOKU_IDLE_MINUTES", "10")) * 60
AUTH = os.environ.get("KIOKU_AUTH", "password")
COOKIE = "kioku_auth"

# reply status (the high bit marks a zlib-compressed body, both ways)
OK, ERROR, FAILED, BUSY, TAKEN = range(5)
COMPRESSED = 0x80
COMPRESS_OVER = 4096

# files of a profile that stay on the server, not mirrored into the app
# (shell/server.js has the same pattern)
SERVER_ONLY = re.compile(r"(^|/)(collection\.anki2[^/]*|collection\.media[^/]*|backups)(/|$)")


def method_names() -> dict[tuple[int, int], str]:
    """(service, method) -> name, from Anki's generated backend."""
    from anki import _backend_generated

    names = {}
    for block in inspect.getsource(_backend_generated).split("\n    def ")[1:]:
        if call := re.search(r"self\._run_command\((\d+), (\d+)", block):
            names[(int(call[1]), int(call[2]))] = re.match(r"\w+", block)[0].removesuffix("_raw")
    return names


class Collection:
    """The one backend, its open collection and the lease."""

    def __init__(self) -> None:
        self.names = method_names()
        self.ids = {name: key for key, name in self.names.items()}
        self.backend: Any = None
        self.lock = threading.RLock()
        self.holder: str | None = None
        self.last = 0.0
        self.open_request: bytes | None = None
        self.open = False
        self.inflight = 0
        self.media_folder: str | None = None
        threading.Thread(target=self._close_when_idle, daemon=True).start()

    def start(self, langs: list[str]) -> None:
        with self.lock:
            if self.backend is None:
                from anki._backend import RustBackend

                self.backend = RustBackend(langs=langs or ["en"])

    def call(self, client: str, service: int, method: int, data: bytes, take_over: bool) -> tuple[int, bytes]:
        name = self.names.get((service, method), "")
        return self._call(client, name, data, take_over, lambda: self.backend._backend.command(service, method, data))

    def db(self, client: str, data: bytes) -> tuple[int, bytes]:
        """Anki's col.db (DBProxy), which has a call of its own."""
        return self._call(client, "db_command", data, False, lambda: self.backend._backend.db_command(data))

    def _call(self, client: str, name: str, data: bytes, take_over: bool, run: Any) -> tuple[int, bytes]:
        with self.lock:
            if self.holder not in (None, client):
                if name == "close_collection":
                    return OK, b""
                if name != "open_collection":
                    return TAKEN, b""
                if time.time() - self.last < LEASE_SECONDS and not take_over:
                    return BUSY, b""
            if name == "open_collection":
                # the other device's session (or this tab's before a reload)
                self._close()
                # a new profile's folder may not be saved here yet (server.js)
                from anki import collection_pb2

                folder = os.path.dirname(collection_pb2.OpenCollectionRequest.FromString(data).collection_path)
                if inside(folder, HOME):
                    os.makedirs(folder, exist_ok=True)
            elif not self.open and self.open_request and self.holder == client:
                self._run("open_collection", self.open_request)
                self.open = True
            self.inflight += 1
            self.last = time.time()
        try:
            out = run()
        except Exception as error:
            return ERROR, bytes(error.args[0])
        finally:
            with self.lock:
                self.inflight -= 1
        with self.lock:
            if name == "open_collection":
                from anki import collection_pb2

                self.holder, self.open_request, self.open = client, data, True
                self.media_folder = collection_pb2.OpenCollectionRequest.FromString(data).media_folder_path
            elif name == "close_collection":
                self.holder, self.open_request, self.open = None, None, False
        return OK, out

    def release(self, client: str) -> None:
        """The client's tab went away: others may open without asking."""
        with self.lock:
            if self.holder == client:
                self.last = 0.0

    def _run(self, name: str, data: bytes) -> bytes:
        return self.backend._backend.command(*self.ids[name], data)

    def _close(self) -> None:
        if not self.open:
            return
        from anki import collection_pb2

        try:
            self._run("close_collection", collection_pb2.CloseCollectionRequest().SerializeToString())
        except Exception:
            logger.exception("closing the collection")
        self.open = False

    def _close_when_idle(self) -> None:
        while True:
            time.sleep(30)
            with self.lock:
                if self.open and not self.inflight and time.time() - self.last > IDLE_SECONDS:
                    logger.info("closing the idle collection")
                    self._close()

    def shutdown(self) -> None:
        with self.lock:
            self._close()


COLLECTION = Collection()


def inside(path: str, folder: str) -> bool:
    path, folder = os.path.realpath(path), os.path.realpath(folder)
    return path == folder or path.startswith(folder + os.sep)


def connect() -> socket.socket:
    """A socket for tools/serve.py's relay: the other end is served here."""
    ours, theirs = socket.socketpair()
    threading.Thread(target=_serve, args=(theirs,), daemon=True).start()
    return ours


def _serve(sock: socket.socket) -> None:
    client, reader = "", sock.makefile("rb")
    try:
        while True:
            head = reader.read(4)
            if len(head) < 4:
                return
            body = reader.read(struct.unpack(">I", head)[0])
            kind, payload = body[0], body[1:]
            if kind & COMPRESSED:
                payload = zlib.decompress(payload)
            kind &= ~COMPRESSED
            try:
                if kind == ord("H"):
                    hello = json.loads(payload)
                    client = hello["client"]
                    COLLECTION.start(hello.get("langs", []))
                    status, out = OK, json.dumps({"home": HOME}).encode()
                else:
                    status, out = _handle(client, chr(kind), payload)
            except Exception as error:
                logger.exception("backend request")
                status, out = FAILED, str(error).encode()
            if len(out) > COMPRESS_OVER:
                status, out = status | COMPRESSED, zlib.compress(out, 1)
            sock.sendall(struct.pack(">IB", len(out) + 1, status) + out)
    except OSError:
        pass
    finally:
        sock.close()


def _handle(client: str, kind: str, payload: bytes) -> tuple[int, bytes]:
    if kind == "D":
        return COLLECTION.db(client, payload)
    if kind == "C":
        service, method, flags = struct.unpack(">HHB", payload[:5])
        return COLLECTION.call(client, service, method, payload[5:], bool(flags & 1))
    if kind in "UT":
        # U: a file from the app for the call that follows (an import);
        # T: a path the call writes (an export), fetched with G
        (n,) = struct.unpack(">H", payload[:2])
        name = os.path.basename(payload[2 : 2 + n].decode()) or "file"
        folder = os.path.join(TMP, uuid.uuid4().hex)
        os.makedirs(folder)
        path = os.path.join(folder, name)
        if kind == "U":
            with open(path, "wb") as f:
                f.write(payload[2 + n :])
        return OK, path.encode()
    path = payload.decode()
    if kind == "G":
        if not inside(path, TMP) or not os.path.isfile(path):
            return FAILED, b"no such file"
        with open(path, "rb") as f:
            data = f.read()
        shutil.rmtree(os.path.dirname(path), ignore_errors=True)
        return OK, data
    if kind == "E":
        return OK, b"1" if inside(path, DATA) and os.path.exists(path) else b"0"
    return FAILED, f"unknown request {kind!r}".encode()


# HTTP: tools/serve.py hands requests for /__kioku/ here
##########################################################################


def _secret() -> bytes:
    path = os.path.join(DATA, ".secret")
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(secrets.token_bytes(32))
        os.chmod(path, 0o600)
    with open(path, "rb") as f:
        return f.read()


def _password() -> str:
    if path := os.environ.get("KIOKU_PASSWORD_FILE"):
        with open(path, encoding="utf8") as f:
            return f.read().strip()
    return os.environ.get("KIOKU_PASSWORD", "")


def _token() -> str:
    return hmac.new(_secret(), _password().encode(), hashlib.sha256).hexdigest()


def check_settings() -> None:
    for folder in (HOME, TMP):
        os.makedirs(folder, exist_ok=True)
    shutil.rmtree(TMP, ignore_errors=True)
    os.makedirs(TMP, exist_ok=True)
    if AUTH not in ("password", "none"):
        raise SystemExit(f"KIOKU_AUTH must be 'password' or 'none', not {AUTH!r}")
    if AUTH == "password" and not _password():
        raise SystemExit("set KIOKU_PASSWORD (or KIOKU_PASSWORD_FILE), or KIOKU_AUTH=none behind a proxy that logs in")


# reachable without logging in: the login page, and what browsers fetch
# without cookies (the installable app's manifest and icons)
PUBLIC = ("/__kioku/login", "/manifest.webmanifest", "/icons/")


def authorized(handler: Any) -> bool:
    if AUTH == "none" or handler.path.startswith(PUBLIC):
        return True
    cookies = dict(
        part.strip().split("=", 1) for part in handler.headers.get("Cookie", "").split(";") if "=" in part
    )
    return hmac.compare_digest(cookies.get(COOKIE, ""), _token())


def refuse(handler: Any) -> None:
    if handler.path.split("?")[0] in ("/", "/app.html"):
        handler.send_response(302)
        handler.send_header("Location", "/__kioku/login")
        handler.end_headers()
    else:
        handler.send_error(401)


LOGIN_PAGE = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Kioku</title><style>body{font:16px system-ui;display:grid;place-items:center;height:90vh;margin:0 16px}
form{display:grid;gap:12px;max-width:320px;width:100%}input,button{font:inherit;padding:10px}
@media(prefers-color-scheme:dark){body{background:#222;color:#eee}}</style>
<form method="post"><h1>Kioku</h1>{error}<input type="password" name="password" placeholder="Password" autofocus>
<button>Log in</button></form>"""


def handle(handler: Any, method: str) -> None:
    url = urllib.parse.urlsplit(handler.path)
    path = url.path[len("/__kioku/") :]
    if path == "login":
        _login(handler, method)
    elif path == "release" and method == "POST":
        COLLECTION.release(handler.rfile.read(int(handler.headers.get("Content-Length", 0))).decode())
        _send(handler, b"", "text/plain")
    elif path == "server.json" and method == "GET":
        _send(handler, json.dumps({"home": HOME}).encode(), "application/json")
    elif path == "home" and method == "GET":
        _send(handler, json.dumps(_home_list()).encode(), "application/json")
    elif path.startswith("home/"):
        _home_file(handler, method, urllib.parse.unquote(path[len("home/") :]), "dir=1" in url.query)
    elif path.startswith("media/") and method in ("GET", "HEAD"):
        _media(handler, urllib.parse.unquote(path[len("media/") :]))
    else:
        handler.send_error(404)


def _send(handler: Any, data: bytes, content_type: str, status: int = 200) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    if handler.command != "HEAD":
        handler.wfile.write(data)


def _login(handler: Any, method: str) -> None:
    error = ""
    if method == "POST" and AUTH == "password":
        body = handler.rfile.read(int(handler.headers.get("Content-Length", 0))).decode()
        given = urllib.parse.parse_qs(body).get("password", [""])[0]
        if hmac.compare_digest(given.encode(), _password().encode()):
            secure = handler.headers.get("X-Forwarded-Proto") == "https" or bool(os.environ.get("KIOKU_TLS"))
            handler.send_response(303)
            handler.send_header(
                "Set-Cookie",
                f"{COOKIE}={_token()}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000" + ("; Secure" if secure else ""),
            )
            handler.send_header("Location", "/app.html")
            handler.end_headers()
            return
        time.sleep(1)
        error = "<p>Wrong password.</p>"
    _send(handler, LOGIN_PAGE.replace("{error}", error).encode(), "text/html; charset=utf-8")


def _home_list() -> dict[str, bool]:
    """Relative path -> is a folder, for the app's small files."""
    found = {}
    for folder, dirs, files in os.walk(HOME):
        rel = os.path.relpath(folder, HOME)
        rel = "" if rel == "." else rel + "/"
        dirs[:] = [d for d in dirs if not SERVER_ONLY.search(rel + d)]
        for d in dirs:
            found[rel + d] = True
        for f in files:
            if not SERVER_ONLY.search(rel + f):
                found[rel + f] = False
    return found


def _home_file(handler: Any, method: str, rel: str, is_dir: bool) -> None:
    path = os.path.join(HOME, rel)
    if SERVER_ONLY.search(rel) or not inside(os.path.dirname(path) or HOME, HOME) or ".." in rel.split("/"):
        handler.send_error(403)
        return
    if method == "GET":
        if not os.path.isfile(path):
            handler.send_error(404)
            return
        with open(path, "rb") as f:
            _send(handler, f.read(), "application/octet-stream")
        return
    if method == "PUT":
        if is_dir:
            os.makedirs(path, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            data = handler.rfile.read(int(handler.headers.get("Content-Length", 0)))
            with open(path + ".kioku-part", "wb") as f:
                f.write(data)
            os.replace(path + ".kioku-part", path)
    elif method == "DELETE":
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            os.remove(path)
    _send(handler, b"", "text/plain")


def _media(handler: Any, name: str) -> None:
    folder = COLLECTION.media_folder
    path = os.path.join(folder or "", name)
    if not folder or not inside(path, os.path.realpath(folder)) or not os.path.isfile(path):
        handler.send_error(404)
        return
    with open(path, "rb") as f:
        _send(handler, f.read(), mimetypes.guess_type(name)[0] or "application/octet-stream")


__all__ = ["TARGET", "authorized", "check_settings", "connect", "handle", "refuse", "COLLECTION"]
