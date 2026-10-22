"""{{tts}} through Android's TextToSpeech, replacing Anki's desktop players
(Android apps cannot start processes). Voices keep the engine's names
(en-us-x-sfg-local); installed voices come before network ones."""

from __future__ import annotations

import re
from dataclasses import dataclass

from anki.sound import AVTag, TTSTag
from aqt import gui_hooks
from aqt.qt import QTimer
from aqt.sound import OnDoneCallback, Player
from aqt.tts import TTSPlayer, TTSVoice

from . import bridge


@dataclass
class AndroidVoice(TTSVoice):
    network: bool


def _lang(voice: dict) -> str:
    """en_US. Samsung's engine gives locales like "eng" (ISO 639-2, no
    country) but names its voices en-US-SMTf00."""
    lang = voice["lang"].replace("-", "_")
    m = re.match(r"([a-z]{2,3})-([A-Z]{2})-", voice["name"])
    if "_" not in lang and m:
        return f"{m[1]}_{m[2]}"
    return lang


class TextToSpeechPlayer(Player, TTSPlayer):
    def __init__(self) -> None:
        # the utterance being spoken; finished ones with another id are stale
        self._id = 0
        self._on_done: OnDoneCallback | None = None
        bridge.listen("ttsDone", self._finished)

    def get_available_voices(self) -> list[TTSVoice]:
        voices = [
            AndroidVoice(name=v["name"], lang=_lang(v), network=v["network"])
            for v in bridge.call("tts.voices")
        ]
        # voice_for_tag() takes the first match
        return sorted(voices, key=lambda v: v.network)

    def rank_for_tag(self, tag: AVTag) -> int | None:
        if not isinstance(tag, TTSTag):
            return None
        match = self.voice_for_tag(tag)
        return match.rank if match else None

    def play(self, tag: AVTag, on_done: OnDoneCallback) -> None:
        assert isinstance(tag, TTSTag)
        match = self.voice_for_tag(tag)
        assert match
        self._id += 1
        self._on_done = on_done
        bridge.call(
            "tts.speak",
            text=tag.field_text,
            voice=match.voice.name,
            rate=tag.speed,
            id=self._id,
        )
        gui_hooks.av_player_did_begin_playing(self, tag)

    def _finished(self, event: dict) -> None:
        if event["id"] != self._id:
            return
        on_done, self._on_done = self._on_done, None
        if on_done is not None:
            on_done()

    def stop(self) -> None:
        # reported asynchronously, as the audio player does (see audio.py)
        self._id += 1
        bridge.call("tts.stop")
        on_done, self._on_done = self._on_done, None
        if on_done is not None:
            QTimer.singleShot(0, on_done)
