# Testing

## How

- **Core without Qt (node, seconds):** `tools/link_core.sh` links CPython
  and rsbridge into `build/core/core.mjs`; run a script from
  `tools/core/` with `node tools/core/run.mjs /app/core_probe.py` from
  `build/core/` (copy `tools/core/run.mjs` there first). Good for Rust or
  Python core problems: the full app takes ~5 minutes to relink.
- **Smoke test:** `python3 tools/test/smoke.py [deck.apkg]` (server on
  8765): ~4 minutes, prints PASS/FAIL per check. Run it after changes.
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

### 2026-10-24 d: add-ons (Chrome 155, headless)

The 14 add-ons from Kioku's iOS/Android tests, downloaded on the host
(`https://ankiweb.net/shared/download/<id>?v=2.1&p=260903`), written into
the wasm file system and installed with `addonManager.install(path,
manifest=dict(package=<id>, …))` as Get Add-ons does (folder = AnkiWeb id;
HyperTTS finds its config only that way). Error dialogs at start dismissed
with Enter.

| Add-on | Code | Result |
| --- | --- | --- |
| Speed Focus Mode | 1046608507 | loads |
| Color Confirmation | 1084228676 | loads |
| HyperTTS | 111623432 | loads (after `_ssl`); panel on the deck list; Configure Services window opens; HyperTTS menu in Browse |
| Review Heatmap | 1771074083 | loads; heatmap section on the deck list ("No activity data" without reviews) |
| Fill the blanks | 1933645497 | loads |
| AnkiConnect | 2055492159 | loads; its server can't start (`socket` has no `SO_REUSEADDR`; a page can't accept connections): expected, its error dialog holds up add-on loading until closed |
| Customize Keyboard Shortcuts | 24411424 | loads (deprecation warnings) |
| AnkiWebView Inspector | 31746032 | loads (needs Qt WebEngine dev tools: the browser's own dev tools instead) |
| Edit Field During Review Cloze | 385888438 | loads |
| Colorful Tags | 594329229 | loads |
| True Retention | 613684242 | loads |
| Anki Simulator | 817108664 | loads |
| Advanced Browser | 874215009 | loads; Browse opens |
| AnKing Notetypes | 952691989 | loads; AnKing menu |

| Test | Result |
| --- | --- |
| Install from .ankiaddon (jsonschema manifest check) | ✅ after building rpds-py for wasm |
| Python HTTPS (`requests.get` ankiweb.net through the relay) | ✅ 200 (after `_ssl`, the socket option and `poll()` fixes) |
| Tools › Add-ons › Get Add-ons code path (`download_addons`, Review Heatmap 1771074083) | ✅ downloaded and installed from AnkiWeb |
| Add-ons still there after a reload | ✅ (`addons21` is under the saved folder) |

### 2026-10-24 e: AMBOSS add-on (1044112126)

| Test | Result |
| --- | --- |
| Get Add-ons, code 1044112126 | ✅ installed from AnkiWeb |
| Loads; talks to `anki.us.production.amboss.com` through the relay | ✅ (after the relay change) |
| Onboarding / login dialog | ✅ renders (after the localhost and COEP fixes) |
| `ambossAddon is not defined` once at start | ⚠️ its inline script is in `web_content.head`, before its own scripts; same order on the desktop |
| Log in through its form (test account from Kioku's `.env`) | ✅ logged in; its "Mobile Support" intro follows (after the main-thread `poll()` fix) |
| After a reload: still logged in; AMBOSS menu, toolbar button, Qbank widget on the deck list | ✅ |
| Kioku's "AMBOSS Test" deck: terms underlined while reviewing | ✅ |
| Hover a term (ADPKD): pop-up with title, images, text | ✅ (a click closes it again: tippy's toggle); the pop-up is taller than the reviewer and is cut at its bottom |
| Qbank session | ⏳ not tried |

### 2026-10-24 f: smoke test (`python3 tools/test/smoke.py`, Chrome 155, headless)

Three runs in one fresh browser profile (about 4 minutes): first run,
reload, extra windows. 27/27 passed, no page errors.

| Check | Result |
| --- | --- |
| First-run dialogs → profile and collection | ✅ |
| Add a note through the editor; answer it in the reviewer | ✅ |
| Import HSK 1 (.apkg, 311 media files); its audio plays; `{{tts}}` speaks | ✅ |
| Browse, Stats, Deck Options, Preferences, Card Types open | ✅ |
| Check Database; undo status | ✅ |
| Export .apkg with media → download (24 MB); export .colpkg | ✅ |
| Reload: profile, notes, review, media kept | ✅ |
| Filtered deck, Custom Study, Note Types, Empty Cards, Check Media, Find and Replace, CSV import page | ✅ open |
| Dark theme; "follow system" follows the browser's `prefers-color-scheme` | ✅ (was hard-coded light) |
| Switch profile (profile manager) | ✅ |

The window checks only see that the window opens, not that everything in
it works.

