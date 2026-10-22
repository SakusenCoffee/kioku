# Testing the native variants

## How

Both native variants have a development mode (`KIOKU_DEV=1`, set by the run
scripts) with a command channel into the running app
(`shared/python/kioku/devtools.py`):

- `ios/tools/run_device.sh` builds, installs and launches on a connected
  iPhone (`KIOKU_TEAM=<team id>` for signing) and prints the app's log.
- `ios/tools/devcmd.sh [--shot] 'python'` runs Python inside the app (with
  `mw`, `aqt`, `shot()`, `widgets()`) and prints its output; `--shot` also
  fetches a screenshot (web views included).
- `ios/tools/sweep.sh` opens every main window and reports widgets that run
  off the screen.

Code run through `devcmd.sh` runs on the main thread: anything that waits for
the main thread (AnkiConnect requests, for example) has to run in a
`threading.Thread`. A command that opens a modal dialog (a prompt, a message
box) and then waits blocks the channel until the dialog closes; open modal
dialogs with `QTimer.singleShot(0, …)` and return, then handle them in the
next command. On iOS, `devicectl` sometimes reports a failed copy although the
command arrived (the app had already picked the file up); `devcmd.sh` waits
for the output anyway.

Test collections: real desktop profiles exported with Anki 26.8.1's own
library (`export_collection_package`) from an APFS clone (`cp -c`) of the
profile folder, so the desktop data is never opened, pushed with
`xcrun devicectl device copy to … Documents/Import/` and imported with
`aqt.import_export.importing.ColpkgImporter._import(mw, path)`.

## Results: iOS (iPhone 15 Pro Max, iOS 26, Anki 26.8.1)

Collections: 41, 602, 61,199 and 258,430 cards (27k media files) imported,
card and review counts identical to the desktop.

| Area | Result |
| --- | --- |
| Start-up, profiles, switching profiles | works |
| Deck list (258k cards) | works; fits the screen |
| Reviewing: question, answer, answer buttons, intervals, revlog written | works |
| Card audio (mp3) | works, including interrupting and the next card |
| Card audio: Ogg Vorbis, Ogg Opus | works (iOS 27.0.1): AVAudioPlayer can't play Ogg, so these play in a hidden web view; stopping mid-file and the next file work |
| `{{tts}}` text-to-speech | works: AVSpeechSynthesizer, 193 voices (Apple_Samantha …); stop mid-sentence works |
| Statistics (new stats page, charts, calendar) | works |
| Statistics: Save PDF | works: 4-page A4 PDF in Documents/Exports |
| Browse | works; sidebar behind a title bar button in portrait |
| Add, editor | works |
| Image occlusion: mask editor with an image | works (masks need touch testing) |
| Image occlusion / import / attachments: choosing a file | fixed (document picker in copy mode); needs a hand test |
| Import .colpkg | works |
| Export | writes to Documents/Exports |
| Preferences, Note Types, Deck Options, Filtered Deck, Study Deck, Add-ons, About | open, fit the screen, close with ‹ Back |
| HTTPS (add-on downloads) | works after the truststore fix |
| AnkiWeb sync | works (physical-device round below): login, full download, media sync, two-way changes, conflict choice |

Popups (shared code, after the Android round): the AnkiWeb login is a card
above the keyboard (iOS reports the keyboard in points, as assumed);
closing it and opening another window with the keyboard up works.

### Add-ons

Installed from AnkiWeb inside the app; all 15 load without errors.

| Add-on | Code | Result |
| --- | --- | --- |
| AnkiConnect | 2055492159 | works: HTTP API on 127.0.0.1:8765 answers (version, deckNames, findCards) |
| Review Heatmap | 1771074083 | works: heatmap on the deck list (slightly wider than a phone screen) |
| Anki Simulator | 817108664 | opens; rendering to check |
| AnKing Note Types Easy Customization | 952691989 | loads, menu works; shows a tutorial at start-up |
| Advanced Browser | 874215009 | loads; to check |
| Fill the blanks | 1933645497 | loads; to check |
| Colorful Tags / Hierarchical Tags | 594329229 | loads; to check |
| Customize Keyboard Shortcuts | 24411424 | loads |
| Edit Field During Review Cloze | 385888438 | loads; to check |
| Speed Focus Mode | 1046608507 | loads |
| True Retention | 613684242 | loads; to check |
| HyperTTS | 111623432 | loads; its configuration window did not appear: to check |
| AnkiWebView Inspector | 31746032 | loads; needs Qt WebEngine dev tools, expected not to work (use Safari's Web Inspector instead: web views are inspectable) |
| Color Confirmation | 1084228676 | works (answer confirmation popup) |
| Japanese Support | 3918629684 | loads; Kanji Stats did not open, and readings use MeCab as a subprocess, which iOS forbids: to check |

AnkiWeb returned 404 for 516643804, 2091361802 and 1572969437 (codes no
longer published).

## Results: Android (emulator, Android 17 arm64, 16 KB pages, Anki 26.8.1)

Android has the same tools: `android/tools/run_device.sh` (build, install,
launch in dev mode, print the log; `KIOKU_NO_BUILD=1` reinstalls the last
build), `devcmd.sh [--shot] 'python'` (screenshots with `adb screencap`) and
`sweep.sh`. Collections are pushed with
`adb push … /sdcard/Android/data/io.ankidesk.kioku/files/Import/`.

Emulator: start it with `emulator -avd Medium_Phone -gpu swiftshader_indirect
-feature GLESDynamicVersion`. With `-gpu host` on a Mac it offers only OpenGL
ES 3.0, and WebView aborts the app on pages with embedded video (see
docs/fixes.md).

Collections: the same 41, 602, 61,199 and 258,430-card profiles imported,
counts identical to the desktop.

| Area | Result |
| --- | --- |
| Start-up, profiles, switching profiles | works |
| Menu bar | works (drawn as a widget) |
| Back key | closes the top window; on the main window moves the app to the background |
| Background and resume | works; no error dialog |
| Deck list (258k cards) | works |
| Reviewing: question, answer, answer buttons, revlog written | works |
| Card audio: mp3, wav, ogg (Vorbis), opus | works, Anki's queue gets "done" for each |
| Statistics (new stats page, charts, calendar) | works |
| Statistics: Save PDF | works (5-page PDF in Exports/) |
| Browse, sidebar, notes with embedded YouTube video | works (emulator: needs the ES 3.1 setting above) |
| Add, editor | works (note added through the Add window) |
| Import .colpkg | works |
| Export (.apkg) | writes to Exports/ in the app's external files folder |
| About, Browse, Add, Statistics, Preferences, Note Types, Deck Options, Filtered Deck, Study Deck, Empty Cards, Export, Add-ons | open full screen, nothing wider than the screen (`sweep.sh`, also after the small-dialog change) |
| HTTPS (add-on downloads) | works after the CA bundle fix |
| Image occlusion / file picking | system picker opens; needs a hand test |
| AnkiWeb sync (User 4) | works: login, full sync (download, 39,754 cards), media sync; still logged in after a force-stop and restart |
| Popups: AnkiWeb login, rename prompt, message boxes | bordered card sized to its content; above the keyboard while typing |
| Top bar height over 5 cold starts | 34 px each time (the retry was needed in 2 of 5) |
| AnkiWeb login: OK tapped with the keyboard up, error box follows | works (5 of 5); crashed before the Qt plugin patch |
| Samsung M30s (Android 11, real device) | start-up, `sweep.sh` (all windows full screen), login card above the keyboard, OK with the keyboard up |

### Add-ons (Android)

All 15 installed from AnkiWeb inside the app and load without errors.

| Add-on | Result |
| --- | --- |
| AnkiConnect | works: version 6, deckNames (252 decks) |
| Review Heatmap | works: heatmap drawn on the deck list (366 day cells) |
| Anki Simulator | opens |
| AnKing Note Types Easy Customization | loads, AnKing menu; shows a tutorial at start-up (add-on loading waits until it is closed, as on the desktop) |
| Advanced Browser | loads (its modules are active in Browse) |
| Fill the blanks | loads |
| Colorful Tags / Hierarchical Tags | loads; sidebar works |
| Customize Keyboard Shortcuts | loads (logs a deprecation warning for `tr(TR.…)`) |
| Edit Field During Review Cloze | works (its EFDRC script is in the card page) |
| Speed Focus Mode | loads |
| True Retention | works: its rows in the legacy statistics window (Shift+Stats) |
| HyperTTS | works: configuration window opens; editor buttons shown |
| AnkiWebView Inspector | loads; needs Qt WebEngine dev tools (use chrome://inspect: web views are debuggable) |
| Color Confirmation | works (popup after answering) |
| Japanese Support | works: Kanji Stats opens with statistics; MeCab readings to check |

## Results: physical devices, user flows (October 22, 2026)

iPhone 15 Pro Max (iOS 26) and Samsung Galaxy M30s (Android 11, 3.6 GB RAM),
both on the builds installed that day (no rebuild). On the Samsung every step
was done with real taps, swipes and the on-screen keyboard (`adb shell input`),
the way a user would; on the iPhone, where input can't be injected, with
`devcmd.sh` clicking the same buttons and links (Qt events, JavaScript
`click()` in the web views) and checking screenshots. Collections: the
258,430-card profile (27k media files) and an AnkiWeb account with 39,754
cards and 13,677 media files.

✅ works, ⚠️ works with a problem, ❌ doesn't work.

### Getting started

| Area | iOS | Android |
| --- | --- | --- |
| Cold start to the deck list (258k cards, one add-on) | ✅ ~6 s | ✅ ~17 s |
| Import a .colpkg with the system file picker (290 MB, 27k media) | not driven (picker can't be scripted) | ✅ about 15 min on the M30s; "replace collection" box, progress, all cards and media |
| Cancel the file picker | – | ✅ |
| Profiles: create, switch (File › Switch Profile), open | ✅ | ✅ |
| File › Exit | ✅ app closes | ✅ app closes, no crash; relaunch from the launcher works |
| Last profile and AnkiWeb login kept after a restart | ✅ | ✅ |

### Studying

| Area | iOS | Android |
| --- | --- | --- |
| Deck list: open a deck, overview, Study Now | ✅ | ✅ real taps |
| Card JavaScript (tap-to-order characters, hint button) | ✅ | ✅ real taps |
| Show Answer, answer buttons with intervals, revlog written | ✅ | ✅ |
| Undo after answering | ✅ | not repeated |
| Flag, mark, bury, suspend (and undo) | ✅ | not repeated |
| Card info (forgetting curve) | ✅ | not repeated |
| Edit current card, change a field, saved | ✅ | not repeated (editing tested in Add and Browse) |
| Card audio (mp3), replay button | ✅ AVFoundation | ✅ MediaPlayer |
| `{{tts}}` text-to-speech | ✅ fixed later that day: AVSpeechSynthesizer (see below) | ✅ fixed later that day: TextToSpeech (see below) |
| Links in cards (`<a href>`) | – | ✅ open the system browser chooser |
| Landscape | not driven | ✅ layout adapts; drag to scroll works |
| Back key while reviewing | – | ⚠️ moves the app to the background (AnkiDroid users expect the deck list) |
| Status and navigation bars after another app's popup (browser chooser) | – | ✅ fixed later that day (see below); before: both bars stayed hidden until the app restarted |

### Adding and editing

| Area | iOS | Android |
| --- | --- | --- |
| Add: type into fields with the keyboard, Add | ✅ | ✅ the window shrinks above the keyboard |
| Note type and deck choosers, typing in the filter | ✅ | ✅ |
| History button label | ✅ "History ▾" | ⚠️ "History ▯" (the ▾ glyph is missing from the font) |
| Image occlusion: pick an image, draw a mask by touch, Add | not driven (picker) | ✅ |
| Image picker filtered to images | – | ⚠️ shows every file type |
| Card types editor (Cards…) | ⚠️ opens, cramped in portrait | ⚠️ opens, cramped in portrait (labels cut: "Fror", "Bac") |

### Browse

| Area | iOS | Android |
| --- | --- | --- |
| Open, search, select a row, editor below the table | ✅ | ✅ |
| Searching with the keyboard's Enter key | ✅ | ✅ fixed later that day (see below); before: the keyboard showed "Next" and moved the focus instead of searching |
| Sidebar button, sidebar search | ⚠️ works; the sidebar squeezes the editor (Back field under Tags) | ✅ |
| Preview, Change Deck, Delete notes | ✅ | not repeated |
| Window title | ⚠️ long titles are cut at both ends ("rowse (24 of 24 cards selectec") | ✅ |

### Decks, statistics, tools

| Area | iOS | Android |
| --- | --- | --- |
| Create Deck prompt (card above the keyboard) | ✅ | ✅ with the Enter-key fix; without it the keyboard's Next only moves to the buttons |
| Deck gear menu: rename, options, delete | ✅ | not repeated |
| Deck options: change a limit, Save | ✅ | opens (`sweep.sh`); saving not repeated |
| Filtered deck: build, study, delete | ✅ | ✅ |
| Statistics page | ✅ | ✅ |
| Statistics: Save PDF | ✅ fixed later that day: A4 PDF in Documents/Exports (see below) | ⚠️ PDF written to `Exports/`, but no message says so |
| Export (.colpkg) | ✅ Documents/Exports, visible in Files | ⚠️ written to `Android/data/io.ankidesk.kioku/files/Exports`, which Android 11+ hides from most file managers; there is no share option |
| Create Backup | ✅ | ✅ |
| Check Database, Check Media, Empty Cards | ✅ | ✅ (identical results on both) |
| Preferences: switch to Light and back | ✅ | ✅ |
| Every main window full screen, nothing wider than the screen (`sweep.sh`) | ✅ 12 windows | ✅ 12 windows |
| Review Heatmap on the deck list | ⚠️ slightly wider than the screen | ⚠️ slightly wider than the screen |

### Add-ons

| Area | iOS | Android |
| --- | --- | --- |
| Tools › Add-ons › Get Add-ons, code 1771074083 (Review Heatmap) | ✅ downloaded and installed | ✅ |
| Add-on active after restarting the app | ✅ | ✅ |

### AnkiWeb sync (both phones on the same account)

Tested in a new, empty profile on each phone so the account's data was never
uploaded over.

| Step | iOS | Android |
| --- | --- | --- |
| Login card, typing email and password, OK | ✅ | ✅ |
| Empty profile: "Download from AnkiWeb?", full download (39,754 cards) | ✅ | ✅ |
| Media sync (13,677 files, about 15 files/s) | ✅ same files on both | ✅ |
| Sync while media is still syncing | shows the media sync log (as on the desktop) | same |
| Note added on Android appears on iOS after syncing both | ✅ | ✅ |
| Field edited on iOS appears on Android | ✅ | ✅ |
| Same note edited on both before syncing | ✅ the later edit wins on both, no prompt | ✅ |
| Note deleted on Android disappears on iOS | ✅ | ✅ |
| Schema change (new field) → conflict box: Upload / Download / Cancel | ⚠️ box fills the screen with a large empty gap | ✅ card with stacked buttons |
| Choosing Download resolves the conflict | ✅ | ✅ |
| Auto sync when opening and closing a profile | ✅ | ✅ |

Check Database marks the collection for a full sync (as on the desktop), so
the next sync asks Upload/Download again.

### Open problems found in this round

- **Android: keyboard Enter = "Next".** Qt reports `EnterKeyNext` for
  single-line fields, so Browse's search, prompts and the login can't be
  submitted from the keyboard. Fixed in `shared/python/kioku/windows.py`
  (`EnterKeyFilter`); verified in the build installed later that day.
- **Android: system bars disappear** after a popup from another app (the
  "Open with" browser chooser). Qt 6.11's
  `QtWindowInsetsController.isFullScreen()` (API 30+) treats "status bar not
  visible" as full screen when the window regains focus, and
  `restoreFullScreenVisibility()` then hides the bars for good. Fixed:
  `KiokuActivity.onWindowFocusChanged` shows the bars instead.
- **Android: exports are hard to reach** on Android 11+ (`Android/data`).
  A share sheet or a document provider would fix it.
- Fixed later that day: iOS Save PDF, `{{tts}}` on both, iOS Ogg audio (see below).
- Cosmetic: Browse title cut on iOS, "History ▯" glyph on Android, cramped
  card types editor, iOS conflict box layout, Review Heatmap a little too wide.

### Fixes tested later the same day

New builds with the fixes on both phones (installed over the old ones, data
kept): iPhone 15 Pro Max (now iOS 27.0.1) and Samsung M30s.

| Fix | iOS | Android |
| --- | --- | --- |
| Ogg Vorbis and Ogg Opus card audio | ✅ hidden web view fallback; through Anki's queue, stop mid-file, mp3 unchanged | already worked (MediaPlayer) |
| Browse search from the keyboard | – | ✅ keyboard shows ✓ instead of Next; tapping it runs the search (301 → 602 cards) |
| `{{tts}}` | ✅ 193 voices, `en_US` → Apple_Samantha; stop mid-sentence | ✅ Samsung engine's 4 voices (en_US, en_GB, en_IN, hi_IN); a sentence spoken and reported done |
| Statistics: Save PDF | ✅ 4 A4 pages | (already worked) |
| System bars after the "Open with" chooser | – | ✅ both bars back after closing the chooser |

Samsung's TTS engine reports locales as `eng` (no country); the language is
taken from its voice names (`en-US-SMTf00`).

## Sync server and AnkiDroid's media (2026-10-22)

Guide: [sync-server.md](sync-server.md). Fixes: [fixes.md](fixes.md#sync-server-and-ankidroids-folder-preferences--advanced).

### Host tests (`shared/tests/run.sh`, macOS, Anki 26.8.1 + patched rsbridge)

48 tests, all passing (three runs in a row for the server tests):

- Server: start, stop, restart on the same port, 25 start/stop cycles without
  leaking threads, port already in use, bad settings, Tailscale not
  connected, "All networks", the password never left in the environment.
- Syncing through it with real Anki clients: full upload/download, changes
  both ways, media both ways, wrong password and unknown user refused, a
  restart keeps data and logins, a new password needs a new login, Delete
  server data means a full upload, stopping during a 300-file media upload
  (stop returns, client doesn't hang, media complete after a restart), three
  clients syncing at once (Anki's "only one copy can sync" error for some,
  nothing lost after syncing again).
- AnkiDroid's folder: media folder override (Python side and backend, kept
  after a reopen, other collections unaffected, AnkiDroid's
  `collection.media.db` untouched), both "apps" open with media sync off and
  nothing uploaded to the server, a second process holding the collection
  (locked → message, fallback to the profile's own collection, setting turned
  off and saved), closing for the background and reopening.
- The Advanced tab (offscreen Qt): off by default, declined warning, first
  enable makes a password, settings survive a new window, port change
  restarts, bad values refused, port in use shown in red, Use for this
  profile (and declining to leave AnkiWeb, and a wrong password), Delete
  server data; the AnkiDroid group's choices, checks and what it saves on
  close.

A test helper bug found on the way: notes made in the same millisecond in
different collections get the same id, which looked like lost changes.

### Devices

Android emulator (API 37, arm64) with AnkiDroid 2.25.3 (GitHub "full" build,
`/storage/emulated/0/AnkiDroid`); iPhone 15 Pro Max (iOS 27.0.1).

| Test | Android | iPhone |
| --- | --- | --- |
| Advanced tab fits the screen | ✅ | ✅ (dark mode) |
| Turning the server on (tap, warning, Yes) | ✅ | ✅ |
| Server starts with the app, before the profile's sync check | ✅ (after a fix) | ✅ |
| Foreground service, notification, Stop action | ✅ type `specialUse`; notification shown again after allowing notifications (after a fix); Stop ends server and service, setting kept | – |
| Desktop Anki (Mac, through `adb forward`) uploads 20 notes with media; a Kioku profile downloads them through Anki's own sync UI | ✅ | – |
| Kioku profile adds a note with media and syncs; the desktop gets both | ✅ | – |
| …while Kioku was in the background for 2.5 minutes | ✅ (process kept as a foreground service) | – |
| Use for this profile, upload, a second profile downloads | ✅ | ✅ |
| Server after 60 s in the background (Settings app in front) | – | ✅ still answering |
| AnkiDroid logs in to `http://127.0.0.1:8080/` and syncs | ✅ | – |
| AnkiDroid's media: Kioku's note with an image goes into AnkiDroid's folder, AnkiDroid gets the note; AnkiDroid's note reaches Kioku; no media uploaded to the server | ✅ | – |
| All files access check, AnkiDroid version, folder checks | ✅ | – |

Not done yet: Samsung M30s (Android 11's storage), Tailscale and "All
networks" from another machine, iOS after a long time in the background.
"AnkiDroid's collection" (opening AnkiDroid's own collection) is written and
tested below but not offered: Anki's backups drop the collection's lock.

## AnkiDroid's collection (2026-10-23)

A profile that opens AnkiDroid's own `collection.anki2` (`ankidroid.FOLDER`),
still hidden (`FOLDER_READY = False`). Fixes:
[fixes.md](fixes.md#sync-server-and-ankidroids-folder-preferences--advanced).

Host tests: 56 passing, 8 new ones: the background watch only for this mode,
close and reopen with AnkiDroid's changes (screens refreshed) and without
(left alone), a busy collection kept open, reopening while another process
holds it (retry, then success once released), operations started while
closed waiting for the reopen, and Anki's backup dropping the lock.

Emulator (API 37) with AnkiDroid 2.25.3 full, profile **DroidFolder**:

| Test | Result |
| --- | --- |
| AnkiDroid started over Kioku (`monkey`, the launcher's intent): AnkiDroid resumes before Kioku's onStop | ✅ Kioku closed it in onPause in 3–60 ms, before AnkiDroid's DeckPicker; no "Database Locked" (14 times) |
| Back to Kioku after AnkiDroid answered a card, AnkiDroid force-stopped in between | ✅ reopened, AnkiDroid's review there, screens refreshed |
| Back to Kioku while AnkiDroid still has it | ✅ retry dialog (8 of 8 trials); stays locked after 60 s; Try again after a force stop reopens it; all 14 answers in the revlog |
| Retry dialog → AnkiDroid app info… → Force stop → back to Kioku | ✅ after a fix (it crashed: see fixes) |
| Tools › Switch to AnkiDroid | ✅ closed first, AnkiDroid opened it |
| AnkiDroid answering cards while its lock was gone | ❌ **lost**: two answers never reached the file. Cause: Anki's backup (see below) |

Anki's backup reads `collection.anki2` through a second file descriptor
while SQLite has it open (rslib `maybe_backup` → `read_locked_db_file`), and
closing it drops the process's POSIX locks on the file, SQLite's exclusive
lock too. Confirmed on macOS (`test_anki_backup_drops_the_lock`): a second
process is locked out before `create_backup`, opens it after. AnkiDroid's
core does this on its automatic backups, so Kioku could open the collection
while AnkiDroid kept it open, and Kioku's close then deleted the `-wal` file
AnkiDroid was still writing to. Kioku can't detect it, so the mode stays
hidden until Anki's core (Kioku's and AnkiDroid's) keeps the lock.

Not done: big collection timings, Samsung M30s, device reboots.
