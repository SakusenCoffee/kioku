# Remote desktop: how it works

User guide: [manual](https://krmanik.github.io/kioku/features/remote-desktop.html) (`docs/manual/src/features/remote-desktop.md`).

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
