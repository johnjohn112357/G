#!/usr/bin/env python3
"""Woods Route Planner — woodland-focused map and pedestrian route planner."""
import json, os, urllib.error, urllib.parse, urllib.request, re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
PORT=int(os.environ.get("PORT","10000"))
OS_MAPS_API_KEY=os.environ.get("OS_MAPS_API_KEY","").strip()  # retained for compatibility; basemap now uses OpenStreetMap
OVERPASS="https://overpass-api.de/api/interpreter"
VALHALLA="https://valhalla1.openstreetmap.de/route"
TILE_RE=re.compile(r"^/api/tiles/(Leisure|Outdoor|Road|Light)/(\d{1,2})/(\d{1,7})/(\d{1,7})\.png$")

HTML=r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Woods Route Planner</title><link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"><style>
:root{color-scheme:light;--green:#214d35;--pale:#edf3e9;--ink:#17251b}*{box-sizing:border-box}body{margin:0;font:16px system-ui,sans-serif;color:var(--ink);background:#f8faf6}header{background:var(--green);color:white;padding:15px 18px}h1{font-size:1.25rem;margin:0}header p{margin:4px 0 0;font-size:.9rem;opacity:.9}main{display:grid;grid-template-columns:minmax(260px,340px) 1fr;min-height:calc(100vh - 78px)}aside{padding:16px;background:white;border-right:1px solid #d8e0d5;overflow:auto}label{display:block;font-weight:650;margin:12px 0 5px}input,select,button{font:inherit;width:100%;padding:11px;border:1px solid #bbc8b9;border-radius:9px;background:white;color:var(--ink)}button{background:var(--green);color:white;font-weight:700;border:0;margin-top:10px;cursor:pointer}button.secondary{background:var(--pale);color:var(--green);border:1px solid #c9d7c7}#map{height:calc(100vh - 78px);min-height:480px;background:#f4f5ef}.note{font-size:.86rem;color:#4b5d4d;line-height:1.45}.status{padding:10px;border-radius:8px;background:var(--pale);margin-top:12px;font-size:.9rem;white-space:pre-wrap}.legend{display:flex;gap:10px;align-items:center;font-size:.85rem;margin-top:12px}.swatch{width:15px;height:15px;border-radius:4px;background:#6f9c62;border:1px solid #456e3b}@media(max-width:760px){main{grid-template-columns:1fr;grid-template-rows:60vh auto}#map{height:60vh;min-height:360px}aside{border-right:0;border-top:1px solid #d8e0d5}header{padding:13px 15px}}
</style></head><body><header><h1>🌲 Woods Route Planner</h1><p>Woodland map, trail-priority routes and live phone GPS.</p></header><main><aside>
<p class="note">Tap the map to set start and destination. Turn on live GPS to show your current position as you move.</p>
<label for="search">Find a place or woodland</label><input id="search" placeholder="e.g. Ashridge Estate, Hertfordshire"><button id="find" class="secondary">Find place</button>
<p class="note">Map background: OpenStreetMap</p>
<button id="gps">Show my location (live GPS)</button><button id="stopgps" class="secondary">Stop live GPS</button>
<label for="radius">Search radius around my location</label><select id="radius"><option value="2">2 km</option><option value="5" selected>5 km</option><option value="10">10 km</option><option value="20">20 km</option><option value="30">30 km</option><option value="50">50 km</option></select><button id="nearwoods">Show woods within radius</button>
<label>Route preference</label><select id="mode"><option value="trails">Prefer trails and tracks; minimise road use</option></select>
<button id="route">Plan route</button><button id="clear" class="secondary">Clear route and pins</button><div class="legend"><span class="swatch"></span> Mapped woodland</div><div id="status" class="status">Loading woodland data…</div>
<p class="note">GPS requires permission in your phone browser and a secure HTTPS connection. Your position is shown on this map while live tracking is enabled. The map background uses OpenStreetMap tiles directly; woodland and path data also comes from OpenStreetMap. Routing prefers trails but cannot guarantee woodland-only travel or exclude all roads. Check local access signs; mapped paths do not prove legal right-of-way.</p>
</aside><div id="map"></div></main><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
const map=L.map('map').setView([51.815,-0.42],12);
const osmTiles=L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'&copy; OpenStreetMap contributors',maxZoom:19});
osmTiles.on('tileerror',()=>status('OpenStreetMap tiles could not load. Check your connection or try refreshing.'));
osmTiles.addTo(map);
const woods=L.geoJSON(null,{style:{color:'#416d3c',weight:1.5,fillColor:'#78a967',fillOpacity:.45},onEachFeature:(f,l)=>l.bindTooltip(f.properties?.name||'Woodland')}).addTo(map);
const trails=L.geoJSON(null,{style:{color:'#8b6b42',weight:2,opacity:.9}}).addTo(map);
let start=null,end=null,startMarker=null,endMarker=null,routeLine=null,gpsWatch=null,positionMarker=null,accuracyCircle=null,nearbyWoodsLayer=null,nearbyCircle=null,currentGPS=null;
const status=t=>document.getElementById('status').textContent=t;
function marker(ll,label){return L.marker(ll,{draggable:true}).addTo(map).bindPopup(label)}
function setPoint(ll){if(!start){start=ll;if(startMarker)map.removeLayer(startMarker);startMarker=marker(ll,'Start');startMarker.on('dragend',e=>start=e.target.getLatLng());status('Start set. Tap the map to set destination.')}else{end=ll;if(endMarker)map.removeLayer(endMarker);endMarker=marker(ll,'Destination');endMarker.on('dragend',e=>end=e.target.getLatLng());status('Start and destination set. Tap Plan route.')}}
map.on('click',e=>setPoint(e.latlng));
async function loadData(){const b=map.getBounds(),box=[b.getSouth(),b.getWest(),b.getNorth(),b.getEast()].join(',');try{const r=await fetch('/api/woods?bbox='+encodeURIComponent(box)),d=await r.json();if(!r.ok)throw Error(d.error||'Woodland query failed');woods.clearLayers();trails.clearLayers();woods.addData(d.woods);trails.addData(d.trails);status('Loaded '+d.woodland_count+' woodland areas and '+d.trail_count+' mapped trail segments.')}catch(e){status('Woodland data unavailable: '+e.message)}}
let moveTimer;map.on('moveend',()=>{clearTimeout(moveTimer);moveTimer=setTimeout(loadData,500)});loadData();
function gpsError(e){status('GPS unavailable: '+({1:'Location permission denied. Allow location access for this site in your browser settings.',2:'Phone could not determine your location; check GPS and signal.',3:'GPS request timed out; try again outdoors.'}[e.code]||e.message))}
document.getElementById('gps').onclick=()=>{if(!navigator.geolocation){status('This browser does not support GPS location.');return}if(gpsWatch!==null)return;status('Requesting location permission…');gpsWatch=navigator.geolocation.watchPosition(p=>{const ll=L.latLng(p.coords.latitude,p.coords.longitude);currentGPS=ll;if(!positionMarker){positionMarker=L.circleMarker(ll,{radius:9,color:'#fff',weight:3,fillColor:'#1479ee',fillOpacity:1}).addTo(map).bindPopup('Your live GPS position');map.setView(ll,15)}else positionMarker.setLatLng(ll);if(accuracyCircle)map.removeLayer(accuracyCircle);accuracyCircle=L.circle(ll,{radius:p.coords.accuracy,color:'#1479ee',weight:1,fillOpacity:.08}).addTo(map);start=ll;if(startMarker){startMarker.setLatLng(ll)}else{startMarker=marker(ll,'Route start (GPS)');startMarker.on('dragend',e=>start=e.target.getLatLng())}status('GPS active. Accuracy about '+Math.round(p.coords.accuracy)+' m. Your blue dot updates as you move; location is also set as route start.')},gpsError,{enableHighAccuracy:true,maximumAge:3000,timeout:15000})};
document.getElementById('stopgps').onclick=()=>{if(gpsWatch!==null)navigator.geolocation.clearWatch(gpsWatch);gpsWatch=null;status('Live GPS stopped. Last position remains on the map.')};
document.getElementById('route').onclick=async()=>{if(!start||!end){status('Set start and destination first. Use live GPS or tap the map twice.');return}status('Calculating trail-priority walking route…');try{const r=await fetch('/api/route',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({start:{lat:start.lat,lng:start.lng},end:{lat:end.lat,lng:end.lng}})}),d=await r.json();if(!r.ok)throw Error(d.error||'Routing failed');if(routeLine)map.removeLayer(routeLine);routeLine=L.geoJSON(d.geometry,{style:{color:'#2468b4',weight:5,opacity:.9}}).addTo(map);map.fitBounds(routeLine.getBounds(),{padding:[25,25]});status('Route: '+d.distance_km.toFixed(2)+' km · approx. '+Math.round(d.duration_min)+' min. '+d.note)}catch(e){status('Route failed: '+e.message)}};
document.getElementById('clear').onclick=()=>{start=end=null;[startMarker,endMarker,routeLine].forEach(x=>{if(x)map.removeLayer(x)});startMarker=endMarker=routeLine=null;status('Route pins cleared. Live GPS marker remains if active.')};
document.getElementById('nearwoods').onclick=async()=>{const center=currentGPS||start;if(!center){status('First tap Show my location (live GPS) and allow location access.');return}const km=Number(document.getElementById('radius').value);status('Searching for mapped woods within '+km+' km…');try{const r=await fetch('/api/nearby-woods?lat='+center.lat+'&lon='+center.lng+'&radius='+km);const d=await r.json();if(!r.ok)throw Error(d.error||'Woodland search failed');if(nearbyWoodsLayer)map.removeLayer(nearbyWoodsLayer);if(nearbyCircle)map.removeLayer(nearbyCircle);nearbyWoodsLayer=L.geoJSON(d.woods,{style:{color:'#245b2a',weight:2,fillColor:'#79b96b',fillOpacity:.5},onEachFeature:(f,l)=>{const p=f.properties||{};l.bindPopup('<b>'+(p.name||'Unnamed woodland')+'</b><br>'+((p.distance_km??'?')+' km from your location')+'<br>'+(p.kind||'Woodland'));}}).addTo(map);nearbyCircle=L.circle(center,{radius:km*1000,color:'#386f9b',weight:1,fillOpacity:.03}).addTo(map);if(d.woods.features.length){const bounds=nearbyWoodsLayer.getBounds();bounds.extend(center);map.fitBounds(bounds,{padding:[20,20]});status('Found '+d.count+' mapped woodland areas within '+km+' km. Tap a green area for details.')}else{map.setView(center,Math.max(10,15-Math.round(Math.log2(km))));status('No mapped woodland polygons found within '+km+' km. Try a larger radius or another map area.')}}catch(e){status('Nearby woods search failed: '+e.message)}};
document.getElementById('find').onclick=async()=>{const q=document.getElementById('search').value.trim();if(!q)return;status('Searching…');try{const r=await fetch('/api/search?q='+encodeURIComponent(q)),d=await r.json();if(!r.ok)throw Error(d.error||'Search failed');map.setView([d.lat,d.lon],14);status('Showing '+d.name)}catch(e){status('Search failed: '+e.message)}};
</script></body></html>"""

def fetch_json(url,data=None,headers=None,timeout=30):
    req=urllib.request.Request(url,data=data,headers=headers or {},method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.loads(r.read().decode())
def osm_geometry(el):
    tags=el.get("tags",{})
    if el["type"]=="way":
        coords=[[n["lon"],n["lat"]] for n in el.get("geometry",[]) if "lon" in n and "lat" in n]
        if len(coords)<2:return None
        if (tags.get("natural")=="wood" or tags.get("landuse")=="forest") and len(coords)>=4 and coords[0]==coords[-1]:return {"type":"Polygon","coordinates":[coords]}
        return {"type":"LineString","coordinates":coords}
    return None
def feature(el):
    geom=osm_geometry(el)
    if not geom:return None
    return {"type":"Feature","geometry":geom,"properties":{"name":el.get("tags",{}).get("name"),"type":el.get("tags",{}).get("natural") or el.get("tags",{}).get("landuse") or "woodland"}}
class Handler(BaseHTTPRequestHandler):
    def send_json(self,code,obj):
        body=json.dumps(obj).encode();self.send_response(code);self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Cache-Control","no-store");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        path=urllib.parse.urlparse(self.path).path
        if path=="/":
            b=HTML.encode();self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b);return
        if path=="/health":return self.send_json(200,{"status":"ok","os_maps_api_key_configured":bool(OS_MAPS_API_KEY)})
        m=TILE_RE.match(path)
        if m:
            style,zs,xs,ys=m.groups();z,x,y=map(int,(zs,xs,ys))
            if z>18 or x>=(1<<z) or y>=(1<<z):return self.send_json(400,{"error":"Invalid tile coordinates"})
            if not OS_MAPS_API_KEY:return self.send_json(503,{"error":"OS Maps API key is not configured"})
            url=f"https://api.os.uk/maps/raster/v1/zxy/{style}_3857/{z}/{x}/{y}.png?key={urllib.parse.quote(OS_MAPS_API_KEY)}"
            try:
                req=urllib.request.Request(url,headers={"User-Agent":"WoodsRoutePlanner/1.0"})
                with urllib.request.urlopen(req,timeout=15) as up:data=up.read()
                self.send_response(200);self.send_header("Content-Type","image/png");self.send_header("Cache-Control","public, max-age=86400");self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data)
            except urllib.error.HTTPError as e:self.send_json(502,{"error":f"OS Maps tile request failed (HTTP {e.code})"})
            except Exception:self.send_json(502,{"error":"OS Maps tile service unavailable"})
            return
        q=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if path=="/api/search":
            term=q.get("q",[""])[0].strip()
            if not term:return self.send_json(400,{"error":"Enter a place name"})
            try:
                data=fetch_json("https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q="+urllib.parse.quote(term),headers={"User-Agent":"WoodsRoutePlanner/1.0"})
                if not data:return self.send_json(404,{"error":"No matching place found"})
                return self.send_json(200,{"lat":float(data[0]["lat"]),"lon":float(data[0]["lon"]),"name":data[0]["display_name"]})
            except Exception:return self.send_json(502,{"error":"Place search temporarily unavailable"})
        if path=="/api/nearby-woods":
            try:
                lat=float(q.get("lat",[""])[0]);lon=float(q.get("lon",[""])[0]);radius=float(q.get("radius",["5"])[0])
                if not (-90<=lat<=90 and -180<=lon<=180) or not (1<=radius<=50):return self.send_json(400,{"error":"Invalid location or radius (1–50 km)."})
                # Convert radius to a conservative bounding box, then filter candidates by haversine distance.
                dlat=radius/111.0;dlon=radius/(111.0*max(0.15,abs(__import__("math").cos(__import__("math").radians(lat)))))
                s,w,n,e=lat-dlat,lon-dlon,lat+dlat,lon+dlon
                query=f"""[out:json][timeout:40];(way[landuse=forest]({s},{w},{n},{e});way[natural=wood]({s},{w},{n},{e});relation[landuse=forest]({s},{w},{n},{e});relation[natural=wood]({s},{w},{n},{e}););out center geom;"""
                raw=fetch_json(OVERPASS,data=urllib.parse.urlencode({"data":query}).encode(),headers={"Content-Type":"application/x-www-form-urlencoded","User-Agent":"WoodsRoutePlanner/1.0"},timeout=50)
                import math
                features=[]
                for el in raw.get("elements",[]):
                    tags=el.get("tags",{}); coords=[]
                    if el.get("type")=="way":
                        coords=[[p["lon"],p["lat"]] for p in el.get("geometry",[]) if "lon" in p and "lat" in p]
                    elif el.get("center"):
                        coords=[[el["center"]["lon"],el["center"]["lat"]]]
                    if not coords:continue
                    clon=sum(p[0] for p in coords)/len(coords);clat=sum(p[1] for p in coords)/len(coords)
                    dist=2*6371*math.asin(min(1,math.sqrt(math.sin(math.radians(clat-lat)/2)**2+math.cos(math.radians(lat))*math.cos(math.radians(clat))*math.sin(math.radians(clon-lon)/2)**2)))
                    if dist>radius:continue
                    if el.get("type")=="way" and len(coords)>=4 and coords[0]==coords[-1]:
                        geom={"type":"Polygon","coordinates":[coords]}
                    elif el.get("center"):
                        geom={"type":"Point","coordinates":[clon,clat]}
                    else:continue
                    features.append({"type":"Feature","geometry":geom,"properties":{"name":tags.get("name","Unnamed woodland"),"kind":tags.get("natural") or tags.get("landuse") or "woodland","distance_km":round(dist,2)}})
                return self.send_json(200,{"woods":{"type":"FeatureCollection","features":features},"count":len(features),"radius_km":radius})
            except Exception:return self.send_json(502,{"error":"OpenStreetMap woodland search is busy or unavailable. Try again."})
        if path=="/api/woods":
            try:
                s,w,n,e=map(float,q.get("bbox",[""])[0].split(","))
                if n-s>.20 or e-w>.20:return self.send_json(400,{"error":"Zoom in closer to load woodland data"})
                query=f"""[out:json][timeout:25];(way[landuse=forest]({s},{w},{n},{e});way[natural=wood]({s},{w},{n},{e});way[highway~"path|footway|track|bridleway|steps"]({s},{w},{n},{e}););out geom;"""
                raw=fetch_json(OVERPASS,data=urllib.parse.urlencode({"data":query}).encode(),headers={"Content-Type":"application/x-www-form-urlencoded","User-Agent":"WoodsRoutePlanner/1.0"},timeout=35);woods=[];trails=[]
                for el in raw.get("elements",[]):
                    f=feature(el)
                    if not f:continue
                    if f["geometry"]["type"]=="Polygon":woods.append(f)
                    else:trails.append(f)
                return self.send_json(200,{"woods":{"type":"FeatureCollection","features":woods},"trails":{"type":"FeatureCollection","features":trails},"woodland_count":len(woods),"trail_count":len(trails)})
            except Exception:return self.send_json(502,{"error":"OpenStreetMap woodland service is busy or unavailable"})
        return self.send_json(404,{"error":"Not found"})
    def do_POST(self):
        if urllib.parse.urlparse(self.path).path!="/api/route":return self.send_json(404,{"error":"Not found"})
        try:
            body=json.loads(self.rfile.read(int(self.headers.get("Content-Length","0"))));a=body["start"];b=body["end"]
            payload={"locations":[{"lat":float(a["lat"]),"lon":float(a["lng"])},{"lat":float(b["lat"]),"lon":float(b["lng"])}],"costing":"pedestrian","units":"kilometers","costing_options":{"pedestrian":{"use_tracks":1.0,"use_living_streets":0.0,"walking_speed":4.5}}}
            req=urllib.request.Request(VALHALLA,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json","User-Agent":"WoodsRoutePlanner/1.0","X-Client-Id":"woods-route-planner"},method="POST")
            with urllib.request.urlopen(req,timeout=35) as up:data=json.loads(up.read().decode())
            trip=data.get("trip",{})
            if trip.get("status",0)!=0:return self.send_json(502,{"error":trip.get("status_message","No walking route found")})
            shape=trip["legs"][0]["shape"];coords=[];i=0;lat=lon=0
            while i<len(shape):
                vals=[]
                for _ in range(2):
                    res=shift=0
                    while True:
                        c=ord(shape[i])-63;i+=1;res|=(c&31)<<shift;shift+=5
                        if c<32:break
                    vals.append(~(res>>1) if res&1 else res>>1)
                lat+=vals[0];lon+=vals[1];coords.append([lon/1e6,lat/1e6])
            summary=trip["summary"]
            return self.send_json(200,{"geometry":{"type":"LineString","coordinates":coords},"distance_km":float(summary.get("length",0)),"duration_min":float(summary.get("time",0))/60,"note":"Trail preference applied; verify road crossings and access. Not guaranteed woodland-only."})
        except urllib.error.HTTPError as e:return self.send_json(502,{"error":f"Routing provider returned HTTP {e.code}"})
        except Exception:return self.send_json(502,{"error":"Could not calculate route; try different endpoints"})
    def log_message(self,fmt,*args):print("%s - %s"%(self.address_string(),fmt%args),flush=True)
if __name__=="__main__":ThreadingHTTPServer(("0.0.0.0",PORT),Handler).serve_forever()
