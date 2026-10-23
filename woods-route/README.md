# Woods Route Planner

A small Python HTTP app for woodland discovery and pedestrian route planning. The browser map uses OpenStreetMap tiles. Woodland searches fetch data on demand from OpenStreetMap/Overpass and official woodland inventory services when available.

## Keep it up to date

- Source code is versioned in GitHub on the `woods-route-planner` branch. Changes pushed to this branch are saved in the repository and trigger the configured Render auto-deploy.
- Woodland records are queried live when you search; the app does not rely on a stale bundled woodland snapshot.
- GitHub Actions builds and publishes the Docker image on relevant pushes, every Monday, or when manually triggered.
- Public data services may be unavailable or incomplete, and weekly Docker rebuilds do not guarantee upstream datasets themselves have changed.

## Run locally with Python

Requires Python 3.10+; the server uses only the Python standard library.

```sh
cd woods-route
PORT=10000 python server.py
```

Open http://localhost:10000.

## Build and run with Docker

From the repository root:

```sh
docker build -t woods-route-planner:local -f woods-route/Dockerfile woods-route
docker run --rm -p 10000:10000 -e PORT=10000 woods-route-planner:local
```

Open http://localhost:10000. The container exposes `/health` for health checks.

GitHub Actions publishes these image tags to GitHub Container Registry (GHCR) after the workflow succeeds:

- `ghcr.io/johnjohn112357/woods-route-planner:latest`
- `ghcr.io/johnjohn112357/woods-route-planner:sha-<commit>`

Pull and run:

```sh
docker pull ghcr.io/johnjohn112357/woods-route-planner:latest
docker run --rm -p 10000:10000 -e PORT=10000 ghcr.io/johnjohn112357/woods-route-planner:latest
```

The package is available only after the first successful workflow run. If GHCR access is private, authenticate to GitHub Container Registry first.

## Render

Render can continue deploying directly from the GitHub branch. Publishing a Docker image is an additional portable deployment route; it does not automatically change the existing Render service to use that image.

## Attribution and limitations

- Map tiles: © OpenStreetMap contributors, https://www.openstreetmap.org/copyright
- Woodland inventory data remains subject to the terms and attribution requirements of its upstream provider.
- Live data is not guaranteed complete or real-time. Public Overpass and routing endpoints can be rate-limited.
- A mapped path or woodland polygon does not establish public access rights.
