# Kioku for iPadOS 16

This branch builds Kioku 0.2.5 for iPadOS 16 with Qt 6.9.3 and PyQt6 6.9.1. I tested the IPA on an A9X iPad Pro running iPadOS 16.7.12 with Dopamine and TrollStore Lite. Kioku opened, synced a collection, loaded add-ons, and served AnkiConnect requests.

Download the IPA from the [release page](https://github.com/SakusenCoffee/kioku/releases/tag/ipados16-v0.2.5-1). It is unsigned. Install it with TrollStore Lite, then open Kioku and set up your profile. If you already use Anki on another device, sync it through AnkiWeb.

## Use AnkiConnect with Yomitan

In Kioku, open **Tools → Add-ons → Get Add-ons** and enter `2055492159` to install AnkiConnect. Restart Kioku. In Yomitan, set the AnkiConnect server to `http://127.0.0.1:8765`.

Kioku must be running for Yomitan to add cards. Without the background tweak below, keep Kioku visible beside your browser in Split View.

## Keep Kioku running behind the browser

This part needs a jailbroken iPad. [Immortalizer](https://github.com/sergealagon/Immortalizer) is a separate tweak from the Havoc repo; it is not included in the IPA.

1. Install **Immortalizer** in Sileo or Zebra. I tested version 2.0.0-1 on Dopamine.
2. Tap **Restart SpringBoard** when the package manager asks.
3. On the Home Screen, long press the Kioku icon and choose **Enable Immortal Foreground**.
4. Open Kioku, then switch to your browser. Yomitan can now reach AnkiConnect while the browser is full screen.

If the server stops after a reboot, run Dopamine again and reopen Kioku. Force quitting Kioku also stops the server. Keeping it active in the background uses more battery.

## About this release

The iOS deployment target is 16.0. The main build change is using Qt 6.9 and PyQt6 6.9, which still support iPadOS 16. Upstream Kioku currently targets iOS 17 or later.

This is a community build of [Kioku by krmanik](https://github.com/krmanik/kioku), not an official upstream release. The source changes are on the [`ipados16` branch](https://github.com/SakusenCoffee/kioku/tree/ipados16).
