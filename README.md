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

## Safety and limits
Calculations are idealised engineering estimates, not safety certifications. Validate inputs and independent assumptions before use. API key auth and in-process rate limiting are basic safeguards, not a substitute for a production gateway/WAF. Do not expose without setting a strong API key. Free hosting may sleep and does not imply durable storage.
