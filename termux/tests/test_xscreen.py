"""The remote screen with the real X programs from the app's prefix: Xvfb,
x11vnc and JWM, on a display of their own (:7; pid files and logs in a
temporary TMPDIR, X sockets in the prefix as always), next to a real session
without touching it. A VNC client (vnc_client.py) sees what a viewer gets.

What XFCE's Display settings did on the phone (2026-10-23): Xvfb's only mode
has no timings ("1920x1080 @ nan"), so Apply couldn't find its mode, and
Scale (CRTC transforms, which Xvfb lacks) shrank the screen to 1280x720 and
switched its output off for good. break_like_xfce() does the same.

    tools/test_on_device.sh        (REAL_PREFIX: the app's prefix)
"""

from __future__ import annotations

import importlib
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest

import vnc_client

REAL = os.environ.get("REAL_PREFIX", "")
HAVE_X = all(os.path.exists(os.path.join(REAL, p)) for p in ("bin/Xvfb", "bin/x11vnc", "bin/jwm", "lib/libxcb-randr.so"))
DISPLAY = ":7"

FAKE_ANKI = """
import signal, sys, time
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
while True: time.sleep(0.1)
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def until(check, seconds: float, what: str):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if value := check():
            return value
        time.sleep(0.2)
    raise AssertionError(f"{what}: not within {seconds} s")


class _X(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tempfile.mkdtemp(prefix="xscreen-test-")
        self.env_before = dict(os.environ)
        os.environ.update({"PREFIX": REAL, "TMPDIR": os.path.join(self.root, "tmp"),
                           "HOME": os.path.join(self.root, "home"), "ANKIDX_REMOTE_DISPLAY": DISPLAY})
        for d in ("tmp", "home"):
            os.makedirs(os.path.join(self.root, d))
        import ankidesk_xscreen
        self.xs = importlib.reload(ankidesk_xscreen)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.env_before)
        shutil.rmtree(self.root, ignore_errors=True)

    def screen(self):
        s = self.xs.Screen(DISPLAY)
        self.addCleanup(s.close)
        return s

    def on(self, s) -> tuple[tuple[int, int], str] | None:
        """(screen size, mode) while an output is on."""
        st = s.state()
        names = {m.id: (n, round(self.xs.refresh(m))) for m, n in st["modes"]}
        crtc = st["crtcs"][0]
        return (st["screen"], names[crtc["mode"]]) if crtc["mode"] and crtc["outputs"] else None

    def break_like_xfce(self, s) -> None:
        st = s.state()
        s.set_crtc(st["crtcs"][0]["id"], 0, [], st["config_ts"])
        s.set_screen_size(1280, 720)


@unittest.skipUnless(HAVE_X, "needs Xvfb, x11vnc and JWM in REAL_PREFIX")
class KeeperTest(_X):
    """ankidesk_xscreen.keep() on a bare Xvfb."""

    def setUp(self) -> None:
        super().setUp()
        self.xvfb = subprocess.Popen([os.path.join(REAL, "bin/Xvfb"), DISPLAY, "-screen", "0", "1920x1080x24",
                                      "-nolisten", "tcp", "-dpi", "96"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        sock = os.path.join(REAL, "tmp", ".X11-unix", "X" + DISPLAY[1:])
        def listening() -> bool:
            with socket.socket(socket.AF_UNIX) as c:
                return c.connect_ex(sock) == 0
        try:
            until(listening, 10, "Xvfb listening")
        except AssertionError:
            self.xvfb.kill()
            raise
        self.stopped = False
        self.log: list[str] = []
        ready = threading.Event()
        self.keeper = threading.Thread(target=self.xs.keep, args=(DISPLAY, lambda: self.stopped,
                                                                  self.log.append, ready.set), daemon=True)
        self.keeper.start()
        self.assertTrue(ready.wait(10))

    def tearDown(self) -> None:
        self.stopped = True
        self.keeper.join(5)
        self.xvfb.terminate()  # SIGKILL would leave its socket behind
        self.xvfb.wait()
        super().tearDown()

    def test_60_hz_modes_up_to_the_screen_size(self) -> None:
        s = self.screen()
        modes = {(m.width, m.height) for m, _ in s.state()["modes"] if round(self.xs.refresh(m)) == 60}
        self.assertEqual(modes, {(w, h) for w, h in self.xs.SIZES if w <= 1920 and h <= 1080})
        # and the screen uses one of them: a desktop sees "60 Hz", not NaN
        self.assertEqual(self.on(s), ((1920, 1080), ("1920x1080_60", 60)))

    def test_a_screen_left_off_comes_back(self) -> None:
        s = self.screen()
        self.break_like_xfce(s)
        self.assertIsNone(self.on(s))
        self.assertEqual(until(lambda: self.on(s), self.xs.QUIET_SECONDS + 5, "screen back"),
                         ((1920, 1080), ("1920x1080_60", 60)))
        self.assertIn("back to 1920x1080", " ".join(self.log))

    def test_a_resolution_change_stays(self) -> None:
        s = self.screen()
        st = s.state()
        mode = next(m for m, n in st["modes"] if n == "1600x900")
        # as a desktop applies one: output off, new screen size, output on
        s.set_crtc(st["crtcs"][0]["id"], 0, [], st["config_ts"])
        s.set_screen_size(1600, 900)
        s.set_crtc(st["crtcs"][0]["id"], mode.id, st["outputs"], s.state()["config_ts"])
        time.sleep(self.xs.QUIET_SECONDS + 2)
        self.assertEqual(self.on(s), ((1600, 900), ("1600x900", 60)))
        # broken after that: back to 1600x900, the last size that worked
        self.break_like_xfce(s)
        self.assertEqual(until(lambda: self.on(s), self.xs.QUIET_SECONDS + 5, "screen back")[0], (1600, 900))


@unittest.skipUnless(HAVE_X, "needs Xvfb, x11vnc and JWM in REAL_PREFIX")
class SessionTest(_X):
    """The whole remote session (ankidesk_remote.start), real X programs,
    a stand-in Anki; a VNC viewer connected throughout."""

    def setUp(self) -> None:
        super().setUp()
        self.launcher = os.path.join(self.root, "launch_anki.py")
        with open(self.launcher, "w") as fh:
            fh.write(f"#!{sys.executable}\n" + textwrap.dedent(FAKE_ANKI))
        os.chmod(self.launcher, 0o755)
        import ankidesk_remote
        self.r = importlib.reload(ankidesk_remote)
        self.r.LAUNCH_ANKI = self.launcher
        s = self.r.load_settings()
        s.listen, s.desktop, s.resolution = self.r.LOCAL, self.r.SIMPLE, "1920x1080"
        s.vnc_port, s.web_port = free_port(), free_port()
        self.r.save_settings(s)
        self.s = s

    def tearDown(self) -> None:
        for pid in self.r.anki_pids():
            os.kill(pid, signal.SIGKILL)
        for name in ("web", "vnc", "jwm", "xvfb"):
            self.r.stop_process(name, seconds=2)
        super().tearDown()

    def viewer(self, seconds: float = 0) -> vnc_client.Client:
        """Connects, retrying for `seconds` as noVNC's reconnect does."""
        def connect():
            try:
                return vnc_client.Client("127.0.0.1", self.s.vnc_port, self.s.password)
            except OSError:
                return None
        c = until(connect, max(seconds, 0.5), "VNC connection")
        self.addCleanup(c.close)
        return c

    def corner(self, c: vnc_client.Client) -> tuple[int, int]:
        return c.update((0, 0, 8, 8))

    def test_display_changes_and_x11vnc_exits_keep_the_viewer(self) -> None:
        self.r.start()
        c = self.viewer()
        self.assertEqual(self.corner(c), (1920, 1080))
        s = self.screen()
        self.assertEqual(self.on(s), ((1920, 1080), ("1920x1080_60", 60)))

        # display settings shrink the screen and leave it off: the viewer
        # follows, stays connected, and gets the full screen back
        self.break_like_xfce(s)
        self.assertEqual(until(lambda: self.corner(c) == (1280, 720) and c.width, 10, "viewer sees 1280x720"), 1280)
        until(lambda: self.corner(c) == (1920, 1080), self.xs.QUIET_SECONDS + 8, "viewer sees 1920x1080 again")
        self.assertIsNotNone(self.on(s))

        # x11vnc exits: the viewer loses it, and reconnecting works
        os.kill(self.r.tracked_pid("vnc"), signal.SIGKILL)
        with self.assertRaises(OSError):
            for _ in range(20):
                self.corner(c)
                time.sleep(0.1)
        c = self.viewer(seconds=15)
        self.assertEqual(self.corner(c), (1920, 1080))

        self.r.stop()
        for name in ("web", "vnc", "jwm", "xvfb"):
            self.assertIsNone(self.r.tracked_pid(name), name)


if __name__ == "__main__":
    unittest.main()
