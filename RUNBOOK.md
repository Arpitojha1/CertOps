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

---

## step-ca `.vlog` corruption after unclean shutdown

### Symptom
`step-ca` fails to start with an error referencing Badger database corruption,
or hangs indefinitely. The file `C:\Users\Arpit\.step\db\000000.vlog` is
pre-allocated at 2GB but contains only partial data.

### Likely cause
`step-ca` uses Badger v2 as its internal database. When `step-ca` is killed
(force-closed, SIGKILL, machine crash, or closing the terminal window without
graceful shutdown), Badger's value log file may not be truncated to its actual
content length. The next startup sees a 2GB file with garbage at the end and
refuses to operate.

### Recovery steps

1. **Stop `step-ca`** if it's still running (or confirm it's dead).

2. **Check the Badger config** in `C:\Users\Arpit\.step\config\ca.json`:
   ```json
   {
     "db": {
       "badgerValueLogTruncate": true
     }
   }
   ```
   If this key is missing or `false`, add/set it to `true`. This tells Badger
   to automatically truncate uncommitted trailing bytes on startup.

3. **Restart `step-ca`** with the corrected config. If Badger auto-truncates
   successfully, `step-ca` should start normally.

4. **If auto-truncation fails** (still won't start):
   - Back up the entire `C:\Users\Arpit\.step\db\` directory.
   - Delete the `.vlog` file (`000000.vlog`).
   - Restart `step-ca`. Badger will recreate the log file from the manifest.
   - **Warning:** this may lose the most recent uncommitted certificate issuance
     records. Certificates already issued and returned to the caller are not
     affected (they exist in the certificate files and Vault/secret store).

5. **Verify** `step-ca` is serving:
   ```powershell
   curl.exe -k https://localhost:8443/health
   ```
   A 200 response confirms recovery.

### Prevention
Always shut down `step-ca` gracefully (Ctrl+C in its terminal window, not
closing the window). The `badgerValueLogTruncate: true` config is the safety
net, not a substitute for graceful shutdown.

---

## Celery worker crash mid-pipeline: operational recovery

### Context
The Celery worker runs a three-stage chained pipeline:
`Renew → Deploy → Reload+Verify`. If the worker process is killed mid-pipeline,
the pipeline state is persisted in SQLite (`certificates.pipeline_stage`) at
each stage transition. Recovery is automatic on the next worker startup.

### What happens on crash
1. The `@worker_ready.connect` signal fires when a new Celery worker starts.
2. `on_worker_ready()` in `src/tasks.py` calls `resume_all_pending_pipelines()`.
3. This queries `certops.db` for any certificate with `pipeline_stage IN
   ('Renewed', 'Deployed pending reload')`.
4. Each found certificate is resumed from its persisted DB stage via
   `resume_pipeline_from_db()`.

### Recovery behavior by crash point

| Crash stage | DB state after crash | Recovery action |
|---|---|---|
| During Stage 1 (issuance) | `pipeline_stage` unchanged or `NULL` | Full pipeline re-run (idempotent) |
| After Stage 1, before Stage 2 | `Issued pending deploy` | Re-run from Stage 1 (idempotent — skips if pending cert already staged) |
| During Stage 2 (deploy) | `Issued pending deploy` | Stage 2 re-runs (writes are idempotent via write-then-rename) |
| After Stage 2, before Stage 3 | `Deployed pending reload` | Skips directly to Stage 3 (cert already on disk) |
| During Stage 3 (verify) | `Deployed pending reload` | Stage 3 re-runs (reload + verify) |

### Verification
The recovery mechanism was verified with a real OS subprocess kill test
(Gate 1 evidence in `session_context.md §16`):
- Worker subprocess #1 started, DB state seeded to `Deployed pending reload`.
- Worker #1 killed with `kill()`.
- New worker #2 started — `@worker_ready` signal automatically advanced
  pipeline_stage to `Reload confirmed` without human intervention.

### If recovery fails
If the automatic resume doesn't complete (e.g., `step-ca` is down, or the
host is unreachable), the pipeline will remain in its current stage. On the
*next* worker restart, the same recovery logic runs again. There is no retry
limit — the pipeline will keep attempting recovery on each worker restart
until it completes or the cert is manually intervened upon.

---

## SQLite hygiene

### WAL mode
`db.py:get_db_connection()` enables WAL (Write-Ahead Logging) mode on every
connection:

```sql
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
```

WAL mode allows concurrent reads while a write is in progress, which is
essential when FastAPI (HTTP requests) and the Celery worker (background
tasks) access the same SQLite file simultaneously.

### Known limitation: runtime migrations
Schema changes (`ALTER TABLE ADD COLUMN`) run inside `get_db_connection()` on
every call. This is functional but not clean:

- It works because SQLite `ALTER TABLE ADD COLUMN` is idempotent (fails
  silently if column already exists via the `PRAGMA table_info` check).
- It will not scale to complex migrations (column type changes, index
  additions, table renames).
- **Planned fix:** move migrations to a versioned script (Alembic or manual
  SQL files) run once at deploy time, not on every connection.

### WAL file management
SQLite WAL mode creates `-wal` and `-shm` files alongside the main `.db`
file. These are normal and should not be deleted while the database is
in use. If you need to compact the database:

```sql
PRAGMA wal_checkpoint(TRUNCATE);
```

This forces the WAL file to be truncated. Only run this when no concurrent
writers are active (e.g., with the Celery worker and API server both stopped).

### Backup
To back up a running SQLite database without locking:

```powershell
python -c "import sqlite3; src=sqlite3.connect('certops.db'); dst=sqlite3.connect('certops-backup.db'); src.backup(dst); dst.close(); src.close()"
```
