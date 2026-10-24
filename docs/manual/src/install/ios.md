# iPhone and iPad

> **Applies to:** iPhone/iPad

Needs iOS or iPadOS 17 or newer.

Two ways to get Kioku:

- **TestFlight**, Apple's beta app: no signing, no 7-day refresh. Sign up
  with a [short form](https://forms.gle/fw4YMTdGbgD8nqPe8) to get the link.
- **Sideloading** the unsigned `.ipa` from GitHub Releases: you sign it with
  your own Apple ID while installing.

Kioku won't be in the App Store; TestFlight is the only Apple-signed way.

## TestFlight

TestFlight has a limited number of testers, so the link comes from a signup
form that allows one signup per Google account.

1. Fill in the [signup form](https://forms.gle/fw4YMTdGbgD8nqPe8); the TestFlight link is shown
   after you submit.
2. Install [TestFlight](https://apps.apple.com/app/testflight/id899247664)
   from the App Store.
3. Open the link on your iPhone or iPad and tap **Accept**, then **Install**.

New builds show up in TestFlight; turn on **Automatic Updates** there.

- **Each build expires 90 days after it was uploaded.** TestFlight shows
  the days left. Install the newer build before then; if a build has expired,
  Kioku won't open until you install a newer one. Your data is kept.
- TestFlight builds can be a little ahead of the GitHub release.
- TestFlight shares some data with the developer; see [Privacy](../privacy.md#testflight).

## AltStore (recommended)

1. Install [AltStore](https://altstore.io) with AltServer on your computer.
2. In AltStore: **Sources › +**, add
   `https://github.com/krmanik/kioku/releases/latest/download/altstore.json`.
3. Install **Kioku** from that source.

New versions then show up in AltStore's updates.

## Other sideloading tools

Download `Kioku-iOS-<version>-unsigned.ipa` from the
[latest release](https://github.com/krmanik/kioku/releases/latest) and
install it with [Sideloadly](https://sideloadly.io), SideStore,
LiveContainer or any tool that signs apps with your Apple ID.

## Things to know

- Sideloaded apps signed with a **free Apple ID expire after 7 days**. AltStore and
  SideStore refresh them in the background; with Sideloadly, install again
  before it expires. An expired app won't open, but its data is kept:
  installing again brings it back.
- To update, install the new `.ipa` over the old one (same bundle id). Your
  data stays.
- A TestFlight copy and a sideloaded copy may be separate apps with separate
  data. To switch, sync with AnkiWeb or export a `.colpkg` (File › Export)
  first.
- Kioku's files are in the **Files** app › On My iPhone › **Kioku**. See
  [Your Files](../using/files.md).

Problems with AltServer: see [Troubleshooting](../troubleshooting.md#altserver).
