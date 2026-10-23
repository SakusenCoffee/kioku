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
  run starts a fresh profile (nothing persists yet), gets through the
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
| Export download | ⏳ not tested |
| Reload keeps the collection | ❌ not implemented (MEMFS) |
| Sync, audio, TTS | ❌ not implemented |
| Firefox, Safari, a phone browser | ⏳ not tested (`moveBefore()` and JSPI-free Asyncify should work; COOP/COEP needed everywhere) |
