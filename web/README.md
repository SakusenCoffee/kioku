# Kioku for the web

Unmodified Anki desktop (aqt 26.09.3) running in a browser tab: CPython
3.14, PyQt6, Qt 6.11 and Anki's Rust core compiled to WebAssembly and
linked into one static `kioku.wasm`, the same design as
[Kioku](https://github.com/krmanik/kioku)'s iOS and Android apps. This is an
early port, not something to ship: studying works, but nothing survives a
reload yet.

<img src="images/web-decks.png" width="270"> <img src="images/web-add.png" width="270">
<img src="images/web-review.png" width="270"> <img src="images/web-import.png" width="270">

## Status (2026-10-24, headless Chrome)

Works: first-run dialogs, profile creation, the main window; the deck list,
deck overview, reviewer (with Anki's keyboard shortcuts), Add (the editor),
Import (.apkg through the browser's file picker), Browse, Stats, Check
Database, export (as a browser download), card audio and `{{tts}}` (Web
Speech API). Profiles, collections and media are kept in the browser's
IndexedDB across reloads. Dialogs that block (`QDialog.exec()`) and
collection work on background threads behave like on the desktop.

Missing: AnkiWeb sync; serving from anywhere but `127.0.0.1`. See [HANDOFF.md](HANDOFF.md)
for what to do next.

Download: `kioku.wasm` 94 MB (18.5 MB with brotli), `kioku.data` 34 MB
(8.5 MB gzipped).

## Quick start

Needs the Kioku repository next to this one (`../anki-desktop-for-android`,
or set `KIOKU_REPO`) with its iOS dependencies fetched and built
(`ios/tools/fetch_deps.sh`, `ios/tools/build.sh` or at least its site-packages
and PyQt6 sdists), plus nightly Rust with `rust-src`, `protoc`, `uvx`,
Python 3.14, Ninja and Chrome.

```sh
tools/fetch_deps.sh      # Emscripten 4.0.7, Qt 6.11 for WebAssembly
tools/build_python.sh    # CPython 3.14 for Emscripten (patched)
tools/build_rust.sh      # Anki's Rust core for wasm32-unknown-emscripten
tools/gen_pyqt.sh        # PyQt6 bindings for Qt for WebAssembly
tools/prepare_site.sh    # Anki's Python packages
tools/build.sh           # build/cmake: kioku.wasm, app.html, sw.js, ...
python3 tools/serve.py build/cmake 8765
```

Open <http://127.0.0.1:8765/app.html>. It must be `127.0.0.1` (Anki's page
URLs have to be the page's own origin, see [docs/architecture.md](docs/architecture.md)).
Python files are packed at link time: after changing only Python,
`touch src/main.cpp` and run `tools/build.sh` (about 5 minutes, Asyncify is
slow); files in `shell/` can be copied into `build/cmake/` directly.

## Layout

| Path | What |
| --- | --- |
| `src/main.cpp` | CPython embedding, statically linked extension modules, the `_kioku_web` module and the `kioku_post` export |
| `python/kioku_platform/` | the web platform layer for Kioku's shared `kioku` package: web views, in-process web server, files |
| `shell/` | the app page, its service worker and JavaScript glue |
| `patches/` | patches for Rust crates, CPython and PyQt6 |
| `tools/` | build scripts, `serve.py`, the node core test (`link_core.sh`, `core/`), the browser driver (`test/`) |
| `app/probe.py` | the first feasibility probe (Qt's `kioku.html` runs it) |
| `docs/` | [architecture](docs/architecture.md), [fixes](docs/fixes.md), [testing](docs/testing.md) |
