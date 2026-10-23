# Testing

## How

- **Core without Qt (node, seconds):** `tools/link_core.sh` links CPython
  and rsbridge into `build/core/core.mjs`; run a script from
  `tools/core/` with `node tools/core/run.mjs /app/core_probe.py` from
  `build/core/` (copy `tools/core/run.mjs` there first). Good for Rust or
  Python core problems: the full app takes ~5 minutes to relink.
- **The app (headless Chrome):** `python3 tools/serve.py build/cmake 8765`,
  then `cd tools/test && npm install` once and
  `node boot.mjs '<steps>'` (steps documented at the top of `boot.mjs`). Each
  run starts a fresh profile unless `PROFILE=<folder>` keeps Chrome's data
  (IndexedDB) between runs (then `NOFIRSTRUN=1`); downloads land in the
  current folder, gets through the
  language dialogs and runs the steps. Screenshots land in the current
  folder. The coordinates below are for the 1000×700 viewport.
- **Inside the app:** the `devexec` hook (`["py", "…"]` in `boot.mjs`, or
  `__kiokuWeb.post({type: "devexec", code})` in the console) runs Python
  and prints `result`. `["pause"]` prints the main thread's stack when the
  page hangs (needs `--profiling-funcs`, on by default).

Useful step sequences (after the deck list is up, ~9 s):

```
add a note:   ["click",428,37,7000],["click",500,173,800],["type","Front"],["click",500,249,800],["type","Back"],["click",761,674,3000],["click",948,674,5000]
study:        ["click",307,167,4000],["click",603,168,5000],["click",500,300,500],["key","Space",3000],["key","3",3000]
import:       ["upload","/path/deck.apkg",[614,666],8000],["click",943,66,8000],["click",48,21,5000]
browse/stats: ["click",500,37,8000] / ["click",575,37,10000]
```

## Results

### 2026-10-23: feasibility (node 26 and Chrome 155, headless, macOS)

| Test | Result |
| --- | --- |
| node: create a collection, add 200 notes, answer a card, search from a worker thread, stats report | ✅ 1.3 s |
| node: update check through reqwest (tokio runtime) | ✅ clean `NetworkError` (no relay) after the mio pipe fix; panicked before |
| Chrome: Python + rsbridge, collection created and a card rendered in the page | ✅ |
| Chrome: PyQt6 widgets; clicks reach Python slots after `app.exec()` | ✅ |
| Chrome: nested `QMessageBox.exec()` returns Yes (Asyncify) | ✅ |
| Chrome: collection opened on a `ThreadPoolExecutor` thread, result on the GUI thread | ✅ |
| Chrome: unmodified aqt: language dialogs, profile, main window, menus, Tools › Check Database | ✅ |

### 2026-10-24: Anki's pages (Chrome 155, headless, 1000×700)

| Test | Result |
| --- | --- |
| Deck list, toolbar, bottom bar render | ✅ |
| Add: editor renders, typed note saved with both fields; deck list shows New 1 after closing | ✅ (after the eval-order and removeChild fixes) |
| Deck overview, Study Now, question → Space → answer with buttons → 3 (Good) | ✅ card moves to learning |
| Import File: browser picker → import page (SvelteKit) → Import → "20 new notes imported" → deck list shows AMBOSS Test 20 new | ✅ (`AMBOSS Test.apkg` from Kioku's `build-testdata/amboss`) |
| Browse window opens (sidebar, table) | ✅ |
| Stats (graphs page) | ✅ |
| Update check | ✅ fails cleanly ("update check failed: A network error occurred") |
| Export download | ✅ see 2026-10-24 b |
| Reload keeps the collection | ✅ see 2026-10-24 b |
| Audio, TTS | ✅ see 2026-10-24 b; sync ❌ not implemented |

### 2026-10-24 b: storage, audio, TTS, export (Chrome 155, headless, test-deck/)

Run with `PROFILE=<folder>` so IndexedDB survives between runs.

| Test | Result |
| --- | --- |
| Import `Anki xiehanzi - HSK 1.apkg` (24 MB, 311 media files) | ✅ 602 notes, 4 decks, 311 media files |
| Reviewer: question audio (`[sound:cmn-的.mp3]`) | ✅ `WebAudioPlayer` → `<audio>` with a blob URL, playing |
| `{{tts}}` (`TTSTag` zh_CN) | ✅ `WebSpeechPlayer` picks a zh_CN voice (macOS voices through Chrome) |
| Export .apkg with media (`save_path` + `export_anki_package`) | ✅ `HSK.apkg` downloaded, 24.4 MB |
| Reload (same browser profile, no first-run dialogs) | ✅ profile "User 1", 602 notes, 311 media files, audio plays from the saved media |
| Import `Anki-NeetCode-Pro.apkg`, review | ✅ card renders; `CodeMirror is not defined` once (the deck's scripts, timing; not on the next run) |
| HSK 1 Writing cards: Space/3 after the question | ⚠️ not answered: the template's drawing canvas keeps the keys |
| Export through File › Export dialog clicks | ⏳ not clicked through (the same `save_path`) |

### 2026-10-24 c: sync (Chrome 155, headless)

Local server: Anki's `anki-sync-server` built from Kioku's Anki source
(`PROTOC=$(command -v protoc) CARGO_TARGET_DIR=…/build/host-sync cargo build
--release -p anki-sync-server` in `ios/deps/anki`), run with
`SYNC_USER1=kioku:test SYNC_HOST=127.0.0.1 SYNC_PORT=8090`, and
`KIOKU_RELAY_ALLOW=127.0.0.1:8090 python3 tools/serve.py build/cmake 8765`.

| Test | Result |
| --- | --- |
| Login with a wrong password (AnkiWeb) | ✅ "Email or password was incorrect" (TLS through the relay) |
| Local server: login, Sync button, "Replace it with local collection?" → Yes | ✅ full upload + media (322 files, 70 MB on the server) |
| Local server, fresh browser profile: Sync → "Download?" → Yes | ✅ 752 notes, 322 media files |
| AnkiWeb (test account, fresh profile): `sync_collection` → full sync required → `full_download` | ✅ 20,858 notes, 39,754 cards, 9 decks, ~3 s; never uploaded |
| `full_download` without a normal sync first | ⚠️ AnkiWeb 400 "missing original size" (skips `meta`, which picks the endpoint; Anki's UI never does this) |
| Firefox, Safari, a phone browser | ⏳ not tested (`moveBefore()` and JSPI-free Asyncify should work; COOP/COEP needed everywhere) |
