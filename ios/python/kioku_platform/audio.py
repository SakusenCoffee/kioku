"""Card audio through AVFoundation, replacing Anki's mpv/mplayer players
(iOS cannot start processes)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable
from urllib.parse import quote

from rubicon.objc import CGPoint, CGRect, CGSize, ObjCClass, at
from rubicon.objc.runtime import load_library

from .webview import AT_DOCUMENT_START, WebView, prop

from anki.sound import AVTag, SoundOrVideoTag
from aqt import gui_hooks
from aqt.qt import QTimer
from aqt.sound import OnDoneCallback, SoundOrVideoPlayer

load_library("AVFoundation")

logger = logging.getLogger("kioku.audio")

AVAudioPlayer = ObjCClass("AVAudioPlayer")
AVAudioSession = ObjCClass("AVAudioSession")
NSURL = ObjCClass("NSURL")

# an <audio> element that reports back once it has ended or failed
_WEB_PAGE = """<!doctype html><audio id="a"></audio><script>
var a = document.getElementById("a"), token = %d;
function done() {
  window.__kiokuNative.call(JSON.stringify({obj: "audio", method: "done", args: [token]}));
}
a.onended = done;
a.onerror = done;
a.src = %s;
a.play().catch(done);
</script>"""


def _activate_session() -> None:
    try:
        session = prop(AVAudioSession, "sharedInstance")
        # play even with the ring/silent switch on, like other study apps
        session.setCategory_error_(at("AVAudioSessionCategoryPlayback"), None)
        session.setActive_error_(True, None)
    except Exception:
        logger.exception("audio session")


class _WebAudio(WebView):
    """A hidden web view for files AVAudioPlayer cannot read. It has no Ogg
    support: it opens Ogg Opus but cannot play it, and does not open Ogg
    Vorbis; WebKit plays both (and WebM)."""

    def __init__(self, on_done: Callable[[int], None]) -> None:
        super().__init__()
        self._on_done = on_done
        self.set_user_scripts([(WebView.BRIDGE, AT_DOCUMENT_START, True)])

    def play(self, url: str, token: int) -> None:
        import aqt

        # WebKit loads no media for a web view outside a window
        if prop(self.webview, "window") is None:
            from . import key_window

            self.webview.setAutoresizingMask_(0)
            self.webview.setFrame_(CGRect(CGPoint(0, 0), CGSize(1, 1)))
            self.webview.setAlpha_(0.01)
            self.webview.setUserInteractionEnabled_(False)
            key_window().addSubview_(self.webview)
        self.load_html(_WEB_PAGE % (token, json.dumps(url)), aqt.mw.serverURL())

    def stop(self) -> None:
        self.load_html("", None)

    def on_channel_call(self, obj: str, method: str, args: list) -> Any:
        if method == "done":
            self._on_done(int(args[0]))
        return None


class AVFoundationPlayer(SoundOrVideoPlayer):
    default_rank = 1

    def __init__(self, taskman: Any, media_folder: str) -> None:
        self._media_folder = media_folder
        self._player: Any = None
        self._web: _WebAudio | None = None
        # the web page playing for the current tag, 0 if none
        self._web_token = 0
        self._on_done: OnDoneCallback | None = None
        self._timer = QTimer()
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._poll)
        _activate_session()

    def rank_for_tag(self, tag: AVTag) -> int | None:
        if isinstance(tag, SoundOrVideoTag):
            return self.default_rank
        return None

    def play(self, tag: AVTag, on_done: OnDoneCallback) -> None:
        assert isinstance(tag, SoundOrVideoTag)
        self._stop_playing()
        self._on_done = on_done
        path = os.path.join(self._media_folder, tag.filename)
        url = NSURL.fileURLWithPath_(at(path))
        player = AVAudioPlayer.alloc().initWithContentsOfURL_error_(url, None)
        if player is not None and player.prepareToPlay():
            self._player = player
            player.play()
            self._timer.start()
        elif os.path.exists(path):
            self._play_web(tag.filename)
        else:
            logger.warning("cannot play %s", tag.filename)
            self._finish()
            return
        gui_hooks.av_player_did_begin_playing(self, tag)

    def _play_web(self, filename: str) -> None:
        if self._web is None:
            self._web = _WebAudio(self._web_done)
        self._web_token += 1
        self._web.play(quote(filename), self._web_token)

    def _web_done(self, token: int) -> None:
        if token == self._web_token:
            self._web_token = 0
            self._finish()

    def _poll(self) -> None:
        if self._player is not None and not prop(self._player, "isPlaying"):
            if self._paused:
                return
            self._timer.stop()
            self._player = None
            self._finish()

    _paused = False

    def _finish(self) -> None:
        on_done, self._on_done = self._on_done, None
        if on_done is not None:
            on_done()

    def _stop_playing(self) -> None:
        self._timer.stop()
        if self._player is not None:
            self._player.stop()
        self._player = None
        if self._web_token:
            self._web_token = 0
            assert self._web is not None
            self._web.stop()
        self._paused = False

    def stop(self) -> None:
        # Anki's queue (aqt.sound.AVPlayer) only plays the next file once the
        # current player reports it is done, also after being stopped; the
        # desktop players (mpv, mplayer) report that asynchronously too.
        self._stop_playing()
        on_done, self._on_done = self._on_done, None
        if on_done is not None:
            QTimer.singleShot(0, on_done)

    def toggle_pause(self) -> None:
        if self._web_token:
            assert self._web is not None
            self._web.evaluate("var a = document.getElementById('a');"
                               " a.paused ? a.play() : a.pause()", None)
            return
        if self._player is None:
            return
        if self._paused:
            self._player.play()
        else:
            self._player.pause()
        self._paused = not self._paused

    def seek_relative(self, secs: int) -> None:
        if self._web_token:
            assert self._web is not None
            self._web.evaluate("var a = document.getElementById('a');"
                               f" a.currentTime = Math.max(0, a.currentTime + {secs})", None)
            return
        if self._player is not None:
            t = max(0.0, float(prop(self._player, "currentTime")) + secs)
            self._player.setCurrentTime_(t)
