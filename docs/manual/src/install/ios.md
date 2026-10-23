# iPhone and iPad

> **Applies to:** iPhone/iPad

Needs iOS or iPadOS 17 or newer.

Kioku is distributed as an unsigned `.ipa`: you sign it with your own Apple
ID while installing (sideloading).

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

- Apps signed with a **free Apple ID expire after 7 days**. AltStore and
  SideStore refresh them in the background; with Sideloadly, install again
  before it expires. An expired app won't open, but its data is kept:
  installing again brings it back.
- To update, install the new `.ipa` over the old one (same bundle id). Your
  data stays.
- Kioku's files are in the **Files** app › On My iPhone › **Kioku**. See
  [Your Files](../using/files.md).

Problems with AltServer: see [Troubleshooting](../troubleshooting.md#altserver).
