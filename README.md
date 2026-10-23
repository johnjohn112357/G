# Research & Engineering Toolkit API

A lightweight Python HTTP API for engineering calculations and a persistent evidence/network ledger.

## Deploy on Render
- Runtime: Python
- Build command: `python -m compileall -q .`
- Start command: `python server.py`
- Plan: Free only unless separately approved
- Set environment variable `API_KEY` to a long random secret using Render's secret environment-variable UI. Never commit it.
- Set `HOST=0.0.0.0` (Render-facing bind) and let Render provide `PORT`.
- Set `DB_PATH=/var/data/toolkit.sqlite3` only if a persistent disk is attached and mounted at `/var/data`. Without a disk, SQLite data may be lost on restarts/redeploys.
- `/health` is public for health checks; all `/api/*` routes require `Authorization: Bearer <API_KEY>`.

## Endpoints
- `GET /health`
- `GET /api/evidence`, `POST /api/evidence`
- `GET /api/networks`, `POST /api/networks`
- `POST /api/calculate/battery-energy`: `{"voltage_v":48,"capacity_ah":20}`
- `POST /api/calculate/battery-sag`: `{"open_circuit_voltage_v":50,"current_a":10,"internal_resistance_ohm":0.1}`
- `POST /api/calculate/wheel-speed`: `{"rpm":500,"wheel_diameter_mm":200}`
- `POST /api/calculate/ohms-law`: provide any two of `voltage_v`, `current_a`, `resistance_ohm`
- `POST /api/calculate/voltage-drop`: `{"current_a":10,"resistance_ohm":0.02}`
- `POST /api/calculate/mechanical-power`: `{"torque_nm":10,"rpm":1000}`
- `POST /api/calculate/battery-runtime`: `{"capacity_ah":20,"current_a":5}` (ideal hours; real-world caveats returned)
- `POST /api/calculate/kinetic-energy`: `{"mass_kg":100,"speed_kmh":36}`
- `POST /api/calculate/torque-from-power`: `{"power_w":1000,"rpm":1000}`
- `POST /api/calculate/gear-ratio`: `{"input_rpm":3000,"output_rpm":1000}`
- `POST /api/calculate/wheel-circumference`: `{"wheel_diameter_mm":200}`
- `POST /api/calculate/resistor-divider`: `{"input_voltage_v":12,"r1_ohm":1000,"r2_ohm":1000}`
- `POST /api/calculate/led-resistor`: `{"supply_voltage_v":12,"led_forward_voltage_v":2,"led_current_ma":20}`
- `POST /api/calculate/solar-energy`: `{"panel_power_w":400,"peak_sun_hours":4,"system_efficiency":0.75}`
- `POST /api/calculate/thermal-expansion`: `{"length_m":2,"alpha_per_c":0.000012,"delta_temp_c":50}`
- `POST /api/calculate/pressure`: `{"force_n":100,"area_m2":0.01}`
- `POST /api/calculate/density`: `{"mass_kg":2,"volume_m3":0.001}`
- `POST /api/convert/unit`: `{"category":"speed","value":60,"from_unit":"mph","to_unit":"km/h"}` (also length, mass, pressure, energy, power, volume and temperature)


## Ordnance Survey (OS) Maps integration
- Open `/maps` while authenticated with the toolkit API key. The page uses Leaflet for display and requests tiles through the toolkit server.
- Set `OS_MAPS_API_KEY` in Render's environment-variable settings to an API key from your OS Data Hub account. Do not put the OS key in the repository or in browser code.
- The server proxies only the allow-listed OS raster styles `Leisure`, `Outdoor`, `Road`, and `Light` using the Web Mercator (`_3857`) tile service. Tile paths and zoom/coordinate bounds are validated.
- The OS key is not returned to the browser. Toolkit API authentication is required for the map page and tile requests.
- OS map tiles are not persistently cached by the toolkit. Do not scrape or bulk-download tiles. Confirm the OS Data Hub product terms, attribution requirements, API quota and intended use before relying on the integration.
- Without `OS_MAPS_API_KEY`, the map viewer loads but tile requests return a clear configuration error.

## Development checks
- Run locally: `python -m compileall -q .`
- Run regression suite: `python -m unittest discover -s tests -v`
- GitHub Actions runs compilation and regression tests on pushes to the main and toolkit development branches, and on pull requests to main.

## Safety and limits
Calculations are idealised engineering estimates, not safety certifications. Validate inputs and independent assumptions before use. API key auth and in-process rate limiting are basic safeguards, not a substitute for a production gateway/WAF. Do not expose without setting a strong API key. Free hosting may sleep and does not imply durable storage.
