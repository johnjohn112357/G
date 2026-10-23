# Self-hosting the Research & Engineering Toolkit

You can run the toolkit without Render. The application uses the Python standard library and SQLite; Docker is optional.

## Option A — Docker Compose (recommended for an easy repeatable setup)

Requirements: Docker Engine/Desktop with the Compose plugin.

1. Download and extract the repository ZIP from https://github.com/johnjohn112357/G/archive/refs/heads/main.zip, or clone the repository.
2. Copy `.env.example` to `.env`.
3. Generate a secret on your own machine:

   ```sh
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

4. Put the generated value after `API_KEY=` in `.env`. Do not commit `.env`.
5. Optionally set `OS_MAPS_API_KEY=` after creating an OS Data Hub project and enabling the OS Maps API. The toolkit can run without this key; the OS basemap tiles cannot.
6. From the project folder, run:

   ```sh
   docker compose up --build -d
   ```

7. Open http://127.0.0.1:8765/tools. The maps page is at http://127.0.0.1:8765/maps.

The Compose file binds to localhost only by default, so the app is not exposed to your LAN or the public internet. Keep it this way unless you deliberately configure a secure reverse proxy/firewall.

Stop the service with `docker compose down`. Your SQLite data remains in the named Docker volume. `docker compose down -v` deletes that volume and its data; do not use `-v` unless you intend to erase it.

## Option B — Run directly with Python

Requirements: Python 3.12 or later. No third-party Python packages are needed.

Linux/macOS:

```sh
export API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export HOST=127.0.0.1
export PORT=8765
export DB_PATH="$PWD/toolkit.sqlite3"
python server.py
```

Windows PowerShell:

```powershell
$env:API_KEY = python -c "import secrets; print(secrets.token_urlsafe(48))"
$env:HOST = "127.0.0.1"
$env:PORT = "8765"
$env:DB_PATH = "$PWD/toolkit.sqlite3"
python server.py
```

Open http://127.0.0.1:8765/tools. Keep the terminal open while using it. In this direct-run mode, the key exists in that terminal session; generate and retain it if you want to use authenticated API calls from another client.

## API key responsibilities

- `API_KEY` is the toolkit's own bearer token. Generate a separate random value for each independent deployment. Never put it in GitHub, screenshots, public messages, or frontend source.
- `OS_MAPS_API_KEY` is a third-party credential. The owner must create/access an OS Data Hub account, enable the OS Maps API and accept applicable terms. It is optional for all other toolkit features.
- Do not reuse the Render API key for a local or alternative-hosted instance.

## Data persistence and backups

The SQLite database stores the evidence and network ledger. In Docker Compose it lives in the persistent named volume `toolkit-data`; for direct Python it lives at the `DB_PATH` you set. Back up the database while the application is stopped, or use SQLite's backup API for a live backup. Keep backups outside the project directory and never commit a live database to GitHub.

## Tests

```sh
python -m compileall -q .
python -m unittest discover -s tests -v
```

The hosted Render service is optional. GitHub stores the source; your local copy and database are independent of Render. OS map tiles still depend on the external OS service and its API terms.
