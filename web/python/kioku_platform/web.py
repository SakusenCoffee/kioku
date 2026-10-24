"""Talking to the page (shell/kioku-web.js, window.__kiokuWeb).

Python calls JavaScript with js(); the page's events arrive in _post(),
called by the wasm export kioku_post from a clean JavaScript stack. HTTP
requests relayed by the service worker run on worker threads (like
Anki's own server thread); everything else is handled on Qt's main loop.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

import _kioku_web

logger = logging.getLogger("kioku.web")

_listeners: dict[str, Callable[[dict], None]] = {}
_http_pool = ThreadPoolExecutor(4, thread_name_prefix="kioku-http")
# Requests are handed to the pool by a thread of their own: the pool starts
# threads on demand, and Thread.start() on the main thread can deadlock
# (a new Web Worker only starts once the main thread yields)
_http_queue: "queue.SimpleQueue[dict]" = queue.SimpleQueue()


def _http_dispatcher() -> None:
    from . import http

    while True:
        _http_pool.submit(http.handle, _http_queue.get())


def js(function: str, *args: Any) -> str:
    """Call __kiokuWeb.<function>(*args) on the page; main thread only."""
    call = f"__kiokuWeb.{function}({','.join(json.dumps(a) for a in args)})"
    return _kioku_web.run_script(f"__kiokuWeb.safe({json.dumps(call)})")


def listen(event_type: str, handler: Callable[[dict], None]) -> None:
    _listeners[event_type] = handler


def start() -> None:
    """Start serving, and deliver the events the page queued before Python
    was listening."""
    threading.Thread(target=_http_dispatcher, name="kioku-http-dispatch", daemon=True).start()
    js("ready")


def _post(text: str) -> None:
    event = json.loads(text)
    if event.get("type") == "http":
        _http_queue.put(event)
        return
    from PyQt6.QtCore import QTimer

    # not from inside this call: handlers may open dialogs, which suspend
    # the wasm stack (Asyncify), and this call came straight from JavaScript
    QTimer.singleShot(0, lambda: _dispatch(event))


def _dispatch(event: dict) -> None:
    handler = _listeners.get(event.get("type", ""))
    if handler is None:
        logger.warning("unhandled page event %s", event.get("type"))
        return
    try:
        handler(event)
    except Exception:
        logger.exception("handling page event %s", event.get("type"))
