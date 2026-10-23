#!/usr/bin/env python3
"""Woods Route Planner — woodland-focused map and pedestrian route planner."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "10000"))
OVERPASS = "https://overpass-api.de/api/interpreter"
VALHALLA = "https://valhalla1.openstreetmap.de/route"

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Woods Route Planner</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
:root{color-scheme:light;--green:#214d35;--pale:#edf3e9;--ink:#17251b}
*{box-sizing:border-box}body{margin:0;font:16px system-ui,-apple-system,sans-serif;color:var(--ink);background:#f8faf6}
header{background:var(--green);color:white;padding:15px 18px}h1{font-size:1.25rem;margin:0}header p{margin:4px 0 0;font-size:.9rem;opacity:.9}
main{display:grid;grid-template-columns:minmax(260px,340px) 1fr;min-height:calc(100vh - 78px)}
aside{padding:16px;background:white;border-right:1px solid #d8e0d5;overflow:auto}
label{display:block;font-weight:650;margin:12px 0 5px}input,select,button{font:inherit;width:100%;padding:11px;border:1px solid #bbc8b9;border-radius:9px;background:white;color:var(--ink)}
button{background:var(--green);color:white;font-weight:700;border:0;margin-top:10px;cursor:pointer}button.secondary{background:var(--pale);color:var(--green);border:1px solid #c9d7c7}
#map{height:calc(100vh - 78px);min-height:480px;background:#f4f5ef}
.note{font-size:.86rem;color:#4b5d4d;line-height:1.45}.status{padding:10px;border-radius:8px;background:var(--pale);margin-top:12px;font-size:.9rem;white-space:pre-wrap}
.legend{display:flex;gap:10px;align-items:center;font-size:.85rem;margin-top:12px}.swatch{width:15px;height:15px;border-radius:4px;background:#6f9c62;border:1px solid #456e3b}
@media(max-width:760px){main{grid-template-columns:1fr;grid-template-rows:auto 60vh}aside{order:2;border-right:0;border-top:1px solid #d8e0d5}#map{height:60vh;min-height:360px;order:1}header{padding:13px 15px}}
</style></head><body>
<header><h1>🌲 Woods Route Planner</h1><p>Find woodland areas, see mapped trails, and plan a walking route.</p></header>
<main><aside>
<p class="note">Woodland-first map: forest and wood areas plus mapped paths. Tap the map to set your start and finish points, or use your location.</p>
<label for="search">Find a place or woodland</label><input id="search" placeholder="e.g. Ashridge Estate, Hertfordshire">
<button id="find" class="secondary">Find place</button>
<label>Route mode</label><select id="mode"><option value="pedestrian">Walking</option></select>
<button id="locate" class="secondary">Use my location as start</button>
<button id="route">Plan route</button><button id="clear" class="secondary">Clear route and pins</button>
<div class="legend"><span class="swatch"></span> Mapped woodland</div>
<div id="status" class="status">Loading woodland data…</div>
<p class="note">Data from OpenStreetMap contributors. Trail routing follows mapped pedestrian routes and may leave woodland where mapped paths require it. Map data does not prove public access or legal right-of-way; check local signs and access restrictions.</p>
</aside><div id="map"></div></main>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const map=L.map('map').setView([51.815,-0.42],12);
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png',{attribution:'&copy; OpenStreetMap contributors &copy; CARTO',maxZoom:19}).addTo(map);
const woods=L.geoJSON(null,{style:{color:'#416d3c',weight:1.5,fillColor:'#78a967',fillOpacity:.55},onEachFeature:(f,l)=>{const n=f.properties?.name||f.properties?.type||'Woodland';l.bindTooltip(n)}}).addTo(map);
const trails=L.geoJSON(null,{style:{color:'#8b6b42',weight:2,opacity:.9},filter:f=>f.geometry?.type==='LineString'}).addTo(map);
let start=null,end=null,startMarker=null,endMarker=null,routeLine=null;
const status=t=>document.getElementById('status').textContent=t;
function setPoint(latlng){if(!start){start=latlng; if(startMarker)map.removeLayer(startMarker);startMarker=L.marker(latlng,{draggable:true}).addTo(map).bindPopup('Start').openPopup();startMarker.on('dragend',e=>start=e.target.getLatLng());status('Start set. Tap the map again to set the destination.');}
else{end=latlng;if(endMarker)map.removeLayer(endMarker);endMarker=L.marker(latlng,{draggable:true}).addTo(map).bindPopup('Destination');endMarker.on('dragend',e=>end=e.target.getLatLng());status('Start and destination set. Tap Plan route.');}}
map.on('click',e=>setPoint(e.latlng));
async function loadData(){const b=map.getBounds();const box=[b.getSouth(),b.getWest(),b.getNorth(),b.getEast()].join(',');status('Loading woods and mapped trails for this map view…');try{const r=await fetch('/api/woods?bbox='+encodeURIComponent(box));const d=await r.json();if(!r.ok)throw Error(d.error||'Woodland query failed');woods.clearLayers();trails.clearLayers();woods.addData(d.woods);trails.addData(d.trails);status('Loaded '+d.woodland_count+' woodland features and '+d.trail_count+' mapped trail segments in this view.');}catch(e){status('Could not load woodland data: '+e.message+'. Try again in a moment.');}}
let moveTimer;map.on('moveend',()=>{clearTimeout(moveTimer);moveTimer=setTimeout(loadData,400)});loadData();
document.getElementById('locate').onclick=()=>{if(!navigator.geolocation){status('Location is not supported by this browser.');return}status('Getting your location…');navigator.geolocation.getCurrentPosition(p=>{const ll=L.latLng(p.coords.latitude,p.coords.longitude);start=ll;if(startMarker)map.removeLayer(startMarker);startMarker=L.marker(ll,{draggable:true}).addTo(map).bindPopup('Start').openPopup();startMarker.on('dragend',e=>start=e.target.getLatLng());map.setView(ll,14);status('Your location is set as the start. Tap the map to set the destination.');},e=>status('Could not get location: '+e.message),{enableHighAccuracy:true,timeout:12000})};
document.getElementById('route').onclick=async()=>{if(!start||!end){status('Set a start and destination first: tap the map twice, or use your location then tap a destination.');return}status('Calculating walking route…');try{const r=await fetch('/api/route',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({start:{lat:start.lat,lng:start.lng},end:{lat:end.lat,lng:end.lng}})});const d=await r.json();if(!r.ok)throw Error(d.error||'Routing failed');if(routeLine)map.removeLayer(routeLine);routeLine=L.geoJSON(d.geometry,{style:{color:'#2468b4',weight:5,opacity:.9}}).addTo(map);map.fitBounds(routeLine.getBounds(),{padding:[25,25]});status('Route: '+(d.distance_km.toFixed(2))+' km · approx. '+Math.round(d.duration_min)+' min walking. '+d.note);}catch(e){status('Route failed: '+e.message)}};
document.getElementById('clear').onclick=()=>{start=end=null;[startMarker,endMarker,routeLine].forEach(x=>{if(x)map.removeLayer(x)});startMarker=endMarker=routeLine=null;status('Cleared. Tap the map to choose a start and destination.')};
document.getElementById('find').onclick=async()=>{const q=document.getElementById('search').value.trim();if(!q)return;status('Searching for place…');try{const r=await fetch('/api/search?q='+encodeURIComponent(q));const d=await r.json();if(!r.ok)throw Error(d.error||'Search failed');map.setView([d.lat,d.lon],14);status('Showing '+d.name+'. Woodland data will load for this area.');}catch(e){status('Search failed: '+e.message)}};
</script></body></html>"""

def fetch_json(url, data=None, headers=None, timeout=30):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))

def osm_geometry(el):
    tags = el.get("tags", {})
    if el["type"] == "node":
        coords = [el["lon"], el["lat"]]
        return {"type":"Point","coordinates":coords}
    if el["type"] == "way":
        coords = [[n["lon"],n["lat"]] for n in el.get("geometry",[]) if "lon" in n and "lat" in n]
        if len(coords) < 2:
            return None
        if tags.get("natural") == "wood" or tags.get("landuse") == "forest":
            if len(coords) >= 4 and coords[0] == coords[-1]:
                return {"type":"Polygon","coordinates":[coords]}
        return {"type":"LineString","coordinates":coords}
    return None

def feature(el):
    geom = osm_geometry(el)
    if not geom:
        return None
    return {"type":"Feature","geometry":geom,"properties":{"name":el.get("tags",{}).get("name"),"type":el.get("tags",{}).get("natural") or el.get("tags",{}).get("landuse") or "woodland"}} 

class Handler(BaseHTTPRequestHandler):
    def send_json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin","*"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        parsed=urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            b=HTML.encode(); self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b); return
        if parsed.path == "/health":
            return self.send_json(200,{"status":"ok","service":"woods-route-planner"})
        q=urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/api/search":
            term=q.get("q",[""])[0].strip()
            if not term: return self.send_json(400,{"error":"Enter a place name."})
            try:
                url="https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q="+urllib.parse.quote(term)
                data=fetch_json(url,headers={"User-Agent":"WoodsRoutePlanner/1.0 contact: site operator"})
                if not data: return self.send_json(404,{"error":"No matching place found."})
                return self.send_json(200,{"lat":float(data[0]["lat"]),"lon":float(data[0]["lon"]),"name":data[0]["display_name"]})
            except Exception as e: return self.send_json(502,{"error":"Place search temporarily unavailable."})
        if parsed.path == "/api/woods":
            bbox=q.get("bbox",[""])[0]
            try:
                south,west,north,east=map(float,bbox.split(","))
                if north-south>0.20 or east-west>0.20: return self.send_json(400,{"error":"Zoom in closer to load woodland data."})
                query=f"""[out:json][timeout:25];(way[landuse=forest]({south},{west},{north},{east});way[natural=wood]({south},{west},{north},{east});way[highway~"path|footway|track|bridleway|steps"]({south},{west},{north},{east}););out geom;"""
                raw=fetch_json(OVERPASS,data=query.encode(),headers={"Content-Type":"application/x-www-form-urlencoded","User-Agent":"WoodsRoutePlanner/1.0"},timeout=35)
                w=[]; t=[]
                for el in raw.get("elements",[]):
                    f=feature(el)
                    if not f: continue
                    if f["geometry"]["type"]=="Polygon": w.append(f)
                    elif f["geometry"]["type"]=="LineString": t.append(f)
                return self.send_json(200,{"woods":{"type":"FeatureCollection","features":w},"trails":{"type":"FeatureCollection","features":t},"woodland_count":len(w),"trail_count":len(t)})
            except Exception as e: return self.send_json(502,{"error":"OpenStreetMap woodland service is busy or unavailable."})
        return self.send_json(404,{"error":"Not found"})
    def do_POST(self):
        if urllib.parse.urlparse(self.path).path != "/api/route": return self.send_json(404,{"error":"Not found"})
        try:
            n=int(self.headers.get("Content-Length","0")); body=json.loads(self.rfile.read(n))
            a=body["start"]; b=body["end"]
            payload={"locations":[{"lat":float(a["lat"]),"lon":float(a["lng"])},{"lat":float(b["lat"]),"lon":float(b["lng"])}],"costing":"pedestrian","units":"kilometers","directions_options":{"units":"kilometers"}}
            req=urllib.request.Request(VALHALLA,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json","User-Agent":"WoodsRoutePlanner/1.0","X-Client-Id":"woods-route-planner"},method="POST")
            with urllib.request.urlopen(req,timeout=35) as response: data=json.loads(response.read().decode())
            trip=data.get("trip",{})
            if trip.get("status",0)!=0: return self.send_json(502,{"error":trip.get("status_message","No walking route found.")})
            shape=data["trip"]["legs"][0]["shape"]
            # Valhalla shape is encoded polyline6; decode into GeoJSON lon/lat coordinates.
            coords=[]; index=0; lat=lon=0
            while index<len(shape):
                vals=[]
                for _ in range(2):
                    result=shift=0
                    while True:
                        bval=ord(shape[index])-63; index+=1; result|=(bval&0x1f)<<shift; shift+=5
                        if bval<0x20: break
                    vals.append(~(result>>1) if result&1 else result>>1)
                lat+=vals[0]; lon+=vals[1]; coords.append([lon/1e6,lat/1e6])
            summary=trip["summary"]
            return self.send_json(200,{"geometry":{"type":"LineString","coordinates":coords},"distance_km":float(summary.get("length",0)),"duration_min":float(summary.get("time",0))/60,"note":"This is a pedestrian route, not a guarantee that the entire route stays inside woodland."})
        except urllib.error.HTTPError as e: return self.send_json(502,{"error":f"Routing provider returned HTTP {e.code}."})
        except Exception as e: return self.send_json(502,{"error":"Could not calculate a route. Check the points and try again."})
    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

if __name__ == "__main__":
    print(f"Woods Route Planner listening on {PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
