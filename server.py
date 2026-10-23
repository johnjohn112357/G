"""Research & Engineering Toolkit API. Python standard library only."""
import os, json, math, sqlite3, time, threading, hmac
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from pathlib import Path

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8765"))
API_KEY = os.getenv("API_KEY", "").strip()
DB_PATH = os.getenv("DB_PATH", str(Path(__file__).with_name("toolkit.sqlite3")))
OS_MAPS_API_KEY = os.getenv("OS_MAPS_API_KEY", "").strip()
OS_STYLES = {"Leisure", "Outdoor", "Road", "Light"}
MAX_BODY = 1_000_000
RATE_LIMIT = max(1, int(os.getenv("RATE_LIMIT_PER_MINUTE", "60")))
hits, hits_lock = {}, threading.Lock()
db_lock = threading.Lock()

def db():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS evidence (
          id INTEGER PRIMARY KEY, claim TEXT NOT NULL, source_title TEXT NOT NULL,
          source_url TEXT NOT NULL, confidence TEXT NOT NULL, notes TEXT NOT NULL,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS networks (
          name TEXT PRIMARY KEY, geojson TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

def number(d, k, minimum=None):
    v = float(d[k])
    if not math.isfinite(v) or (minimum is not None and v < minimum):
        raise ValueError(k + " is outside the allowed range")
    return v

def parse_os_tile_path(path):
    parts = path.strip("/").split("/")
    if len(parts) != 7 or parts[:3] != ["api", "maps", "os"]:
        raise ValueError("Invalid OS tile path")
    style = parts[3]
    if style not in OS_STYLES:
        raise ValueError("Unsupported OS map style")
    try:
        z, x = int(parts[4]), int(parts[5])
        ypart = parts[6]
        if not ypart.endswith(".png"): raise ValueError()
        y = int(ypart[:-4])
    except (ValueError, IndexError):
        raise ValueError("Invalid tile coordinates")
    if z < 0 or z > 18 or x < 0 or y < 0 or x >= 2**z or y >= 2**z:
        raise ValueError("Tile coordinates outside allowed range")
    return style, z, x, y


def calculate(path, d):
    if path == "/api/calculate/battery-energy":
        v, ah = number(d,"voltage_v",0), number(d,"capacity_ah",0)
        return {"nominal_energy_wh": v*ah, "voltage_v":v, "capacity_ah":ah}
    if path == "/api/calculate/battery-sag":
        v, i, r = number(d,"open_circuit_voltage_v",0), number(d,"current_a",0), number(d,"internal_resistance_ohm",0)
        return {"estimated_loaded_voltage_v":v-i*r, "voltage_sag_v":i*r, "model":"V_loaded = V_open - I*R"}
    if path == "/api/calculate/wheel-speed":
        rpm, diameter = number(d,"rpm",0), number(d,"wheel_diameter_mm",0)
        return {"ideal_speed_kmh": rpm*math.pi*diameter*60/1_000_000, "rpm":rpm, "wheel_diameter_mm":diameter}
    if path == "/api/calculate/ohms-law":
        known = {k:float(v) for k,v in d.items() if k in ("voltage_v","current_a","resistance_ohm")}
        if len(known) < 2: raise ValueError("Provide any two of voltage_v, current_a, resistance_ohm")
        if "voltage_v" not in known: known["voltage_v"] = known["current_a"]*known["resistance_ohm"]
        if "current_a" not in known: known["current_a"] = known["voltage_v"]/known["resistance_ohm"]
        if "resistance_ohm" not in known: known["resistance_ohm"] = known["voltage_v"]/known["current_a"]
        return known
    if path == "/api/calculate/voltage-drop":
        i, r = number(d,"current_a",0), number(d,"resistance_ohm",0)
        return {"voltage_drop_v":i*r, "power_dissipation_w":i*i*r}
    if path == "/api/calculate/mechanical-power":
        torque, rpm = number(d,"torque_nm",0), number(d,"rpm",0)
        return {"power_w":torque*2*math.pi*rpm/60}
    if path == "/api/calculate/battery-runtime":
        capacity, current = number(d,"capacity_ah",0), number(d,"current_a",0)
        if current <= 0: raise ValueError("current_a must be greater than zero")
        return {"ideal_runtime_hours":capacity/current,"capacity_ah":capacity,"current_a":current,
                "caveat":"Ideal estimate; real runtime depends on usable capacity, load, temperature, ageing and BMS cut-off."}
    if path == "/api/calculate/kinetic-energy":
        mass, speed = number(d,"mass_kg",0), number(d,"speed_kmh",0)
        speed_ms = speed / 3.6
        return {"kinetic_energy_j":0.5*mass*speed_ms**2,"mass_kg":mass,"speed_kmh":speed}
    if path == "/api/calculate/torque-from-power":
        power, rpm = number(d,"power_w",0), number(d,"rpm",0)
        if rpm <= 0: raise ValueError("rpm must be greater than zero")
        return {"torque_nm":power/(2*math.pi*rpm/60),"power_w":power,"rpm":rpm}
    if path == "/api/calculate/gear-ratio":
        input_rpm, output_rpm = number(d,"input_rpm",0), number(d,"output_rpm",0)
        if output_rpm <= 0: raise ValueError("output_rpm must be greater than zero")
        return {"reduction_ratio":input_rpm/output_rpm,"input_rpm":input_rpm,"output_rpm":output_rpm}
    if path == "/api/calculate/wheel-circumference":
        diameter = number(d,"wheel_diameter_mm",0)
        return {"circumference_mm":math.pi*diameter,"circumference_m":math.pi*diameter/1000}
    raise KeyError(path)

MAPS_HTML = "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n<title>Research Toolkit — OS Maps</title>\n<link rel=\"stylesheet\" href=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css\">\n<style>\n:root{color-scheme:light dark}body{font:16px system-ui;margin:0}header{padding:12px 16px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}input,select,button{font:inherit;padding:8px;border-radius:6px}#map{height:calc(100dvh - 120px);min-height:360px}.note{padding:0 16px 10px;font-size:13px;opacity:.8}#status{font-size:13px}\n</style></head><body>\n<header><strong>OS Maps</strong>\n<label>Toolkit API key <input id=\"token\" type=\"password\" autocomplete=\"off\" placeholder=\"Bearer token\" size=\"18\"></label>\n<label>Style <select id=\"style\"><option>Leisure</option><option>Outdoor</option><option>Road</option><option>Light</option></select></label>\n<button id=\"load\">Load map</button><span id=\"status\">Enter your toolkit API key to load OS tiles.</span></header>\n<div class=\"note\">Map tiles are requested through the toolkit server; the OS Maps API key stays server-side. OS map data and attribution are subject to Ordnance Survey terms.</div>\n<div id=\"map\" aria-label=\"Interactive Ordnance Survey map\"></div>\n<script src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\"></script>\n<script>\nconst map=L.map('map').setView([52.0,-1.5],7);\nlet layer=null, activeUrls=new Set();\nfunction status(t){document.getElementById('status').textContent=t}\nfunction makeLayer(style,token){return L.gridLayer({tileSize:256,updateWhenIdle:true,keepBuffer:2}).on('tileerror',()=>status('Tile request failed. Check toolkit key, OS_MAPS_API_KEY, and OS Data Hub access.')).addTo(map);}\ndocument.getElementById('load').addEventListener('click',()=>{\n const token=document.getElementById('token').value.trim(),style=document.getElementById('style').value;\n if(!token){status('Enter the toolkit API key first.');return}\n if(layer){map.removeLayer(layer);layer=null}\n layer=L.gridLayer({tileSize:256,keepBuffer:2});\n layer.createTile=function(coords,done){\n  const tile=document.createElement('img');tile.alt='OS map tile';tile.setAttribute('role','presentation');\n  const url='/api/maps/os/'+encodeURIComponent(style)+'/'+coords.z+'/'+coords.x+'/'+coords.y+'.png';\n  fetch(url,{headers:{Authorization:'Bearer '+token}}).then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.blob()}).then(blob=>{\n   const objectUrl=URL.createObjectURL(blob);activeUrls.add(objectUrl);tile.onload=()=>{URL.revokeObjectURL(objectUrl);activeUrls.delete(objectUrl);done(null,tile)};tile.onerror=()=>{URL.revokeObjectURL(objectUrl);activeUrls.delete(objectUrl);done(new Error('image decode failed'),tile)};tile.src=objectUrl;\n  }).catch(err=>{status('Tile error: '+err.message+'. Check OS Maps API key configured on server.');done(err,tile)});\n  return tile;\n };\n layer.addTo(map);status('Loading OS '+style+' map…');\n});\n</script></body></html>"

class Handler(BaseHTTPRequestHandler):
    server_version = "ResearchEngineeringToolkit/3.3"
    def reply(self, status, obj):
        raw=json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(raw))); self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Cache-Control","no-store"); self.send_header("Referrer-Policy","no-referrer")
        self.end_headers(); self.wfile.write(raw)
    def auth(self):
        if urlparse(self.path).path in ("/health", "/maps", "/"): return True
        if not API_KEY:
            self.reply(503,{"error":"API_KEY is not configured"}); return False
        h=self.headers.get("Authorization","")
        token=h[7:].strip() if h.lower().startswith("bearer ") else ""
        if not token or not hmac.compare_digest(token,API_KEY):
            self.reply(401,{"error":"Unauthorized"}); return False
        now=time.time(); ip=self.client_address[0]
        route = urlparse(self.path).path
        bucket = ip + (":tiles" if route.startswith("/api/maps/os/") else ":api")
        limit = max(RATE_LIMIT, 600) if route.startswith("/api/maps/os/") else RATE_LIMIT
        with hits_lock:
            recent=[t for t in hits.get(bucket,[]) if now-t<60]
            if len(recent)>=limit:
                self.reply(429,{"error":"Rate limit exceeded"}); return False
            recent.append(now); hits[bucket]=recent
        return True
    def body(self):
        try: n=int(self.headers.get("Content-Length","0"))
        except ValueError: raise ValueError("Invalid Content-Length")
        if n<1 or n>MAX_BODY: raise ValueError("Request body must be 1..1000000 bytes")
        d=json.loads(self.rfile.read(n))
        if not isinstance(d,dict): raise ValueError("JSON body must be an object")
        return d
    def os_tile(self, path):
        try:
            style, z, x, y = parse_os_tile_path(path)
        except ValueError as e:
            self.reply(400, {"error":str(e)})
            return True
        if not OS_MAPS_API_KEY:
            self.reply(503, {"error":"OS_MAPS_API_KEY is not configured on the server"})
            return True
        style = parts[3]
        if style not in OS_STYLES:
            self.reply(400, {"error":"Unsupported OS map style"})
            return True
        try:
            z, x = int(parts[4]), int(parts[5])
            ypart = parts[6]
            if not ypart.endswith(".png"): raise ValueError()
            y = int(ypart[:-4])
            if z < 0 or z > 18 or x < 0 or y < 0 or x >= 2**z or y >= 2**z:
                raise ValueError()
        except (ValueError, IndexError):
            self.reply(400, {"error":"Invalid tile coordinates"})
            return True
        url = f"https://api.os.uk/maps/raster/v1/zxy/{style}_3857/{z}/{x}/{y}.png?key={OS_MAPS_API_KEY}"
        try:
            req = Request(url, headers={"User-Agent":"ResearchEngineeringToolkit/3.3"})
            with urlopen(req, timeout=10) as response:
                tile = response.read(2_000_000 + 1)
                if len(tile) > 2_000_000:
                    self.reply(502, {"error":"Upstream tile exceeded size limit"})
                    return True
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(tile)))
                self.send_header("Cache-Control", "private, max-age=300")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(tile)
        except (HTTPError, URLError, TimeoutError, OSError):
            self.reply(502, {"error":"OS Maps upstream request failed; check OS Data Hub key, plan and service availability"})
        return True

    def do_HEAD(self):
        p = urlparse(self.path).path
        if p in ("/", "/health", "/maps"):
            self.send_response(302 if p == "/" else 200)
            if p == "/": self.send_header("Location", "/maps")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        if not self.auth(): return
        p=urlparse(self.path).path
        if p == "/":
            self.send_response(302)
            self.send_header("Location", "/maps")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if p == "/maps":
            raw = MAPS_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(raw)
            return
        if p.startswith("/api/maps/os/") and self.os_tile(p): return
        try:
            if p=="/health":
                with db() as c: c.execute("SELECT 1")
                return self.reply(200,{"status":"ok","version":"3.3","database":"connected"})
            if p=="/api/evidence":
                with db() as c: rows=c.execute("SELECT * FROM evidence ORDER BY id DESC LIMIT 500").fetchall()
                return self.reply(200,{"items":[dict(x) for x in rows]})
            if p=="/api/networks":
                with db() as c: rows=c.execute("SELECT name,created_at FROM networks ORDER BY name").fetchall()
                return self.reply(200,{"items":[dict(x) for x in rows]})
            return self.reply(404,{"error":"Not found"})
        except Exception:
            return self.reply(500,{"error":"Internal server error"})
    def do_POST(self):
        if not self.auth(): return
        p=urlparse(self.path).path
        try:
            d=self.body()
            if p.startswith("/api/calculate/"):
                return self.reply(200,calculate(p,d))
            if p=="/api/evidence":
                for k in ("claim","source_title","source_url"):
                    if not isinstance(d.get(k),str) or not d[k].strip(): raise ValueError(k+" is required")
                confidence=d.get("confidence","medium")
                if confidence not in ("low","medium","high"): raise ValueError("confidence must be low, medium, or high")
                with db_lock, db() as c:
                    cur=c.execute("INSERT INTO evidence(claim,source_title,source_url,confidence,notes) VALUES(?,?,?,?,?)",
                      (d["claim"],d["source_title"],d["source_url"],confidence,str(d.get("notes",""))))
                    return self.reply(201,{"id":cur.lastrowid})
            if p=="/api/networks":
                name=d.get("name"); geo=d.get("geojson")
                if not isinstance(name,str) or not name.strip() or not isinstance(geo,dict): raise ValueError("name and GeoJSON object are required")
                if geo.get("type")!="FeatureCollection" or not isinstance(geo.get("features"),list): raise ValueError("GeoJSON must be a FeatureCollection")
                with db_lock, db() as c:
                    c.execute("INSERT OR REPLACE INTO networks(name,geojson) VALUES(?,?)",(name, json.dumps(geo)))
                return self.reply(201,{"saved":name,"feature_count":len(geo["features"])})
            return self.reply(404,{"error":"Not found"})
        except (ValueError,KeyError,TypeError,ZeroDivisionError,json.JSONDecodeError) as e:
            return self.reply(400,{"error":str(e)})
        except Exception:
            return self.reply(500,{"error":"Internal server error"})
    def log_message(self, fmt, *args):
        super().log_message(fmt,*args)

if __name__=="__main__":
    init_db()
    if HOST not in ("127.0.0.1","localhost") and not API_KEY:
        raise SystemExit("Refusing non-local bind without API_KEY")
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
