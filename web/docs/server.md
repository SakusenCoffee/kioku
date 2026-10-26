# Server mode (self-hosting, Docker)

The same web build, served by a Kioku server, keeps the collection on the
server: the browser runs Kioku's interface and nothing else. There is one
copy of each collection, so there is no syncing between the browser and
the server and nothing to merge
([issue #5](https://github.com/krmanik/kioku/issues/5)). How to run it:
the manual's [Self-hosted server](../../docs/manual/src/install/self-hosted.md).

```
Browser (kioku.wasm)                         Server (tools/serve.py + KIOKU_DATA)
──────────────────────                       ────────────────────────────────────
Anki's Python + Qt + add-ons                 server/kioku_server.py
local Rust core: translations,               Anki's Rust core (PyPI `anki`, same
  text-only card rendering helpers             version as the app): the collection
backend calls ─── WebSocket /__relay/kioku-backend:1 ──▶ lease, calls, file transfer
media in pages ── service worker ─── /__kioku/media/… ─▶ open collection's media
small files ───── shell/server.js ── /__kioku/home/… ──▶ $KIOKU_DATA/home
```

## How it works

- **Detection.** `shell/server.js` fetches `/__kioku/server.json`; only a
  Kioku server answers it. `shell/storage.js` then loads and saves
  `/home/web_user` from the server instead of IndexedDB and sets
  `KIOKU_SERVER_HOME`/`KIOKU_CLIENT` for Python, and
  `kioku_platform.remote.install()` runs. Without a server (Cloudflare,
  plain `serve.py`) nothing changes.
- **Backend calls** (`python/kioku_platform/remote.py`). Every call Anki's
  Python makes to its Rust core passes `RustBackend._run_command` (and
  `_db_command` for `col.db`). The method comes from the
  `(service, method)` pair, read from Anki's generated
  `_backend_generated.py`, so new Anki releases need no table update.
  Translations and the card-rendering helpers that only transform text
  (`extract_av_tags`, `encode_iri_paths`, …) run in the browser against a
  scratch collection; everything else goes to the server. Each thread has
  its own socket to `kioku-backend:1`, which the page's WebSocket wrapper
  sends to the relay, and `serve.py` hands to `kioku_server` instead of a
  TCP host. Frames: 4-byte length, a kind byte (`H` hello, `C` call, `D`
  db, `U`/`T`/`G` file in/out, `E` exists), zlib over 4 KB.
- **Paths.** Requests whose message has `*path*`/`*folder*` fields are
  rewritten: `/home/web_user/…` becomes the server's home; other files
  (a picked `.apkg`) are uploaded first, and paths the call writes (an
  export) point at a server temp file that is fetched afterwards.
- **Cache.** Reads repeated many times per card (`get_config_*`,
  `get_deck_legacy`, `get_deck_config_legacy`, `get_notetype_legacy`,
  `get_current_deck`) are cached until the next call that isn't a known
  read. That is safe because only the lease holder changes the collection.
- **Lease.** One device uses a collection at a time. Opening it while
  another device made a call in the last minute asks "Use it here
  instead?"; the other device's next call is refused and its page shows
  "Kioku is open on another device" with a button that reloads. Each tab
  has its own client id (kept across reloads); closing or reloading a tab
  frees the lease at once (`navigator.sendBeacon`).
- **Server side.** One backend for the whole server (one household; Anki's
  profiles are the people). Before another device opens the collection, or
  after `KIOKU_IDLE_MINUTES` without calls, it is closed (committed); the
  holder's next call opens it again. `docker stop` (SIGTERM) closes it.
  Backups are made by Anki's timer through the backend, so they land in the
  profile's `backups` folder on the server.
- **Small files.** Profiles' preferences (`prefs21.db`), add-ons and logs
  are copied to `$KIOKU_DATA/home`, and back at start. Collections, their
  media and backups are never copied into the browser (`SERVER_ONLY` in
  `kioku_server.py` and `server.js`).
- **Media.** The service worker asks Anki's in-page server first and, for
  a 404, `/__kioku/media/<file>` (the open collection's media folder).
  Audio plays from that URL; `MediaManager.have()` asks the server.
- **Auth.** `KIOKU_AUTH=password` (default) needs `KIOKU_PASSWORD` or
  `KIOKU_PASSWORD_FILE`: a login page sets an HttpOnly cookie, an HMAC of
  the password with a random key in `$KIOKU_DATA/.secret` (changing the
  password logs everyone out). Everything except the login page, the web
  app manifest and icons needs it, the relay too. `KIOKU_AUTH=none` leaves
  logging in to the reverse proxy (Authelia, basic auth, …); the server
  refuses to start with neither.

## Speed

Measured in headless Chrome with the HSK 1 deck (calls that reach the
server, before the cache): showing an answer 10, answering 15, opening
Browse 143 (48 rows), scrolling Browse 24, adding a note 15. With the
local helpers and the cache, the native test (`answerCard` loop) needs
about 5 calls per card: a few milliseconds on a LAN, ~0.25 s per card at
50 ms round trips. Browse still fetches its rows one call each; batching
them is the next step if that is slow over the internet.

A WebSocket per thread costs one round trip per call and no HTTP headers;
the main thread waits by yielding to the browser every 2 ms (`poll()` in
`src/main.cpp`).

## Building the image

```sh
tools/build.sh
tools/docker.sh [tag]        # tools/dist.sh, then docker build (docker/Dockerfile)
```

The image is `python:3.13-slim` with `anki==$ANKI_PY_VERSION` from
`shared/versions.env` (Kioku's Rust patch only adds sync-server functions,
so PyPI's core speaks the app's protocol), `tools/serve.py`,
`server/kioku_server.py` and `build/dist` (`kioku.wasm`/`kioku.data`
stay brotli-compressed; `serve.py` serves the `.br` with
`Content-Encoding: br`). About 300 MB.

GitHub (`.github/workflows/web-docker.yml`): attach the app files to a
release as `kioku-web.tar.gz` (`tar -C build/dist -czf kioku-web.tar.gz .`
after `tools/dist.sh`); the workflow builds the image for amd64 and arm64
and pushes `ghcr.io/krmanik/kioku-server:<tag>` and `:latest`. Run it by
hand for an existing release (Actions › Web server image).

## Testing

`tools/test/server.py` (Python with `anki` installed, for the server)
starts a server with fresh data and runs two browsers: see
[testing.md](testing.md#server-mode).
