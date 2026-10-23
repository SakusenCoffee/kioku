"""A small VNC (RFB 3.8) client for the tests: VNC password auth, the screen
size the server reports (it follows RandR changes), and screenshots.

Pure Python: VNC auth needs DES, which neither the prefix nor a Mac has as a
module, so it's here (single-block encryption only).
"""

from __future__ import annotations

import socket
import struct
import time
import zlib

# DES (FIPS 46-3), encryption of one block
############################################################

_PC1 = [57, 49, 41, 33, 25, 17, 9, 1, 58, 50, 42, 34, 26, 18, 10, 2, 59, 51, 43, 35, 27, 19, 11, 3, 60, 52, 44,
        36, 63, 55, 47, 39, 31, 23, 15, 7, 62, 54, 46, 38, 30, 22, 14, 6, 61, 53, 45, 37, 29, 21, 13, 5, 28, 20, 12, 4]
_PC2 = [14, 17, 11, 24, 1, 5, 3, 28, 15, 6, 21, 10, 23, 19, 12, 4, 26, 8, 16, 7, 27, 20, 13, 2, 41, 52, 31, 37,
        47, 55, 30, 40, 51, 45, 33, 48, 44, 49, 39, 56, 34, 53, 46, 42, 50, 36, 29, 32]
_SHIFTS = [1, 1, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 1]
_IP = [58, 50, 42, 34, 26, 18, 10, 2, 60, 52, 44, 36, 28, 20, 12, 4, 62, 54, 46, 38, 30, 22, 14, 6, 64, 56, 48, 40,
       32, 24, 16, 8, 57, 49, 41, 33, 25, 17, 9, 1, 59, 51, 43, 35, 27, 19, 11, 3, 61, 53, 45, 37, 29, 21, 13, 5, 63,
       55, 47, 39, 31, 23, 15, 7]
_FP = [_IP.index(i) + 1 for i in range(1, 65)]
_E = [32, 1, 2, 3, 4, 5, 4, 5, 6, 7, 8, 9, 8, 9, 10, 11, 12, 13, 12, 13, 14, 15, 16, 17, 16, 17, 18, 19, 20, 21, 20,
      21, 22, 23, 24, 25, 24, 25, 26, 27, 28, 29, 28, 29, 30, 31, 32, 1]
_P = [16, 7, 20, 21, 29, 12, 28, 17, 1, 15, 23, 26, 5, 18, 31, 10, 2, 8, 24, 14, 32, 27, 3, 9, 19, 13, 30, 6, 22,
      11, 4, 25]
_S = [
    [14, 4, 13, 1, 2, 15, 11, 8, 3, 10, 6, 12, 5, 9, 0, 7, 0, 15, 7, 4, 14, 2, 13, 1, 10, 6, 12, 11, 9, 5, 3, 8,
     4, 1, 14, 8, 13, 6, 2, 11, 15, 12, 9, 7, 3, 10, 5, 0, 15, 12, 8, 2, 4, 9, 1, 7, 5, 11, 3, 14, 10, 0, 6, 13],
    [15, 1, 8, 14, 6, 11, 3, 4, 9, 7, 2, 13, 12, 0, 5, 10, 3, 13, 4, 7, 15, 2, 8, 14, 12, 0, 1, 10, 6, 9, 11, 5,
     0, 14, 7, 11, 10, 4, 13, 1, 5, 8, 12, 6, 9, 3, 2, 15, 13, 8, 10, 1, 3, 15, 4, 2, 11, 6, 7, 12, 0, 5, 14, 9],
    [10, 0, 9, 14, 6, 3, 15, 5, 1, 13, 12, 7, 11, 4, 2, 8, 13, 7, 0, 9, 3, 4, 6, 10, 2, 8, 5, 14, 12, 11, 15, 1,
     13, 6, 4, 9, 8, 15, 3, 0, 11, 1, 2, 12, 5, 10, 14, 7, 1, 10, 13, 0, 6, 9, 8, 7, 4, 15, 14, 3, 11, 5, 2, 12],
    [7, 13, 14, 3, 0, 6, 9, 10, 1, 2, 8, 5, 11, 12, 4, 15, 13, 8, 11, 5, 6, 15, 0, 3, 4, 7, 2, 12, 1, 10, 14, 9,
     10, 6, 9, 0, 12, 11, 7, 13, 15, 1, 3, 14, 5, 2, 8, 4, 3, 15, 0, 6, 10, 1, 13, 8, 9, 4, 5, 11, 12, 7, 2, 14],
    [2, 12, 4, 1, 7, 10, 11, 6, 8, 5, 3, 15, 13, 0, 14, 9, 14, 11, 2, 12, 4, 7, 13, 1, 5, 0, 15, 10, 3, 9, 8, 6,
     4, 2, 1, 11, 10, 13, 7, 8, 15, 9, 12, 5, 6, 3, 0, 14, 11, 8, 12, 7, 1, 14, 2, 13, 6, 15, 0, 9, 10, 4, 5, 3],
    [12, 1, 10, 15, 9, 2, 6, 8, 0, 13, 3, 4, 14, 7, 5, 11, 10, 15, 4, 2, 7, 12, 9, 5, 6, 1, 13, 14, 0, 11, 3, 8,
     9, 14, 15, 5, 2, 8, 12, 3, 7, 0, 4, 10, 1, 13, 11, 6, 4, 3, 2, 12, 9, 5, 15, 10, 11, 14, 1, 7, 6, 0, 8, 13],
    [4, 11, 2, 14, 15, 0, 8, 13, 3, 12, 9, 7, 5, 10, 6, 1, 13, 0, 11, 7, 4, 9, 1, 10, 14, 3, 5, 12, 2, 15, 8, 6,
     1, 4, 11, 13, 12, 3, 7, 14, 10, 15, 6, 8, 0, 5, 9, 2, 6, 11, 13, 8, 1, 4, 10, 7, 9, 5, 0, 15, 14, 2, 3, 12],
    [13, 2, 8, 4, 6, 15, 11, 1, 10, 9, 3, 14, 5, 0, 12, 7, 1, 15, 13, 8, 10, 3, 7, 4, 12, 5, 6, 11, 0, 14, 9, 2,
     7, 11, 4, 1, 9, 12, 14, 2, 0, 6, 10, 13, 15, 3, 5, 8, 2, 1, 14, 7, 4, 10, 8, 13, 15, 12, 9, 0, 3, 5, 6, 11],
]


def _permute(value: int, table: list[int], width: int) -> int:
    out = 0
    for pos in table:
        out = (out << 1) | ((value >> (width - pos)) & 1)
    return out


def des_encrypt(key: bytes, block: bytes) -> bytes:
    k = _permute(int.from_bytes(key, "big"), _PC1, 64)
    c, d = k >> 28, k & 0xFFFFFFF
    subkeys = []
    for shift in _SHIFTS:
        c = ((c << shift) | (c >> (28 - shift))) & 0xFFFFFFF
        d = ((d << shift) | (d >> (28 - shift))) & 0xFFFFFFF
        subkeys.append(_permute((c << 28) | d, _PC2, 56))
    b = _permute(int.from_bytes(block, "big"), _IP, 64)
    left, right = b >> 32, b & 0xFFFFFFFF
    for sk in subkeys:
        x = _permute(right, _E, 32) ^ sk
        f = 0
        for i in range(8):
            six = (x >> (42 - 6 * i)) & 0x3F
            f = (f << 4) | _S[i][(((six & 0x20) >> 4) | (six & 1)) * 16 + ((six >> 1) & 0xF)]
        left, right = right, left ^ _permute(f, _P, 32)
    return _permute((right << 32) | left, _FP, 64).to_bytes(8, "big")


def vnc_response(password: str, challenge: bytes) -> bytes:
    """VNC auth: DES with the password's bits reversed in each byte."""
    key = bytes(int(f"{b:08b}"[::-1], 2) for b in password.encode()[:8].ljust(8, b"\0"))
    return des_encrypt(key, challenge[:8]) + des_encrypt(key, challenge[8:16])


# RFB
############################################################

RAW, DESKTOP_SIZE, EXT_DESKTOP_SIZE = 0, -223, -308


class AuthFailed(Exception):
    pass


class Client:
    """Connects and asks for 32-bit raw pixels; tells the server it follows
    screen size changes (DesktopSize), as noVNC does."""

    def __init__(self, host: str, port: int, password: str | None = None, timeout: float = 30) -> None:
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self._recv(12)
        self.sock.sendall(b"RFB 003.008\n")
        types = self._recv(self._recv(1)[0])
        if not types:
            raise AuthFailed(self._reason())
        if 1 in types and password is None:
            self.sock.sendall(b"\x01")
        elif 2 in types:
            self.sock.sendall(b"\x02")
            self.sock.sendall(vnc_response(password or "", self._recv(16)))
        else:
            raise AuthFailed(f"security types {list(types)}")
        if struct.unpack(">I", self._recv(4))[0] != 0:
            raise AuthFailed(self._reason())
        self.sock.sendall(b"\x01")  # shared
        self.width, self.height = struct.unpack(">HH", self._recv(4))
        self._recv(16)
        self.name = self._recv(struct.unpack(">I", self._recv(4))[0]).decode(errors="replace")
        # 32 bpp, depth 24, little endian, true colour, r/g/b at 16/8/0
        self.sock.sendall(struct.pack(">B3xBBBBHHHBBB3x", 0, 32, 24, 0, 1, 255, 255, 255, 16, 8, 0))
        self.sock.sendall(struct.pack(">BxHiii", 2, 3, RAW, DESKTOP_SIZE, EXT_DESKTOP_SIZE))
        self.pixels = bytearray(self.width * self.height * 4)

    def close(self) -> None:
        self.sock.close()

    def _recv(self, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("the server closed the connection")
            buf += chunk
        return bytes(buf)

    def _reason(self) -> str:
        return self._recv(struct.unpack(">I", self._recv(4))[0]).decode(errors="replace")

    def update(self, region: tuple[int, int, int, int] | None = None, seconds: float = 10) -> tuple[int, int]:
        """Asks for (part of) the screen and reads until those pixels came;
        returns the screen size, which the server may have changed."""
        x, y, w, h = region or (0, 0, self.width, self.height)
        self.sock.sendall(struct.pack(">BBHHHH", 3, 0, x, y, w, h))
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            kind = self._recv(1)[0]
            if kind == 0:
                self._recv(1)
                got_pixels = False
                for _ in range(struct.unpack(">H", self._recv(2))[0]):
                    rx, ry, rw, rh, enc = struct.unpack(">HHHHi", self._recv(12))
                    if enc == RAW:
                        data = self._recv(rw * rh * 4)
                        for row in range(rh):
                            start = ((ry + row) * self.width + rx) * 4
                            self.pixels[start:start + rw * 4] = data[row * rw * 4:(row + 1) * rw * 4]
                        got_pixels = True
                    elif enc in (DESKTOP_SIZE, EXT_DESKTOP_SIZE):
                        if enc == EXT_DESKTOP_SIZE:
                            self._recv(16 * self._recv(4)[0])
                        # x11vnc also sends it, unchanged, for every full request
                        if (rw, rh) != (self.width, self.height):
                            self.width, self.height = rw, rh
                            self.pixels = bytearray(rw * rh * 4)
                            if region is None:
                                # the whole (new) screen
                                self.sock.sendall(struct.pack(">BBHHHH", 3, 0, 0, 0, rw, rh))
                    else:
                        raise ValueError(f"unexpected encoding {enc}")
                if got_pixels:
                    return self.width, self.height
            elif kind == 1:  # colour map
                self._recv(3)
                self._recv(6 * struct.unpack(">H", self._recv(2))[0])
            elif kind == 2:  # bell
                pass
            elif kind == 3:  # clipboard
                self._recv(3)
                self._recv(struct.unpack(">I", self._recv(4))[0])
            else:
                raise ValueError(f"unexpected message {kind}")
        raise TimeoutError("no screen update")

    def png(self, path: str, shrink: int = 1) -> None:
        """The last screen read, as a PNG (every `shrink`th pixel)."""
        w, h = self.width // shrink, self.height // shrink
        rows = bytearray()
        for y in range(h):
            rows.append(0)
            start = y * shrink * self.width * 4
            line = self.pixels[start:start + self.width * 4]
            for x in range(0, w * shrink, shrink):
                b, g, r = line[x * 4:x * 4 + 3]
                rows += bytes((r, g, b))

        def chunk(kind: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

        with open(path, "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(bytes(rows), 6)) + chunk(b"IEND", b""))
