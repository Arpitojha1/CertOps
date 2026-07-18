# CertOps Agent (`certops-agent`) — Standalone Operations & Configuration Guide

`certops-agent` is an open-source (Apache-2.0) certificate renewal engine designed to run directly on your target infrastructure (virtual machines, bare-metal servers, or private cloud networks). It operates **100% independently of any hosted dashboard** to discover, renew, deploy, reload, and verify certificates.

If you are self-hosting `certops-agent` standalone without connecting to our commercial cloud dashboard, this guide provides the authoritative operating instructions.

---

## 1. What the Agent Does Standalone

When executed on your host (`python certops-agent/src/main.py`), the agent runs a self-contained renewal cycle:
1. **Reads Active Connectors:** Queries the local SQLite database (`agent.db` / `certops.db`) for enabled `Secret Store` and `Host` connectors.
2. **Evaluates Expiry:** Inspects current X.509 certificate lifetimes against `renewal_threshold_days`. If remaining validity is greater than the threshold, it logs cleanly and short-circuits.
3. **Issues Certificates:** Invokes your local Certificate Authority (`step-ca`) via CLI subprocess (`ca_client.py`) to generate a fresh X.509 certificate and private key.
4. **Deploys Atomically:** Writes the new certificate and key to target secret stores (HashiCorp Vault or Azure Key Vault) or host filesystems (`local.crt`, `local.key`). Host file updates use atomic replacement (`local.crt.tmp` -> `os.replace`) with an automatic `.bak` rollback backup.
5. **Reloads & Verifies:** Executes reverse proxy worker reloads (`nginx -s reload` / IIS recycles) and opens a live raw TLS socket (`verify.get_live_cert_info()`) to `host:port` to confirm that the actively served certificate matches the new SHA-256 fingerprint.

---

## 2. Configuration & Environment Variables (`.env`)

For standalone operation, configure the following variables inside your local `.env` file (copy from `.env.example`):

### Production / Standalone Variables
```ini
# --- Local SQLite Storage ---
CERTOPS_DB_PATH=./certops.db

# --- HashiCorp Vault Connector Config ---
VAULT_ADDR=http://localhost:8200
VAULT_TOKEN=root
VAULT_CERT_PATH=secret/local-certs

# --- Smallstep (step-ca) Authority Config ---
STEP_CA_URL=https://localhost:8443
STEP_CA_PASSWORD_FILE=./pass.txt
STEP_CA_FINGERPRINT=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# --- Target Host & Reverse Proxy Config ---
NGINX_CONTAINER_NAME=certops-nginx-1
DEPLOY_CERT_PATH=./local.crt
DEPLOY_KEY_PATH=./local.key
RENEWAL_THRESHOLD_DAYS=30

# --- Live TLS Verification Config ---
VERIFY_HOST=127.0.0.1
VERIFY_PORT=443
```

### Development & Test-Only Variables (Do Not Set in Production)
```ini
# When set to true, forces immediate test expiration or accelerates scheduler loops during test runs
CERTOPS_TEST_STAGE_DELAY_SECONDS=0
CERTOPS_IGNORE_VERIFY_SSL=false
```

---

## 3. Running the Renewal Loop Standalone

You can execute the renewal loop manually, via cron/Windows Task Scheduler, or as an ongoing Celery background worker:

### Manual One-Shot Execution

#### POSIX (bash)
```bash
source venv/bin/activate
python certops-agent/src/main.py
```

#### Windows (PowerShell)
```powershell
.\venv\Scripts\Activate.ps1
python certops-agent/src/main.py
```

### Verified Healthy Terminal Output (`main.py:707-715`)
When run on a host with active connectors, `main.py` outputs:
```
======================================================================
RENEWAL LOOP SUMMARY
======================================================================
Connector: vault_store  | Succeeded: 1 | Skipped: 0 | Failed: 0
Connector: ssh_nginx_01 | Succeeded: 1 | Skipped: 0 | Failed: 0
======================================================================
```
*(Note: Because `AGENT_TOKEN` and `INGEST_URL` are unset in standalone mode, `_try_push_telemetry()` cleanly short-circuits with zero push errors).*

---

## 4. Standalone Connector Setup (Direct Database Configuration)

Because environment-variable fallback discovery (`from_env()`) has been retired in favor of strict DB-authoritative records, all connectors monitored by the renewal loop must be registered in your local database (`certops.db`).

You can register connectors programmatically or via our verified interactive setup wizard:

### Using the Interactive Setup Wizard (`main.py setup --agent-db`)

#### POSIX & Windows
```bash
python certops-agent/src/main.py setup --agent-db ./certops.db
```
Follow the interactive prompts to configure HashiCorp Vault, Azure Key Vault, SSH hosts, or WinRM hosts directly into `certops.db`.

### Programmatic Registration via Python Snippet
```python
import sqlite3, json

conn = sqlite3.connect("certops.db")
cursor = conn.cursor()

# Register an SSH / Nginx Host Connector
config = {
    "hostname": "web-01.internal",
    "port": 22,
    "username": "deploy",
    "password": "SuperSecretHostPassword!",
    "nginx_conf_dir": "/etc/nginx/certs"
}

cursor.execute("""
    INSERT OR REPLACE INTO connectors (id, name, category, config, renewal_threshold_days, is_active, tenant_id)
    VALUES (?, ?, ?, ?, ?, ?, ?)
""", ("conn_ssh_01", "Production Web Nginx", "Host", json.dumps(config), 30, 1, "default"))

conn.commit()
conn.close()
```

---

## 5. Optional: Connecting to a Hosted Dashboard (Telemetry Push)

If you later decide to connect your standalone agent to a self-hosted or commercial `certops-dashboard` instance to view central fleet health:

1. Register the agent with the dashboard API to obtain an `AGENT_TOKEN` (see [USAGE.md](USAGE.md)).
2. Add your token and dashboard URL to the agent's `.env` file:
   ```ini
   DASHBOARD_URL=http://localhost:8000
   INGEST_URL=http://localhost:8000/api/telemetry/ingest
   AGENT_TOKEN=eyJhZ2VudF9pZCI6InByb2QtYWdlbnQtMDEiLCJleHAiOjE4MDAwMDAwMDB9.xxxxxxxxxxxx
   ```
3. On the very next execution of `python certops-agent/src/main.py`, `_try_push_telemetry()` will automatically collect sanitized connector health and usage metrics (`agent_telemetry.py`) and transmit them over HTTPS to your dashboard using `Authorization: Bearer <AGENT_TOKEN>`.

**Privacy Guarantee (`TELEMETRY_CONTRACT.md`):** Telemetry push is strictly additive. The agent strips all private keys, passwords, Azure client secrets, and internal hostnames from the payload before sending (`agent_telemetry.build_payload()`).

---

## 6. Standalone Troubleshooting & Known Rough Edges

### 1. Smallstep (`step-ca`) `.vlog` File Corruption on Windows
When running `step-ca` on Windows, improper process termination (or system reboots) can corrupt the Badger database transaction log (`ca.json.vlog`), causing `step-ca` to crash on startup with `bad value` or `corrupted log`.
- **Fix:** Delete the corrupted Badger database directory and restart `step-ca`:
  ```powershell
  Remove-Item -Recurse -Force "$env:USERPROFILE\.step\db"
  step-ca "$env:USERPROFILE\.step\config\ca.json" --password-file pass.txt
  ```

### 2. SQLite File-Lock Behavior Under Concurrent Celery Workers
If running `certops-agent` with multiple background Celery workers alongside interactive test scripts against a single `certops.db` file on Windows, you may encounter `sqlite3.OperationalError: database is locked`.
- **Fix:** Our agent code mitigates this by wrapping all database calls in `agent_db.py` and `db.py` with a thread-safe `RLock` singleton (`_db_conn`) and enabling Write-Ahead Logging (`journal_mode=WAL`). Ensure you never open `certops.db` in third-party GUI viewers (like DB Browser for SQLite) with exclusive write locks while `main.py` is actively executing.

### 3. Azure Key Vault Credential Expiry Symptoms (`AADSTS7000222`)
If an active `azure` connector begins failing with `DefaultAzureCredential failed to retrieve a token from the included credentials` or `ClientSecretCredential authentication failed: AADSTS7000222`:
- **Root Cause:** Your local Azure CLI `az login` token has expired, or the Azure Active Directory service principal client secret (`AZURE_CLIENT_SECRET`) has passed its expiration date.
- **Fix:** Run `az login --tenant <AZURE_TENANT_ID>` on the host machine, or rotate your service principal client secret in the Azure Portal and update `connectors.config` inside `certops.db`.
