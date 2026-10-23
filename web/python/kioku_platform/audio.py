"""Card audio through an <audio> element on the app page, and {{tts}}
through the Web Speech API (shell/kioku-web.js play(), speak()), replacing
Anki's mpv/mplayer and `say` players (the browser cannot start processes)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from anki.sound import AVTag, SoundOrVideoTag, TTSTag
from aqt import gui_hooks
from aqt.qt import QTimer
from aqt.sound import OnDoneCallback, Player, SoundOrVideoPlayer
from aqt.tts import TTSPlayer, TTSVoice

from . import web

logger = logging.getLogger("kioku.audio")


class _Done:
    """The callback of the current play() call, reported by the page with
    a token so a stopped file can't end the next one."""

    def __init__(self, event_type: str) -> None:
        self.token = 0
        self._on_done: OnDoneCallback | None = None
        web.listen(event_type, self._event)

    def start(self, on_done: OnDoneCallback) -> int:
        self.token += 1
        self._on_done = on_done
        return self.token

    def _event(self, event: dict) -> None:
        if event.get("token") == self.token:
            self.finish()

    def finish(self, later: bool = False) -> None:
        # Anki's queue (aqt.sound.AVPlayer) plays the next file only once the
        # current player reports it is done, also after being stopped; the
        # desktop players report that asynchronously
        self.token += 1
        on_done, self._on_done = self._on_done, None
        if on_done is not None:
            QTimer.singleShot(0, on_done) if later else on_done()


class WebAudioPlayer(SoundOrVideoPlayer):
    default_rank = 1

    def __init__(self, taskman: Any, media_folder: str) -> None:
        self._media_folder = media_folder
        self._done = _Done("audio_done")

    def rank_for_tag(self, tag: AVTag) -> int | None:
        if isinstance(tag, SoundOrVideoTag):
            return self.default_rank
        return None

    def play(self, tag: AVTag, on_done: OnDoneCallback) -> None:
        assert isinstance(tag, SoundOrVideoTag)
        path = os.path.join(self._media_folder, tag.filename)
        token = self._done.start(on_done)
        if not os.path.exists(path):
            logger.warning("cannot play %s: not found", tag.filename)
            self._done.finish(later=True)
            return
        web.js("play", path, token)
        gui_hooks.av_player_did_begin_playing(self, tag)

    def stop(self) -> None:
        web.js("stopAudio")
        self._done.finish(later=True)

    def toggle_pause(self) -> None:
        web.js("pauseAudio")

    def seek_relative(self, secs: int) -> None:
        web.js("seekAudio", secs)


@dataclass
class WebVoice(TTSVoice):
    uri: str


class WebSpeechPlayer(Player, TTSPlayer):
    def __init__(self) -> None:
        self._done = _Done("tts_done")

    def voices(self) -> list[TTSVoice]:
        # the browser fills its voice list in after the page loads: don't
        # keep an empty list (TTSPlayer caches the first one)
        if not self._available_voices:
            self._available_voices = self.get_available_voices()
        return self._available_voices

    def get_available_voices(self) -> list[TTSVoice]:
        try:
            voices = json.loads(web.js("voices") or "[]")
        except ValueError:
            return []
        # voice_for_tag() matches languages like Anki's (en_US)
        return [
            WebVoice(name=v["name"].replace(" ", "_"), lang=v["lang"].replace("-", "_"), uri=v["uri"])
            for v in voices
        ]

    def rank_for_tag(self, tag: AVTag) -> int | None:
        if not isinstance(tag, TTSTag):
            return None
        match = self.voice_for_tag(tag)
        return match.rank if match else None

    def play(self, tag: AVTag, on_done: OnDoneCallback) -> None:
        assert isinstance(tag, TTSTag)
        match = self.voice_for_tag(tag)
        assert match and isinstance(match.voice, WebVoice)
        token = self._done.start(on_done)
        web.js("speak", tag.field_text, match.voice.uri, tag.lang.replace("_", "-"), tag.speed, token)
        gui_hooks.av_player_did_begin_playing(self, tag)

    def stop(self) -> None:
        web.js("stopSpeaking")
        self._done.finish(later=True)

    def toggle_pause(self) -> None:
        web.js("pauseSpeaking")
