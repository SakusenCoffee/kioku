"""Serve a directory with the headers SharedArrayBuffer (pthreads) needs,
and relay sockets: Emscripten turns connect() into a WebSocket, which the
app page (kioku-web.js) points at /__relay/<host>:<port>; it is passed on
over TCP (TLS stays inside wasm). Only for the app page (Origin check):
any host on port 443 (AnkiWeb, add-ons' services), other ports with
KIOKU_RELAY_ALLOW="host:port,*.example.com:8080".
KIOKU_SELFTEST=<folder> (tools/test/selftest.py) adds tools/test/selftest.js
to app.html and serves /__selftest/: steps.json and files from the folder,
the page's console appended to its log.txt.
KIOKU_HOST=0.0.0.0 listens on the LAN too; a phone then needs https (the
page needs a secure context): KIOKU_TLS=<cert.pem>:<key.pem>, for example
from mkcert with its CA trusted on the phone.
Usage: serve.py <dir> [port]"""
import base64
import fnmatch
import functools
import hashlib
import http.server
import os
import socket
import ssl
import struct
import sys
import threading

RELAY = "/__relay/"
ALLOW = ["*:443"] + [
    a.strip() for a in os.environ.get("KIOKU_RELAY_ALLOW", "").split(",") if a.strip()
]
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
SELFTEST = os.environ.get("KIOKU_SELFTEST")
TLS = os.environ.get("KIOKU_TLS")
SELFTEST_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test", "selftest.js")


def embedder_policy(user_agent: str) -> str:
    """credentialless: cross-origin scripts and images (add-ons' CDNs) load
    without opting in, as they do on the desktop. WebKit (Safari, every iOS
    browser) lacks it: the page would not be cross-origin isolated and
    Emscripten's threads fail (DataCloneError), so it gets require-corp and
    sw.js proxies cross-origin requests. Same test in cloudflare/worker.js
    and shell/sw.js."""
    webkit = "AppleWebKit" in user_agent and "Chrome/" not in user_agent
    return "require-corp" if webkit else "credentialless"


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", embedder_policy(self.headers.get("User-Agent", "")))
        self.send_header("Vary", "User-Agent")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        if self.path.startswith(RELAY) and self.headers.get("Upgrade", "").lower() == "websocket":
            self.relay(self.path[len(RELAY) :])
        elif self.path == "/":
            # like cloudflare/_redirects
            self.send_response(302)
            self.send_header("Location", "/app.html")
            self.end_headers()
        elif SELFTEST and self.path.split("?")[0] == "/app.html":
            with open(os.path.join(self.directory, "app.html"), "rb") as f:
                page = f.read()
            page = page.replace(b'<script src="kioku-web.js">', b'<script src="__selftest/selftest.js"></script>\n    <script src="kioku-web.js">')
            self.send_bytes(page, "text/html")
        elif SELFTEST and self.path.startswith("/__selftest/"):
            name = self.path[len("/__selftest/") :].split("?")[0]
            path = SELFTEST_JS if name == "selftest.js" else os.path.join(SELFTEST, os.path.basename(name))
            if not os.path.isfile(path):
                self.send_error(404)
                return
            with open(path, "rb") as f:
                self.send_bytes(f.read(), self.guess_type(path))
        else:
            super().do_GET()

    def do_POST(self) -> None:
        if not (SELFTEST and self.path == "/__selftest/log"):
            self.send_error(404)
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        with open(os.path.join(SELFTEST, "log.txt"), "ab") as f:
            f.write(body)
        self.send_bytes(b"", "text/plain")

    def send_bytes(self, data: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def relay(self, target: str) -> None:
        # WebSockets aren't bound by CORS: without this any website open in
        # the browser could use the relay
        scheme = "https" if TLS else "http"
        if self.headers.get("Origin") != f"{scheme}://{self.headers.get('Host')}":
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
server = http.server.ThreadingHTTPServer((os.environ.get("KIOKU_HOST", "127.0.0.1"), port), handler)
if TLS:
    cert, _, key = TLS.partition(":")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
server.serve_forever()
