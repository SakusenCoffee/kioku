# Web browser (experimental)

> **Applies to:** web

Kioku also runs in a browser tab, nothing to install:
**[kioku.krmanik.workers.dev](https://kioku.krmanik.workers.dev)**. Anki
itself runs inside the tab (compiled to WebAssembly), and your collection
lives in that browser.

This is an early test version, for trying things out. It may crash or lose
data.

- **Back up first.** Before using a collection you care about, export it
  with scheduling information from Anki desktop or your phone
  (**File › Export**: a `.colpkg`, or an `.apkg` with **Include scheduling
  information**).
- **Sync with a test AnkiWeb account**, not the one you use.
- Your collection stays in that browser on that device. Clearing the site's
  data deletes it, and Safari deletes it after 7 days without a visit
  (unless it is on the Home Screen). To keep one collection on your own
  server and open it from any browser instead, see
  [Self-hosted server](self-hosted.md).

## Browsers

Tested in Chrome on a computer, and in Safari on a Mac and on an iPhone
15 Pro Max. Opening it downloads about 31 MB and takes 20–40 s on a fast
connection. Phones have less memory: keep collections small there.

## Install it as an app

The page opens full screen from the home screen, without the address bar:

- **iPhone, iPad (Safari):** Share › **Add to Home Screen**.
- **Android (Chrome):** ⋮ › **Add to Home screen** (or **Install app**).
- **Chrome or Edge on a computer:** the install button in the address bar.

On iPhone and iPad the home screen app keeps its own storage, apart from
Safari's: import or sync your collection again there.

## Files

**File › Import** opens the browser's file picker. Exports and backups are
downloaded like any file from a website.
