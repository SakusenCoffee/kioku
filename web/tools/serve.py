"""Serve a directory with the headers SharedArrayBuffer (pthreads) needs.
Usage: serve.py <dir> [port]"""
import functools
import http.server
import sys


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


port = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
handler = functools.partial(Handler, directory=sys.argv[1])
http.server.ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()
