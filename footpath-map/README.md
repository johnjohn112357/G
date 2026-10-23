# Footpath Map

A mobile-friendly Ordnance Survey raster map with automatic pedestrian routing, manual route tracing and GPX import/export. The backend proxies OS map tiles so the OS Maps API key is not exposed to browsers.

## Features

- OS Leisure, Outdoor, Road and Light raster layer selector
- Mobile pan/zoom and device geolocation
- Automatic pedestrian routing between two map-selected points via Valhalla/OpenStreetMap
- Manual route tracing with drawn-line distance calculation
- GPX route/track import and GPX export
- `/health` endpoint reports service health and whether an OS Maps API key is configured (never returns the key)

## Configuration

Set `OS_MAPS_API_KEY` to an OS Maps API key authorised for the Raster API. Render supplies `PORT`. Check `/health` after deployment: `os_maps_api_key_configured` should be `true`.

A configured key does not prove that the key is valid, has quota remaining, or is authorised for every requested style. Open the live map and confirm tiles actually render. The tile endpoint returns a generic error rather than exposing upstream credentials or URLs.

## Important limitations

Automatic routing asks the public Valhalla service to calculate a pedestrian route over OpenStreetMap data. The public endpoint may rate-limit or become unavailable; it is a prototype dependency, not a production SLA. The result is not a legal-right-of-way determination and mapped footpaths may have access restrictions or be missing/outdated. Manual route tracing remains available. GPX import uses route points when present, otherwise the first track segment; it does not preserve multiple separate tracks/segments. The map cannot establish whether a path is a public right of way or currently open. Check OS API terms, attribution, quotas and key restrictions before wider use.
