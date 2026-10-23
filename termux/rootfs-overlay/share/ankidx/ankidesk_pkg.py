"""Install and remove optional desktop apps from Termux apt repositories.

The bundled runtime has no apt/dpkg. This is a small replacement that
understands enough of the Debian formats for Termux packages:

* reads the repositories' Packages indexes and resolves dependencies,
  treating the bundled runtime (var/lib/ankidesk/base-packages.tsv) as installed,
* downloads .deb files and checks their SHA256,
* unpacks them into the prefix, rewriting the Termux prefix path when the app
  uses a different package name of the same length,
* records the files of every package so it can be removed again, together with
  dependencies nothing else needs.

Maintainer scripts are not run; packages offered in the catalog do not need them.

CLI: python ankidesk_pkg.py update|install NAME...|remove NAME...|restore|list|search WORD
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tarfile
import time
import urllib.request
from typing import Callable

PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
STATE_DIR = os.path.join(PREFIX, "var/lib/ankidesk")
CACHE_DIR = os.path.join(PREFIX, "var/cache/ankidesk")
INSTALLED = os.path.join(STATE_DIR, "installed.json")
BASE = os.path.join(STATE_DIR, "base-packages.tsv")

# Packages in the repositories are built for this rootfs (Termux's files/,
# which holds usr/). Split so tools/build_rootfs.py, which rewrites the Termux
# path in every bundled file, leaves it alone. A repo.json in STATE_DIR can
# point at a repository built for this app's own package name instead
# ("source_root": its app data directory).
SOURCE_ROOT = "/data/data/" + "com" + ".termux" + "/files"
TARGET_ROOT = os.path.dirname(PREFIX)  # /data/data/<package>/<rootfs dir>, same length

REPOS = {
    "main": ("https://packages-cf.termux.dev/apt/termux-main/", "dists/stable/main/binary-aarch64/Packages"),
    "x11": ("https://packages-cf.termux.dev/apt/termux-x11/", "dists/x11/main/binary-aarch64/Packages"),
}

try:
    with open(os.path.join(STATE_DIR, "repo.json"), encoding="utf-8") as _fh:
        _conf = json.load(_fh)
    REPOS = {k: tuple(v) for k, v in _conf["repos"].items()}
    if "source_root" in _conf:
        SOURCE_ROOT = _conf["source_root"] + "/files"
except FileNotFoundError:
    pass

Progress = Callable[[str, float], None]

# Full-colour file and folder icons for the file-based apps (no icon theme is
# bundled); see ankidesk_theme.ICON_THEME.
ICON_THEME_PACKAGE = "adwaita-icon-theme-legacy"


def _no_progress(message: str, fraction: float) -> None:
    pass


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    bundle = os.path.join(PREFIX, "etc/tls/cert.pem")
    if os.path.exists(bundle):
        ctx.load_verify_locations(bundle)
    return ctx


def _fetch(url: str, progress: Progress = _no_progress, label: str = "") -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Debian APT-HTTP/1.3 (kioku)"})
    with urllib.request.urlopen(req, context=_ssl_context(), timeout=60) as r:
        total = int(r.headers.get("Content-Length") or 0)
        buf = io.BytesIO()
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            buf.write(chunk)
            if total:
                progress(label, buf.tell() / total)
        return buf.getvalue()


# --- indexes -----------------------------------------------------------------


def _parse_index(text: str, repo: str) -> dict[str, dict[str, str]]:
    pkgs: dict[str, dict[str, str]] = {}
    for block in text.split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            if line and not line[0].isspace() and ":" in line:
                k, v = line.split(":", 1)
                fields[k] = v.strip()
        if "Package" in fields:
            fields["_repo"] = repo
            pkgs[fields["Package"]] = fields
    return pkgs


def update(progress: Progress = _no_progress) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    for repo, (base, path) in REPOS.items():
        data = _fetch(base + path, progress, f"Updating {repo} package list")
        with open(os.path.join(CACHE_DIR, repo + ".Packages"), "wb") as fh:
            fh.write(data)


def index(progress: Progress = _no_progress, max_age: float | None = None) -> dict[str, dict[str, str]]:
    """All packages in the repositories. The lists are downloaded when missing
    or, with `max_age` (seconds), when older than that: packages are replaced
    on the server, so old lists point at files that are gone."""
    paths = [os.path.join(CACHE_DIR, r + ".Packages") for r in REPOS]
    if not all(os.path.exists(p) for p in paths) or (
            max_age is not None and time.time() - min(os.path.getmtime(p) for p in paths) > max_age):
        update(progress)
    pkgs: dict[str, dict[str, str]] = {}
    for repo in REPOS:
        with open(os.path.join(CACHE_DIR, repo + ".Packages"), encoding="utf-8") as fh:
            for name, fields in _parse_index(fh.read(), repo).items():
                pkgs.setdefault(name, fields)
    return pkgs


def _deps(fields: dict[str, str]) -> list[str]:
    out = []
    for key in ("Pre-Depends", "Depends"):
        for dep in fields.get(key, "").split(","):
            dep = dep.strip()
            if dep:
                out.append(re.sub(r"\(.*?\)", "", dep.split("|")[0]).strip())
    return out


# --- state -------------------------------------------------------------------


def base_packages() -> set[str]:
    try:
        with open(BASE, encoding="utf-8") as fh:
            return {line.split("\t")[0] for line in fh if line.strip()}
    except FileNotFoundError:
        return set()


def installed() -> dict[str, dict]:
    try:
        with open(INSTALLED, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}


def _save(state: dict[str, dict]) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = INSTALLED + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1, sort_keys=True)
    os.replace(tmp, INSTALLED)


def is_installed(name: str) -> bool:
    return name in installed()


# --- resolution ----------------------------------------------------------------


def plan(names: list[str], pkgs: dict[str, dict[str, str]]) -> list[str]:
    """Packages that must be downloaded to install `names`, dependencies first."""
    have = base_packages() | set(installed())
    provides: dict[str, str] = {}
    for n, f in pkgs.items():
        for p in f.get("Provides", "").split(","):
            p = re.sub(r"\(.*?\)", "", p).strip()
            if p:
                provides.setdefault(p, n)

    order: list[str] = []
    seen: set[str] = set()

    def visit(n: str) -> None:
        name = n if n in pkgs else provides.get(n, n)
        if name in seen or name in have or n in have:
            return
        if name not in pkgs:
            raise RuntimeError(f"Package '{n}' is not available")
        seen.add(name)
        for d in _deps(pkgs[name]):
            visit(d)
        order.append(name)

    for n in names:
        visit(n)
    return order


def download_size(names: list[str], pkgs: dict[str, dict[str, str]]) -> tuple[int, int]:
    """(download bytes, installed bytes) for installing `names`."""
    todo = plan(names, pkgs)
    return (sum(int(pkgs[n].get("Size", 0)) for n in todo),
            sum(int(pkgs[n].get("Installed-Size", 0)) * 1024 for n in todo))


# --- deb handling --------------------------------------------------------------


def _ar_members(data: bytes) -> dict[str, bytes]:
    if data[:8] != b"!<arch>\n":
        raise RuntimeError("not a .deb file")
    out, pos = {}, 8
    while pos + 60 <= len(data):
        header = data[pos:pos + 60]
        name = header[:16].decode().strip().rstrip("/")
        size = int(header[48:58].decode().strip())
        out[name] = data[pos + 60:pos + 60 + size]
        pos += 60 + size + (size % 2)
    return out


def _patch(data: bytes) -> bytes:
    old, new = SOURCE_ROOT.encode(), TARGET_ROOT.encode()
    user = b"/data/user/0/"
    old_user = old.replace(b"/data/data/", user)
    if old == new or (old not in data and old_user not in data):
        return data
    if len(old) != len(new):
        raise RuntimeError(f"cannot relocate {SOURCE_ROOT} to {TARGET_ROOT}: lengths differ")
    return data.replace(old, new).replace(old_user, new.replace(b"/data/data/", user))


def _unpack(deb: bytes) -> list[str]:
    members = _ar_members(deb)
    data = next(v for k, v in members.items() if k.startswith("data.tar"))
    root = SOURCE_ROOT.lstrip("/") + "/usr/"
    files: list[str] = []
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for m in tar.getmembers():
            name = m.name.lstrip("./")
            if not name.startswith(root):
                continue
            rel = name[len(root):]
            if not rel:
                continue
            dest = os.path.join(PREFIX, rel)
            if m.isdir():
                os.makedirs(dest, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if os.path.lexists(dest):
                os.unlink(dest)
            if m.issym():
                os.symlink(m.linkname.replace(SOURCE_ROOT, TARGET_ROOT), dest)
            elif m.isfile():
                with open(dest, "wb") as fh:
                    fh.write(_patch(tar.extractfile(m).read()))
                os.chmod(dest, 0o700 if m.mode & 0o111 else 0o600)
            else:
                continue
            files.append(rel)
    return files


# --- operations ------------------------------------------------------------------


def search(query: str, pkgs: dict[str, dict[str, str]], limit: int = 50) -> tuple[list[str], int]:
    """Names matching `query` (name first, then description), best first, and the number of matches."""
    q = query.strip().lower()
    scored = []
    for name, fields in pkgs.items():
        if q in name:
            score = 0 if name == q else 1 if name.startswith(q) else 2
        elif q in fields.get("Description", "").lower():
            score = 3
        else:
            continue
        scored.append((score, len(name), name))
    scored.sort()
    return [n for *_, n in scored[:limit]], len(scored)


def install(names: list[str], progress: Progress = _no_progress, extras: list[str] = ()) -> list[str]:
    """Install `names` and, as automatic dependencies (removed with them),
    `extras` such as an icon theme an app looks bare without."""
    pkgs = index(progress, max_age=24 * 3600)
    extras = [e for e in extras if e in pkgs]
    todo = plan(list(names) + extras, pkgs)
    state = installed()
    for i, name in enumerate(todo):
        fields = pkgs[name]

        def step(label: str, fraction: float, i: int = i) -> None:
            progress(label, (i + fraction) / max(len(todo), 1))

        deb = _fetch(REPOS[fields["_repo"]][0] + fields["Filename"], step, f"Downloading {name}")
        if hashlib.sha256(deb).hexdigest() != fields["SHA256"]:
            raise RuntimeError(f"Checksum mismatch for {name}")
        step(f"Installing {name}", 0.99)
        files = _unpack(deb)
        state[name] = {"version": fields["Version"], "files": files, "auto": name not in names}
        _save(state)
    for name in names:
        if name in state:
            state[name]["auto"] = False
    _save(state)
    _run_triggers()
    progress("Done", 1.0)
    return todo


def _needed(state: dict[str, dict], pkgs: dict[str, dict[str, str]]) -> set[str]:
    keep: set[str] = set()
    stack = [n for n, s in state.items() if not s.get("auto")]
    while stack:
        n = stack.pop()
        if n in keep:
            continue
        keep.add(n)
        if n in pkgs:
            stack.extend(d for d in _deps(pkgs[n]) if d in state)
    return keep


def _inside_prefix(path: str) -> bool:
    real, root = os.path.realpath(path), os.path.realpath(PREFIX)
    return real == root or real.startswith(root + os.sep)


def remove(names: list[str], progress: Progress = _no_progress) -> list[str]:
    from ankidesk_menu import storage_off

    # Phone storage is turned off first, so nothing removed here can be on it.
    storage_off()
    pkgs = index(progress)
    state = installed()
    for n in names:
        if n in state:
            state[n]["auto"] = True
    keep = _needed(state, pkgs)
    gone = [n for n in state if n not in keep]
    still_owned = {f for n in keep for f in state[n]["files"]}
    for i, n in enumerate(gone):
        progress(f"Removing {n}", i / max(len(gone), 1))
        for rel in state[n]["files"]:
            if rel in still_owned:
                continue
            path = os.path.join(PREFIX, rel)
            # Never a file reached through a link out of the prefix.
            if os.path.lexists(path) and _inside_prefix(os.path.dirname(path)):
                os.unlink(path)
        del state[n]
    _save(state)
    _run_triggers()
    progress("Done", 1.0)
    return gone


RESTORE = os.path.join(os.path.dirname(PREFIX), "apps-to-restore.json")


def restore(progress: Progress = _no_progress) -> list[str]:
    """Reinstall the apps a user had before the runtime was replaced by an app update."""
    try:
        with open(RESTORE, encoding="utf-8") as fh:
            wanted = [n for n, s in json.load(fh).items() if not s.get("auto")]
    except FileNotFoundError:
        return []
    done = install(wanted, progress) if wanted else []
    os.unlink(RESTORE)
    return done


def _run_triggers() -> None:
    """The few post-install steps desktop apps rely on (normally maintainer
    scripts): GTK's image loader cache, without which GTK apps draw no icons,
    the icon themes' caches, and telling the desktop about new apps."""
    from ankidesk_menu import notify_shell

    def run(*argv: str) -> None:
        if os.path.exists(argv[0]):
            subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=False)

    run(os.path.join(PREFIX, "bin/gdk-pixbuf-query-loaders"), "--update-cache")
    icons = os.path.join(PREFIX, "share/icons")
    for theme in sorted(os.listdir(icons)) if os.path.isdir(icons) else []:
        if os.path.exists(os.path.join(icons, theme, "index.theme")):
            run(os.path.join(PREFIX, "bin/gtk-update-icon-cache"), "-q", "-f", "-t", os.path.join(icons, theme))
    notify_shell()


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]

    def show(label: str, fraction: float) -> None:
        print(f"\r{label}: {fraction * 100:5.1f}%", end="", file=sys.stderr)

    if cmd == "update":
        update(show)
    elif cmd == "install":
        print("\ninstalled:", install(args, show))
    elif cmd == "remove":
        print("\nremoved:", remove(args, show))
    elif cmd == "restore":
        print("\nrestored:", restore(show))
    elif cmd == "search":
        pkgs = index(show)
        names, total = search(" ".join(args), pkgs)
        for n in names:
            print(f"{n}\t{pkgs[n].get('Version', '')}\t{pkgs[n].get('Description', '')}")
        print(f"({total} matches)", file=sys.stderr)
    elif cmd == "list":
        for n, s in sorted(installed().items()):
            print(f"{n}\t{s['version']}{'' if s.get('auto') else '\t(manual)'}")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main(sys.argv[1:]))
