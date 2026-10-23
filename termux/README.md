<p align="center">
  <img src="../shared/icon/kioku.svg" width="120" alt="Kioku icon">
</p>

<h1 align="center">Kioku</h1>

<p align="center">
  <b>The real Anki desktop app, on your Android phone.</b><br>
  Tap one icon and a small Linux desktop starts with Anki open: add-ons, the card browser,
  every desktop feature, made for a touch screen.
</p>

<p align="center">
  <a href="https://github.com/krmanik/kioku/releases/latest"><img alt="Download the latest APK" src="https://img.shields.io/github/v/release/krmanik/kioku?label=download%20APK&style=for-the-badge&color=2E8BFF"></a>
</p>

<p align="center">
  <img src="docs/screenshots/desktop.png" width="19%" alt="The Kioku desktop with Anki, Terminal, Web Browser and other apps">
  <img src="docs/screenshots/anki-decks.png" width="19%" alt="Anki's deck list">
  <img src="docs/screenshots/anki-review.png" width="19%" alt="Reviewing a card in Anki">
  <img src="docs/screenshots/software.png" width="19%" alt="The Software page with recommended Linux apps">
  <img src="docs/screenshots/settings.png" width="19%" alt="Settings with wallpapers and touch options">
</p>

<p align="center"><sub>Desktop · Decks · Review · Software · Settings</sub></p>

---

## Why

AnkiDroid is great, but some things only exist in Anki desktop: add-ons, and the desktop's own
card browser, editors and tools. Kioku runs the
**unmodified desktop Anki** (Qt 6 + Qt WebEngine, built for Termux) as a normal Android app.
No Termux, no Termux:X11, no setup. (Kioku, 記憶, is Japanese for "memory".)

## Features

- **Anki desktop, ready to go.** Opens with the session; your decks, media, add-ons and settings
  stay on the phone and survive app updates.
- **Made for touch.** Drag to scroll with momentum, big type and buttons, the keyboard opens when
  a text field is tapped. Prefer a pointer? Switch to **mouse pad** mode in Settings.
- **A tiny phone desktop.** App launcher with search, a dock with your open windows, a Kioku
  button that hides all windows (tap again to bring them back), six wallpapers or your own
  picture, portrait and landscape.
- **Linux apps on demand.** Software installs a file manager, text editor, terminal, web browser,
  image viewer and more, or anything from the Termux repositories, only when you want them.
- **Works with your phone's files.** Import `.apkg`/`.colpkg` decks from Downloads, open them
  from other apps or share them to Kioku, and optionally link your phone's folders.
- **Remote desktop.** Use Anki from a computer, in a web browser or a VNC viewer, on a
  desktop-sized screen; over Tailscale by default. See [Remote desktop](docs/remote-desktop.md).
- **Recovers by itself.** If something goes wrong at start-up: Retry, Safe mode (Anki without
  add-ons), Repair runtime (your decks are kept) or Share log.

## Install

1. On your phone, download `Kioku-<version>-arm64.apk` from the
   **[latest release](https://github.com/krmanik/kioku/releases/latest)**.
2. Open it and allow installing from your browser or file manager when Android asks.
3. Tap **Kioku**. The first start unpacks the runtime, which takes about a minute.

**Needs:** a 64-bit ARM phone (arm64-v8a; nearly every phone from the last years),
Android 7 or newer, about 1 GB of free storage; 3 GB of RAM or more recommended.

### Moving your collection

Sync with AnkiWeb (Anki → Sync), or export a `.colpkg` from Anki on your computer and use
**Settings → Import a deck from the phone**.

## Tips

| To … | do this |
|---|---|
| see the desktop | tap the Kioku button at the left of the dock; tap again to get your windows back |
| switch apps | tap a window in the dock |
| show or hide the keyboard | tap the keyboard button in the dock |
| scroll | drag with one finger (touch screen) or two fingers (mouse pad) |
| close Kioku | Settings → Power off (Anki saves your collection first) |

## Documentation

- [How it works](docs/how-it-works.md): start-up, where your data lives, updates, phone files
- [The desktop](docs/desktop.md): apps, window manager, touch and keyboard handling
- [Remote desktop](docs/remote-desktop.md): Anki from a computer's browser or VNC viewer
- [Building](docs/building.md): local builds, GitHub Actions releases and signing, the runtime
- [Distribution and licenses](docs/distribution.md)

## Credits

Kioku stands on [Anki](https://apps.ankiweb.net), [Termux](https://termux.dev) and its
packages, [Termux:X11](https://github.com/termux/termux-x11), [JWM](https://joewing.net/projects/jwm/)
and [Qt](https://www.qt.io). Anki is AGPL-3.0, termux-x11 and the Termux packages are GPL-3.0 and
others; see [distribution.md](docs/distribution.md).

"Anki" is a trademark of Ankitects. Kioku is an independent project, not affiliated with or
endorsed by Ankitects.
