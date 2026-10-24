"""Serve a directory with the headers SharedArrayBuffer (pthreads) needs,
and relay sockets: Emscripten turns connect() into a WebSocket, which the
app page (kioku-web.js) points at /__relay/<host>:<port>; it is passed on
over TCP (TLS stays inside wasm). Only for the app page (Origin check):
any host on port 443 (AnkiWeb, add-ons' services), other ports with
KIOKU_RELAY_ALLOW="host:port,*.example.com:8080".
Usage: serve.py <dir> [port]"""
import base64
import fnmatch
import functools
import hashlib
import http.server
import os
import socket
import struct
import sys
import threading

RELAY = "/__relay/"
ALLOW = ["*:443"] + [
    a.strip() for a in os.environ.get("KIOKU_RELAY_ALLOW", "").split(",") if a.strip()
]
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        # credentialless: cross-origin scripts and images (add-ons' CDNs) load
        # without opting in, as they do on the desktop; Safari lacks it
        self.send_header("Cross-Origin-Embedder-Policy", "credentialless")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        if self.path.startswith(RELAY) and self.headers.get("Upgrade", "").lower() == "websocket":
            self.relay(self.path[len(RELAY) :])
        else:
            super().do_GET()

    def relay(self, target: str) -> None:
        # WebSockets aren't bound by CORS: without this any website open in
        # the browser could use the relay
        if self.headers.get("Origin") != f"http://{self.headers.get('Host')}":
            self.send_error(403, "relay is for the app page only")
            return
        host, _, port = target.rpartition(":")
        if not port.isdigit() or not any(fnmatch.fnmatch(target.lower(), a) for a in ALLOW):
            self.send_error(403, f"not relayed: {target}")
            return
        try:
            upstream = socket.create_connection((host, int(port)), timeout=20)
            upstream.settimeout(None)
        except OSError as e:
            self.send_error(502, f"{target}: {e}")
            return
        accept = base64.b64encode(
            hashlib.sha1((self.headers["Sec-WebSocket-Key"] + WS_GUID).encode()).digest()
        ).decode()
        self.protocol_version = "HTTP/1.1"
        self.send_response(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        if "binary" in self.headers.get("Sec-WebSocket-Protocol", ""):
            self.send_header("Sec-WebSocket-Protocol", "binary")
        self.end_headers()
        self.wfile.flush()
        self.close_connection = True
        lock = threading.Lock()

        def send(opcode: int, data: bytes) -> None:
            n = len(data)
            head = bytes([0x80 | opcode])
            if n < 126:
                head += bytes([n])
            elif n < 1 << 16:
                head += bytes([126]) + struct.pack(">H", n)
            else:
                head += bytes([127]) + struct.pack(">Q", n)
            with lock:
                self.connection.sendall(head + data)

        def downstream() -> None:
            try:
                while data := upstream.recv(65536):
                    send(0x2, data)
            except OSError:
                pass
            try:
                send(0x8, b"")
            except OSError:
                pass

        thread = threading.Thread(target=downstream, daemon=True)
        thread.start()
        try:
            while True:
                head = self.rfile.read(2)
                if len(head) < 2:
                    break
                opcode, n = head[0] & 0x0F, head[1] & 0x7F
                if n == 126:
                    n = struct.unpack(">H", self.rfile.read(2))[0]
                elif n == 127:
                    n = struct.unpack(">Q", self.rfile.read(8))[0]
                mask = self.rfile.read(4) if head[1] & 0x80 else b"\0\0\0\0"
                raw = self.rfile.read(n)
                keys = (mask * (n // 4 + 1))[:n]
                data = (int.from_bytes(raw, "big") ^ int.from_bytes(keys, "big")).to_bytes(n, "big")
                if opcode == 0x8:
                    break
                if opcode == 0x9:
                    send(0xA, data)
                elif opcode in (0x0, 0x1, 0x2):
                    upstream.sendall(data)
        except OSError:
            pass
        finally:
            try:
                upstream.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            upstream.close()
            thread.join(5)


port = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
handler = functools.partial(Handler, directory=sys.argv[1])
http.server.ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()
