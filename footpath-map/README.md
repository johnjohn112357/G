# Footpath Map

A standalone mobile-friendly map using the Ordnance Survey Leisure raster layer. The backend proxies map tiles so the OS Maps API key is not exposed to browsers.

## Features
- OS Leisure map layer with mapped paths and tracks
- Mobile pan/zoom and device geolocation
- Manual route tracing with distance calculation
- GPX export for a traced route
- Health endpoint at /health

## Configuration
Set `OS_MAPS_API_KEY` to an OS Maps API key that is authorised for the Raster API. Render supplies `PORT`.

## Important limitations
The route tool records points clicked by the user; it does not automatically snap to footpaths or calculate a route over a path network. The map cannot establish whether a path is a public right of way or currently open. Check OS API terms, attribution, quotas and key restrictions before wider use.
