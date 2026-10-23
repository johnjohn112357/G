# Woods Route Planner

A lightweight woodland-focused walking route planner. The Python backend uses only the standard library; the frontend uses Leaflet.

## Live app

https://woods-route-planner.onrender.com

## Run with Python

Requires Python 3.10+ and an internet connection.

```sh
cd woods-route
python server.py
```

Open http://127.0.0.1:10000. On desktop the app opens a browser automatically. Set `PORT` to change the port, or `WOODS_NO_BROWSER=1` to suppress browser launch.

## Docker

From the repository root:

```sh
docker compose -f woods-route/docker-compose.yml up --build -d
```

Open http://localhost:10000. Stop with:

```sh
docker compose -f woods-route/docker-compose.yml down
```

Or build and run directly:

```sh
docker build -t woods-route-planner:local -f woods-route/Dockerfile woods-route
docker run --rm -p 10000:10000 -e PORT=10000 -e WOODS_NO_BROWSER=1 woods-route-planner:local
```

The container exposes a `/health` endpoint for health checks.

## Windows installer

The GitHub Actions workflow **Woods Route Planner Windows build** builds a standalone Windows executable, a portable ZIP, and an Inno Setup installer. The executable bundles Python, so users do not need to install Python separately.

To get the build, open the repository's **Actions** tab, choose the latest successful **Woods Route Planner Windows build**, and download the `WoodsRoutePlanner-Windows` artifact. The workflow can also be started manually with **Run workflow**.

The installer creates Start Menu and desktop shortcuts. The app needs internet access for map tiles, geocoding, woodland data and routing.

## Data sources and limitations

- Basemap: Esri World Topographic Map.
- Woodland and footpath overlays: OpenStreetMap/Overpass, plus the England Ancient Woodland Inventory where available.
- Routing: Valhalla pedestrian routing with a BRouter trekking fallback.
- Public data services may rate-limit or be temporarily unavailable; the app reports source errors when possible.
- A mapped path is not proof of a public right of way. Check access restrictions, signs, crossings and local conditions.

## Project files

- `server.py` — HTTP server, API endpoints and embedded browser interface.
- `Dockerfile` — container image.
- `docker-compose.yml` — Compose configuration (at repository root).
- `windows/` — Windows launcher and installer definition.
- `.github/workflows/woods-route-windows.yml` — Windows build workflow.
