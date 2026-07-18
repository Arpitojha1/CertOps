# CertOps — Clean-Machine Setup & Installation Guide

This guide takes you from a bare host to a fully verified, running `certops-agent` renewal loop and local development dashboard (`certops-dashboard`). Every step includes both POSIX (`bash`) and Windows (`powershell`) commands, exact expected outputs, and known troubleshooting notes.

---

## Prerequisites

- **Python:** `3.11` or higher (`python --version`)
- **Node.js & npm:** `18.0` or higher (`node -v`, required only if developing/running the `certops-dashboard` UI)
- **Docker & Docker Compose:** Required to run local HashiCorp Vault (`certops-vault-1`) and Nginx (`certops-nginx-1`) verification containers.
- **Smallstep (`step-ca`):** Required for local Certificate Authority issuance. Download and put `step.exe` (Windows) or `step` (Linux/macOS) in your system `PATH`.

---

## Step 1: Clone Repository & Virtual Environment Bootstrap

### POSIX (bash)
```bash
git clone https://github.com/Arpitojha1/clm.git certops && cd certops
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

### Windows (PowerShell)
```powershell
git clone https://github.com/Arpitojha1/clm.git certops; cd certops
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

**Expected Output:** Clean installation of dependencies (`requests`, `paramiko`, `pywinrm`, `azure-identity`, `azure-keyvault-secrets`, `fastapi`, `uvicorn`, `celery`, `redis`, `pyjwt`, `passlib`).

---

## Step 2: Start Local Verification Infrastructure (Vault & Nginx)

Start the local HashiCorp Vault instance (port `8200`, root token `root`) and target Nginx reverse proxy (port `443`, bind-mounting `./` to `/etc/nginx/certs:ro`):

### POSIX & Windows
```bash
docker compose up -d certops-vault-1 certops-nginx-1
docker ps
```

**Expected Output:**
```
CONTAINER ID   IMAGE                  STATUS          PORTS                  NAMES
xxxxxxxxxxxx   nginx:alpine           Up 5 seconds    0.0.0.0:443->443/tcp   certops-nginx-1
yyyyyyyyyyyy   hashicorp/vault:latest Up 5 seconds    0.0.0.0:8200->8200/tcp certops-vault-1
```

---

## Step 3: Initialize Local Smallstep Certificate Authority (`step-ca`)

Create a local JWK provisioner (`admin`) authenticated via password file (`pass.txt`):

### POSIX (bash)
```bash
echo -n "CertOpsSuperSecretPassword2026!" > pass.txt
step ca init --name "CertOps Local CA" --dns "localhost" --address "127.0.0.1:8443" --provisioner "admin" --password-file pass.txt
step-ca $(step path)/config/ca.json --password-file pass.txt &
```

### Windows (PowerShell)
```powershell
[IO.File]::WriteAllText("pass.txt", "CertOpsSuperSecretPassword2026!")
step ca init --name "CertOps Local CA" --dns "localhost" --address "127.0.0.1:8443" --provisioner "admin" --password-file pass.txt
Start-Process -FilePath "step-ca" -ArgumentList "$env:USERPROFILE\.step\config\ca.json --password-file pass.txt" -NoNewWindow
```

**Expected Output:** `step-ca` listening on `https://127.0.0.1:8443`. To extract your root CA fingerprint for `.env`:
```bash
step certificate fingerprint $(step path)/certs/root_ca.crt
```
Update `STEP_CA_FINGERPRINT` in `.env` with the printed SHA-256 hex string.

---

## Step 4: Seed Dashboard Database & Start Backend API Server

Initialize the database schema (`user_version: 7`) and create the initial global administrator account (`admin@example.com`):

> [!WARNING]
> **Security Warning:** By default, `seed_admin.py` reads `ADMIN_EMAIL=admin@example.com` and `ADMIN_PASSWORD=change-me` from `.env.example`. **Change `ADMIN_PASSWORD` immediately in `.env` — never use default credentials in a real deployment.**

### POSIX (bash)
```bash
python certops-dashboard/src/seed_admin.py
uvicorn certops-dashboard.src.api:app --host 0.0.0.0 --port 8000 --reload &
```

### Windows (PowerShell)
```powershell
python certops-dashboard/src/seed_admin.py
Start-Process -FilePath ".\venv\Scripts\python.exe" -ArgumentList "-m uvicorn certops-dashboard.src.api:app --host 0.0.0.0 --port 8000 --reload" -NoNewWindow
```

**Expected Output from `seed_admin.py`:**
```
Applied migration to version 7
Admin seeded successfully: admin@example.com (Plan: Enterprise)
```
**Expected Output from `uvicorn`:**
```
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     [Scheduler] Background scheduler loop initialized (check interval: 3600s).
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

## Step 5: Start Modern Dashboard Frontend (`frontendNew`)

### POSIX & Windows
```bash
cd certops-dashboard/frontendNew
npm install
npm run dev
```

**Expected Output:**
```
  VITE v5.4.x  ready in 450 ms

  ➜  Local:   http://localhost:3000/
```
Open `http://localhost:3000/` and log in with email `admin@example.com` and password `change-me` (or the `ADMIN_PASSWORD` defined in `.env`).

---

## Known Troubleshooting & Failure Modes

### 1. Smallstep (`step-ca`) `.vlog` File Corruption on Windows
If `step-ca` crashes on startup on Windows with `bad value` or `corrupted badger log`, delete the Badger database transaction log and restart `step-ca`:
```powershell
Remove-Item -Recurse -Force "$env:USERPROFILE\.step\db"
step-ca "$env:USERPROFILE\.step\config\ca.json" --password-file pass.txt
```

### 2. SQLite Concurrency File Locks (`sqlite3.OperationalError: database is locked`)
If running test suites or multi-worker pipelines simultaneously against a single local database file on Windows, SQLite may raise `database is locked` or `WinError 32`.
- **Fix:** Ensure all Celery workers and FastAPI threads access `certops.db` via our thread-safe pooled connection wrapper (`_db_conn` with `RLock` in `db.py`) which enforces Write-Ahead Logging (`PRAGMA journal_mode=WAL`) and a 10-second busy timeout (`busy_timeout=10000`).

### 3. Azure Key Vault Token Expiry (`azure.identity.CredentialUnavailableError` / `AADSTS7000222`)
If the Azure connector fails during `test_connection()` or renewal with `DefaultAzureCredential failed to retrieve a token` or `AADSTS7000222: The provided client secret keys for app are expired`:
- **Fix:** Re-run `az login` (if using Azure CLI auth) or verify that `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET` in `.env` contain valid, unexpired credentials.
