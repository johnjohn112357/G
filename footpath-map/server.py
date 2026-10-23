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


def decode_polyline6(encoded):
    """Decode Valhalla's default six-decimal encoded route shape."""
    index = 0
    lat = lon = 0
    points = []
    while index < len(encoded):
        values = []
        for _ in range(2):
            result = shift = 0
            while True:
                if index >= len(encoded):
                    raise ValueError("Truncated route shape")
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1f) << shift
                shift += 5
                if byte < 0x20:
                    break
                if shift > 35:
                    raise ValueError("Invalid route shape")
            values.append(~(result >> 1) if result & 1 else result >> 1)
        lat += values[0]
        lon += values[1]
        points.append([lat / 1000000.0, lon / 1000000.0])
    return points

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

    def do_POST(self):
        if urlparse(self.path).path != "/api/route":
            self.send_error(404, "Not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 16384:
                self.send_error(413, "Invalid request size")
                return
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            self.send_error(400, "Invalid JSON")
            return
        locations = payload.get("locations") if isinstance(payload, dict) else None
        if not isinstance(locations, list) or len(locations) != 2:
            self.send_error(400, "Exactly two route locations are required")
            return
        checked = []
        for point in locations:
            if not isinstance(point, dict):
                self.send_error(400, "Invalid route location")
                return
            lat, lon = point.get("lat"), point.get("lon")
            if isinstance(lat, bool) or isinstance(lon, bool) or not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)) or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                self.send_error(400, "Invalid route coordinates")
                return
            checked.append({"lat": float(lat), "lon": float(lon)})
        request_body = json.dumps({"locations": checked, "costing": "pedestrian", "units": "kilometers"}).encode("utf-8")
        upstream_request = urllib.request.Request("https://valhalla1.openstreetmap.de/route", data=request_body, headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "FootpathMap/1.3", "X-Client-Id": "footpath-map.onrender.com"}, method="POST")
        try:
            with urllib.request.urlopen(upstream_request, timeout=25) as upstream:
                result = json.loads(upstream.read(4000000).decode("utf-8"))
            trip = result.get("trip", {})
            legs = trip.get("legs", [])
            if not legs:
                raise ValueError("No route legs returned")
            shape = legs[0].get("shape", "")
            if not isinstance(shape, str) or not shape:
                raise ValueError("Route geometry unavailable")
            route_coords = decode_polyline6(shape)
            if len(route_coords) < 2 or any(not (-90 <= p[0] <= 90 and -180 <= p[1] <= 180) for p in route_coords):
                raise ValueError("Invalid route geometry")
            length_km = trip.get("summary", {}).get("length")
            if not isinstance(length_km, (int, float)) or length_km < 0:
                length_km = legs[0].get("summary", {}).get("length", 0)
            body = json.dumps({"status": "ok", "coordinates": route_coords, "distance_m": round(float(length_km) * 1000, 1)}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except urllib.error.HTTPError as exc:
            self.send_error(429 if exc.code == 429 else 502, "Routing service rejected the request; try again later")
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
            self.send_error(502, "No pedestrian route returned; try different endpoints")
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
                reason = "OS Maps API key rejected (HTTP 401/403)" if exc.code in (401, 403) else ("OS Maps API rate limit reached" if exc.code == 429 else f"OS Maps tile request failed (HTTP {exc.code})")
                self.send_error(status, reason)
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
