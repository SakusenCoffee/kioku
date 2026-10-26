# FAQs

**Is this the real Anki?**
Yes: Anki desktop's own Python code and Rust core, unmodified, with a layer
that fits its windows to a phone. Your collection is a normal Anki
collection.

**Why not AnkiDroid or AnkiMobile?**
Use them if they do what you need. Kioku is for desktop add-ons and the
desktop's own Browse, editors and tools on the go.

**Can I use Kioku and AnkiDroid together?**
Yes. Sync both with AnkiWeb, or with [the phone's own sync
server](features/sync-server.md). On Android, a profile can also
[share AnkiDroid's media folder](features/ankidroid.md).

**Can Kioku open AnkiDroid's collection directly?**
No: it could lose AnkiDroid's changes. [Why](features/ankidroid.md#why-not-open-ankidroids-collection-directly).

**Does it cost anything? Is there an account?**
No. Kioku is free and open source, with no account, ads or tracking. AnkiWeb
sync uses your own AnkiWeb account.

**Where's Kioku in the App Store or Play Store?**
It isn't, and there's no plan for the App Store. Install it from
[GitHub Releases](install/intro.md); on iPhone and iPad, a
[TestFlight](install/ios.md#testflight) build is available: [sign up](https://forms.gle/fw4YMTdGbgD8nqPe8).

**Which Anki version is inside?**
Help › About shows it. Kioku 0.2.3 and later have Anki 26.09.3.

**Can I use it on a computer?**
Yes, in a browser: the [web version](install/web.md) runs in the tab
(experimental), and the [Docker image](install/self-hosted.md) runs Anki
desktop on your server and shows it in any browser, phones included. On
your own computer, [Anki desktop](https://apps.ankiweb.net) itself is the
better choice.

**My collection is huge (gigabytes of media). Which one?**
On a phone, any app variant keeps it on the phone. To use one copy from
several devices without syncing it to each, use the
[self-hosted server](install/self-hosted.md): only the screen travels to
the browser.

**Does it work on tablets?**
Yes: iPads and Android tablets, in portrait and landscape.

**Is there an Intel/32-bit Android build?**
No: arm64 only. The Docker image runs on amd64 and arm64 servers.
