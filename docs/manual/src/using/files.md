# Your Files

> **Applies to:** iPhone/iPad, Android native, Android Termux (differences noted per variant)

Kioku keeps Anki's data (profiles, collections, media, backups, add-ons)
inside the app. It survives updates; uninstalling deletes it.

## Importing

**File › Import** (or **Import File** under the deck list) opens the phone's
file picker. Pick a `.colpkg`, `.apkg`, text or CSV file; Anki then imports it
as described in [Anki: Importing](https://docs.ankiweb.net/importing/intro.html).
A big `.colpkg` with media can take minutes on a phone; keep Kioku open.

| Variant | Also |
| --- | --- |
| iPhone, iPad | Put files in Files › Kioku first, or pick them from iCloud Drive. |
| Android, native | Any folder the system picker shows: Downloads, Drive… |
| Termux | **Settings › Import a deck from the phone**, or open/share an `.apkg`/`.colpkg` from another app to Kioku. |

Images for the editor and Image Occlusion are picked the same way.

## Exporting, Save PDF and backups

| Variant | Exports and PDFs go to |
| --- | --- |
| iPhone, iPad | Files › On My iPhone › Kioku › **Exports** |
| Android, native | `Android/data/io.ankidesk.kioku/files/Exports` (see below) |
| Termux | the home folder, or a linked phone folder (Settings › Phone storage) |

**Statistics › Save PDF** writes there too.

On Android 11 and newer, most file managers can't open `Android/data`.
Connect the phone to a computer over USB to copy them, or use AnkiWeb sync
instead of export files.

**Backups** are made automatically, as in
[Anki: Backups](https://docs.ankiweb.net/backups.html). File › Create Backup
makes one now; restore with File › Switch Profile › Open Backup.

## iPhone: the Files app

Files › On My iPhone › **Kioku** shows:

| Folder | What |
| --- | --- |
| `Anki2/` | profiles, collections, media, add-ons (as on a computer) |
| `Exports/` | exported decks, PDFs |

Don't change files in `Anki2/` while Kioku is open.

## Termux: phone storage

**Settings › Phone storage** asks for Android's all-files access and links
the phone's folders (Downloads, Documents, Pictures…) into Kioku's home
folder, so Files and Anki can reach them. Tap again to unlink. Kioku's home
folder also shows in Android's Files app.
