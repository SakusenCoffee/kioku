"""What changed between two Anki releases that Kioku depends on.

Kioku changes Anki's Python code at runtime (replacing functions and methods,
or their __code__) instead of patching its source, and patches only a few
lines of its Rust source (shared/patches/). A replaced function keeps working
across releases unless upstream changes it, so this report lists:

- every Anki function or method that Kioku's Python code replaces or wraps,
  found by reading the assignments in shared/python, the platform modules and
  the Termux launcher, and whether it changed between the two releases (with
  the diff);
- the files whose changes need a look although nothing replaces them (the web
  view that Kioku's stand-in for Qt WebEngine serves, the web server);
- whether shared/patches/anki-*.patch apply to the new release.

Usage: python3 -I anki_drift.py <anki git dir> <old tag> <new tag> > report.md
The git dir needs both tags; a partial clone is enough:
    git clone --filter=blob:none --no-checkout https://github.com/ankitects/anki
    git -C anki fetch origin tag <old> tag <new>
"""

from __future__ import annotations

import ast
import difflib
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES = [
    REPO_ROOT / "shared/python",
    REPO_ROOT / "ios/python",
    REPO_ROOT / "android/python",
    REPO_ROOT / "termux/rootfs-overlay/share/ankidx",
]
# changes here can break Kioku without touching anything it replaces
WATCHED = [
    "qt/aqt/webview.py",
    "qt/aqt/mediasrv.py",
    "qt/aqt/qt",
    "qt/aqt/__init__.py",
    "qt/aqt/sound.py",
    "pylib/rsbridge",
    "rslib/src/sync/http_server",
    "rust-toolchain.toml",
    "qt/pyproject.toml",
    "pylib/pyproject.toml",
]
# replaced by name in a loop (setattr), which the scan below can't follow
EXTRA = [
    ("aqt.profiles", "ProfileManager.set_sync_key"),
    ("aqt.profiles", "ProfileManager.set_sync_username"),
    ("aqt.profiles", "ProfileManager.set_host_number"),
    ("aqt.profiles", "ProfileManager.set_current_sync_url"),
]


def git(repo: str, *args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", repo, *args], text=True, stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        return None


def module_file(repo: str, tag: str, module: str) -> str | None:
    """Path of an aqt/anki module in Anki's repository, if it exists."""
    root = "qt" if module.split(".")[0] == "aqt" else "pylib"
    base = f"{root}/{module.replace('.', '/')}"
    for path in (f"{base}.py", f"{base}/__init__.py"):
        if git(repo, "cat-file", "-e", f"{tag}:{path}") is not None:
            return path
    return None


def dotted(node: ast.expr) -> list[str] | None:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return parts[::-1]


def hooked_names(path: Path) -> set[str]:
    """Dotted names under aqt/anki that a file assigns to, e.g.
    aqt.main.AnkiQt.__init__ (also for `from aqt.main import AnkiQt` and
    then `AnkiQt.x = ...`)."""
    tree = ast.parse(path.read_text(), str(path))
    imported: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in ("aqt", "anki"):
                for alias in node.names:
                    imported[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    names = set()
    for node in ast.walk(tree):
        targets = node.targets if isinstance(node, ast.Assign) else []
        for target in targets:
            parts = dotted(target) if isinstance(target, ast.Attribute) else None
            if not parts:
                continue
            if parts[0] in imported:
                parts = imported[parts[0]].split(".") + parts[1:]
            if parts[0] not in ("aqt", "anki"):
                continue
            if parts[-1] == "__code__":
                parts = parts[:-1]
            names.add(".".join(parts))
    return names


def split_module(repo: str, tag: str, name: str) -> tuple[str, str, str] | None:
    """aqt.main.AnkiQt.__init__ -> (aqt.main, qt/aqt/main.py, AnkiQt.__init__)"""
    parts = name.split(".")
    for i in range(len(parts) - 1, 0, -1):
        module = ".".join(parts[:i])
        path = module_file(repo, tag, module)
        if path:
            return module, path, ".".join(parts[i:])
    return None


def source_of(repo: str, tag: str, path: str, qualname: str) -> str | None:
    text = git(repo, "show", f"{tag}:{path}")
    if text is None:
        return None
    node: ast.AST = ast.parse(text)
    for part in qualname.split("."):
        found = None
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if child.name == part:
                    found = child
            elif isinstance(child, (ast.Assign, ast.AnnAssign)):
                targets = child.targets if isinstance(child, ast.Assign) else [child.target]
                if any(getattr(t, "id", None) == part for t in targets):
                    found = child
        if found is None:
            return None
        node = found
    return ast.get_source_segment(text, node)


def main() -> int:
    repo, old, new = sys.argv[1:4]
    users: dict[str, set[str]] = {}
    for root in SOURCES:
        for path in sorted(root.rglob("*.py")):
            if "tests" in path.parts:
                continue
            for name in hooked_names(path):
                users.setdefault(name, set()).add(str(path.relative_to(REPO_ROOT)))
    for module, qualname in EXTRA:
        users.setdefault(f"{module}.{qualname}", set()).add("shared/python/kioku/patches.py")

    changed, missing, same, ours = [], [], [], []
    for name in sorted(users):
        where = ", ".join(sorted(users[name]))
        split = split_module(repo, new, name) or split_module(repo, old, name)
        if split is None:
            missing.append(f"- `{name}` ({where}): module gone")
            continue
        _, path, qualname = split
        before = source_of(repo, old, path, qualname)
        after = source_of(repo, new, path, qualname)
        if before is None and after is None:
            ours.append(name)  # an attribute Kioku adds
        elif after is None:
            missing.append(f"- `{name}` ({where}): gone in {new}")
        elif before == after:
            same.append(name)
        else:
            diff = "".join(
                difflib.unified_diff(
                    (before or "").splitlines(True),
                    after.splitlines(True),
                    f"{old}:{path}",
                    f"{new}:{path}",
                )
            )
            changed.append(f"#### `{name}` ({where})\n```diff\n{diff}```\n")

    out = [f"## Anki {old} → {new}: what Kioku depends on\n"]
    out.append("### Rust patches\n")
    for patch in sorted((REPO_ROOT / "shared/patches").glob("anki-*.patch")):
        ok = check_patch(repo, new, patch)
        out.append(f"- {'applies' if ok else '**does not apply**'}: `{patch.name}`")
    out.append("")
    out.append(f"### Replaced functions: {len(changed)} changed, {len(missing)} gone, {len(same)} unchanged\n")
    out += missing
    out += changed
    if same:
        out.append("<details><summary>Unchanged</summary>\n")
        out += [f"- `{name}`" for name in same]
        out.append("\n</details>\n")
    stat = git(repo, "diff", "--stat=100", old, new, "--", *WATCHED) or ""
    out.append("### Files to read although nothing replaces them\n")
    out.append(f"```\n{stat.rstrip() or '(no changes)'}\n```")
    print("\n".join(out))
    return 1 if missing or changed else 0


def check_patch(repo: str, tag: str, patch: Path) -> bool:
    """Applies the patch to a scratch worktree of the tag."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp) / "tree"
        if git(repo, "worktree", "add", "-q", "--detach", "--no-checkout", str(tree), tag) is None:
            return False
        try:
            files = []
            for line in patch.read_text().splitlines():
                if line.startswith("--- a/"):
                    files.append(line[6:])
            if files:
                git(str(tree), "checkout", tag, "--", *files)
            return git(str(tree), "apply", "--check", str(patch)) is not None
        finally:
            git(repo, "worktree", "remove", "--force", str(tree))


if __name__ == "__main__":
    sys.exit(main())
