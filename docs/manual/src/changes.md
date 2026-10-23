# Changes

All releases: [GitHub Releases](https://github.com/krmanik/kioku/releases).

## 0.2.2

Anki 26.08.1.

New:

- **Sync server on the phone** (iOS, Android, Preferences › Advanced): AnkiDroid,
  Kioku's profiles and Anki on your computers can sync with the phone instead
  of AnkiWeb. [Guide](features/sync-server.md).
- **AnkiDroid's media** (Android): a profile can use AnkiDroid's media folder, and
  syncs when you switch between the apps. [Guide](features/ankidroid.md).
- **Remote desktop** (Termux): use the phone's Anki from a computer's web browser
  or VNC viewer. [Guide](features/remote-desktop.md).
- **`{{tts}}` text-to-speech** with the phone's voices (iOS, Android).
- **Statistics › Save PDF** on iPhone (iOS).
- **Ogg/Opus card audio** on iPhone (iOS).
- The review screen's **Edit** and **More** are in the Edit menu (iOS, Android).

Fixed:

- Crash right after choosing the language on first start with VoiceOver or
  another accessibility feature on, and on iOS 18 (iOS).
- The keyboard's Enter key now submits Browse's search, prompts and the login
  (Android).
- Status and navigation bars disappeared after another app's popup, such as
  the "Open with" chooser (Android).
- Power off in the Termux desktop didn't end the session (Termux).

iOS = iPhone/iPad, Android = Android native, Termux = Android Termux.

## Earlier

See [GitHub Releases](https://github.com/krmanik/kioku/releases).
