<p align="center">
  <img src="shared/icon/kioku.svg" width="120" alt="Kioku icon">
</p>

<h1 align="center">Kioku</h1>

<p align="center">
  <b>The real Anki desktop app on your phone.</b><br>
  Add-ons, the card browser and every desktop feature, made for a touch screen.
</p>

<p align="center">
  <a href="https://github.com/krmanik/kioku/releases/download/v0.2.1/Kioku-iOS-0.2.1-unsigned.ipa"><img alt="Download for iOS" src="https://img.shields.io/badge/iOS-IPA%20%C2%B7%2039%20MB-000000?style=for-the-badge&logo=apple&logoColor=white"></a>
  <a href="https://github.com/krmanik/kioku/releases/download/v0.2.1/Kioku-Android-0.2.1-arm64.apk"><img alt="Download for Android (native)" src="https://img.shields.io/badge/Android-APK%20%C2%B7%2048%20MB-3DDC84?style=for-the-badge&logo=android&logoColor=white"></a>
  <a href="https://github.com/krmanik/kioku/releases/download/v0.2.1/Kioku-Termux-0.2.1-arm64.apk"><img alt="Download for Android (Termux)" src="https://img.shields.io/badge/Termux-APK%20%C2%B7%20235%20MB-2563EB?style=for-the-badge&logo=gnubash&logoColor=white"></a>
</p>

<p align="center">
  <a href="https://github.com/krmanik/kioku/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/krmanik/kioku?label=latest%20release&color=2563EB"></a>
</p>

<p align="center">
  <img alt="Anki 26.08.1" src="https://img.shields.io/badge/Anki-26.08.1-2563EB">
  <img alt="iOS 17+" src="https://img.shields.io/badge/iOS-17%2B-000000?logo=apple&logoColor=white">
  <img alt="Android 7+" src="https://img.shields.io/badge/Android-7%2B-3DDC84?logo=android&logoColor=white">
  <img alt="Qt 6.11" src="https://img.shields.io/badge/Qt-6.11-41CD52?logo=qt&logoColor=white">
  <img alt="Python 3.14" src="https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white">
</p>

---

AnkiDroid and AnkiMobile are great, but some things exist only in Anki
desktop: add-ons, and the desktop's own card browser, editors and tools.
Kioku runs the **unmodified Anki desktop app** (`aqt`, Qt 6) on phones, with
your decks, add-ons and settings kept on the device. (Kioku, 記憶, is Japanese
for "memory".)

It comes in three variants, each built a different way.

## iPhone and iPad

Anki compiled into a normal iOS app: embedded Python, Qt and PyQt6, with the
system web view (WKWebView) in place of Qt WebEngine. Every window opens full
screen; your collection is in the Files app.

<p align="center">
  <img src="docs/images/strip-ios.png" alt="iPhone: deck list, reviewing a Chinese card, reviewing a NeetCode card and Browse">
</p>

## Android: native variant

The same native build for Android, with Android's WebView. Every window
opens full screen, the Back key closes it.

<p align="center">
  <img src="docs/images/strip-android.png" alt="Native Android: deck list, reviewing a Chinese card, Browse and Statistics">
</p>

## Android: Termux variant

A small Linux desktop inside the APK, with Anki open: Termux packages, an X11
display and a window manager. Anki runs with Qt WebEngine exactly as on a
Linux PC, and other Linux apps install on demand.

<p align="center">
  <img src="docs/images/strip-termux.png" alt="Termux variant: the Kioku desktop, the deck list, reviewing a card and the Software page">
</p>

More screenshots: [docs/screenshots.md](docs/screenshots.md).

## Which one?

| | iPhone, iPad | Android, native | Android, Termux |
| --- | --- | --- | --- |
| **Needs** | iOS 17+ | Android 9+, arm64 | Android 7+, arm64, ~1 GB free, 3 GB+ RAM recommended |
| **Download** | [39 MB IPA](https://github.com/krmanik/kioku/releases/download/v0.2.1/Kioku-iOS-0.2.1-unsigned.ipa) | [48 MB APK](https://github.com/krmanik/kioku/releases/download/v0.2.1/Kioku-Android-0.2.1-arm64.apk) | [235 MB APK](https://github.com/krmanik/kioku/releases/download/v0.2.1/Kioku-Termux-0.2.1-arm64.apk) |
| **How Anki runs** | Python 3.14, Qt 6.11 and PyQt6 compiled into the app | Python 3.14, Qt 6.11 and PyQt6 compiled into the app | Termux userland, termux-x11 display, JWM window manager |
| **Web pages** (cards, stats, editor) | WKWebView | Android System WebView | Qt WebEngine (Chromium), as on the desktop |
| **Windows** | Full screen, ‹ Back closes, popups as cards above the keyboard | Full screen, Back key closes, popups as cards above the keyboard | Desktop windows, a dock, touch or mouse pad mode |
| **Add-ons** | Yes; 15 tested. No subprocesses (MeCab readings in Japanese Support) | Yes; 15 popular ones tested | Yes, as on Linux |
| **Card audio** | mp3, wav, ogg, opus (next release) | mp3, wav, ogg, opus | Not tested |
| **Text-to-speech** (`{{tts}}`) | Yes, system voices (next release) | Yes, system TTS engine (next release) | Not tested |
| **Statistics: Save PDF** | Yes, to Exports/ (next release) | Yes (to Exports/) | Not tested |
| **AnkiWeb sync** | Yes, media too; login kept across restarts | Yes, media too; login kept across restarts | Yes |
| **Your files** | Files app → Kioku (Anki2/, Exports/) | Import with the system file picker; exports go to `Android/data/io.ankidesk.kioku/files/Exports` (on Android 11+ reach it over USB) | Import from Downloads, share decks to Kioku, link phone folders |
| **Other Linux apps** | No | No | Yes: file manager, terminal, web browser… from Termux |
| **Install** | AltStore source, or sideload the unsigned IPA | APK from Releases | APK from Releases |
| **Pick it if** | You have an iPhone or iPad | You want a light, fast app that feels native | You want the full desktop, Linux tools and every add-on |

Test results per area and add-on: [docs/testing.md](docs/testing.md). The
native variants were last tested end to end on an iPhone 15 Pro Max (iOS 26)
and a Samsung Galaxy M30s (Android 11), both syncing with the same AnkiWeb
account.

## Features

All variants:

- **Anki desktop, unmodified.** Anki 26.08.1's own Python code and Rust core:
  the deck list, reviewer, Browse, the editor, image occlusion, the new
  statistics page, deck options, filtered decks, note types, import and export.
- **Desktop add-ons.** Install them from AnkiWeb inside the app with their
  codes. AnkiConnect, Review Heatmap, HyperTTS, Advanced Browser and others
  are tested.
- **Made for touch.** Big type and buttons, drag to scroll, the keyboard opens
  when a text field is tapped, windows fit the phone in portrait and landscape.
- **Your data stays on the phone.** Collections, media and add-ons survive app
  updates. Move them with AnkiWeb sync or an exported `.colpkg`.

Native variants only:

- **Small and fast to start**: no Linux userland, a fraction of the size.
- **Phone-sized popups**: login, prompts and message boxes are cards that
  stay above the keyboard.
- **System web view**: debuggable with Safari's Web Inspector (iOS) or
  `chrome://inspect` (Android).
- **The phone as a sync server** (Preferences › Advanced): AnkiDroid, Kioku's
  profiles and Anki on your computers sync with the phone instead of AnkiWeb.
  On Android a profile can also use AnkiDroid's media folder, so large media is
  stored once. See [docs/sync-server.md](docs/sync-server.md).

Termux variant only:

- **A tiny phone desktop**: app launcher with search, a dock with open windows,
  wallpapers, a Kioku button that hides all windows.
- **Linux apps on demand** from the Termux repositories.
- **Recovers by itself**: Retry, Safe mode (no add-ons), Repair runtime (decks
  kept) or Share log when start-up fails.

## Known issues

Native variants, as of the last device test ([details](docs/testing.md)):

- **Android:** the keyboard's Enter key shows "Next": a Browse search can't be
  started from the keyboard, and prompts need their OK button (fixed for the
  next release).
- **Android:** after a link in a card opens the "Open with" chooser, the status
  and navigation bars stay hidden until Kioku is restarted (fixed for the next
  release).
- **Android:** exported files and PDFs go to the app's own folder, which
  Android 11 and later hide from most file managers; copy them over USB.
- **Android:** Back while reviewing leaves the app instead of returning to the
  deck list.
- **iPhone:** Save PDF in Statistics does nothing; Ogg/Opus card audio is
  silent (both fixed for the next release).
- **Both:** `{{tts}}` text-to-speech is silent (fixed for the next release).
  The card types editor is cramped in portrait.

## Install

Current version: **0.2.1** ([release notes and checksums](https://github.com/krmanik/kioku/releases/tag/v0.2.1),
[all releases](https://github.com/krmanik/kioku/releases)).

| Variant | Download |
| --- | --- |
| iPhone, iPad | [`Kioku-iOS-0.2.1-unsigned.ipa`](https://github.com/krmanik/kioku/releases/download/v0.2.1/Kioku-iOS-0.2.1-unsigned.ipa) (39 MB) or the AltStore source below |
| Android, native | [`Kioku-Android-0.2.1-arm64.apk`](https://github.com/krmanik/kioku/releases/download/v0.2.1/Kioku-Android-0.2.1-arm64.apk) (48 MB) |
| Android, Termux | [`Kioku-Termux-0.2.1-arm64.apk`](https://github.com/krmanik/kioku/releases/download/v0.2.1/Kioku-Termux-0.2.1-arm64.apk) (235 MB) |

**iPhone, iPad:** in [AltStore](https://altstore.io), add the source
`https://github.com/krmanik/kioku/releases/latest/download/altstore.json`
(Sources → +) and install Kioku; new versions then show up in AltStore. Or
sideload the `.ipa` with any tool that signs apps with your Apple ID
([Sideloadly](https://sideloadly.io), …). Apps signed with a free Apple ID
expire after 7 days; AltStore refreshes them while AltServer runs on your
computer.

**Android, native:** download the APK on your phone, open it and allow
installing from your browser or file manager.

**Android, Termux:** download the APK and install it
the same way. The first start unpacks the runtime, about a minute. Both
Android variants can be installed side by side.

**Moving your collection:** sync with AnkiWeb (Sync in the top bar), or export
a `.colpkg` from Anki on your computer and import it in Kioku.

### Troubleshooting: AltServer

**"AltServer could not retrieve anisette data value “machineID”"** (AltServer
on newer macOS, such as the macOS 27 betas). AltServer cannot get the device
data Apple's sign-in needs. Until AltStore releases a fix:

- Use [Sideloadly](https://sideloadly.io) to install the `.ipa` instead.
- Or try a community build of AltServer with an anisette fix, for example
  [kimziro/altserver-macos27-anisette-fix](https://github.com/kimziro/altserver-macos27-anisette-fix)
  or [an-vo90/AltServer-1.8-build97-Anisette-Fix-macos27-alpha](https://github.com/an-vo90/AltServer-1.8-build97-Anisette-Fix-macos27-alpha).
  These are unofficial and not reviewed by this project: they handle your
  Apple ID sign-in, so use them only if you trust them, and preferably with
  a separate Apple ID made just for sideloading.

**"Failed to verify code signature … (The provisioning profile is banned.)"**
when installing AltStore: Apple has temporarily blocked sideloading for that
Apple ID. Wait, or sign in to AltServer with another Apple ID used only for
sideloading.

## Repository

| Folder | What's in it |
| --- | --- |
| [`ios/`](ios/) | The iOS variant: Xcode build, WKWebView layer ([README](ios/README.md)) |
| [`android/`](android/) | The native Android variant: CMake/Gradle build, Android web view, Qt patches |
| [`termux/`](termux/) | The Termux variant: Android app, desktop shell, runtime build ([README](termux/README.md)) |
| [`shared/`](shared/) | What the native variants share: the Python layer (`shared/python/kioku/`), versions, icon and build tools |
| [`docs/`](docs/) | [Fixes log](docs/fixes.md), [test results](docs/testing.md), [screenshots](docs/screenshots.md), [sync server and AnkiDroid's media](docs/sync-server.md) |

Host tests for the Python layer (sync server, AnkiDroid's folder, the
Advanced tab; no device needed): `shared/tests/run.sh`.

Building:

- iOS: `cd ios && tools/build.sh`, see [ios/README.md](ios/README.md)
- Native Android: `cd android && tools/build.sh` (Android SDK, NDK, uv, rustup)
- Termux: [termux/docs/building.md](termux/docs/building.md)

GitHub Actions build every variant on a `v*` tag and attach it to the release;
another workflow checks daily for a new Anki release.

## Credits

Kioku stands on [Anki](https://apps.ankiweb.net), [Qt](https://www.qt.io) and
[PyQt](https://riverbankcomputing.com/software/pyqt/),
[BeeWare's Python builds](https://github.com/beeware/Python-Apple-support) and
[rubicon-objc](https://github.com/beeware/rubicon-objc),
[Termux](https://termux.dev) and its packages,
[Termux:X11](https://github.com/termux/termux-x11) and
[JWM](https://joewing.net/projects/jwm/). Anki is AGPL-3.0; see
[termux/docs/distribution.md](termux/docs/distribution.md) for the other
licenses.

"Anki" is a trademark of Ankitects. Kioku is an independent project, not
affiliated with or endorsed by Ankitects.
