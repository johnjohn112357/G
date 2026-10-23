#!/usr/bin/env python3
"""Woods Route Planner — woodland-focused map and pedestrian route planner."""
import json, os, urllib.error, urllib.parse, urllib.request, re, socket

# Force outbound HTTP lookups to IPv4: Render logs show Errno 101 Network is unreachable on data-source calls.
_original_getaddrinfo = socket.getaddrinfo
def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if family in (0, socket.AF_UNSPEC):
        family = socket.AF_INET
    return _original_getaddrinfo(host, port, family, type, proto, flags)
socket.getaddrinfo = _ipv4_getaddrinfo
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
PORT=int(os.environ.get("PORT","10000"))
OS_MAPS_API_KEY=os.environ.get("OS_MAPS_API_KEY","").strip()  # retained for compatibility; basemap now uses OpenStreetMap
OVERPASS_SERVERS=["https://overpass.kumi.systems/api/interpreter","https://overpass-api.de/api/interpreter"]
VALHALLA="https://valhalla1.openstreetmap.de/route"
TILE_RE=re.compile(r"^/api/tiles/(Leisure|Outdoor|Road|Light)/(\d{1,2})/(\d{1,7})/(\d{1,7})\.png$")

HTML=r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Woods Route Planner</title><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css"><style>
:root{color-scheme:light;--green:#214d35;--pale:#edf3e9;--ink:#17251b}*{box-sizing:border-box}body{margin:0;font:16px system-ui,sans-serif;color:var(--ink);background:#f8faf6}header{background:var(--green);color:white;padding:15px 18px}h1{font-size:1.25rem;margin:0}header p{margin:4px 0 0;font-size:.9rem;opacity:.9}main{display:grid;grid-template-columns:minmax(260px,340px) 1fr;min-height:calc(100vh - 78px)}aside{padding:16px;background:white;border-right:1px solid #d8e0d5;overflow:auto}label{display:block;font-weight:650;margin:12px 0 5px}input,select,button{font:inherit;width:100%;padding:11px;border:1px solid #bbc8b9;border-radius:9px;background:white;color:var(--ink)}button{background:var(--green);color:white;font-weight:700;border:0;margin-top:10px;cursor:pointer}button.secondary{background:var(--pale);color:var(--green);border:1px solid #c9d7c7}#map{height:calc(100vh - 78px);min-height:480px;background:#f4f5ef}.note{font-size:.86rem;color:#4b5d4d;line-height:1.45}.status{padding:10px;border-radius:8px;background:var(--pale);margin-top:12px;font-size:.9rem;white-space:pre-wrap}.legend{display:flex;gap:10px;align-items:center;font-size:.85rem;margin-top:12px}.swatch{width:15px;height:15px;border-radius:4px;background:#6f9c62;border:1px solid #456e3b}@media(max-width:760px){main{display:flex;flex-direction:column;min-height:calc(100vh - 78px)}#map{order:-1;height:60vh;min-height:360px;flex:0 0 60vh}aside{order:0;overflow:visible;border-right:0;border-top:1px solid #d8e0d5}header{padding:13px 15px}}
</style></head><body><header><h1>🌲 Woods Route Planner</h1><p>Woodland map, trail-priority routes and live phone GPS.</p></header><main><aside>
<p class="note">Tap the map to set start and destination. Turn on live GPS to show your current position as you move.</p>
<label for="search">Find a place or woodland</label><input id="search" placeholder="e.g. Ashridge Estate, Hertfordshire"><button id="find" class="secondary">Find place</button>
<p class="note">Map background: OpenStreetMap</p>
<button id="gps">Show my location (live GPS)</button><button id="stopgps" class="secondary">Stop live GPS</button>
<label for="radius">Search radius around my location</label><select id="radius"><option value="2">2 km</option><option value="5" selected>5 km</option><option value="10">10 km</option><option value="20">20 km</option><option value="30">30 km</option><option value="50">50 km</option></select><button id="nearwoods">Show woods within radius</button>
<label>Route preference</label><select id="mode"><option value="trails">Prefer trails and tracks; minimise road use</option></select>
<button id="route">Plan route</button><button id="clear" class="secondary">Clear route and pins</button><div class="legend"><span class="swatch"></span> Mapped woodland</div><div id="status" class="status">Loading woodland data…</div>
<p class="note">GPS requires permission in your phone browser and a secure HTTPS connection. Your position is shown on this map while live tracking is enabled. The map background uses OpenStreetMap tiles directly; woodland and path data also comes from OpenStreetMap. Routing prefers trails but cannot guarantee woodland-only travel or exclude all roads. Check local access signs; mapped paths do not prove legal right-of-way.</p>
</aside><div id="map"><iframe id="fallback-map" title="Fallback OpenStreetMap map" src="https://www.openstreetmap.org/export/embed.html?bbox=-0.55%2C51.76%2C-0.29%2C51.87&layer=mapnik&marker=51.815%2C-0.42" style="display:block;width:100%;height:100%;min-height:360px;border:0" loading="eager" referrerpolicy="no-referrer"></iframe></div></main><script>(function(){const s=document.getElementById("status"),frame=document.getElementById("fallback-map"),gps=document.getElementById("gps"),stop=document.getElementById("stopgps");let watch=null,frameCentered=false;function err(e){s.textContent="GPS error: "+({1:"Location permission denied. In Android Settings, allow location for Chrome and this site.",2:"Phone could not determine location. Turn on device Location and try outdoors.",3:"GPS timed out. Keep the page open and retry outdoors."}[e.code]||e.message)}gps.onclick=function(){if(!navigator.geolocation){s.textContent="GPS API unavailable. Open the HTTPS link directly in Chrome.";return}if(watch!==null)return;s.textContent="Requesting phone location… allow permission if prompted.";watch=navigator.geolocation.watchPosition(function(p){const lat=p.coords.latitude,lon=p.coords.longitude,delta=0.04;s.textContent="GPS FIX: "+lat.toFixed(6)+", "+lon.toFixed(6)+" (accuracy ±"+Math.round(p.coords.accuracy)+" m).";if(!frameCentered){frame.src="https://www.openstreetmap.org/export/embed.html?bbox="+(lon-delta)+"%2C"+(lat-delta)+"%2C"+(lon+delta)+"%2C"+(lat+delta)+"&layer=mapnik&marker="+lat+"%2C"+lon;frameCentered=true;}},function(e){watch=null;err(e)},{enableHighAccuracy:true,maximumAge:0,timeout:30000})};stop.onclick=function(){if(watch!==null)navigator.geolocation.clearWatch(watch);watch=null;s.textContent="Live GPS stopped."};if(s.textContent.indexOf("Loading woodland data")===0)s.textContent="Basic map ready. GPS can run independently; tap Show my location.";})();</script><script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js"></script><script>
document.getElementById('map').innerHTML='';if(!window.L){document.getElementById('status').textContent='Interactive map library failed to load. GPS and woodland overlays cannot start. Try reloading or opening directly in Chrome.';throw new Error('Leaflet library failed to load')}const map=L.map('map').setView([51.815,-0.42],12);
const osmTiles=L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',{attribution:'&copy; OpenStreetMap contributors &copy; CARTO',subdomains:'abcd',maxZoom:20});
let fallbackShown=false;osmTiles.on('tileerror',()=>{if(fallbackShown)return;fallbackShown=true;status('Map tiles failed; switching to embedded OpenStreetMap.');const frame=document.createElement('iframe');frame.title='Fallback OpenStreetMap map';frame.src='https://www.openstreetmap.org/export/embed.html?bbox=-0.55%2C51.76%2C-0.29%2C51.87&layer=mapnik&marker=51.815%2C-0.42';frame.style.cssText='display:block;width:100%;height:100%;min-height:360px;border:0';frame.loading='eager';document.getElementById('map').replaceChildren(frame);});
osmTiles.addTo(map);
const woods=L.geoJSON(null,{style:{color:'#e32636',weight:2.5,fillColor:'#e32636',fillOpacity:.12},onEachFeature:(f,l)=>l.bindTooltip(f.properties?.name||'Woodland')}).addTo(map);
const trails=L.geoJSON(null,{style:{color:'#8b6b42',weight:2,opacity:.9}}).addTo(map);
let start=null,end=null,startMarker=null,endMarker=null,routeLine=null,gpsWatch=null,positionMarker=null,accuracyCircle=null,nearbyWoodsLayer=null,nearbyCircle=null,currentGPS=null;
const status=t=>document.getElementById('status').textContent=t;
function marker(ll,label){return L.marker(ll,{draggable:true}).addTo(map).bindPopup(label)}
function setPoint(ll){if(!start){start=ll;if(startMarker)map.removeLayer(startMarker);startMarker=marker(ll,'Start');startMarker.on('dragend',e=>start=e.target.getLatLng());status('Start set. Tap the map to set destination.')}else{end=ll;if(endMarker)map.removeLayer(endMarker);endMarker=marker(ll,'Destination');endMarker.on('dragend',e=>end=e.target.getLatLng());status('Start and destination set. Tap Plan route.')}}
map.on('click',e=>setPoint(e.latlng));
async function loadData(){const b=map.getBounds(),box=[b.getSouth(),b.getWest(),b.getNorth(),b.getEast()].join(',');const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),8000);try{const r=await fetch('/api/woods?bbox='+encodeURIComponent(box),{signal:controller.signal}),d=await r.json();if(!r.ok)throw Error(d.error||'Woodland query failed');woods.clearLayers();trails.clearLayers();woods.addData(d.woods);trails.addData(d.trails);status('Loaded '+d.woodland_count+' woodland areas and '+d.trail_count+' mapped trail segments.')}catch(e){try{status('Server woodland data unavailable; checking OpenStreetMap directly…');const q='[out:json][timeout:20];(way[landuse=forest]('+box+');way[natural=wood]('+box+');way[highway~"path|footway|track|bridleway|steps"]('+box+'););out geom;';const ctl=new AbortController();const t=setTimeout(()=>ctl.abort(),12000);let raw;try{let rr;let last;for(const endpoint of ['https://overpass.kumi.systems/api/interpreter','https://overpass-api.de/api/interpreter']){try{rr=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded;charset=UTF-8'},body:'data='+encodeURIComponent(q),signal:ctl.signal});if(!rr.ok)throw Error('HTTP '+rr.status);raw=await rr.json();break}catch(ex){last=ex}}if(!raw)throw last||Error('No response')}finally{clearTimeout(t)}const wf=[],tf=[];for(const el of (raw.elements||[])){const pts=(el.geometry||[]).filter(p=>Number.isFinite(p.lon)&&Number.isFinite(p.lat)).map(p=>[p.lon,p.lat]);if(pts.length<2)continue;const tags=el.tags||{},isWood=tags.landuse==='forest'||tags.natural==='wood',closed=pts.length>=4&&pts[0][0]===pts[pts.length-1][0]&&pts[0][1]===pts[pts.length-1][1];if(isWood&&closed)wf.push({type:'Feature',geometry:{type:'Polygon',coordinates:[pts]},properties:{name:tags.name||'Mapped woodland'}});else if(!isWood)tf.push({type:'Feature',geometry:{type:'LineString',coordinates:pts},properties:{name:tags.name||tags.highway||'Footpath'}})}woods.clearLayers();trails.clearLayers();woods.addData({type:'FeatureCollection',features:wf});trails.addData({type:'FeatureCollection',features:tf});status('Direct OpenStreetMap: '+wf.length+' woodland areas and '+tf.length+' mapped paths in view.')}catch(fallbackError){status('Woodland pins unavailable: '+fallbackError.message+'. Try Show woods within radius after GPS, or zoom in and retry.')}}finally{clearTimeout(timeout)}}
let moveTimer;map.on('moveend',()=>{clearTimeout(moveTimer);moveTimer=setTimeout(loadData,500)});loadData();
function gpsError(e){status('GPS unavailable: '+({1:'Location permission denied. Allow location access for this site in your browser settings.',2:'Phone could not determine your location; check GPS and signal.',3:'GPS request timed out; try again outdoors.'}[e.code]||e.message))}
document.getElementById('gps').onclick=()=>{if(!navigator.geolocation){status('GPS is unavailable in this browser. Open the HTTPS planner directly in Chrome, not inside an in-app browser.');return}if(gpsWatch!==null)return;status('Requesting GPS fix… allow location permission and wait outdoors for a clear signal.');gpsWatch=navigator.geolocation.watchPosition(p=>{const ll=L.latLng(p.coords.latitude,p.coords.longitude);currentGPS=ll;if(!positionMarker){positionMarker=L.circleMarker(ll,{radius:9,color:'#fff',weight:3,fillColor:'#1479ee',fillOpacity:1}).addTo(map).bindPopup('Your live GPS position');map.setView(ll,15)}else positionMarker.setLatLng(ll);if(accuracyCircle)map.removeLayer(accuracyCircle);accuracyCircle=L.circle(ll,{radius:p.coords.accuracy,color:'#1479ee',weight:1,fillOpacity:.08}).addTo(map);start=ll;if(startMarker){startMarker.setLatLng(ll)}else{startMarker=marker(ll,'Route start (GPS)');startMarker.on('dragend',e=>start=e.target.getLatLng())}status('GPS fix acquired: '+ll.lat.toFixed(5)+', '+ll.lng.toFixed(5)+' (accuracy about '+Math.round(p.coords.accuracy)+' m). Blue dot marks your position; location is set as route start.')},e=>{gpsWatch=null;gpsError(e)},{enableHighAccuracy:true,maximumAge:0,timeout:30000})};
document.getElementById('stopgps').onclick=()=>{if(gpsWatch!==null)navigator.geolocation.clearWatch(gpsWatch);gpsWatch=null;status('Live GPS stopped. Last position remains on the map.')};
document.getElementById('route').onclick=async()=>{if(!start||!end){status('Set start and destination first. Use live GPS or tap the map twice.');return}status('Calculating trail-priority walking route…');try{const r=await fetch('/api/route',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({start:{lat:start.lat,lng:start.lng},end:{lat:end.lat,lng:end.lng}})}),d=await r.json();if(!r.ok)throw Error(d.error||'Routing failed');if(routeLine)map.removeLayer(routeLine);routeLine=L.geoJSON(d.geometry,{style:{color:'#2468b4',weight:5,opacity:.9}}).addTo(map);map.fitBounds(routeLine.getBounds(),{padding:[25,25]});status('Route: '+d.distance_km.toFixed(2)+' km · approx. '+Math.round(d.duration_min)+' min. '+d.note)}catch(e){status('Route failed: '+e.message)}};
document.getElementById('clear').onclick=()=>{start=end=null;[startMarker,endMarker,routeLine].forEach(x=>{if(x)map.removeLayer(x)});startMarker=endMarker=routeLine=null;status('Route pins cleared. Live GPS marker remains if active.')};
document.getElementById('nearwoods').onclick=async()=>{const center=currentGPS;if(!center){status('GPS fix required. Tap Show my location (live GPS), wait for the blue dot, then search.');return}const km=Number(document.getElementById('radius').value);status('GPS locked at '+center.lat.toFixed(5)+', '+center.lng.toFixed(5)+'. Searching within '+km+' km…');try{let d;try{const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),8000);let r;try{r=await fetch('/api/nearby-woods?lat='+center.lat+'&lon='+center.lng+'&radius='+km,{signal:controller.signal})}finally{clearTimeout(timeout)}d=await r.json();if(!r.ok)throw Error(d.error||'Server woodland search failed')}catch(serverError){status('Server data source unavailable; trying direct OpenStreetMap lookup…');const query='[out:json][timeout:35];(way[landuse=forest](around:'+(km*1000)+','+center.lat+','+center.lng+');way[natural=wood](around:'+(km*1000)+','+center.lat+','+center.lng+');relation[landuse=forest](around:'+(km*1000)+','+center.lat+','+center.lng+');relation[natural=wood](around:'+(km*1000)+','+center.lat+','+center.lng+'););out center tags;';let raw,lastError;for(const endpoint of ['https://overpass.kumi.systems/api/interpreter','https://overpass-api.de/api/interpreter']){try{const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),12000);let rr;try{rr=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded;charset=UTF-8'},body:'data='+encodeURIComponent(query),signal:controller.signal})}finally{clearTimeout(timeout)}if(!rr.ok)throw Error('HTTP '+rr.status);raw=await rr.json();break}catch(err){lastError=err}}if(!raw)throw Error('OpenStreetMap lookup also failed ('+(lastError?.message||serverError.message)+').');const features=(raw.elements||[]).filter(el=>el.center).map(el=>({type:'Feature',geometry:{type:'Point',coordinates:[el.center.lon,el.center.lat]},properties:{name:el.tags?.name||'Unnamed woodland',kind:el.tags?.natural||el.tags?.landuse||'woodland',source:'OpenStreetMap',osm_id:el.id, distance_km:(L.latLng(center).distanceTo([el.center.lat,el.center.lon])/1000).toFixed(2)}}));d={woods:{type:'FeatureCollection',features},count:features.length,partial_sources:['Official inventories (server unavailable)']}}if(nearbyWoodsLayer)map.removeLayer(nearbyWoodsLayer);if(nearbyCircle)map.removeLayer(nearbyCircle);nearbyWoodsLayer=L.geoJSON(d.woods,{style:f=>{const src=f.properties?.source||'';return src==='Ancient Woodland'?{color:'#8b3fb0',weight:3,fillColor:'#bb75d6',fillOpacity:.48}:src==='National Forest Inventory'?{color:'#235da8',weight:2,fillColor:'#5d9fe0',fillOpacity:.35}:{color:'#245b2a',weight:2,fillColor:'#79b96b',fillOpacity:.5}},pointToLayer:(f,ll)=>L.marker(ll,{icon:L.divIcon({className:'wood-pin-wrap',html:'<span style="display:block;width:16px;height:16px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);background:'+(f.properties?.source==='Ancient Woodland'?'#8b3fb0':f.properties?.source==='National Forest Inventory'?'#235da8':'#247a32')+';border:2px solid white;box-shadow:0 1px 5px #333;'></span>',iconSize:[18,18],iconAnchor:[9,16]})}),onEachFeature:(f,l)=>{const p=f.properties||{};l.bindPopup('<b>'+(p.name||'Unnamed woodland')+'</b><br>'+((p.distance_km??'?')+' km from your location')+'<br>'+(p.kind||'Woodland')+'<br><small>Source: '+(p.source||'OpenStreetMap')+'</small>');}}).addTo(map);nearbyCircle=L.circle(center,{radius:km*1000,color:'#386f9b',weight:1,fillOpacity:.03}).addTo(map);if(d.woods.features.length){const bounds=nearbyWoodsLayer.getBounds();bounds.extend(center);map.fitBounds(bounds,{padding:[20,20]});status('Showing '+d.count+' woodland pinpoints within '+km+' km. Tap a pin for its name and distance.'+(d.partial_sources?.length?' Some data sources unavailable: '+d.partial_sources.join(', ')+'.':''))}else{map.setView(center,Math.max(10,15-Math.round(Math.log2(km))));status('No mapped woodland features found within '+km+' km. Try a larger radius.')}}catch(e){status('Woodland pin search failed: '+e.message)}};
document.getElementById('find').onclick=async()=>{const q=document.getElementById('search').value.trim();if(!q)return;status('Searching…');try{const r=await fetch('/api/search?q='+encodeURIComponent(q)),d=await r.json();if(!r.ok)throw Error(d.error||'Search failed');map.setView([d.lat,d.lon],14);status('Showing '+d.name)}catch(e){status('Search failed: '+e.message)}};
</script></body></html>"""

def fetch_json(url,data=None,headers=None,timeout=30):
    req=urllib.request.Request(url,data=data,headers=headers or {},method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.loads(r.read().decode())

def fetch_overpass(query,timeout=40):
    payload=urllib.parse.urlencode({"data":query}).encode()
    headers={"Content-Type":"application/x-www-form-urlencoded","User-Agent":"WoodsRoutePlanner/1.0"}
    errors=[]
    for endpoint in OVERPASS_SERVERS:
        try:
            return fetch_json(endpoint,data=payload,headers=headers,timeout=timeout)
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError("All woodland query servers failed: "+"; ".join(errors))
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
            b=HTML.encode();self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.send_header("Cache-Control","no-store, no-cache, must-revalidate");self.send_header("Pragma","no-cache");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b);return
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
                import math
                dlat=radius/111.0;dlon=radius/(111.0*max(0.15,abs(math.cos(math.radians(lat)))))
                south,west,north,east=lat-dlat,lon-dlon,lat+dlat,lon+dlon
                query=f"""[out:json][timeout:40];(way[landuse=forest]({south},{west},{north},{east});way[natural=wood]({south},{west},{north},{east});relation[landuse=forest]({south},{west},{north},{east});relation[natural=wood]({south},{west},{north},{east}););out center geom;"""
                raw=fetch_overpass(query,timeout=50)
                features=[];seen=set()
                def add_feature(geom,props,source):
                    coords=[]
                    def visit(v):
                        if isinstance(v,(list,tuple)):
                            if len(v)>=2 and isinstance(v[0],(int,float)) and isinstance(v[1],(int,float)):
                                coords.append((float(v[0]),float(v[1])))
                            else:
                                for item in v:visit(item)
                    visit(geom.get("coordinates",[]))
                    if not coords:return
                    clon=sum(p[0] for p in coords)/len(coords);clat=sum(p[1] for p in coords)/len(coords)
                    dist=2*6371*math.asin(min(1,math.sqrt(math.sin(math.radians(clat-lat)/2)**2+math.cos(math.radians(lat))*math.cos(math.radians(clat))*math.sin(math.radians(clon-lon)/2)**2)))
                    if dist>radius:return
                    props=dict(props or {});props["source"]=source;props["distance_km"]=round(dist,2)
                    features.append({"type":"Feature","geometry":geom,"properties":props})
                for el in raw.get("elements",[]):
                    key=("osm",el.get("type"),el.get("id"))
                    if key in seen:continue
                    seen.add(key);tags=el.get("tags",{});geom=None
                    if el.get("type")=="way":
                        coords=[[p["lon"],p["lat"]] for p in el.get("geometry",[]) if "lon" in p and "lat" in p]
                        if len(coords)>=4 and coords[0]==coords[-1]:geom={"type":"Polygon","coordinates":[coords]}
                    elif el.get("type")=="relation":
                        rings=[]
                        for member in el.get("members",[]):
                            if member.get("role")!="outer" or member.get("type")!="way":continue
                            ring=[[p["lon"],p["lat"]] for p in member.get("geometry",[]) if "lon" in p and "lat" in p]
                            if len(ring)>=4 and ring[0]==ring[-1]:rings.append(ring)
                        if rings:geom={"type":"Polygon","coordinates":rings}
                    if geom is None and el.get("center"):geom={"type":"Point","coordinates":[el["center"]["lon"],el["center"]["lat"]]}
                    if geom is None:continue
                    add_feature(geom,{"osm_type":el.get("type"),"osm_id":el.get("id"),"name":tags.get("name","Unnamed woodland"),"kind":tags.get("natural") or tags.get("landuse") or "woodland"},"OpenStreetMap")
                # Official inventories fill gaps in OSM. Query only the selected bounding box to keep responses bounded.
                envelope=urllib.parse.quote(json.dumps({"xmin":west,"ymin":south,"xmax":east,"ymax":north,"spatialReference":{"wkid":4326}},separators=(",",":")))
                arcgis_sources=[
                    ("National Forest Inventory","https://services2.arcgis.com/mHXjwgl3OARRqqD4/ArcGIS/rest/services/National_Forest_Inventory_GB_2024/FeatureServer/0/query"),
                    ("Ancient Woodland","https://services.arcgis.com/JJzESW51TqeY9uat/arcgis/rest/services/Ancient_Woodland_England/FeatureServer/0/query")
                ]
                official_errors=[]
                for source,url in arcgis_sources:
                    params=urllib.parse.urlencode({"where":"1=1","geometry":json.dumps({"xmin":west,"ymin":south,"xmax":east,"ymax":north,"spatialReference":{"wkid":4326}},separators=(",",":")),"geometryType":"esriGeometryEnvelope","inSR":"4326","spatialRel":"esriSpatialRelIntersects","outFields":"*","returnGeometry":"true","outSR":"4326","f":"geojson","resultRecordCount":"1000"})
                    try:
                        official=fetch_json(url+"?"+params,headers={"User-Agent":"WoodsRoutePlanner/1.0"},timeout=35)
                        if official.get("error"):raise ValueError(official["error"].get("message","ArcGIS query error"))
                        for feature in official.get("features",[]):
                            props=feature.get("properties",{})
                            if source=="National Forest Inventory":
                                props["name"]=props.get("CATEGORY") or "Woodland (National Forest Inventory)"
                                props["kind"]=props.get("CATEGORY") or "National Forest Inventory"
                            else:
                                props["name"]=props.get("NAME") or props.get("Name") or "Ancient woodland"
                                props["kind"]="Ancient woodland"
                            add_feature(feature.get("geometry") or {},props,source)
                    except Exception as ex:
                        print("Official woodland source %s failed: %s"%(source,ex),flush=True)
                        official_errors.append(source)
                return self.send_json(200,{"woods":{"type":"FeatureCollection","features":features},"count":len(features),"radius_km":radius,"sources":["OpenStreetMap"]+[x for x in ["National Forest Inventory","Ancient Woodland"] if x not in official_errors],"partial_sources":official_errors})
            except Exception as exc:
                print("Nearby woodland search error: %s" % exc,flush=True)
                return self.send_json(502,{"error":"Woodland search failed. Try again in a moment."})
        if path=="/api/woods":
            try:
                s,w,n,e=map(float,q.get("bbox",[""])[0].split(","))
                if n-s>.20 or e-w>.20:return self.send_json(400,{"error":"Zoom in closer to load woodland data"})
                query=f"""[out:json][timeout:25];(way[landuse=forest]({s},{w},{n},{e});way[natural=wood]({s},{w},{n},{e});way[highway~"path|footway|track|bridleway|steps"]({s},{w},{n},{e}););out geom;"""
                raw=fetch_overpass(query,timeout=35);woods=[];trails=[]
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
