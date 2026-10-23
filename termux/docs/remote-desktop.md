# Remote desktop

Use Kioku's Anki from a computer: in a web browser, or in any VNC viewer, on a
desktop-sized screen with a real mouse and keyboard. The phone does the work and
keeps your collection; the computer only shows it.

| The Remote page | While it is on | In a web browser |
|---|---|---|
| <img src="screenshots/remote-settings.png" width="240" alt="Remote desktop page: Turn on, Listen on (Tailscale, All networks, This phone only), screen size"> | <img src="screenshots/remote-active.png" width="240" alt="Remote session active: the web and VNC addresses, the password, Turn off"> | <img src="screenshots/remote-browser.png" width="320" alt="Anki on the remote screen in a web browser through noVNC, with a taskbar"> |

**Settings › Remote desktop › Turn on.** Anki closes on the phone (it saves first,
as when it quits) and opens on the remote screen. The page then shows the
addresses to open on the computer and the password. The phone shows
**Remote session active** until you turn it off; Anki then moves back to the phone.

## Connecting

| From | Open |
|---|---|
| a web browser | `http://<address>:6080/` (the page shows the full address), then enter the password |
| a VNC viewer (TigerVNC, RealVNC, macOS Screen Sharing, Remmina) | `<address>:5900`, then the password |

Where Kioku listens (choose it before turning it on):

| Listen on | Who can connect |
|---|---|
| **Tailscale** (default) | your own devices on your Tailscale network, from anywhere. Tailscale encrypts the connection. The Tailscale app must be connected on the phone. |
| **All networks** | any device on the same Wi-Fi or VPN. **Not encrypted**: VNC only scrambles the password check. Use it only on networks you trust. |
| **This phone only** | nothing outside the phone; for a USB cable with `adb forward tcp:6080 tcp:6080 && adb forward tcp:5900 tcp:5900`, then `http://localhost:6080/vnc.html` on the computer. |

The password is made up when you first open the page; tap it for a new one. VNC
uses at most 8 characters of a password, so it is 8 random letters and digits.

Screen sizes: 1280 × 800, 1600 × 900, 1920 × 1080 (default) and 2560 × 1440. The
web viewer scales the screen to the browser window.

## While it is on

- Anki runs on the remote screen at 100% size, without the phone's touch changes
  (on-screen keyboard, one-finger scrolling). Its windows have a taskbar, with an
  **Anki** button to open it again if you close it.
- Tapping Anki on the phone shows the Remote page instead: Anki can be open in one
  place only.
- Other apps on the phone's desktop keep working on the phone.
- The phone keeps the CPU and Wi-Fi awake (a wake lock and a Wi-Fi lock), and the
  notification says that the remote desktop is on. This uses battery: keep the
  phone charging for long sessions.
- **Run without battery limits** (on the Remote page): Android otherwise stops the
  network of an app with the screen off after a while (Doze), which ends the
  session. Android asks once; the page shows whether it is allowed.

## Turning it off

**Turn off** on the Remote page. Anki on the remote screen closes (it saves first)
and opens on the phone again. If Anki doesn't close because one of its windows is
asking something (an unsaved card in Add, say), the session stays on so you can
answer it on the computer; then turn it off again.

**Power off** in Settings also ends the remote session first.

If Kioku is stopped some other way (Android ends it, or the phone restarts), the
remote session is gone too, and Anki opens on the phone the next time.

## How it works

- A second X server, **Xvfb**, on display `:1`, at the chosen size, with its own
  JWM window manager. The phone's display is Termux:X11 on `:0`.
- Anki is moved by closing it (SIGTERM, Anki's own clean close) and starting it on
  `:1` with `ANKIDX_REMOTE=1` (`launch_anki.py`: scale 1, no `ankidesk_mobile`).
- **x11vnc** shares `:1` on port 5900 with the password, with `-noshm` (Android has
  no SysV shared memory for apps; without it x11vnc exits right after it starts
  listening). Its library, libvncserver, also accepts WebSocket connections on that
  port, so **noVNC** (1.7.0, bundled) connects to it directly, with no websockify in
  between. `ankidesk_novnc.py` serves noVNC on port 6080 and makes its
  `defaults.json` per request, with the host the browser used (noVNC only takes its
  own port together with a host), so the same page works over Tailscale, Wi-Fi or
  `adb forward`.
- Anki keeps separate window sizes for the remote screen (`kioku_remote_` keys in
  the profile), so the phone's are untouched; the first time, it opens maximized.
- Code: `rootfs-overlay/share/ankidx/ankidesk_remote.py` and `ankidesk_novnc.py` (no Qt; tests in
  `tests/test_remote.py`, run on the phone with `tools/test_on_device.sh`), the
  Remote page in `ankidesk_shell.py`, and `remote/on`, `remote/off`, `battery` in
  `AndroidBridge.java` / `AnkiService.java`.
- Size: Xvfb, x11vnc and their libraries add about 8 MB to the runtime, noVNC
  1.4 MB.

## Tested

Android emulator (API 37, arm64), runtime rebuilt with current Termux packages,
2026-10-23:

| Test | Result |
| --- | --- |
| `tools/test_on_device.sh`: 19 tests with stand-ins for Xvfb, JWM, x11vnc and Anki (moving Anki and back, failures putting everything back, an Anki that doesn't close, port in use, power off, stale state, reused pids, only this launcher counts as Anki) | ✅ twice in a row, next to a real session without touching it |
| Turn on with Tailscale not connected | ✅ refused with the reason, nothing changed |
| Turn on (This phone only): Anki closes on the phone, opens on `:1` maximized at 100%, the phone shows the Remote page | ✅ |
| VNC viewer (RFB 3.8, VNC password) through `adb forward`: wrong password refused, right one gets the 1920 × 1080 screen, three times | ✅ after a fix (`-noshm`) |
| Web browser (Chrome, noVNC) at `http://127.0.0.1:6080/?password=…`, three times | ✅ after a fix (`defaults.json` per request) |
| A deck created on the remote screen is there after Turn off; the phone's Anki window is full size again | ✅ after a fix (separate window sizes) |
| Notification text, wake lock and Wi-Fi lock while on; released on Turn off, restart and Power off | ✅ |
| Run without battery limits: Android's prompt, then the page shows it allowed | ✅ after a fix (the state is re-read after the prompt) |
| The app force-stopped while on: next start clears the stale session, Anki opens on the phone | ✅ |
| Power off while on: Anki on `:1` closes cleanly, then the session ends | ✅ after a fix (Power off didn't end the session at all: Qt 6 cancels `quit()` when a window refuses to close, and the desktop always does; it now uses `exit()`) |
| Updating the app keeps the collection (the deck made remotely) | ✅ |

Not done yet: a real phone, Tailscale and Wi-Fi from another computer, long sessions
with the screen off, 2560 × 1440.
