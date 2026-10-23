"""The remote screen's RandR side (ankidesk_remote.py), through XCB.

Xvfb has one RandR mode, without timings, so desktops see its refresh rate
as NaN: XFCE's Display settings then can't find the mode they saved, and
Scale, which needs CRTC transforms Xvfb doesn't have, fails half way, after
the screen was shrunk and its only output switched off. Nothing in XFCE can
switch it on again ("screen (Disabled)").

So:

- keep() gives the output real 60 Hz modes, every common size up to the
  screen's own, and switches to the one of the current size; then it
  watches RandR and, when a change leaves no output on, puts the last
  working size and mode back. It must keep running: the X server drops a
  client's modes when it disconnects.

XCB, not Xlib: Xlib exits the process when the X server goes away.
"""

from __future__ import annotations

import ctypes
import os
import select
import time

PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
# sizes offered besides the screen's own (largest first); only those that fit
SIZES = [(2560, 1440), (1920, 1200), (1920, 1080), (1680, 1050), (1600, 900), (1440, 900),
         (1366, 768), (1280, 800), (1280, 720), (1024, 768)]
REFRESH = 60
# how long RandR must stay quiet before a broken screen is put back: a
# desktop switches the output off and on again while it applies a change
QUIET_SECONDS = 3.0
SCREEN_CHANGE, CRTC_CHANGE, OUTPUT_CHANGE = 1, 2, 4


class XError(Exception):
    pass


class _Cookie(ctypes.Structure):
    _fields_ = [("sequence", ctypes.c_uint)]


class ModeInfo(ctypes.Structure):
    _fields_ = [("id", ctypes.c_uint32), ("width", ctypes.c_uint16), ("height", ctypes.c_uint16),
                ("dot_clock", ctypes.c_uint32), ("hsync_start", ctypes.c_uint16), ("hsync_end", ctypes.c_uint16),
                ("htotal", ctypes.c_uint16), ("hskew", ctypes.c_uint16), ("vsync_start", ctypes.c_uint16),
                ("vsync_end", ctypes.c_uint16), ("vtotal", ctypes.c_uint16), ("name_len", ctypes.c_uint16),
                ("mode_flags", ctypes.c_uint32)]


class _ScreenIter(ctypes.Structure):
    _fields_ = [("data", ctypes.c_void_p), ("rem", ctypes.c_int), ("index", ctypes.c_int)]


_lib: dict[str, ctypes.CDLL] = {}


def _libs() -> tuple[ctypes.CDLL, ctypes.CDLL, ctypes.CDLL]:
    if not _lib:
        xcb = ctypes.CDLL(os.path.join(PREFIX, "lib/libxcb.so"))
        rr = ctypes.CDLL(os.path.join(PREFIX, "lib/libxcb-randr.so"))
        libc = ctypes.CDLL(None)
        P, C, U32, U16 = ctypes.c_void_p, _Cookie, ctypes.c_uint32, ctypes.c_uint16
        for lib, name, res, args in [
            (xcb, "xcb_connect", P, [ctypes.c_char_p, P]),
            (xcb, "xcb_connection_has_error", ctypes.c_int, [P]),
            (xcb, "xcb_disconnect", None, [P]),
            (xcb, "xcb_flush", ctypes.c_int, [P]),
            (xcb, "xcb_get_file_descriptor", ctypes.c_int, [P]),
            (xcb, "xcb_get_setup", P, [P]),
            (xcb, "xcb_setup_roots_iterator", _ScreenIter, [P]),
            (xcb, "xcb_poll_for_event", P, [P]),
            (xcb, "xcb_request_check", P, [P, C]),
            (xcb, "xcb_get_geometry", C, [P, U32]),
            (xcb, "xcb_get_geometry_reply", P, [P, C, P]),
            (rr, "xcb_randr_query_version", C, [P, U32, U32]),
            (rr, "xcb_randr_query_version_reply", P, [P, C, P]),
            (rr, "xcb_randr_select_input", C, [P, U32, U16]),
            (rr, "xcb_randr_get_screen_size_range", C, [P, U32]),
            (rr, "xcb_randr_get_screen_size_range_reply", P, [P, C, P]),
            (rr, "xcb_randr_get_screen_resources_current", C, [P, U32]),
            (rr, "xcb_randr_get_screen_resources_current_reply", P, [P, C, P]),
            (rr, "xcb_randr_get_screen_resources_current_crtcs", ctypes.POINTER(U32), [P]),
            (rr, "xcb_randr_get_screen_resources_current_crtcs_length", ctypes.c_int, [P]),
            (rr, "xcb_randr_get_screen_resources_current_outputs", ctypes.POINTER(U32), [P]),
            (rr, "xcb_randr_get_screen_resources_current_outputs_length", ctypes.c_int, [P]),
            (rr, "xcb_randr_get_screen_resources_current_modes", ctypes.POINTER(ModeInfo), [P]),
            (rr, "xcb_randr_get_screen_resources_current_modes_length", ctypes.c_int, [P]),
            (rr, "xcb_randr_get_screen_resources_current_names", ctypes.POINTER(ctypes.c_char), [P]),
            (rr, "xcb_randr_get_crtc_info", C, [P, U32, U32]),
            (rr, "xcb_randr_get_crtc_info_reply", P, [P, C, P]),
            (rr, "xcb_randr_set_crtc_config", C, [P, U32, U32, U32, ctypes.c_int16, ctypes.c_int16, U32, U16,
                                                   U32, ctypes.POINTER(U32)]),
            (rr, "xcb_randr_set_crtc_config_reply", P, [P, C, P]),
            (rr, "xcb_randr_set_screen_size_checked", C, [P, U32, U16, U16, U32, U32]),
            (rr, "xcb_randr_create_mode", C, [P, U32, ModeInfo, U32, ctypes.c_char_p]),
            (rr, "xcb_randr_create_mode_reply", P, [P, C, P]),
            (rr, "xcb_randr_add_output_mode_checked", C, [P, U32, U32]),
        ]:
            fn = getattr(lib, name)
            fn.restype, fn.argtypes = res, args
        libc.free.argtypes = [P]
        _lib.update(xcb=xcb, rr=rr, libc=libc)
    return _lib["xcb"], _lib["rr"], _lib["libc"]


def timed_mode(width: int, height: int, name: str) -> ModeInfo:
    """A mode with blanking (CVT reduced-blanking-like) and REFRESH Hz."""
    htotal, vtotal = width + 160, height + 30
    return ModeInfo(id=0, width=width, height=height, dot_clock=htotal * vtotal * REFRESH,
                    hsync_start=width + 48, hsync_end=width + 80, htotal=htotal, hskew=0,
                    vsync_start=height + 3, vsync_end=height + 8, vtotal=vtotal, name_len=len(name), mode_flags=0)


def refresh(m: ModeInfo) -> float:
    return m.dot_clock / (m.htotal * m.vtotal) if m.htotal and m.vtotal else 0.0


class Screen:
    """One XCB connection to a display, with the RandR calls used here."""

    def __init__(self, display: str) -> None:
        self.xcb, self.rr, self.libc = _libs()
        self.c = self.xcb.xcb_connect(display.encode(), None)
        if self.xcb.xcb_connection_has_error(self.c):
            self.xcb.xcb_disconnect(self.c)
            raise XError(f"can't connect to {display}")
        it = self.xcb.xcb_setup_roots_iterator(self.xcb.xcb_get_setup(self.c))
        screen = ctypes.cast(it.data, ctypes.POINTER(ctypes.c_uint8 * 28)).contents
        self.root = int.from_bytes(bytes(screen[0:4]), "little")
        self._reply(self.rr.xcb_randr_query_version_reply, self.rr.xcb_randr_query_version(self.c, 1, 5))

    def close(self) -> None:
        self.xcb.xcb_disconnect(self.c)

    def broken(self) -> bool:
        return bool(self.xcb.xcb_connection_has_error(self.c))

    def _reply(self, fn, cookie: _Cookie) -> bytes:
        """The reply's fixed part, copied (the rest via accessors on `raw`)."""
        raw = fn(self.c, cookie, None)
        if not raw:
            raise XError(f"{fn.__name__} failed")
        try:
            return ctypes.string_at(raw, 32)
        finally:
            self.libc.free(raw)

    def _check(self, cookie: _Cookie, what: str) -> None:
        err = self.xcb.xcb_request_check(self.c, cookie)
        if err:
            code = ctypes.string_at(err, 2)[1]
            self.libc.free(err)
            raise XError(f"{what}: X error {code}")

    @staticmethod
    def _u(data: bytes, offset: int, size: int) -> int:
        return int.from_bytes(data[offset:offset + size], "little")

    def size_range(self) -> tuple[int, int]:
        """The largest screen size (Xvfb: the size it was started with)."""
        r = self._reply(self.rr.xcb_randr_get_screen_size_range_reply,
                        self.rr.xcb_randr_get_screen_size_range(self.c, self.root))
        return self._u(r, 12, 2), self._u(r, 14, 2)

    def state(self) -> dict:
        """Screen size, CRTCs (mode, size, outputs), outputs and modes."""
        rr = self.rr
        raw = rr.xcb_randr_get_screen_resources_current_reply(
            self.c, rr.xcb_randr_get_screen_resources_current(self.c, self.root), None)
        if not raw:
            raise XError("can't read the screen's resources")
        try:
            head = ctypes.string_at(raw, 32)
            config_ts = self._u(head, 12, 4)
            crtc_ids = rr.xcb_randr_get_screen_resources_current_crtcs(raw)
            crtcs = [crtc_ids[i] for i in range(rr.xcb_randr_get_screen_resources_current_crtcs_length(raw))]
            out_ids = rr.xcb_randr_get_screen_resources_current_outputs(raw)
            outputs = [out_ids[i] for i in range(rr.xcb_randr_get_screen_resources_current_outputs_length(raw))]
            mode_ptr = rr.xcb_randr_get_screen_resources_current_modes(raw)
            names = rr.xcb_randr_get_screen_resources_current_names(raw)
            modes, at = [], 0
            for i in range(rr.xcb_randr_get_screen_resources_current_modes_length(raw)):
                m = ModeInfo.from_buffer_copy(mode_ptr[i])
                modes.append((m, names[at:at + m.name_len].decode(errors="replace")))
                at += m.name_len
        finally:
            self.libc.free(raw)
        info = []
        for crtc in crtcs:
            r = self._reply(rr.xcb_randr_get_crtc_info_reply, rr.xcb_randr_get_crtc_info(self.c, crtc, config_ts))
            info.append({"id": crtc, "mode": self._u(r, 20, 4), "width": self._u(r, 16, 2),
                         "height": self._u(r, 18, 2), "outputs": self._u(r, 28, 2)})
        return {"config_ts": config_ts, "crtcs": info, "outputs": outputs, "modes": modes,
                "screen": self._root_size()}

    def _root_size(self) -> tuple[int, int]:
        """The root window's size now (the setup has it as of connecting)."""
        r = self._reply(self.xcb.xcb_get_geometry_reply, self.xcb.xcb_get_geometry(self.c, self.root))
        return self._u(r, 16, 2), self._u(r, 18, 2)

    def set_screen_size(self, width: int, height: int) -> None:
        # millimetres at 96 dpi, as Xvfb's -dpi 96
        self._check(self.rr.xcb_randr_set_screen_size_checked(self.c, self.root, width, height,
                                                              round(width * 25.4 / 96), round(height * 25.4 / 96)),
                    f"screen size {width}x{height}")

    def set_crtc(self, crtc: int, mode: int, outputs: list[int], config_ts: int) -> None:
        arr = (ctypes.c_uint32 * len(outputs))(*outputs)
        r = self._reply(self.rr.xcb_randr_set_crtc_config_reply,
                        self.rr.xcb_randr_set_crtc_config(self.c, crtc, 0, config_ts, 0, 0, mode, 1,
                                                          len(outputs), arr))
        if r[1] != 0:
            raise XError(f"CRTC {crtc}: status {r[1]}")

    def add_mode(self, output: int, width: int, height: int, name: str) -> int:
        r = self._reply(self.rr.xcb_randr_create_mode_reply,
                        self.rr.xcb_randr_create_mode(self.c, self.root, timed_mode(width, height, name),
                                                      len(name), name.encode()))
        mode = self._u(r, 8, 4)
        self._check(self.rr.xcb_randr_add_output_mode_checked(self.c, output, mode), f"add mode {name}")
        return mode

    def watch_events(self) -> None:
        self.rr.xcb_randr_select_input(self.c, self.root, SCREEN_CHANGE | CRTC_CHANGE | OUTPUT_CHANGE)
        self.xcb.xcb_flush(self.c)

    def drain_events(self, seconds: float) -> bool:
        """Waits up to `seconds` for events; True if any came."""
        got = False
        fd = self.xcb.xcb_get_file_descriptor(self.c)
        select.select([fd], [], [], seconds)
        while ev := self.xcb.xcb_poll_for_event(self.c):
            self.libc.free(ev)
            got = True
        return got


def _timed(modes: list[tuple[ModeInfo, str]], width: int, height: int) -> ModeInfo | None:
    for m, _ in modes:
        if (m.width, m.height) == (width, height) and abs(refresh(m) - REFRESH) < 0.5:
            return m
    return None


def add_modes(s: Screen) -> list[str]:
    """Gives the output 60 Hz modes up to the screen's size and switches to
    the one of the current size. Returns the sizes added. The modes last as
    long as `s` stays connected."""
    max_w, max_h = s.size_range()
    st = s.state()
    if not st["outputs"] or not st["crtcs"]:
        return []
    output = st["outputs"][0]
    names = {name for _, name in st["modes"]}
    added = []
    for w, h in sorted({(max_w, max_h), *SIZES}, reverse=True):
        if w > max_w or h > max_h or _timed(st["modes"], w, h):
            continue
        name = f"{w}x{h}"
        # Xvfb's own mode already has the plain name
        s.add_mode(output, w, h, name if name not in names else f"{name}_{REFRESH}")
        added.append(name)
    st = s.state()
    mode = _timed(st["modes"], *st["screen"])
    if mode:
        s.set_crtc(st["crtcs"][0]["id"], mode.id, [output], st["config_ts"])
    return added


def keep(display: str, stop=lambda: False, log=lambda text: None, ready=lambda: None) -> None:
    """Adds the modes, calls ready(), then runs until stop() or the display
    goes away: whenever RandR has been quiet for QUIET_SECONDS and no CRTC
    is on, the last working screen size and mode come back."""
    s = Screen(display)
    try:
        try:
            log("modes added: " + (", ".join(add_modes(s)) or "none"))
        except XError as err:
            log(f"no modes added: {err}")
        ready()
        s.watch_events()
        good = None
        quiet_from = time.monotonic()
        while not stop() and not s.broken():
            if s.drain_events(1.0):
                quiet_from = time.monotonic()
                continue
            if time.monotonic() - quiet_from < QUIET_SECONDS:
                continue
            st = s.state()
            on = [c for c in st["crtcs"] if c["mode"] and c["outputs"]]
            if on:
                good = (st["screen"], on[0]["mode"])
                continue
            if not st["crtcs"] or not st["outputs"]:
                continue
            size, mode = good or _fallback(s, st)
            log(f"no output on (screen {st['screen'][0]}x{st['screen'][1]}): back to {size[0]}x{size[1]}")
            try:
                if st["screen"] != size:
                    s.set_screen_size(*size)
                s.set_crtc(st["crtcs"][0]["id"], mode, [st["outputs"][0]], s.state()["config_ts"])
            except XError as err:
                log(f"couldn't put the screen back: {err}")
                good = None
            quiet_from = time.monotonic()
    finally:
        s.close()


def _fallback(s: Screen, st: dict) -> tuple[tuple[int, int], int]:
    """Without a known good state: the largest size, its timed mode."""
    w, h = s.size_range()
    mode = _timed(st["modes"], w, h)
    if mode is None:
        mode = next((m for m, _ in st["modes"] if (m.width, m.height) == (w, h)), st["modes"][0][0])
    return (mode.width, mode.height), mode.id
