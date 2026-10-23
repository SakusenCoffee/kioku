"""Files in the browser: picked files are copied into the wasm file system
(shell/kioku-web.js pick()), exports are handed to the browser as
downloads."""

from __future__ import annotations

import os

from PyQt6.QtCore import QEventLoop, QTimer

from . import web

_state: dict = {}


def _on_picked(event: dict) -> None:
    _state["paths"] = event.get("paths", [])
    loop = _state.get("loop")
    if loop is not None:
        loop.quit()


web.listen("picked", _on_picked)


def pick_files(name_filter: str = "*", multi: bool = False) -> list[str]:
    exts = {
        part.lstrip("*.").lower()
        for part in name_filter.replace("(", " ").replace(")", " ").replace(";", " ").split()
        if part.startswith("*.") and part != "*.*"
    }
    accept = ",".join(f".{e}" for e in sorted(exts))
    loop = QEventLoop()
    _state.update(loop=loop, paths=[])
    web.js("pick", multi, accept)
    loop.exec()
    _state["loop"] = None
    return list(_state.get("paths", []))


def save_path(file_name: str) -> str:
    """Exports are written to Exports/ in the wasm file system, then
    downloaded once the file stops growing."""
    from . import documents_dir

    folder = os.path.join(documents_dir(), "Exports")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, file_name)
    if os.path.exists(path):
        os.remove(path)
    _watch_export(path, file_name)
    return path


def _watch_export(path: str, name: str, tries: int = 1200) -> None:
    last = {"size": -1}

    def check() -> None:
        size = os.path.getsize(path) if os.path.exists(path) else -1
        if size > 0 and size == last["size"]:
            web.js("download", path, name)
            return
        last["size"] = size
        if check.tries > 0:  # type: ignore[attr-defined]
            check.tries -= 1  # type: ignore[attr-defined]
            QTimer.singleShot(1000, check)

    check.tries = tries  # type: ignore[attr-defined]
    QTimer.singleShot(1000, check)
