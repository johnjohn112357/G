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
    if path == "/api/calculate/resistor-divider":
        vin, r1, r2 = number(d,"input_voltage_v",0), number(d,"r1_ohm",0), number(d,"r2_ohm",0)
        if r1+r2 <= 0: raise ValueError("r1_ohm + r2_ohm must be greater than zero")
        return {"output_voltage_v":vin*r2/(r1+r2),"divider_current_a":vin/(r1+r2),"r1_power_w":(vin/(r1+r2))**2*r1,"r2_power_w":(vin/(r1+r2))**2*r2,"caveat":"Ideal unloaded divider; account for load current and resistor tolerances."}
    if path == "/api/calculate/led-resistor":
        supply, led, current_ma = number(d,"supply_voltage_v",0), number(d,"led_forward_voltage_v",0), number(d,"led_current_ma",0)
        if current_ma <= 0: raise ValueError("led_current_ma must be greater than zero")
        if supply <= led: raise ValueError("supply_voltage_v must exceed led_forward_voltage_v")
        current = current_ma/1000
        resistance = (supply-led)/current
        return {"minimum_ideal_resistance_ohm":resistance,"resistor_power_w":(supply-led)*current,"current_a":current,"caveat":"Choose a standard resistor at or above the calculated resistance and check LED and resistor ratings."}
    if path == "/api/calculate/solar-energy":
        panel_w, sun_hours, efficiency = number(d,"panel_power_w",0), number(d,"peak_sun_hours",0), number(d,"system_efficiency",0)
        if efficiency > 1: raise ValueError("system_efficiency must be between 0 and 1")
        return {"estimated_daily_energy_wh":panel_w*sun_hours*efficiency,"panel_power_w":panel_w,"peak_sun_hours":sun_hours,"system_efficiency":efficiency,"caveat":"Planning estimate only; seasonal irradiance, orientation, shading and system losses vary."}
    if path == "/api/calculate/thermal-expansion":
        length, alpha = number(d,"length_m",0), number(d,"alpha_per_c",0)
        delta_t = float(d["delta_temp_c"])
        if not math.isfinite(delta_t): raise ValueError("delta_temp_c must be finite")
        change = length*alpha*delta_t
        return {"length_change_m":change,"final_length_m":length+change,"delta_temp_c":delta_t,"model":"linear expansion: delta_L = L * alpha * delta_T"}
    if path == "/api/calculate/pressure":
        force, area = number(d,"force_n",0), number(d,"area_m2",0)
        if area <= 0: raise ValueError("area_m2 must be greater than zero")
        return {"pressure_pa":force/area,"pressure_kpa":force/area/1000}
    if path == "/api/calculate/density":
        mass, volume = number(d,"mass_kg",0), number(d,"volume_m3",0)
        if volume <= 0: raise ValueError("volume_m3 must be greater than zero")
        return {"density_kg_m3":mass/volume,"density_g_cm3":mass/volume/1000}
    if path == "/api/convert/unit":
        value = number(d,"value")
        category, source, target = d.get("category"), d.get("from_unit"), d.get("to_unit")
        tables = {"length":{"m":1.0,"mm":0.001,"cm":0.01,"km":1000.0,"in":0.0254,"ft":0.3048,"mi":1609.344},"speed":{"m/s":1.0,"km/h":1/3.6,"mph":0.44704,"ft/s":0.3048},"mass":{"kg":1.0,"g":0.001,"mg":0.000001,"lb":0.45359237,"oz":0.028349523125},"pressure":{"Pa":1.0,"kPa":1000.0,"bar":100000.0,"psi":6894.757293168},"energy":{"J":1.0,"kJ":1000.0,"Wh":3600.0,"kWh":3600000.0},"power":{"W":1.0,"kW":1000.0,"hp":745.699871582},"volume":{"m3":1.0,"L":0.001,"mL":0.000001,"gal_uk":0.00454609}}
        if category == "temperature":
            if source not in ("C","F","K") or target not in ("C","F","K"): raise ValueError("temperature units must be C, F, or K")
            celsius = value if source=="C" else (value-32)*5/9 if source=="F" else value-273.15
            result = celsius if target=="C" else celsius*9/5+32 if target=="F" else celsius+273.15
            return {"value":result,"from_unit":source,"to_unit":target}
        if category not in tables or source not in tables[category] or target not in tables[category]: raise ValueError("Unsupported category or unit; supported categories: length, speed, mass, pressure, energy, power, volume, temperature")
        return {"value":value*tables[category][source]/tables[category][target],"from_unit":source,"to_unit":target,"category":category}
    if path == "/api/calculate/gps-distance":
        lat1, lon1 = number(d,"lat1"), number(d,"lon1")
        lat2, lon2 = number(d,"lat2"), number(d,"lon2")
        if not (-90 <= lat1 <= 90 and -90 <= lat2 <= 90 and -180 <= lon1 <= 180 and -180 <= lon2 <= 180): raise ValueError("Latitude must be -90..90 and longitude -180..180")
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp, dl = math.radians(lat2-lat1), math.radians(lon2-lon1)
        a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
        distance = 6371008.8 * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0,1-a)))
        y = math.sin(dl)*math.cos(p2)
        x = math.cos(p1)*math.sin(p2)-math.sin(p1)*math.cos(p2)*math.cos(dl)
        bearing = (math.degrees(math.atan2(y,x))+360)%360
        return {"distance_m":distance,"distance_km":distance/1000,"initial_bearing_deg":bearing,"model":"great-circle distance using mean Earth radius 6371008.8 m"}
    if path == "/api/calculate/track-stats":
        coords = d.get("coordinates")
        if not isinstance(coords,list) or len(coords)<2 or len(coords)>10000: raise ValueError("coordinates must be a list of 2..10000 [longitude, latitude, optional elevation_m] points")
        parsed=[]
        for point in coords:
            if not isinstance(point,list) or len(point)<2 or len(point)>3: raise ValueError("Each point must contain longitude, latitude, and optional elevation")
            lon,lat=float(point[0]),float(point[1])
            if not (math.isfinite(lon) and math.isfinite(lat) and -180<=lon<=180 and -90<=lat<=90): raise ValueError("Coordinates outside valid longitude/latitude bounds")
            ele=float(point[2]) if len(point)==3 and point[2] is not None else None
            if ele is not None and not math.isfinite(ele): raise ValueError("Elevation must be finite")
            parsed.append((lon,lat,ele))
        distance=ascent=descent=0.0
        for a,b in zip(parsed,parsed[1:]):
            lon1,lat1,e1=a; lon2,lat2,e2=b
            p1,p2=math.radians(lat1),math.radians(lat2)
            dp,dl=math.radians(lat2-lat1),math.radians(lon2-lon1)
            h=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
            distance += 6371008.8*2*math.atan2(math.sqrt(h),math.sqrt(max(0.0,1-h)))
            if e1 is not None and e2 is not None:
                if e2>e1: ascent += e2-e1
                else: descent += e1-e2
        return {"point_count":len(parsed),"distance_m":distance,"distance_km":distance/1000,"ascent_m":ascent,"descent_m":descent,"elevation_note":"Ascent/descent includes only adjacent points where both elevations are supplied."}
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
        url = f"https://api.os.uk/maps/raster/v1/zxy/{style}_3857/{z}/{x}/{y}.png?key={OS_MAPS_API_KEY}"
        try:
            req = Request(url, headers={"User-Agent":"ResearchEngineeringToolkit/3.4"})
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
        except HTTPError:
            self.reply(502, {"error":"OS Maps rejected the tile request; verify the Data Hub key, enabled API and plan"})
        except (URLError, TimeoutError, OSError):
            self.reply(502, {"error":"OS Maps upstream request failed; check Data Hub access and service availability"})
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
