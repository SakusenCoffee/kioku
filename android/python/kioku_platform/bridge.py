"""Calls to and events from the Java side (KiokuBridge.java), through the
_kioku_android module (src/kioku_android.cpp)."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

import _kioku_android

logger = logging.getLogger("kioku.bridge")

_listeners: dict[str, list[Callable[[dict], None]]] = {}
_answerers: dict[str, Callable[[dict], str]] = {}


def call(method: str, **args: Any) -> Any:
    result = json.loads(_kioku_android.call(method, json.dumps(args)))
    if isinstance(result, dict) and "error" in result:
        raise RuntimeError(f"{method}: {result['error']}")
    return result


def listen(event_type: str, callback: Callable[[dict], None]) -> None:
    _listeners.setdefault(event_type, []).append(callback)


def answer(request_type: str, callback: Callable[[dict], str]) -> None:
    """`callback` answers requests the Java side waits for: keep it short,
    and don't call() from it (the Java side may be waiting on its UI thread)."""
    _answerers[request_type] = callback


def _answer(text: str) -> str:
    request = json.loads(text)
    callback = _answerers.get(request.get("type", ""))
    if callback is None:
        return ""
    try:
        return callback(request)
    except Exception:
        logger.exception("answering %s", request.get("type"))
        return "error"


def _dispatch(text: str) -> None:
    event = json.loads(text)
    for callback in _listeners.get(event.get("type", ""), []):
        try:
            callback(event)
        except Exception:
            logger.exception("handling %s", event.get("type"))


_kioku_android.set_handler(_dispatch)
_kioku_android.set_request_handler(_answer)
