# CertOps — Local Environment Startup Runbook

Purpose: get from a cold machine to "main.py can run the renewal loop" without live debugging during a demo. Follow in order — each step depends on the previous one being fully up, not just started.

## 0. First-time setup: seed the admin account

After filling in `.env` (copy from `.env.example`), run once to create the initial admin user:

```powershell
cd C:\Arpit\CertOps
.\venv\Scripts\python.exe src/seed_admin.py
```

Required env vars: `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `JWT_SECRET`. Re-running is safe (exits cleanly if already exists).

## 0b. Start the API server

```powershell
.\venv\Scripts\python.exe -m uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload
```

Or directly:
```powershell
.\venv\Scripts\python.exe src/api.py
```

The Vite dev server proxies `/api/*` and `/auth/*` to `http://localhost:8000`, so the frontend only needs to know about port 3000.

## 1. Start Docker Desktop
Docker Desktop is not always running on boot. Start it and wait for the engine, not just the window, to be ready.

```powershell
Start-Process 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
```

Confirm the engine is actually up (not just the process existing) before moving on:

```powershell
docker context use desktop-linux
docker ps
```

If `docker ps` errors or hangs, wait and retry — Docker Desktop's engine takes longer to be ready than the Docker Desktop window/process does. Don't proceed to step 2 until `docker ps` returns cleanly.

## 2. Bring up Dockerized services
```powershell
docker compose up -d
```
This brings up whatever is defined in `docker-compose.yml` (HashiCorp Vault dev server / Nginx / other Phase 1 infra). Confirm Vault is actually reachable before moving on — don't assume "the container started" means "the service inside is ready":

```powershell
python.exe -c "import requests; print(requests.get('http://localhost:8200/v1/secret/metadata?list=true', headers={'X-Vault-Token': 'root'}).status_code)"
```

A 200 (or 404 for an empty path, but NOT a connection error) means Vault is up.

## 3. Start step-ca
`step-ca` is not Dockerized — it runs natively and needs to be started manually, pointed at its config and password file:

```powershell
& 'C:\Users\Arpit\AppData\Local\Microsoft\WinGet\Packages\Smallstep.step-ca_Microsoft.Winget.Source_8wekyb3d8bbwe\step-ca.exe' $env:USERPROFILE\.step\config\ca.json --password-file C:\Users\Arpit\certOps\pass.txt
```

Run this in its own terminal/window (or background it) — it's a long-running foreground process, not a one-shot command. If `step-ca`'s log file gets written mid-session, note it's UTF-16LE encoded on this machine, not UTF-8, if you ever need to tail it manually.

## 4. Confirm .env is present and correct
Required for both vault clients:
- `VAULT_ADDR`, `VAULT_TOKEN` (HashiCorp)
- `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_KEYVAULT_URL` (Azure)

Quick sanity check without printing secrets:
```powershell
python.exe -c "import os; from dotenv import load_dotenv; load_dotenv(); print(all(os.getenv(v) for v in ['VAULT_ADDR','VAULT_TOKEN','AZURE_TENANT_ID','AZURE_CLIENT_ID','AZURE_CLIENT_SECRET','AZURE_KEYVAULT_URL']))"
```
Should print `True`.

## 5. Run the loop
Once steps 1–4 all check out clean, `main.py`'s renewal loop is safe to run live. Running it before Vault/`step-ca` are actually ready (not just "started") is the most likely source of a confusing live failure — the symptoms look like a code bug but are actually a startup-ordering issue.

## Known Limitations

- **Live-renewal smoke test: PENDING** — The end-to-end smoke test (Docker/Vault/step-ca up, real certificate renewal, audit log verified after) is paused. This machine does not have Docker/Vault/step-ca services running during this session. To be run on the primary dev machine before claiming Phase 1 end-to-end verification. Do not mark it as passed until it is actually run.
- **Phase 3.4 scheduler write path**: The `smoke test confirmed` status recorded in session context predates the `timedelta` import bug fix in `db.py`. The scheduler's `next_renewal_at` write path was unverified until the fix was applied.
- **ConnectorsPage still uses mockData**: The `/connectors` route was not wired to a real API in this session. Connector health/status data is still from `lib/mockData.ts`.

## Known friction points (from bringing this up cold)
- Docker Desktop's engine readiness lags behind the process/window appearing — always verify with `docker ps`, never assume it's ready right after launch.
- `step-ca` must be started manually every session; it is not part of `docker compose up`.
- **`step-ca` Badger database recovery after unclean shutdown**: If `step-ca` is terminated forcefully without graceful shutdown, its Badger v2 database (`C:\Users\Arpit\.step\db\000000.vlog`) may remain pre-allocated at 2GB un-truncated. Ensure `"badgerValueLogTruncate": true` is set under `"db"` in `C:\Users\Arpit\.step\config\ca.json` so Badger automatically truncates uncommitted trailing bytes on startup rather than refusing to start.
- If a fresh terminal window doesn't have the right Python on PATH, confirm with `where python` / `Get-Command python` before assuming a script failure is a code issue rather than an environment issue.
