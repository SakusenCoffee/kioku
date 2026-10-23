"""Remote desktop (Settings > Remote desktop): Anki on a desktop-sized screen,
used from a computer.

Turning it on:

1. starts a second X server, Xvfb on :1, at a desktop resolution, with JWM;
2. moves Anki there: Anki on the phone closes the way it does when it quits
   (it saves the collection, and syncs if it syncs on close), then opens on
   :1 at desktop scale, without the phone tweaks of ankidesk_mobile;
3. shares :1 with x11vnc, which asks for a password. libvncserver also
   speaks WebSocket on the same port, so noVNC (served here over HTTP) makes
   any web browser a viewer too (ankidesk_novnc.py serves it).

The process serving noVNC (`python ankidesk_remote.py serve`, "web") also
looks after the session while it's up: it gives :1 proper display modes and
puts the screen back when a desktop's display settings leave it switched off
(ankidesk_xscreen.py), and starts x11vnc again if it exits, so viewers that
reconnect (noVNC does) find it.

The phone shows "Remote session active" (the desktop's Remote page) and the
Android app holds a Wi-Fi lock. Turning it off closes Anki on :1 and opens it
on the phone again. If Anki doesn't close (a window is asking something),
nothing is torn down and the user is told.

No Qt here: the desktop shell runs start() and stop() on a worker thread.
The processes are tracked by pid files; the Android app kills every process
of the app when the session ends, so after a restart only stale files are
left (reset_stale()).
"""

from __future__ import annotations

import ipaddress
import json
import os
import secrets
import signal
import socket
import string
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from typing import Callable

PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
HOME = os.environ.get("HOME", os.path.join(os.path.dirname(PREFIX), "home"))
TMPDIR = os.environ.get("TMPDIR", os.path.join(PREFIX, "tmp"))
# where X servers put their sockets and locks (built in; TMPDIR in the app)
X_TMP = os.path.join(PREFIX, "tmp")
CONFIG_DIR = os.path.join(HOME, ".config/kioku")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "remote.json")
PASSWD_FILE = os.path.join(CONFIG_DIR, "remote.passwd")
JWMRC = os.path.join(CONFIG_DIR, "remote-jwmrc")
XFCE_SCRIPT = os.path.join(CONFIG_DIR, "remote-xfce.sh")
# an XDG data dir only the remote XFCE reads: Anki in its menu, not twice on the phone
XFCE_DATA = os.path.join(CONFIG_DIR, "remote-share")
# exists while the remote session is up; holds what the phone shows
STATE_FILE = os.path.join(CONFIG_DIR, "remote-active")
NOVNC_DIR = os.path.join(PREFIX, "share/novnc")
LAUNCH_ANKI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "launch_anki.py")
REMOTE_SCRIPT = os.path.abspath(__file__)

# another one only for tests, next to a real session
DISPLAY = os.environ.get("ANKIDX_REMOTE_DISPLAY", ":1")
LOCAL, TAILSCALE, ALL = "local", "tailscale", "all"
LISTEN = (LOCAL, TAILSCALE, ALL)
RESOLUTIONS = ("1280x800", "1600x900", "1920x1080", "2560x1440")
SIMPLE, XFCE = "simple", "xfce"
DESKTOPS = (SIMPLE, XFCE)
# what choosing XFCE installs: Termux's xfce4 has no xfdesktop, without which
# nothing repaints the background and moved windows leave trails
XFCE_PACKAGES = ["xfce4", "xfdesktop", "fluent-gtk-theme"]
XFCE_THEME = "Fluent-Dark"
# VNC's own password check uses only the first 8 characters
PASSWORD_LENGTH = 8
TAILSCALE_NET = ipaddress.ip_network("100.64.0.0/10")
TAILSCALE_PROBE = "100.100.100.100"
ANKI_CLOSE_SECONDS = 120
# x11vnc started again at most this often (it exits at once on a bad display)
VNC_RESTARTS, VNC_RESTART_WINDOW = 5, 60.0

Progress = Callable[[str, float], None]

# started processes: kept so they are reaped, not garbage collected running
_children: list[subprocess.Popen] = []


class RemoteError(Exception):
    pass


# Settings
######################################################################


@dataclass
class Settings:
    listen: str = TAILSCALE
    resolution: str = "1920x1080"
    vnc_port: int = 5900
    web_port: int = 6080
    password: str = ""
    desktop: str = SIMPLE

    def problem(self) -> str | None:
        if self.listen not in LISTEN:
            return "Choose where to listen."
        if self.desktop not in DESKTOPS:
            return "Choose a desktop."
        if self.desktop == XFCE and not xfce_installed():
            return "XFCE isn't installed: choose it again to install it."
        if self.resolution not in RESOLUTIONS:
            return "Choose a screen size."
        for port in (self.vnc_port, self.web_port):
            if not 1024 <= port <= 65535:
                return "Ports go from 1024 to 65535."
        if self.vnc_port == self.web_port:
            return "The VNC and web ports must differ."
        if len(self.password) < 6:
            return "The password needs at least 6 characters."
        return None


def new_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(PASSWORD_LENGTH))


def load_settings() -> Settings:
    s = Settings()
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    for key, value in data.items():
        if hasattr(s, key) and isinstance(value, type(getattr(s, key))):
            setattr(s, key, value)
    if not s.password:
        s.password = new_password()
        save_settings(s)
    return s


def save_settings(s: Settings) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = SETTINGS_FILE + ".tmp"
    # the password is in it
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(asdict(s), fh)
    os.replace(tmp, SETTINGS_FILE)


# Addresses
######################################################################


def _route_address(target: str) -> str | None:
    """The phone's own address on the route to `target` (no packet is sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((target, 9))
            return s.getsockname()[0]
    except OSError:
        return None


def tailscale_address() -> str | None:
    address = _route_address(TAILSCALE_PROBE)
    if address and ipaddress.ip_address(address) in TAILSCALE_NET:
        return address
    return None


def network_address() -> str | None:
    address = _route_address("192.0.2.1")
    if address and not ipaddress.ip_address(address).is_loopback:
        return address
    return None


def bind_host(s: Settings) -> str:
    if s.listen == LOCAL:
        return "127.0.0.1"
    if s.listen == TAILSCALE:
        address = tailscale_address()
        if address is None:
            raise RemoteError(
                "Tailscale isn't connected, so there is no Tailscale address to "
                "listen on. Open the Tailscale app, or choose another network."
            )
        return address
    return "0.0.0.0"


def addresses(s: Settings, host: str) -> list[tuple[str, str]]:
    """(who it is for, address) pairs: the web page, then VNC viewers."""
    if host == "0.0.0.0":
        hosts = [h for h in (network_address(), tailscale_address()) if h] or ["127.0.0.1"]
    else:
        hosts = [host]
    found = []
    for h in hosts:
        who = "Tailscale" if ipaddress.ip_address(h) in TAILSCALE_NET else (
            "This phone" if h == "127.0.0.1" else "This network")
        found.append((f"{who}, web browser", f"http://{h}:{s.web_port}/vnc.html"))
        found.append((f"{who}, VNC viewer", f"{h}:{s.vnc_port}"))
    return found


def port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def wait_port(host: str, port: int, seconds: float) -> bool:
    target = "127.0.0.1" if host == "0.0.0.0" else host
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((target, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


# Processes
######################################################################


def _pid_file(name: str) -> str:
    return os.path.join(TMPDIR, f"remote-{name}.pid")


def _log_file(name: str) -> str:
    return os.path.join(TMPDIR, f"remote-{name}.log")


def _cmdline(pid: int) -> list[str]:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            return [a.decode(errors="replace") for a in fh.read().split(b"\0") if a]
    except OSError:
        return []


def _environ(pid: int) -> dict[str, str]:
    try:
        with open(f"/proc/{pid}/environ", "rb") as fh:
            pairs = [a.decode(errors="replace").split("=", 1) for a in fh.read().split(b"\0") if b"=" in a]
    except OSError:
        return {}
    return dict(pairs)


def spawn(name: str, argv: list[str], env: dict[str, str] | None = None, append: bool = False) -> int:
    with open(_log_file(name), "ab" if append else "wb") as log:
        proc = subprocess.Popen(argv, env=env, start_new_session=True, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT)
    _children.append(proc)
    with open(_pid_file(name), "w", encoding="utf-8") as fh:
        fh.write(f"{proc.pid} {os.path.basename(argv[0])}")
    return proc.pid


def tracked_pid(name: str) -> int | None:
    """The pid of `name` if it still runs (and is still that program)."""
    try:
        with open(_pid_file(name), encoding="utf-8") as fh:
            pid_text, exe = fh.read().split()
        pid = int(pid_text)
    except (OSError, ValueError):
        return None
    args = _cmdline(pid)
    if not args or exe not in " ".join(args):
        return None
    return pid


def stop_process(name: str, seconds: float = 5) -> None:
    pid = tracked_pid(name)
    if pid is not None:
        _signal_group(pid, signal.SIGTERM)
        if not _wait_exit(pid, seconds):
            _signal_group(pid, signal.SIGKILL)
            _wait_exit(pid, 2)
    try:
        os.remove(_pid_file(name))
    except OSError:
        pass


def _signal_group(pid: int, sig: int) -> None:
    """spawn() starts each program in a session of its own: signal everything
    it started too (XFCE's session is a tree of processes)."""
    try:
        if os.getpgid(pid) == pid:
            os.killpg(pid, sig)
            return
    except OSError:
        pass
    _signal(pid, sig)


def _signal(pid: int, sig: int) -> None:
    try:
        os.kill(pid, sig)
    except OSError:
        pass


def _alive(pid: int) -> bool:
    for child in _children[:]:
        if child.poll() is not None:  # reaps it
            _children.remove(child)
    try:
        os.waitpid(pid, os.WNOHANG)  # a child started elsewhere
    except OSError:
        pass
    if not os.path.exists(f"/proc/{pid}"):
        return False
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
            return fh.read().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return False


def _wait_exit(pid: int, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.2)
    return not _alive(pid)


# Anki
######################################################################


def anki_pids() -> list[int]:
    """Anki started by this desktop (its launcher, by path)."""
    launcher = os.path.realpath(LAUNCH_ANKI)
    found = []
    for entry in os.listdir("/proc"):
        if entry.isdigit():
            args = _cmdline(int(entry))
            if any(a.endswith("launch_anki.py") and os.path.realpath(a) == launcher for a in args):
                found.append(int(entry))
    return found


def anki_display(pid: int) -> str:
    return _environ(pid).get("DISPLAY", "")


def close_anki(seconds: float | None = None) -> None:
    """Asks Anki to quit (SIGTERM: Anki's own close, which saves) and waits."""
    if seconds is None:
        seconds = ANKI_CLOSE_SECONDS
    pids = anki_pids()
    for pid in pids:
        _signal(pid, signal.SIGTERM)
    deadline = time.monotonic() + seconds
    for pid in pids:
        if not _wait_exit(pid, max(0.0, deadline - time.monotonic())):
            raise RemoteError(
                "Anki didn't close; a window may be asking something. Answer it, "
                "close Anki, and try again."
            )


def anki_environment(remote: bool) -> dict[str, str]:
    env = dict(os.environ)
    if remote:
        env.update({"DISPLAY": DISPLAY, "ANKIDX_REMOTE": "1", "ANKIDX_SCALE": "1"})
        # tells the Android app the phone's desktop is up: not this one
        env.pop("ANKIDX_READY_FILE", None)
    else:
        env["DISPLAY"] = os.environ.get("DISPLAY", ":0")
        env.pop("ANKIDX_REMOTE", None)
    return env


def start_anki(remote: bool) -> None:
    with open(os.path.join(TMPDIR, "anki.log"), "ab") as log:
        _children.append(subprocess.Popen([sys.executable, LAUNCH_ANKI], env=anki_environment(remote),
                                          start_new_session=True, stdin=subprocess.DEVNULL,
                                          stdout=log, stderr=subprocess.STDOUT))


# The remote session
######################################################################


def is_active() -> bool:
    return os.path.exists(STATE_FILE)


def state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def reset_stale() -> None:
    """At desktop start: a session that was up before a restart is gone (the
    Android app killed its processes); forget it."""
    for name in ("web", "vnc", "jwm", "xvfb"):
        stop_process(name, seconds=1)
    try:
        os.remove(STATE_FILE)
    except OSError:
        pass


def write_jwmrc(s: Settings) -> None:
    """A plain desktop for :1: a taskbar with Anki's button and a clock."""
    anki = f"{sys.executable} {LAUNCH_ANKI}"
    with open(JWMRC, "w", encoding="utf-8") as fh:
        fh.write(f"""<?xml version="1.0"?>
<JWM>
  <Tray x="0" y="-1" height="36" autohide="off">
    <TrayButton label="Anki">exec:{anki}</TrayButton>
    <Spacer width="8"/>
    <TaskList maxwidth="320"/>
    <Clock format="%H:%M"><Button mask="123">exec:true</Button></Clock>
  </Tray>
  <Desktops width="1" height="1"><Background type="solid">#1E2638</Background></Desktops>
  <WindowStyle><Font>DejaVu Sans-11</Font></WindowStyle>
  <TrayStyle><Font>DejaVu Sans-11</Font></TrayStyle>
  <FocusModel>click</FocusModel>
</JWM>
""")


def xfce_installed() -> bool:
    return all(os.path.exists(os.path.join(PREFIX, "bin", exe)) for exe in ("startxfce4", "xfdesktop"))


def install_xfce(progress: Progress | None = None) -> list[str]:
    import ankidesk_pkg

    return ankidesk_pkg.install(XFCE_PACKAGES, progress or (lambda text, fraction: None))


def remove_xfce(progress: Progress | None = None) -> list[str]:
    import ankidesk_pkg

    s = load_settings()
    if s.desktop == XFCE:
        s.desktop = SIMPLE
        save_settings(s)
    return ankidesk_pkg.remove(XFCE_PACKAGES, progress or (lambda text, fraction: None))


def _write_new(path: str, text: str) -> None:
    """XFCE's own settings: only the first time, later changes made in XFCE win."""
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def write_xfce_files() -> None:
    """XFCE for :1: Anki in its menu, the Fluent theme, and a script that
    falls back to the plain taskbar (with Anki's button) on Log Out."""
    os.makedirs(os.path.join(XFCE_DATA, "applications"), exist_ok=True)
    with open(os.path.join(XFCE_DATA, "applications", "kioku-anki.desktop"), "w", encoding="utf-8") as fh:
        fh.write(f"""[Desktop Entry]
Type=Application
Name=Anki
Comment=Your collection, on this screen
Exec={sys.executable} {LAUNCH_ANKI}
Icon=anki
Categories=Education;
""")
    xml = os.path.join(HOME, ".config/xfce4/xfconf/xfce-perchannel-xml")
    _write_new(os.path.join(xml, "xsettings.xml"), f"""<?xml version="1.0" encoding="UTF-8"?>
<channel name="xsettings" version="1.0">
  <property name="Net" type="empty">
    <property name="ThemeName" type="string" value="{XFCE_THEME}"/>
    <property name="IconThemeName" type="string" value="Adwaita"/>
  </property>
</channel>
""")
    _write_new(os.path.join(xml, "xfwm4.xml"), f"""<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfwm4" version="1.0">
  <property name="general" type="empty">
    <property name="theme" type="string" value="{XFCE_THEME}"/>
  </property>
</channel>
""")
    bin_ = os.path.join(PREFIX, "bin")
    with open(XFCE_SCRIPT, "w", encoding="utf-8") as fh:
        fh.write(f"""# XFCE on the remote screen (ankidesk_remote.py). After Log Out the
# plain taskbar takes over, so Anki can be opened again.
{bin_}/dbus-launch --exit-with-session {bin_}/startxfce4
{bin_}/jwm -f {JWMRC}
""")


def xfce_environment() -> dict[str, str]:
    env = anki_environment(remote=True)
    env["XDG_DATA_DIRS"] = f"{XFCE_DATA}:{os.path.join(PREFIX, 'share')}"
    # a session bus of its own (dbus-launch), not the phone desktop's
    env.pop("DBUS_SESSION_BUS_ADDRESS", None)
    return env


def _xvfb_lock_stale() -> None:
    lock = os.path.join(X_TMP, f".X{DISPLAY[1:]}-lock")
    try:
        with open(lock, encoding="utf-8") as fh:
            pid = int(fh.read().strip())
    except (OSError, ValueError):
        return
    if not _alive(pid):
        for path in (lock, os.path.join(X_TMP, ".X11-unix", f"X{DISPLAY[1:]}")):
            try:
                os.remove(path)
            except OSError:
                pass


def _keeps_running(name: str, seconds: float = 2) -> bool:
    """Still running a moment after it got ready (a zombie has no cmdline)."""
    time.sleep(seconds)
    return tracked_pid(name) is not None


def _wait_display(seconds: float) -> bool:
    sock = os.path.join(X_TMP, ".X11-unix", f"X{DISPLAY[1:]}")
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if tracked_pid("xvfb") is None:
            return False
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
                c.connect(sock)
                return True
        except OSError:
            time.sleep(0.2)
    return False


def start(progress: Progress | None = None) -> dict:
    """Brings the remote session up; returns what the phone shows. Raises
    RemoteError with what went wrong, after undoing what was done."""
    report = progress or (lambda text, fraction: None)
    s = load_settings()
    if problem := s.problem():
        raise RemoteError(problem)
    host = bind_host(s)
    for port in (s.vnc_port, s.web_port):
        if not port_free(host, port):
            raise RemoteError(f"Port {port} is in use by another app; choose another.")
    for exe in ("Xvfb", "x11vnc"):
        if not os.path.exists(os.path.join(PREFIX, "bin", exe)):
            raise RemoteError(f"{exe} is missing from the runtime: update Kioku.")

    moved_anki = False
    try:
        report("Starting the remote screen…", 0.1)
        # still up if Anki on it didn't close last time: share it again
        if tracked_pid("xvfb") is None:
            _xvfb_lock_stale()
            width, height = s.resolution.split("x")
            spawn("xvfb", [os.path.join(PREFIX, "bin", "Xvfb"), DISPLAY, "-screen", "0",
                           f"{width}x{height}x24", "-nolisten", "tcp", "-dpi", "96"])
        if not _wait_display(15):
            raise RemoteError("The remote screen (Xvfb) didn't start:\n" + _tail("xvfb"))
        # before the desktop: it gives :1 the display modes XFCE expects
        if tracked_pid("web") is None:
            spawn("web", [sys.executable, REMOTE_SCRIPT, "serve", str(s.web_port), host, str(s.vnc_port)])
        if not wait_port(host, s.web_port, 15):
            raise RemoteError("The web viewer didn't start:\n" + _tail("web"))
        if tracked_pid("jwm") is None:
            write_jwmrc(s)
            if s.desktop == XFCE:
                write_xfce_files()
                spawn("jwm", [os.path.join(PREFIX, "bin", "dash"), XFCE_SCRIPT], env=xfce_environment())
            else:
                spawn("jwm", [os.path.join(PREFIX, "bin", "jwm"), "-f", JWMRC],
                      env=anki_environment(remote=True))

        if not any(anki_display(pid) == DISPLAY for pid in anki_pids()):
            report("Moving Anki to the remote screen (Anki saves first)…", 0.3)
            if anki_pids():
                close_anki()
            moved_anki = True
            start_anki(remote=True)

        report("Sharing the screen…", 0.7)
        with open(os.devnull, "wb") as null:
            subprocess.run([os.path.join(PREFIX, "bin", "x11vnc"), "-storepasswd", s.password,
                            PASSWD_FILE], stdout=null, stderr=null, check=True)
        os.chmod(PASSWD_FILE, 0o600)
        vnc = vnc_argv(s, host)
        spawn("vnc", vnc)
        if not wait_port(host, s.vnc_port, 15) or not _keeps_running("vnc"):
            raise RemoteError("Screen sharing (x11vnc) didn't start:\n" + _tail("vnc"))
    except Exception as err:
        _teardown(anki_back=moved_anki)
        if isinstance(err, RemoteError):
            raise
        raise RemoteError(str(err)) from err

    info = {"addresses": addresses(s, host), "password": s.password, "resolution": s.resolution,
            "listen": s.listen, "started": time.time(), "vnc": vnc}
    with open(STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump(info, fh)
    report("Remote session active", 1.0)
    return info


def vnc_argv(s: Settings, host: str) -> list[str]:
    listen = ["-localhost"] if host == "127.0.0.1" else ["-listen", host]
    return [os.path.join(PREFIX, "bin", "x11vnc"), "-display", DISPLAY,
            "-rfbport", str(s.vnc_port), *listen, "-rfbauth", PASSWD_FILE,
            # Android has no SysV shared memory for apps: x11vnc would exit
            # right after binding its port
            "-forever", "-shared", "-noipv6", "-noshm", "-xkb", "-ncache", "0",
            # follow screen size changes (display settings), and tell viewers
            "-xrandr", "resize"]


def stop(progress: Progress | None = None) -> None:
    """Moves Anki back to the phone and ends the remote session. If Anki on
    the remote screen doesn't close, the session stays up (so whatever it
    asks can be answered remotely) and RemoteError says so."""
    report = progress or (lambda text, fraction: None)
    report("Closing Anki on the remote screen (Anki saves first)…", 0.2)
    remote_anki = [pid for pid in anki_pids() if anki_display(pid) == DISPLAY]
    if remote_anki:
        close_anki()
    report("Ending the remote session…", 0.7)
    _teardown(anki_back=True)
    report("Anki is back on the phone", 1.0)


def end(progress: Progress | None = None) -> None:
    """Power off: closes Anki on the remote screen (it saves) and ends the
    session, without opening Anki on the phone."""
    if progress:
        progress("Closing Anki on the remote screen…", 0.5)
    close_anki()
    _teardown(anki_back=False)


def _teardown(anki_back: bool) -> None:
    for name in ("web", "vnc"):
        stop_process(name)
    if any(anki_display(pid) == DISPLAY for pid in anki_pids()):
        # start() failed after moving Anki; if Anki doesn't close, this
        # raises and leaves the remote screen up, for the next try to share
        close_anki()
    for name in ("jwm", "xvfb"):
        stop_process(name)
    try:
        os.remove(STATE_FILE)
    except OSError:
        pass
    if anki_back and not anki_pids():
        start_anki(remote=False)


# The session's helper (the "web" process)
######################################################################


def _log(text: str) -> None:
    print(time.strftime("%H:%M:%S"), text, flush=True)


def keep_screen(ready) -> None:
    import ankidesk_xscreen

    try:
        ankidesk_xscreen.keep(DISPLAY, log=_log, ready=ready)
    except Exception as err:  # no RandR, a stand-in X server: only less help
        _log(f"not watching the screen: {err!r}")
    finally:
        ready()


def keep_vnc(stop=lambda: False, seconds: float = 2.0) -> None:
    """Starts x11vnc again when it's gone while the session is up (it is
    up once start() wrote the state, with x11vnc's command line)."""
    restarts: list[float] = []
    while not stop():
        time.sleep(seconds)
        _alive(0)  # reaps an x11vnc started here that exited
        argv = state().get("vnc")
        if not argv or tracked_pid("vnc") is not None:
            continue
        now = time.monotonic()
        restarts = [t for t in restarts if now - t < VNC_RESTART_WINDOW]
        if len(restarts) >= VNC_RESTARTS:
            continue
        restarts.append(now)
        _log("x11vnc is gone: starting it again")
        with open(_log_file("vnc"), "ab") as log:
            log.write(f"\n--- {time.strftime('%H:%M:%S')} started again by the session helper\n".encode())
        spawn("vnc", argv, append=True)


def serve(web_port: int, host: str, vnc_port: int) -> None:
    import threading

    import ankidesk_novnc

    ready = threading.Event()
    threading.Thread(target=keep_screen, args=(ready.set,), daemon=True).start()
    # the modes are there before the port opens, which start() waits for
    ready.wait(10)
    threading.Thread(target=keep_vnc, daemon=True).start()
    ankidesk_novnc.serve(web_port, host, NOVNC_DIR, vnc_port)


def _tail(name: str, lines: int = 8) -> str:
    try:
        with open(_log_file(name), encoding="utf-8", errors="replace") as fh:
            return "".join(fh.readlines()[-lines:]).strip()
    except OSError:
        return ""


if __name__ == "__main__":
    if sys.argv[1:2] == ["serve"]:
        serve(int(sys.argv[2]), sys.argv[3], int(sys.argv[4]))
