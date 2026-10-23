"""Research & Engineering Toolkit API. Python standard library only."""
import os, json, math, sqlite3, time, threading, hmac
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from pathlib import Path

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8765"))
API_KEY = os.getenv("API_KEY", "").strip()
DB_PATH = os.getenv("DB_PATH", str(Path(__file__).with_name("toolkit.sqlite3")))
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
    raise KeyError(path)

class Handler(BaseHTTPRequestHandler):
    server_version = "ResearchEngineeringToolkit/3.1"
    def reply(self, status, obj):
        raw=json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(raw))); self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Cache-Control","no-store"); self.send_header("Referrer-Policy","no-referrer")
        self.end_headers(); self.wfile.write(raw)
    def auth(self):
        if urlparse(self.path).path == "/health": return True
        if not API_KEY:
            self.reply(503,{"error":"API_KEY is not configured"}); return False
        h=self.headers.get("Authorization","")
        token=h[7:].strip() if h.lower().startswith("bearer ") else ""
        if not token or not hmac.compare_digest(token,API_KEY):
            self.reply(401,{"error":"Unauthorized"}); return False
        now=time.time(); ip=self.client_address[0]
        with hits_lock:
            recent=[t for t in hits.get(ip,[]) if now-t<60]
            if len(recent)>=RATE_LIMIT:
                self.reply(429,{"error":"Rate limit exceeded"}); return False
            recent.append(now); hits[ip]=recent
        return True
    def body(self):
        try: n=int(self.headers.get("Content-Length","0"))
        except ValueError: raise ValueError("Invalid Content-Length")
        if n<1 or n>MAX_BODY: raise ValueError("Request body must be 1..1000000 bytes")
        d=json.loads(self.rfile.read(n))
        if not isinstance(d,dict): raise ValueError("JSON body must be an object")
        return d
    def do_GET(self):
        if not self.auth(): return
        p=urlparse(self.path).path
        try:
            if p=="/health":
                with db() as c: c.execute("SELECT 1")
                return self.reply(200,{"status":"ok","version":"3.1","database":"connected"})
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
