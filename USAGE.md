# CertOps — Dashboard Operations & Multi-Tenancy Guide

This guide covers operating the commercial `certops-dashboard` UI (`http://localhost:3000`), registering agents, managing connectors across multi-tenant scopes, and understanding subscription entitlement tiers.

---

## 1. Dashboard Architecture: API vs. UI Responsibilities

| Responsibility | Dashboard UI (`frontendNew/`) | Backend API Server (`src/api.py`) |
| :--- | :--- | :--- |
| **Authentication** | Renders login page and stores session context. | Validates credentials, sets `httpOnly` JWT cookie (`certops_token`), enforces `require_admin`. |
| **Tenant Scoping** | Sends `X-Tenant-Id` header with requests based on user scope. | Enforces data ownership (`require_owned_entity`); filters queries (`db.list_certificates(tenant_id=...)`). |
| **Connector Config** | Collects connector parameters (`name`, `category`, `config` JSON). | Persists DB-authoritative connector records and executes `connector.test_connection()`. |
| **Telemetry Ingestion** | Displays fleet status cards, expiries, and activity logs. | Ingests agent telemetry (`POST /api/telemetry/ingest`) via `AGENT_TOKEN` auth (`agent_auth.py`). |
| **Entitlement Gating** | Renders enterprise UI or fallback upgrade prompts (`Upgrade.tsx`). | Enforces server-side plan checks (`require_plan("Enterprise")` across `/api/enterprise/*`). |

---

## 2. Registering a Remote Agent with the Dashboard

Because `certops-agent` never transmits user passwords, each agent instance authenticates with the dashboard ingestion endpoint (`/api/telemetry/ingest`) using a dedicated, cryptographically signed `AGENT_TOKEN`.

To register a new agent and generate an `AGENT_TOKEN`, authenticate as a dashboard administrator (`admin@example.com` / `change-me`) and issue a `POST /api/agents/register` request:

### POSIX (bash)
```bash
# 1. Log in to obtain your certops_token cookie
curl -i -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"change-me"}' -c cookies.txt

# 2. Register the remote agent
curl -X POST http://localhost:8000/api/agents/register \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"agent_id":"prod-web-agent-01","hostname":"web-01.internal"}'
```

### Windows (PowerShell)
```powershell
# 1. Log in and capture session cookie
$loginBody = @{ email = "admin@example.com"; password = "change-me" } | ConvertTo-Json
$sess = Invoke-WebRequest -Uri "http://localhost:8000/auth/login" -Method POST -Body $loginBody -ContentType "application/json" -SessionVariable certopsSess

# 2. Register the remote agent
$regBody = @{ agent_id = "prod-web-agent-01"; hostname = "web-01.internal" } | ConvertTo-Json
$res = Invoke-RestMethod -Uri "http://localhost:8000/api/agents/register" -Method POST -Body $regBody -ContentType "application/json" -WebSession $certopsSess
$res.token | Out-File -FilePath "agent_token.txt"
```

**Expected Response JSON:**
```json
{
  "status": "registered",
  "agent_id": "prod-web-agent-01",
  "token": "eyJhZ2VudF9pZCI6InByb2Qtd2ViLWFnZW50LTAxIiwiZXhwIjoxODAwMDAwMDAwfQ.xxxxxxxxxxxx"
}
```
Copy the returned `token` and configure it on the remote agent host inside its `.env` file as `AGENT_TOKEN=eyJh...` (or via `python certops-agent/src/main.py setup`).

---

## 3. Adding Connectors via the Dashboard

Connectors define where active certificates are stored (`Secret Store`) and where reverse proxy worker processes must be reloaded (`Host`).

1. Navigate to **Connectors** in the left sidebar (`http://localhost:3000/connectors`).
2. Click **Add Connector**.
3. Select the **Category** (`Secret Store`, `Host`, or `CA`) and provide the configuration JSON payload matching the target provider:

### Example Configuration Payloads
- **HashiCorp Vault (`Secret Store`):**
  ```json
  { "url": "http://localhost:8200", "token": "root", "mount": "secret", "prefix": "local-certs" }
  ```
- **Azure Key Vault (`Secret Store`):**
  ```json
  { "keyvault_url": "https://my-vault.vault.azure.net/", "tenant_id": "...", "client_id": "...", "client_secret": "..." }
  ```
- **SSH / Nginx Host (`Host`):**
  ```json
  { "hostname": "web-01.internal", "port": 22, "username": "deploy", "password": "...", "nginx_conf_dir": "/etc/nginx/certs" }
  ```
- **WinRM / IIS Host (`Host`):**
  ```json
  { "hostname": "iis-01.internal", "port": 5985, "username": "Administrator", "password": "...", "auth_type": "ntlm", "iis_site_name": "Default Web Site" }
  ```

Click **Test Connection** (`POST /api/connectors/{id}/test`). The dashboard instructs the backend to perform a live probe (`connector.test_connection()`) and displays `Connected` upon success.

---

## 4. Triggering & Watching the Renewal Pipeline

When a certificate's remaining validity falls below its `renewal_threshold_days` (or when manually triggered by clicking **Force Renew** on the **Certificates** page):

1. **Stage 1 (`Issued pending deploy`):** `task_renew_certificate` issues a fresh X.509 certificate via Smallstep (`step-ca`) and writes the raw PEM strings atomically into database staging columns (`pending_cert_pem`, `pending_cert_key`).
2. **Stage 2 (`Deployed pending reload`):** `task_deploy_certificate` writes the certificate and private key to the target secret store or host filesystem (`local.crt.tmp` -> `os.replace` with `.bak` rollback backup).
3. **Stage 3 (`Reload confirmed`):** `task_verify_reload` executes the service reload command on the target host (`nginx -s reload` / IIS recycle) and initiates the **Live TLS Verification Loop**. It opens a raw socket (`ssl.CERT_NONE`, `check_hostname=False`) to the target `host:port` every 0.5 seconds for up to 5 seconds until the live served X.509 SHA-256 fingerprint matches the newly issued certificate.

You can monitor these transitions in real time under **Activity Log** (`http://localhost:3000/activity`) or via the API (`GET /api/renewal-log`).

---

## 5. Subscription Entitlement Tiers & Plan Gating

The CertOps dashboard enforces strict server-side subscription tier access controls (`require_plan(required_plan: str)` in `auth.py`). Every user account is assigned a `plan` (`Starter`, `Professional`, or `Enterprise`) inside the `users` database table.

### Tier Boundaries
- **`Starter` & `Professional` Tiers:** Have access to all standard fleet monitoring pages (`Dashboard`, `Certificates`, `Connectors`, `Activity`, `Groups`, `Notifications`, `Scheduler`, `Settings`).
- **`Enterprise` Tier Only (`/api/enterprise/*`):** Required to access advanced fleet automation features, including:
  - Bulk Certificate Actions (`POST /api/certificates/bulk-renew`, `bulk-revoke`)
  - Automated CIDR Network Discovery & Scanning (`GET/POST /api/enterprise/discovery/*`)
  - Multi-CA Uptime & Error Rate Health Monitoring (`GET /api/enterprise/health/*`)
  - Granular CA Restriction Policies (`GET/POST /api/enterprise/ca-policies`)
  - Long-Term Issuance vs. Expiration Volume Insights (`GET /api/enterprise/insights/*`)

### Understanding `403 Forbidden` Responses
If a `Starter` user attempts to navigate to an Enterprise page (e.g., **Discovery** or **CA Health**) or directly calls an `/api/enterprise/*` endpoint via `curl`, the FastAPI server immediately rejects the request with HTTP status `403 Forbidden` (`{"detail": "This feature requires the Enterprise plan"}`). The web UI intercepts this state and renders the clean upgrade onboarding prompt (`Upgrade.tsx`).

Administrators can elevate an account's plan tier via the administration API:
```bash
curl -X PUT http://localhost:8000/api/users/<user_id>/plan \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"plan":"Enterprise"}'
```
