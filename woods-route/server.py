#!/usr/bin/env python3
"""Woods Route Planner v2: simple, resilient woodland and footpath map."""
import json, os, urllib.parse, urllib.request, urllib.error, math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "10000"))
VALHALLA_URL = "https://valhalla1.openstreetmap.de/route"
OVERPASS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]
HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>Woods Route Planner</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
*{box-sizing:border-box}body{margin:0;font:15px system-ui,-apple-system,sans-serif;color:#17251b;background:#f6f8f4}header{background:#173e2a;color:#fff;padding:12px 16px}h1{font-size:20px;margin:0}header p{margin:3px 0 0;font-size:13px;opacity:.9}main{display:grid;grid-template-columns:320px 1fr;height:calc(100dvh - 65px)}aside{padding:14px;overflow:auto;background:#fff;border-right:1px solid #d7dfd4}#map{height:100%;min-height:380px;background:#e8ede5}label{display:block;font-weight:650;margin:13px 0 5px}input,select,button{font:inherit;width:100%;padding:10px;border-radius:8px;border:1px solid #bdc9bb;background:white;color:#17251b}button{margin-top:8px;background:#245438;color:#fff;border:0;font-weight:700}button.alt{background:#edf3e9;color:#245438;border:1px solid #cbd9c7}.row{display:grid;grid-template-columns:1fr 1fr;gap:8px}.status{white-space:pre-wrap;background:#edf3e9;border-radius:8px;padding:10px;margin-top:12px;font-size:13px;line-height:1.4}.help{font-size:12px;line-height:1.45;color:#566456}.legend{display:flex;align-items:center;gap:7px;font-size:12px;margin-top:10px}.dot{width:12px;height:12px;background:#d92332;border-radius:50%;display:inline-block}@media(max-width:720px){main{display:flex;flex-direction:column;height:auto;min-height:calc(100dvh - 65px)}#map{order:0;height:53dvh;min-height:330px;flex:none}aside{order:1;overflow:visible}header{padding:10px 13px}}
</style></head><body>
<header><h1>🌲 Woods Route Planner</h1><p>Find woods, see footpaths and plan a walking route</p></header>
<main><aside>
<label for="place">Find a place or woodland</label><input id="place" placeholder="e.g. Ashridge Estate">
<button id="find" class="alt">Find place</button>
<div class="row"><button id="gps">Use my GPS</button><button id="nearby" class="alt">Woods near me</button></div>
<label for="radius">Woodland search radius</label><select id="radius"><option value="2">2 km</option><option value="5" selected>5 km</option><option value="10">10 km</option><option value="20">20 km</option><option value="30">30 km</option><option value="50">50 km</option></select>
<p class="help">To plan a route, tap the map once for the start and again for the destination. Or use GPS for the start, then tap a destination.</p>
<div class="row"><button id="route">Plan walking route</button><button id="reset" class="alt">Reset</button></div>
<div class="legend"><span class="dot"></span> Woodland / point of interest</div><div class="status" id="status">Starting map…</div>
<p class="help">Map tiles: Esri World Topographic Map. Woodland and paths: OpenStreetMap plus official woodland inventories where available. Routing: Valhalla with BRouter fallback. Check signs and legal access; a mapped path does not itself prove public right of way.</p>
</aside><div id="map"></div></main>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
(function(){
const $=id=>document.getElementById(id),status=t=>$('status').textContent=t;
if(!window.L){status('Map library failed to load. Check connection and reload.');return}
const map=L.map('map').setView([51.815,-0.42],12);
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}',{maxZoom:19,attribution:'Tiles © Esri, USGS, NOAA'}).addTo(map);
const woods=L.geoJSON(null,{style:{color:'#bd1726',weight:2,fillColor:'#e32636',fillOpacity:.26},pointToLayer:(f,ll)=>L.circleMarker(ll,{radius:7,color:'#fff',weight:2,fillColor:'#d92332',fillOpacity:1}),onEachFeature:(f,l)=>{const p=f.properties||{};l.bindPopup('<b>'+safe(p.name||p.NAME||'Woodland')+'</b><br>'+safe(p.source||'Mapped woodland')+(p.distance_km!==undefined?'<br>'+p.distance_km+' km from search centre':''))}}).addTo(map);
const paths=L.geoJSON(null,{style:{color:'#8a673d',weight:2,opacity:.9}}).addTo(map);
const pins=L.layerGroup().addTo(map);
let start=null,end=null,startMark=null,endMark=null,routeLayer=null,gpsMarker=null,gpsCircle=null,lastGPS=null,loadTimer=null;
function safe(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function mark(ll,label){return L.marker(ll).addTo(map).bindPopup(label)}
function setStart(ll){start=ll;if(startMark)map.removeLayer(startMark);startMark=mark(ll,'Route start');startMark.openPopup();status('Start set. Tap the map to choose the destination.')}
function setEnd(ll){end=ll;if(endMark)map.removeLayer(endMark);endMark=mark(ll,'Destination');endMark.openPopup();status('Start and destination set. Tap Plan walking route.')}
map.on('click',e=>{if(!start||end){if(end&&start){end=null;if(endMark)map.removeLayer(endMark);endMark=null}setStart(e.latlng)}else setEnd(e.latlng)});
async function jsonFetch(url,opts={},ms=18000){const ctl=new AbortController(),t=setTimeout(()=>ctl.abort(),ms);try{const r=await fetch(url,{...opts,signal:ctl.signal});if(!r.ok)throw Error('HTTP '+r.status);return await r.json()}finally{clearTimeout(t)}}
async function findPlace(){const q=$('place').value.trim();if(!q){status('Type a place name first.');return}status('Searching for '+q+'…');try{const a=await jsonFetch('https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q='+encodeURIComponent(q),{headers:{Accept:'application/json'}},15000);if(!a.length)throw Error('No match found. Try a more specific name.');const ll=L.latLng(+a[0].lat,+a[0].lon);map.setView(ll,15);L.marker(ll).addTo(pins).bindPopup(safe(a[0].display_name)).openPopup();status('Found '+a[0].display_name+'. Loading nearby woods…');loadWoods(ll,Number($('radius').value));}catch(e){status('Place search failed: '+e.message+'. If this is a browser CORS restriction, try GPS or tap the map.')} }
$('find').onclick=findPlace;$('place').addEventListener('keydown',e=>{if(e.key==='Enter')findPlace()});
async function gps(){if(!navigator.geolocation){status('GPS is unavailable in this browser. Open the HTTPS link in your browser.');return}status('Waiting for GPS permission and location…');navigator.geolocation.getCurrentPosition(p=>{lastGPS=L.latLng(p.coords.latitude,p.coords.longitude);if(gpsMarker)map.removeLayer(gpsMarker);gpsMarker=L.circleMarker(lastGPS,{radius:9,color:'#fff',weight:3,fillColor:'#1675e8',fillOpacity:1}).addTo(map).bindPopup('Your GPS position');if(gpsCircle)map.removeLayer(gpsCircle);gpsCircle=L.circle(lastGPS,{radius:p.coords.accuracy,color:'#1675e8',weight:1,fillOpacity:.08}).addTo(map);map.setView(lastGPS,15);setStart(lastGPS);status('GPS acquired (accuracy ±'+Math.round(p.coords.accuracy)+' m). Tap a destination, then Plan walking route.')},e=>status('GPS failed: '+({1:'Location permission denied.',2:'Location unavailable; try outdoors.',3:'GPS timed out; try again.'}[e.code]||e.message)),{enableHighAccuracy:true,timeout:25000,maximumAge:0})}
$('gps').onclick=gps;$('nearby').onclick=()=>{if(!lastGPS){gps();status('Allow GPS; when location is acquired, tap Woods near me again.');return}loadWoods(lastGPS,Number($('radius').value))};
async function loadWoods(center,radius){status('Searching for woodland within '+radius+' km…');paths.clearLayers();let fc=null,features=[],errors=[];
const south=center.lat-radius/110.8, north=center.lat+radius/110.8, cos=Math.max(.2,Math.cos(center.lat*Math.PI/180)),west=center.lng-radius/(110.8*cos),east=center.lng+radius/(110.8*cos);
try{const q='[out:json][timeout:20];(way[landuse=forest]('+south+','+west+','+north+','+east+');way[natural=wood]('+south+','+west+','+north+','+east+');relation[landuse=forest]('+south+','+west+','+north+','+east+');relation[natural=wood]('+south+','+west+','+north+','+east+');way[highway~"path|footway|track|bridleway|steps"]('+south+','+west+','+north+','+east+'););out center geom tags;';
let raw;for(const host of ['https://overpass.kumi.systems/api/interpreter','https://overpass-api.de/api/interpreter']){try{raw=await jsonFetch(host,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded;charset=UTF-8'},body:'data='+encodeURIComponent(q)},25000);break}catch(e){errors.push(e.message)}}if(!raw)throw Error('OpenStreetMap query failed: '+errors.join(', '));
for(const el of raw.elements||[]){const t=el.tags||{},isWood=t.landuse==='forest'||t.natural==='wood';let geom=null;if(el.type==='way'&&el.geometry?.length){const coords=el.geometry.filter(p=>Number.isFinite(p.lon)&&Number.isFinite(p.lat)).map(p=>[p.lon,p.lat]);if(isWood&&coords.length>=4&&coords[0][0]===coords.at(-1)[0]&&coords[0][1]===coords.at(-1)[1])geom={type:'Polygon',coordinates:[coords]};else if(!isWood&&coords.length>1){geom={type:'LineString',coordinates:coords};paths.addData({type:'Feature',geometry:geom,properties:{name:t.name||t.highway||'Footpath'}});continue}}if(!geom&&el.center)geom={type:'Point',coordinates:[el.center.lon,el.center.lat]};if(!geom)continue;const ll=geom.type==='Point'?L.latLng(geom.coordinates[1],geom.coordinates[0]):L.geoJSON({type:'Feature',geometry:geom,properties:{}}).getBounds().getCenter();const dist=ll.distanceTo(center)/1000;if(dist>radius+1)continue;features.push({type:'Feature',geometry:geom,properties:{name:t.name||'Unnamed woodland',source:'OpenStreetMap',distance_km:dist.toFixed(2)}})}
}catch(e){errors.push(e.message)}
// Query official England ancient woodland inventory when available.
try{const params=new URLSearchParams({where:'1=1',geometry:JSON.stringify({xmin:west,ymin:south,xmax:east,ymax:north,spatialReference:{wkid:4326}}),geometryType:'esriGeometryEnvelope',inSR:'4326',spatialRel:'esriSpatialRelIntersects',outFields:'*',returnGeometry:'true',outSR:'4326',f:'geojson',resultRecordCount:'500'});const a=await jsonFetch('https://services.arcgis.com/JJzESW51TqeY9uat/arcgis/rest/services/Ancient_Woodland_England/FeatureServer/0/query?'+params,{},20000);for(const f of a.features||[]){if(!f.geometry)continue;f.properties=f.properties||{};f.properties.name=f.properties.NAME||f.properties.Name||'Ancient woodland';f.properties.source='Ancient Woodland Inventory';features.push(f)}}catch(e){errors.push('Ancient woodland layer: '+e.message)}
woods.clearLayers();pins.clearLayers();woods.addData({type:'FeatureCollection',features});if(!features.length){status('No woodland features returned for this area. '+(errors.length?'Sources: '+errors.join(' | '):'Try a larger radius or another location.'));return}
const pts=[];for(const f of features){try{const ll=f.geometry.type==='Point'?L.latLng(f.geometry.coordinates[1],f.geometry.coordinates[0]):L.geoJSON(f).getBounds().getCenter();const name=f.properties?.name||'Woodland';const icon=L.divIcon({className:'woodpin',html:'<div style="font-size:24px;line-height:28px;text-shadow:0 1px 3px white">📍</div>',iconSize:[28,30],iconAnchor:[14,28]});pins.addLayer(L.marker(ll,{icon,title:name}).bindPopup('<b>'+safe(name)+'</b><br>'+safe(f.properties?.source||'Woodland')+(f.properties?.distance_km?'<br>'+f.properties.distance_km+' km from centre':'')));pts.push(ll)}catch(e){}}
if(pts.length)map.fitBounds(L.latLngBounds(pts).pad(.15),{maxZoom:14});status('Found '+features.length+' woodland features; displayed '+pins.getLayers().length+' pins. Footpaths are shown in brown where the data service returned them.'+(errors.length?'\nSome sources unavailable: '+errors.join(' | '):''))}
async function planRoute(){if(!start||!end){status('Set a start and destination first. Use GPS for start or tap the map twice.');return}status('Requesting a pedestrian route from Valhalla…');let geo=null,dist=null,duration=null,provider='';
try{const payload={locations:[{lat:start.lat,lon:start.lng},{lat:end.lat,lon:end.lng}],costing:'pedestrian',units:'kilometers',shape_format:'geojson',costing_options:{pedestrian:{use_tracks:1.0,use_trails:1.0,use_living_streets:0.1}}};const d=await jsonFetch('/api/route',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)},35000);geo=d.geometry;dist=d.distance_km;duration=d.duration_min;provider=d.provider||'Valhalla'}catch(e){status('Valhalla proxy unavailable; trying BRouter trekking profile…');try{const url='https://brouter.de/brouter?lonlats='+encodeURIComponent(start.lng+','+start.lat+'|'+end.lng+','+end.lat)+'&profile=trekking&alternativeidx=0&format=geojson';const d=await jsonFetch(url,{headers:{Accept:'application/geo+json,application/json'}},35000);geo=d.features?.[0]?.geometry;if(!geo)throw Error('No route geometry');let metres=0;for(let i=1;i<geo.coordinates.length;i++)metres+=map.distance([geo.coordinates[i-1][1],geo.coordinates[i-1][0]],[geo.coordinates[i][1],geo.coordinates[i][0]]);dist=metres/1000;duration=dist/4.5*60;provider='BRouter trekking'}catch(e2){status('Route failed. Valhalla: '+e.message+'; BRouter: '+e2.message+'. Try again or choose closer points.');return}}
if(routeLayer)map.removeLayer(routeLayer);routeLayer=L.geoJSON(geo,{style:{color:'#1769c2',weight:5,opacity:.95}}).addTo(map);map.fitBounds(routeLayer.getBounds().pad(.12));status('Route calculated by '+provider+'\nDistance: '+Number(dist).toFixed(2)+' km · estimated walking time: '+Math.round(duration)+' min.\nTrail preference applied where supported; check crossings, access rights and conditions.')}
$('route').onclick=planRoute;$('reset').onclick=()=>{start=end=null;[startMark,endMark,routeLayer].forEach(x=>{if(x)map.removeLayer(x)});startMark=endMark=routeLayer=null;status('Route cleared. Tap map twice to choose new endpoints.')};
async function initial(){status('Loading map and nearby woodland…');try{await loadWoods(map.getCenter(),5)}catch(e){status('Map is ready. Tap Woods near me or search a place to load woodland.')}}initial();
})();
</script></body></html>"""

def fetch_json(url, data=None, timeout=25, headers=None):
    h={"User-Agent":"WoodsRoutePlanner/2.0 (walking route planner)","Accept":"application/json"}
    if headers:h.update(headers)
    req=urllib.request.Request(url,data=data,headers=h,method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req,timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))

class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, code, body, content_type):
        self.send_response(code);self.send_header("Content-Type",content_type);self.send_header("Cache-Control","no-store");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
    def send_json(self, code, obj):
        self.send_bytes(code,json.dumps(obj).encode("utf-8"),"application/json; charset=utf-8")
    def do_HEAD(self):
        if self.path=="/":
            self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.end_headers()
        else:self.send_response(404);self.end_headers()
    def do_GET(self):
        path=urllib.parse.urlparse(self.path).path
        if path=="/":return self.send_bytes(200,HTML.encode("utf-8"),"text/html; charset=utf-8")
        if path=="/health":return self.send_json(200,{"status":"ok","app":"Woods Route Planner v2"})
        if path=="/api/search":
            q=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("q",[""])[0].strip()
            if not q:return self.send_json(400,{"error":"Enter a place name"})
            try:
                rows=fetch_json("https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q="+urllib.parse.quote(q),timeout=15)
                if not rows:return self.send_json(404,{"error":"No matching place found"})
                return self.send_json(200,{"lat":float(rows[0]["lat"]),"lon":float(rows[0]["lon"]),"name":rows[0]["display_name"]})
            except Exception as e:return self.send_json(502,{"error":"Geocoding failed: "+str(e)[:180]})
        return self.send_json(404,{"error":"Not found"})
    def do_POST(self):
        if urllib.parse.urlparse(self.path).path!="/api/route":return self.send_json(404,{"error":"Not found"})
        try:
            payload=json.loads(self.rfile.read(int(self.headers.get("Content-Length","0"))))
            loc=payload.get("locations",[])
            if len(loc)!=2:raise ValueError("Two route endpoints are required")
            for p in loc:
                if not (-90<=float(p["lat"])<=90 and -180<=float(p["lon"])<=180):raise ValueError("Invalid coordinates")
            payload["costing"]="pedestrian";payload["units"]="kilometers";payload["shape_format"]="geojson"
            result=fetch_json(VALHALLA_URL,data=json.dumps(payload).encode(),timeout=35,headers={"Content-Type":"application/json"})
            trip=result.get("trip",{})
            if trip.get("status",0)!=0:raise RuntimeError(trip.get("status_message","Valhalla found no route"))
            legs=trip.get("legs",[])
            if not legs:raise RuntimeError("Valhalla returned no route legs")
            shape=legs[0].get("shape")
            if isinstance(shape,dict):geometry=shape
            else:
                # Valhalla encoded polyline precision 6.
                coords=[];i=0;lat=lon=0
                while i<len(shape):
                    vals=[]
                    for _ in range(2):
                        value=shift=0
                        while True:
                            b=ord(shape[i])-63;i+=1;value|=(b&31)<<shift;shift+=5
                            if b<32:break
                        vals.append(~(value>>1) if value&1 else value>>1)
                    lat+=vals[0];lon+=vals[1];coords.append([lon/1e6,lat/1e6])
                geometry={"type":"LineString","coordinates":coords}
            summary=trip.get("summary",{})
            return self.send_json(200,{"geometry":geometry,"distance_km":float(summary.get("length",0)),"duration_min":float(summary.get("time",0))/60,"provider":"Valhalla","note":"Pedestrian routing; verify access and conditions."})
        except urllib.error.HTTPError as e:return self.send_json(502,{"error":"Valhalla HTTP "+str(e.code)})
        except Exception as e:return self.send_json(502,{"error":str(e)[:240] or "Could not calculate route"})
    def log_message(self, fmt, *args):print("%s - %s"%(self.address_string(),fmt%args),flush=True)

if __name__=="__main__":ThreadingHTTPServer(("0.0.0.0",PORT),Handler).serve_forever()
