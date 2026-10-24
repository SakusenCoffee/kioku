<p align="center">
  <img src="shared/icon/kioku.svg" width="120" alt="Kioku icon">
</p>

<h1 align="center">Kioku</h1>

<p align="center">
  <b>The real Anki desktop app on your phone.</b><br>
  Add-ons, the card browser and every desktop feature, made for a touch screen.
</p>

<p align="center">
  <a href="https://github.com/krmanik/kioku/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/krmanik/kioku?label=version"></a>
  <a href="https://github.com/krmanik/kioku/commits/main"><img alt="Commit activity" src="https://img.shields.io/github/commit-activity/m/krmanik/kioku"></a>
  <a href="https://github.com/krmanik/kioku/stargazers"><img alt="Stars" src="https://img.shields.io/github/stars/krmanik/kioku?style=flat"></a>
  <a href="https://github.com/krmanik/kioku/forks"><img alt="Forks" src="https://img.shields.io/github/forks/krmanik/kioku?style=flat"></a>
  <a href="https://github.com/krmanik/kioku/graphs/contributors"><img alt="Contributors" src="https://img.shields.io/github/contributors/krmanik/kioku"></a><br>
  <img alt="Anki 26.08.1" src="https://img.shields.io/badge/Anki-26.08.1-2563EB">
  <img alt="iOS 17+" src="https://img.shields.io/badge/iOS-17%2B-000000?logo=apple&logoColor=white">
  <img alt="Android 7+" src="https://img.shields.io/badge/Android-7%2B-3DDC84?logo=android&logoColor=white">
  <img alt="Qt 6.11" src="https://img.shields.io/badge/Qt-6.11-41CD52?logo=qt&logoColor=white">
  <img alt="Python 3.14" src="https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white">
</p>

<h3 align="center">Download</h3>

<p align="center">
  <a href="https://github.com/krmanik/kioku/releases/download/v0.2.2/Kioku-iOS-0.2.2-unsigned.ipa"><img alt="Download iOS" src="https://img.shields.io/badge/Download-iOS-000000?labelColor=333333&style=for-the-badge&logo=apple&logoColor=white"></a>
  <a href="https://forms.gle/fw4YMTdGbgD8nqPe8"><img alt="iOS TestFlight beta" src="https://img.shields.io/badge/TestFlight-join%20beta-0D96F6?labelColor=333333&style=for-the-badge&logo=apple&logoColor=white"></a><br>
  <a href="https://github.com/krmanik/kioku/releases/download/v0.2.2/Kioku-Android-0.2.2-arm64.apk"><img alt="Download Android (native)" src="https://img.shields.io/badge/Download-Android-1E7F3C?labelColor=333333&style=for-the-badge&logo=android&logoColor=white"></a>
  <a href="https://github.com/krmanik/kioku/releases/download/v0.2.2/Kioku-Termux-0.2.2-arm64.apk"><img alt="Download Android (Termux)" src="https://img.shields.io/badge/Download-Termux-2563EB?labelColor=333333&style=for-the-badge&logo=gnubash&logoColor=white"></a>
</p>

<p align="center">
  <a href="https://kioku.krmanik.workers.dev"><img alt="Try in the browser (experimental)" src="https://img.shields.io/badge/Try-Web%20%C2%B7%20experimental-B45309?labelColor=333333&style=for-the-badge&logo=googlechrome&logoColor=white"></a>
</p>

<p align="center">
  <a href="https://krmanik.github.io/kioku/"><b>User manual</b></a> ·
  <a href="web/README.md">Web version</a> ·
  <a href="https://github.com/krmanik/kioku/releases/latest">Releases</a> ·
  <a href="https://github.com/krmanik/kioku/issues">Issues</a>
</p>

---

AnkiDroid and AnkiMobile are great, but some things exist only in Anki
desktop: add-ons, and the desktop's own card browser, editors and tools.
Kioku runs the **unmodified Anki desktop app** (`aqt`, Qt 6) on phones, with
your decks, add-ons and settings kept on the device. (Kioku, 記憶, is Japanese
for "memory".)

## Three variants

| | iPhone, iPad | Android, native | Android, Termux |
| --- | --- | --- | --- |
| **Needs** | iOS 17+ | Android 9+, arm64 | Android 7+, arm64, ~1 GB free, 3 GB+ RAM |
| **Size** | 39 MB | 48 MB | 235 MB |
| **How** | Python, Qt and PyQt6 compiled into the app; system web view | same as iOS, Android System WebView | Termux userland, X11 display, Qt WebEngine as on Linux |
| **Feels like** | a phone app | a phone app | a small Linux desktop |
| **Extras** | sync server on the phone | sync server, AnkiDroid's media | Linux apps on demand, remote desktop |
| **Install** | [TestFlight, AltStore or sideload](https://krmanik.github.io/kioku/install/ios.html) | [APK](https://krmanik.github.io/kioku/install/android.html) | [APK](https://krmanik.github.io/kioku/install/termux.html) |

<h3 align="center">iPhone and iPad</h3>
<p align="center">
  <img src="docs/images/strip-ios.png" alt="iPhone: deck list, reviewing a Chinese card, reviewing a NeetCode card and Browse">
</p>
<h3 align="center">Android, native</h3>
<p align="center">
  <img src="docs/images/strip-android.png" alt="Native Android: deck list, reviewing a Chinese card, Browse and Statistics">
</p>
<h3 align="center">Android, Termux</h3>
<p align="center">
  <img src="docs/images/strip-termux.png" alt="Termux variant: the Kioku desktop, the deck list, reviewing a card and the Software page">
</p>

More: [screenshots](docs/screenshots.md).

## Features

- **Anki desktop, unmodified**: Anki 26.08.1's own Python code and Rust core.
- **Desktop add-ons** from AnkiWeb, installed inside the app.
- **Made for touch**: big type, drag to scroll, the keyboard opens on text
  fields, windows fit the phone in portrait and landscape.
- **Your data stays on the phone**; AnkiWeb sync, import and export as usual.
- **The phone as a sync server** for AnkiDroid, Kioku and Anki on your
  computers (iPhone, Android native).
- **Remote desktop**: the phone's Anki in a computer's browser (Termux).

How to install and use it: the **[Kioku manual](https://krmanik.github.io/kioku/)**
(source in [docs/manual/](docs/manual/src/SUMMARY.md)). Everything about
Anki itself is in [Anki's manual](https://docs.ankiweb.net/).

## Repository

| Folder | What's in it |
| --- | --- |
| [`ios/`](ios/) | iOS variant: Xcode build, WKWebView layer ([README](ios/README.md)) |
| [`android/`](android/) | native Android variant: CMake/Gradle build, Android web view, Qt patches |
| [`termux/`](termux/) | Termux variant: Android app, desktop shell, runtime build ([README](termux/README.md)) |
| [`web/`](web/) | web variant: Anki in a browser tab, compiled to WebAssembly; Cloudflare hosting ([README](web/README.md)) |
| [`shared/`](shared/) | shared by the native variants: Python layer, versions, icon, build tools |
| [`docs/`](docs/) | [user manual](docs/manual/), [fixes log](docs/fixes.md), [test results](docs/testing.md), [privacy](docs/privacy.md) |

Building: iOS `cd ios && tools/build.sh` ([ios/README.md](ios/README.md));
native Android `cd android && tools/build.sh`; Termux
[termux/docs/building.md](termux/docs/building.md). Host tests for the Python
layer: `shared/tests/run.sh`. GitHub Actions build every variant on a `v*`
tag and attach it to the release.

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
