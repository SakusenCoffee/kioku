"""Anki's update prompts: Yes opens Kioku's releases instead of desktop Anki's
download page or installer (kioku.patches)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import aqt
import aqt.update
import aqt.utils

from kioku import patches


def test_update_prompts_open_kioku_releases(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    patches._patch_update_check()  # apply() patches other things only once per process
    opened: list[str] = []
    monkeypatch.setattr(aqt.utils, "openLink", opened.append)

    # startup check: prompt_to_update() opens this on Yes
    assert aqt.appWebsiteDownloadSection == patches.KIOKU_RELEASES
    # Tools › Check for Updates: prompt_and_install_github_update() calls this on Yes
    aqt.update._download_github_update_and_install(object())
    assert opened == [patches.KIOKU_RELEASES]
