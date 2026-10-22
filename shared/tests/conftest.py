"""Host tests for Kioku's Python code, run with desktop Anki's Python packages
and an rsbridge built from deps/anki with Kioku's patches (shared/tests/run.sh).

kioku_platform is replaced by a stub whose folders are temporary.
"""

from __future__ import annotations

import os
import sys
import types

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
# appended: shared/python also holds a PyQt6 stand-in, desktop PyQt6 comes first
sys.path.append(os.path.join(HERE, "..", "python"))


class FakePlatform(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("kioku_platform")
        self.root = ""
        self.service_calls: list[tuple[bool, str]] = []
        self.watching: tuple | None = None

    def config_dir(self) -> str:
        return os.path.join(self.root, "config")

    def documents_dir(self) -> str:
        return os.path.join(self.root, "documents")

    def cache_dir(self) -> str:
        return os.path.join(self.root, "cache")

    def sync_server_running(self, running: bool, text: str) -> None:
        self.service_calls.append((running, text))

    files_access = True
    versions: dict[str, str] = {}

    def all_files_access(self) -> bool:
        return self.files_access

    def app_versions(self, packages: list[str]) -> dict[str, str]:
        return {p: v for p, v in self.versions.items() if p in packages}

    def watch_background(self, on_background, on_foreground) -> None:  # type: ignore[no-untyped-def]
        self.watching = (on_background, on_foreground) if on_background else None


_platform = FakePlatform()
sys.modules["kioku_platform"] = _platform


@pytest.fixture
def platform(tmp_path):
    _platform.root = str(tmp_path)
    _platform.service_calls.clear()
    _platform.files_access = True
    _platform.versions = {}
    _platform.watching = None
    yield _platform
    from kioku import syncserver

    syncserver.stop()
