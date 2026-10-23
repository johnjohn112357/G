#!/usr/bin/env python3
"""Small standalone OS Leisure map tile proxy and static web server."""
import os
import re
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", "8080"))
OS_MAPS_API_KEY = os.environ.get("OS_MAPS_API_KEY", "").strip()
TILE_RE = re.compile(r"^/api/tiles/Leisure/(\d{1,2})/(\d{1,7})/(\d{1,7})\.png$")


class Handler(BaseHTTPRequestHandler):
    server_version = "FootpathMap/1.0"

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            try:
                body = (ROOT / "index.html").read_bytes()
            except OSError:
                self.send_error(500, "Map page unavailable")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"ok")
            return

        match = TILE_RE.match(path)
        if match:
            z, x, y = map(int, match.groups())
            if z > 18 or x >= (1 << z) or y >= (1 << z):
                self.send_error(400, "Invalid tile coordinates")
                return
            if not OS_MAPS_API_KEY:
                self.send_error(503, "OS Maps API key is not configured")
                return
            url = (
                "https://api.os.uk/maps/raster/v1/zxy/"
                f"Leisure_3857/{z}/{x}/{y}.png"
                f"?key={OS_MAPS_API_KEY}"
            )
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "FootpathMap/1.0 (OS Maps tile proxy)"},
            )
            try:
                with urllib.request.urlopen(request, timeout=12) as upstream:
                    data = upstream.read()
                    content_type = upstream.headers.get("Content-Type", "image/png")
                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
            except urllib.error.HTTPError as exc:
                # Do not leak the key or upstream URL in the response.
                status = 502 if exc.code not in (429,) else 503
                self.send_error(status, "OS Maps tile request was rejected")
            except (urllib.error.URLError, TimeoutError, OSError):
                self.send_error(502, "OS Maps tile service is temporarily unavailable")
            return

        self.send_error(404, "Not found")

    def log_message(self, fmt, *args):
        # Keep normal request logs, but never log query strings or secrets.
        super().log_message(fmt, *args)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Footpath Map listening on port {PORT}", flush=True)
    server.serve_forever()
