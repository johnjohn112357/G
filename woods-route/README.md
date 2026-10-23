# Woods Route Planner

A woodland-focused map and walking route planner. It displays mapped woodland polygons and OpenStreetMap footpaths/tracks, supports place search, GPS start points, map-selected destinations, and pedestrian route calculation.

## Run

`python woods-route/server.py`

No third-party Python packages are required. Leaflet is loaded from a CDN. Woodland and trail features come from the public OpenStreetMap Overpass API, place search from Nominatim, and pedestrian routes from the public Valhalla demo service. These public services have fair-use limits and may occasionally be unavailable.

## Important limitation

The route engine calculates pedestrian routes but does not guarantee that the route remains entirely within woodland. OpenStreetMap data does not establish public access or legal right-of-way; verify local access rules.
