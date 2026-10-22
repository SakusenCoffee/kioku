"""{{tts}} through AVSpeechSynthesizer, replacing Anki's macOS `say` player
(iOS cannot start processes). Voices are named as on the desktop
(Apple_Samantha), so templates written on a Mac pick the same voice."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from rubicon.objc import NSObject, ObjCClass, at, objc_method
from rubicon.objc.runtime import load_library

from .webview import prop, same

from anki.sound import AVTag, TTSTag
from aqt import gui_hooks
from aqt.qt import QTimer
from aqt.sound import OnDoneCallback, Player
from aqt.tts import TTSPlayer, TTSVoice

load_library("AVFoundation")

logger = logging.getLogger("kioku.tts")

AVSpeechSynthesizer = ObjCClass("AVSpeechSynthesizer")
AVSpeechSynthesisVoice = ObjCClass("AVSpeechSynthesisVoice")
AVSpeechUtterance = ObjCClass("AVSpeechUtterance")

# AVSpeechUtteranceDefaultSpeechRate; the rate runs from 0 to 1
DEFAULT_RATE = 0.5


@dataclass
class AppleVoice(TTSVoice):
    identifier: str


class KiokuSpeechDelegate(NSObject):
    @objc_method
    def speechSynthesizer_didFinishSpeechUtterance_(self, synthesizer, utterance) -> None:
        if _player is not None:
            _player._finished(utterance)

    @objc_method
    def speechSynthesizer_didCancelSpeechUtterance_(self, synthesizer, utterance) -> None:
        if _player is not None:
            _player._finished(utterance)


_player: AVSpeechPlayer | None = None


class AVSpeechPlayer(Player, TTSPlayer):
    def __init__(self) -> None:
        global _player
        _player = self
        self._delegate = KiokuSpeechDelegate.alloc().init()
        self._synthesizer = AVSpeechSynthesizer.alloc().init()
        self._synthesizer.setDelegate_(self._delegate)
        self._utterance = None
        self._on_done: OnDoneCallback | None = None

    def get_available_voices(self) -> list[TTSVoice]:
        voices = list(AVSpeechSynthesisVoice.speechVoices())
        # the best quality first: voice_for_tag() takes the first match
        voices.sort(key=lambda v: -int(prop(v, "quality")))
        return [
            AppleVoice(
                name="Apple_" + str(prop(v, "name")).replace(" ", "_"),
                lang=str(prop(v, "language")).replace("-", "_"),
                identifier=str(prop(v, "identifier")),
            )
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
        assert match and isinstance(match.voice, AppleVoice)
        utterance = AVSpeechUtterance.speechUtteranceWithString_(at(tag.field_text))
        utterance.setVoice_(
            AVSpeechSynthesisVoice.voiceWithIdentifier_(at(match.voice.identifier))
        )
        utterance.setRate_(min(1.0, DEFAULT_RATE * tag.speed))
        self._utterance = utterance
        self._on_done = on_done
        self._synthesizer.speakUtterance_(utterance)
        gui_hooks.av_player_did_begin_playing(self, tag)

    def _finished(self, utterance: object) -> None:
        if not same(utterance, self._utterance):
            return
        self._utterance = None
        on_done, self._on_done = self._on_done, None
        if on_done is not None:
            on_done()

    def stop(self) -> None:
        # reported asynchronously, as the audio players do (see audio.py)
        self._utterance = None
        self._synthesizer.stopSpeakingAtBoundary_(0)  # AVSpeechBoundaryImmediate
        on_done, self._on_done = self._on_done, None
        if on_done is not None:
            QTimer.singleShot(0, on_done)

    def toggle_pause(self) -> None:
        if prop(self._synthesizer, "isPaused"):
            self._synthesizer.continueSpeaking()
        else:
            self._synthesizer.pauseSpeakingAtBoundary_(0)
