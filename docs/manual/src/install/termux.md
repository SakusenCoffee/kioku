# Android, Termux

> **Applies to:** Android Termux

Needs Android 7 or newer on a 64-bit ARM phone, about 1 GB of free storage,
and 3 GB of RAM or more for a smooth experience.

You don't need Termux or Termux:X11: everything is inside the APK.

1. On the phone, download `Kioku-Termux-<version>-arm64.apk` from the
   [latest release](https://github.com/krmanik/kioku/releases/latest).
2. Open it, allow installing from your browser or file manager, and install.
3. Tap **Kioku**. The **first start unpacks the runtime**, about a minute;
   the splash screen shows the progress. Then the desktop opens with Anki.

## Updating

Install the new APK over the old one. The first start after an update
unpacks the new runtime again. Your home folder (Anki's collections,
add-ons, settings) is never touched, and Linux apps you installed from
**Software** are reinstalled automatically.

## Removing

Uninstalling deletes everything inside the app, including collections that
weren't synced or exported. Kioku never deletes anything in the phone's own
storage (Downloads, pictures…), even when you linked those folders.
