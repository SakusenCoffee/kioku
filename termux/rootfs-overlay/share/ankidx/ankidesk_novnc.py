"""Serves noVNC for the remote desktop (ankidesk_remote.py).

noVNC connects straight to x11vnc's port, which also takes WebSocket
connections. It only uses a port of its own choosing together with a host,
and the host is whichever address the browser reached this page by
(Tailscale, Wi-Fi, localhost through adb forward), so defaults.json is made
per request from the request's Host header. "/" opens vnc.html.

    python ankidesk_novnc.py WEB_PORT BIND_HOST NOVNC_DIR VNC_PORT
"""

from __future__ import annotations

import json
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


def host_of(header: str) -> str:
    """The host part of a Host header; an IPv6 address keeps its brackets."""
    header = header.strip()
    if header.startswith("["):
        return header[: header.find("]") + 1]
    return header.rsplit(":", 1)[0] if ":" in header else header


class Handler(SimpleHTTPRequestHandler):
    vnc_port = 5900

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        parts = urlsplit(self.path)
        path = parts.path
        if path in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/vnc.html" + (f"?{parts.query}" if parts.query else ""))
            self.end_headers()
            return
        if path == "/mandatory.json":
            # nothing forced; noVNC asks for it on every load
            self._json({})
            return
        if path == "/defaults.json":
            self._json({
                "host": host_of(self.headers.get("Host", "")) or "127.0.0.1",
                "port": self.vnc_port,
                "path": "",
                "autoconnect": True,
                "resize": "scale",
                "reconnect": True,
            })
            return
        super().do_GET()

    def _json(self, value: dict) -> None:
        body = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - http.server API
        pass


def serve(web_port: int, host: str, directory: str, vnc_port: int) -> None:
    Handler.vnc_port = vnc_port
    server = ThreadingHTTPServer((host, web_port), partial(Handler, directory=directory))
    server.serve_forever()


def main() -> None:
    web_port, host, directory, vnc_port = sys.argv[1:5]
    serve(int(web_port), host, directory, int(vnc_port))


if __name__ == "__main__":
    main()
