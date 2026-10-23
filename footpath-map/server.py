#!/usr/bin/env python3
"""Small standalone OS Raster tile proxy and static web server."""
import json
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
TILE_RE = re.compile(r"^/api/tiles/(Leisure|Outdoor|Road|Light)/(\d{1,2})/(\d{1,7})/(\d{1,7})\.png$")


class Handler(BaseHTTPRequestHandler):
    server_version = "FootpathMap/1.2"

    def _send_page_headers(self, body_length):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(body_length))
        self.end_headers()

    def _send_health(self, head_only=False):
        body = json.dumps({
            "status": "ok",
            "os_maps_api_key_configured": bool(OS_MAPS_API_KEY),
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def do_HEAD(self):
        """Support platform health probes without downloading page or map tiles."""
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            try:
                body_length = (ROOT / "index.html").stat().st_size
            except OSError:
                self.send_error(500, "Map page unavailable")
                return
            self._send_page_headers(body_length)
            return
        if path == "/health":
            self._send_health(head_only=True)
            return
        self.send_error(404, "Not found")

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            try:
                body = (ROOT / "index.html").read_bytes()
            except OSError:
                self.send_error(500, "Map page unavailable")
                return
            self._send_page_headers(len(body))
            self.wfile.write(body)
            return

        if path == "/health":
            self._send_health()
            return

        match = TILE_RE.match(path)
        if match:
            style, z_text, x_text, y_text = match.groups()
            z, x, y = int(z_text), int(x_text), int(y_text)
            if z > 18 or x >= (1 << z) or y >= (1 << z):
                self.send_error(400, "Invalid tile coordinates")
                return
            if not OS_MAPS_API_KEY:
                self.send_error(503, "OS Maps API key is not configured")
                return
            url = (
                "https://api.os.uk/maps/raster/v1/zxy/"
                f"{style}_3857/{z}/{x}/{y}.png"
                f"?key={OS_MAPS_API_KEY}"
            )
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "FootpathMap/1.2 (OS Maps tile proxy)"},
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
                status = 503 if exc.code == 429 else 502
                self.send_error(status, "OS Maps tile request was rejected")
            except (urllib.error.URLError, TimeoutError, OSError):
                self.send_error(502, "OS Maps tile service is temporarily unavailable")
            return

        self.send_error(404, "Not found")

    def log_message(self, fmt, *args):
        # The handler's normal access log includes only the path, not query strings.
        super().log_message(fmt, *args)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Footpath Map listening on port {PORT}", flush=True)
    server.serve_forever()
