"""Tests for ankidesk_remote.py, the remote desktop's session logic.

They use /proc, so they run on the phone, in the app's own prefix
(tools/test_on_device.sh), with stand-ins for Xvfb, JWM, x11vnc and Anki that
behave like them where it matters: Xvfb opens the display's socket, x11vnc
stores its password and listens, Anki quits on SIGTERM (or, to test that
case, doesn't). The real Anki and the real desktop are never touched: only
processes started from this test's own launcher count as Anki.

    python -m unittest test_remote      (with ankidesk_remote.py on sys.path)
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import signal
import socket
import stat
import sys
import tempfile
import textwrap
import time
import unittest
import urllib.request

FAKE_XVFB = """
import os, signal, socket, sys, time
tmp = os.environ["TMPDIR"]
open(os.path.join(tmp, "xvfb.args"), "w").write(" ".join(sys.argv[1:]))
os.makedirs(os.path.join(tmp, ".X11-unix"), exist_ok=True)
path = os.path.join(tmp, ".X11-unix", "X1")
lock = os.path.join(tmp, ".X1-lock")
if os.path.exists(lock):
    sys.exit("Server is already active for display 1")
open(lock, "w").write(str(os.getpid()))
s = socket.socket(socket.AF_UNIX); s.bind(path); s.listen()
def bye(*_):
    for p in (path, lock):
        try: os.remove(p)
        except OSError: pass
    sys.exit(0)
signal.signal(signal.SIGTERM, bye)
while True: time.sleep(1)
"""

FAKE_JWM = """
import os, sys, time
open(os.path.join(os.environ["TMPDIR"], "jwm.args"), "w").write(
    os.environ.get("DISPLAY", "") + " " + " ".join(sys.argv[1:]))
while True: time.sleep(1)
"""

FAKE_X11VNC = """
import os, socket, sys, time
args = sys.argv[1:]
if args[0] == "-storepasswd":
    open(args[2], "w").write("obfuscated " + args[1]); sys.exit(0)
tmp = os.environ["TMPDIR"]
open(os.path.join(tmp, "vnc.args"), "w").write(" ".join(args))
if os.path.exists(os.path.join(tmp, "vnc-fails")):
    sys.exit("x11vnc: cannot open display")
port = int(args[args.index("-rfbport") + 1])
host = "127.0.0.1" if "-localhost" in args else args[args.index("-listen") + 1]
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind((host, port)); s.listen()
if os.path.exists(os.path.join(tmp, "vnc-dies")):
    time.sleep(0.5)  # as without -noshm: listening, then gone
    sys.exit(1)
while True: time.sleep(1)
"""

# stands in for launch_anki.py: records where it runs, quits on SIGTERM
# after "saving", unless the test made it stuck (a dialog asking something)
FAKE_ANKI = """
import json, os, signal, sys, time
tmp = os.environ["TMPDIR"]
with open(os.path.join(tmp, "anki.runs"), "a") as fh:
    fh.write(json.dumps({k: os.environ.get(k) for k in
        ("DISPLAY", "ANKIDX_REMOTE", "ANKIDX_SCALE", "ANKIDX_READY_FILE")}) + "\\n")
def term(*_):
    if os.path.exists(os.path.join(tmp, "anki-stuck")):
        return
    time.sleep(0.3)
    sys.exit(0)
signal.signal(signal.SIGTERM, term)
while True: time.sleep(0.1)
"""


# XFCE's session: dbus-launch runs what follows --exit-with-session; startxfce4
# records how it was started and runs until stopped, or quits at once when the
# test "logs out" (xfce-logout)
FAKE_DBUS_LAUNCH = """
import os, subprocess, sys
sys.exit(subprocess.call(sys.argv[sys.argv.index("--exit-with-session") + 1:]))
"""

FAKE_STARTXFCE4 = """
import json, os, time
tmp = os.environ["TMPDIR"]
with open(os.path.join(tmp, "xfce.json"), "w") as fh:
    json.dump({"pid": os.getpid(), "DISPLAY": os.environ.get("DISPLAY"),
               "XDG_DATA_DIRS": os.environ.get("XDG_DATA_DIRS"),
               "DBUS_SESSION_BUS_ADDRESS": os.environ.get("DBUS_SESSION_BUS_ADDRESS")}, fh)
if not os.path.exists(os.path.join(tmp, "xfce-logout")):
    while True: time.sleep(1)
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class RemoteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tempfile.mkdtemp(prefix="remote-test-")
        prefix = os.path.join(self.root, "usr")
        self.env_before = dict(os.environ)
        os.environ.update({
            "PREFIX": prefix,
            "HOME": os.path.join(self.root, "home"),
            "TMPDIR": os.path.join(prefix, "tmp"),  # as in the app: X sockets are there
            "DISPLAY": ":0",
            "ANKIDX_READY_FILE": os.path.join(prefix, "tmp", "ready"),
        })
        for d in ("usr/bin", "usr/share/novnc", "usr/tmp", "home", "ankidx"):
            os.makedirs(os.path.join(self.root, d), exist_ok=True)
        with open(os.path.join(prefix, "share/novnc/vnc.html"), "w") as fh:
            fh.write("<title>noVNC</title>")
        for name, code in (("Xvfb", FAKE_XVFB), ("jwm", FAKE_JWM), ("x11vnc", FAKE_X11VNC)):
            self._script(os.path.join(prefix, "bin", name), code)
        self.launcher = os.path.join(self.root, "ankidx", "launch_anki.py")
        self._script(self.launcher, FAKE_ANKI)

        import ankidesk_remote
        self.r = importlib.reload(ankidesk_remote)
        self.r.LAUNCH_ANKI = self.launcher
        self.r.ANKI_CLOSE_SECONDS = 5
        s = self.r.load_settings()
        s.listen = self.r.LOCAL
        s.vnc_port, s.web_port = free_port(), free_port()
        self.r.save_settings(s)
        self.tmp = os.environ["TMPDIR"]

    def tearDown(self) -> None:
        for pid in self.r.anki_pids():
            os.kill(pid, signal.SIGKILL)
        for name in ("web", "vnc", "jwm", "xvfb"):
            self.r.stop_process(name, seconds=2)
        for child in self.r._children:
            child.kill()
            child.wait()
        os.environ.clear()
        os.environ.update(self.env_before)
        shutil.rmtree(self.root, ignore_errors=True)

    @staticmethod
    def _script(path: str, code: str) -> None:
        with open(path, "w") as fh:
            fh.write(f"#!{sys.executable}\n" + textwrap.dedent(code))
        os.chmod(path, 0o755)

    def _phone_anki(self) -> int:
        """Anki on the phone, as session.sh starts it."""
        self.r.start_anki(remote=False)
        return self._wait_anki(":0")

    def _wait_anki(self, display: str) -> int:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            pids = [p for p in self.r.anki_pids() if self.r.anki_display(p) == display]
            # and it has written down where it runs
            if pids and os.path.exists(os.path.join(self.tmp, "anki.runs")) \
                    and self._runs()[-1]["DISPLAY"] == display:
                return pids[0]
            time.sleep(0.1)
        self.fail(f"no Anki on {display}")

    def _read(self, name: str) -> str:
        with open(os.path.join(self.tmp, name)) as fh:
            return fh.read()

    def _runs(self) -> list[dict]:
        with open(os.path.join(self.tmp, "anki.runs")) as fh:
            return [json.loads(line) for line in fh]

    # Settings and addresses
    ##################################################################

    def test_settings_get_a_private_password(self) -> None:
        os.remove(self.r.SETTINGS_FILE)
        s = self.r.load_settings()
        self.assertEqual(len(s.password), self.r.PASSWORD_LENGTH)
        self.assertEqual(stat.S_IMODE(os.stat(self.r.SETTINGS_FILE).st_mode), 0o600)
        self.assertEqual(self.r.load_settings().password, s.password)
        self.assertEqual(s.listen, self.r.TAILSCALE)

    def test_settings_problems(self) -> None:
        S = self.r.Settings
        self.assertIsNone(S(password="abcdefgh").problem())
        self.assertIn("6 characters", S(password="abc").problem())
        self.assertIn("differ", S(password="abcdefgh", vnc_port=6000, web_port=6000).problem())
        self.assertIn("1024", S(password="abcdefgh", vnc_port=80).problem())
        self.assertIsNotNone(S(password="abcdefgh", resolution="99x99").problem())
        self.assertIsNotNone(S(password="abcdefgh", listen="moon").problem())

    def test_bind_host(self) -> None:
        S = self.r.Settings
        self.assertEqual(self.r.bind_host(S(listen=self.r.LOCAL)), "127.0.0.1")
        self.assertEqual(self.r.bind_host(S(listen=self.r.ALL)), "0.0.0.0")
        self.r.tailscale_address = lambda: None
        with self.assertRaisesRegex(self.r.RemoteError, "Tailscale isn't connected"):
            self.r.bind_host(S(listen=self.r.TAILSCALE))
        self.r.tailscale_address = lambda: "100.101.102.103"
        self.assertEqual(self.r.bind_host(S(listen=self.r.TAILSCALE)), "100.101.102.103")

    def test_novnc_host_of(self) -> None:
        import ankidesk_novnc
        self.assertEqual(ankidesk_novnc.host_of("100.1.2.3:6080"), "100.1.2.3")
        self.assertEqual(ankidesk_novnc.host_of("[fd7a:115c::1]:6080"), "[fd7a:115c::1]")
        self.assertEqual(ankidesk_novnc.host_of("phone.tail1234.ts.net"), "phone.tail1234.ts.net")

    def test_addresses(self) -> None:
        s = self.r.Settings(vnc_port=5901, web_port=6081)
        found = dict(self.r.addresses(s, "100.101.102.103"))
        self.assertEqual(found["Tailscale, web browser"], "http://100.101.102.103:6081/vnc.html")
        self.assertEqual(found["Tailscale, VNC viewer"], "100.101.102.103:5901")
        self.r.network_address = lambda: "192.168.1.20"
        self.r.tailscale_address = lambda: None
        self.assertEqual(dict(self.r.addresses(s, "0.0.0.0"))["This network, VNC viewer"], "192.168.1.20:5901")

    # Processes
    ##################################################################

    def test_spawn_track_stop(self) -> None:
        pid = self.r.spawn("probe", [sys.executable, "-c", "import time; time.sleep(60)"])
        self.assertEqual(self.r.tracked_pid("probe"), pid)
        self.r.stop_process("probe")
        self.assertIsNone(self.r.tracked_pid("probe"))
        self.assertFalse(self.r._alive(pid))

    def test_a_reused_pid_is_not_killed(self) -> None:
        # this test's own pid under another program's name
        with open(self.r._pid_file("xvfb"), "w") as fh:
            fh.write(f"{os.getpid()} Xvfb")
        self.assertIsNone(self.r.tracked_pid("xvfb"))
        self.r.stop_process("xvfb")  # must not kill us

    def test_only_this_launcher_counts_as_anki(self) -> None:
        other = os.path.join(self.root, "elsewhere", "launch_anki.py")
        os.makedirs(os.path.dirname(other))
        self._script(other, FAKE_ANKI)
        import subprocess
        proc = subprocess.Popen([sys.executable, other], env=dict(os.environ))
        try:
            time.sleep(0.5)
            self.assertNotIn(proc.pid, self.r.anki_pids())
        finally:
            proc.kill()
            proc.wait()

    # The session
    ##################################################################

    def test_start_moves_anki_and_stop_moves_it_back(self) -> None:
        phone = self._phone_anki()
        info = self.r.start()
        s = self.r.load_settings()

        # Anki on the phone closed (SIGTERM, its own save), now on :1
        self.assertFalse(self.r._alive(phone))
        remote = self._wait_anki(":1")
        run = self._runs()[-1]
        self.assertEqual((run["DISPLAY"], run["ANKIDX_REMOTE"], run["ANKIDX_SCALE"]), (":1", "1", "1"))
        self.assertIsNone(run["ANKIDX_READY_FILE"])
        self.assertIn("1920x1080x24", self._read("xvfb.args"))
        self.assertTrue(self._read("jwm.args").startswith(":1 -f "))
        vnc = self._read("vnc.args")
        self.assertIn("-localhost", vnc)
        self.assertIn(f"-rfbport {s.vnc_port}", vnc)
        self.assertIn("-rfbauth", vnc)
        self.assertEqual(stat.S_IMODE(os.stat(self.r.PASSWD_FILE).st_mode), 0o600)

        # the web viewer, set up to connect to x11vnc's own port
        base = f"http://127.0.0.1:{s.web_port}"
        self.assertIn(b"noVNC", urllib.request.urlopen(base + "/vnc.html", timeout=5).read())
        defaults = json.loads(urllib.request.urlopen(base + "/defaults.json", timeout=5).read())
        self.assertEqual((defaults["host"], defaults["port"], defaults["path"]), ("127.0.0.1", s.vnc_port, ""))
        # the host the browser used (Tailscale, Wi-Fi), not one fixed address
        req = urllib.request.Request(base + "/defaults.json", headers={"Host": f"100.101.102.103:{s.web_port}"})
        self.assertEqual(json.loads(urllib.request.urlopen(req, timeout=5).read())["host"], "100.101.102.103")
        self.assertIn(b"noVNC", urllib.request.urlopen(base + "/", timeout=5).read())
        # "/" keeps the query (?password=...) when it opens vnc.html
        page = urllib.request.urlopen(base + "/?password=x", timeout=5)
        self.assertTrue(page.geturl().endswith("/vnc.html?password=x"), page.geturl())
        self.assertEqual(json.loads(urllib.request.urlopen(base + "/mandatory.json", timeout=5).read()), {})

        # what the phone shows
        self.assertTrue(self.r.is_active())
        self.assertEqual(self.r.state()["password"], s.password)
        self.assertIn(("This phone, web browser", base + "/vnc.html"), [tuple(a) for a in info["addresses"]])

        self.r.stop()
        self.assertFalse(self.r._alive(remote))
        self._wait_anki(":0")
        self.assertEqual(self._runs()[-1]["DISPLAY"], ":0")
        self.assertFalse(self.r.is_active())
        for name in ("xvfb", "jwm", "vnc", "web"):
            self.assertIsNone(self.r.tracked_pid(name), name)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".X11-unix", "X1")))

    def test_x11vnc_comes_back_when_it_exits(self) -> None:
        # what viewers reconnect to (noVNC does) after x11vnc died, e.g. on
        # a screen change
        self.r.start()
        s = self.r.load_settings()
        self.assertIn("-xrandr resize", self._read("vnc.args"))
        first = self.r.tracked_pid("vnc")
        os.kill(first, signal.SIGKILL)
        deadline = time.monotonic() + 10
        while self.r.tracked_pid("vnc") in (None, first):
            if time.monotonic() > deadline:
                self.fail("x11vnc wasn't started again")
            time.sleep(0.2)
        self.assertTrue(self.r.wait_port("127.0.0.1", s.vnc_port, 5))
        with open(self.r._log_file("vnc")) as fh:
            self.assertIn("started again", fh.read())

        self.r.stop()
        self.assertIsNone(self.r.tracked_pid("vnc"))
        time.sleep(3)  # and nothing starts it after the session ended
        self.assertIsNone(self.r.tracked_pid("vnc"))

    def test_the_helper_is_up_before_the_desktop(self) -> None:
        # it adds the display modes the desktop reads when it starts
        self.r.start()
        web = self.r.tracked_pid("web")
        self.assertEqual(self.r._cmdline(web)[-4:-3], ["serve"])
        def started(name: str) -> int:  # in clock ticks since boot
            with open(f"/proc/{self.r.tracked_pid(name)}/stat") as fh:
                return int(fh.read().rsplit(")", 1)[1].split()[19])
        self.assertLessEqual(started("web"), started("jwm"))
        self.r.stop()

    # XFCE as the remote desktop
    ##################################################################

    def _fake_xfce(self) -> None:
        bin_ = os.path.join(os.environ["PREFIX"], "bin")
        os.symlink("/system/bin/sh" if os.path.exists("/system/bin/sh") else "/bin/sh", os.path.join(bin_, "dash"))
        self._script(os.path.join(bin_, "dbus-launch"), FAKE_DBUS_LAUNCH)
        self._script(os.path.join(bin_, "startxfce4"), FAKE_STARTXFCE4)
        self._script(os.path.join(bin_, "xfdesktop"), "")
        os.environ["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/phone/desktop/bus"
        s = self.r.load_settings()
        s.desktop = self.r.XFCE
        self.r.save_settings(s)

    def _wait_file(self, name: str) -> str:
        deadline = time.monotonic() + 10
        while not os.path.exists(os.path.join(self.tmp, name)):
            if time.monotonic() > deadline:
                self.fail(f"{name} never appeared")
            time.sleep(0.1)
        time.sleep(0.2)
        return self._read(name)

    def test_xfce_needs_installing(self) -> None:
        S = self.r.Settings
        self.assertIn("install", S(password="abcdefgh", desktop=self.r.XFCE).problem())
        self.assertIsNotNone(S(password="abcdefgh", desktop="moon").problem())
        self.assertEqual(S().desktop, self.r.SIMPLE)

    def test_xfce_desktop_starts_and_stops_with_the_session(self) -> None:
        self._fake_xfce()
        self.r.start()
        self._wait_anki(":1")
        xfce = json.loads(self._wait_file("xfce.json"))
        self.assertEqual(xfce["DISPLAY"], ":1")
        self.assertTrue(xfce["XDG_DATA_DIRS"].startswith(self.r.XFCE_DATA + ":"))
        self.assertIsNone(xfce["DBUS_SESSION_BUS_ADDRESS"])  # its own bus, not the phone's
        with open(os.path.join(self.r.XFCE_DATA, "applications", "kioku-anki.desktop")) as fh:
            self.assertIn(self.launcher, fh.read())
        xsettings = os.path.join(os.environ["HOME"], ".config/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml")
        with open(xsettings) as fh:
            self.assertIn(self.r.XFCE_THEME, fh.read())
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "jwm.args")))

        self.r.stop()
        # the whole session tree is gone, not only the script that started it
        self.assertFalse(self.r._alive(xfce["pid"]))
        self.assertFalse(self.r.is_active())

    def test_xfce_settings_are_written_once(self) -> None:
        self._fake_xfce()
        xsettings = os.path.join(os.environ["HOME"], ".config/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml")
        os.makedirs(os.path.dirname(xsettings))
        with open(xsettings, "w") as fh:
            fh.write("chosen in XFCE")
        self.r.write_xfce_files()
        self.assertEqual(self._read_path(xsettings), "chosen in XFCE")

    def _read_path(self, path: str) -> str:
        with open(path) as fh:
            return fh.read()

    def test_xfce_log_out_leaves_the_plain_taskbar(self) -> None:
        self._fake_xfce()
        open(os.path.join(self.tmp, "xfce-logout"), "w").close()
        self.r.start()
        self.assertTrue(self._wait_file("jwm.args").startswith(":1 -f "))
        self.r.stop()
        self.assertIsNone(self.r.tracked_pid("jwm"))

    def test_start_without_anki_open_starts_it_remotely(self) -> None:
        self.r.start()
        self._wait_anki(":1")
        self.r.stop()
        self._wait_anki(":0")

    def test_failed_sharing_puts_everything_back(self) -> None:
        self._phone_anki()
        open(os.path.join(self.tmp, "vnc-fails"), "w").close()
        with self.assertRaisesRegex(self.r.RemoteError, "x11vnc"):
            self.r.start()
        self._wait_anki(":0")
        self.assertFalse(any(self.r.anki_display(p) == ":1" for p in self.r.anki_pids()))
        self.assertIsNone(self.r.tracked_pid("xvfb"))
        self.assertFalse(self.r.is_active())

    def test_sharing_that_dies_after_listening_puts_everything_back(self) -> None:
        open(os.path.join(self.tmp, "vnc-dies"), "w").close()
        with self.assertRaisesRegex(self.r.RemoteError, "x11vnc"):
            self.r.start()
        self._wait_anki(":0")
        self.assertFalse(self.r.is_active())

    def test_x11vnc_runs_without_shared_memory(self) -> None:
        self.r.start()
        self.assertIn("-noshm", self._read("vnc.args"))
        self.r.stop()

    def test_anki_that_doesnt_close_moves_nothing(self) -> None:
        phone = self._phone_anki()
        open(os.path.join(self.tmp, "anki-stuck"), "w").close()
        with self.assertRaisesRegex(self.r.RemoteError, "didn't close"):
            self.r.start()
        self.assertTrue(self.r._alive(phone))
        self.assertEqual(self.r.anki_display(phone), ":0")
        self.assertIsNone(self.r.tracked_pid("xvfb"))
        self.assertFalse(self.r.is_active())

    def test_stop_keeps_the_session_while_remote_anki_is_asking(self) -> None:
        self.r.start()
        remote = self._wait_anki(":1")
        open(os.path.join(self.tmp, "anki-stuck"), "w").close()
        with self.assertRaisesRegex(self.r.RemoteError, "didn't close"):
            self.r.stop()
        # still reachable, to answer it remotely
        self.assertTrue(self.r.is_active())
        self.assertTrue(self.r._alive(remote))
        self.assertIsNotNone(self.r.tracked_pid("vnc"))
        os.remove(os.path.join(self.tmp, "anki-stuck"))
        self.r.stop()
        self._wait_anki(":0")

    def test_port_in_use(self) -> None:
        s = self.r.load_settings()
        with socket.socket() as busy:
            busy.bind(("127.0.0.1", s.web_port))
            busy.listen()
            with self.assertRaisesRegex(self.r.RemoteError, f"Port {s.web_port}"):
                self.r.start()
        self.assertIsNone(self.r.tracked_pid("xvfb"))

    def test_power_off_ends_without_bringing_anki_back(self) -> None:
        self.r.start()
        remote = self._wait_anki(":1")
        self.r.end()
        self.assertFalse(self.r._alive(remote))
        self.assertEqual(self.r.anki_pids(), [])
        self.assertFalse(self.r.is_active())

    def test_reset_stale_after_a_restart(self) -> None:
        self.r.start()
        self.r.reset_stale()
        self.assertFalse(self.r.is_active())
        self.assertIsNone(self.r.tracked_pid("xvfb"))

    def test_stale_display_lock_is_cleared(self) -> None:
        # Xvfb was killed (the session restarted): its lock and socket remain
        os.makedirs(os.path.join(self.tmp, ".X11-unix"), exist_ok=True)
        with open(os.path.join(self.tmp, ".X1-lock"), "w") as fh:
            fh.write("999999")
        open(os.path.join(self.tmp, ".X11-unix", "X1"), "w").close()
        self.r.start()
        self.assertTrue(self.r.is_active())
        self.r.stop()


if __name__ == "__main__":
    unittest.main()
