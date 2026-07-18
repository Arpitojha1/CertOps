# CertOps

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

**CertOps provides verified last-mile certificate delivery for Nginx and IIS fleets that HashiCorp Vault and Azure Key Vault cannot reach on their own, and that `cert-manager` does not cover because they run outside Kubernetes.**

While traditional Certificate Lifecycle Management (CLM) platforms focus on policy administration, and secret stores excel at safe storage, neither guarantees what matters most: **that the reverse proxy on disk has actually reloaded its worker processes and is actively serving the newly issued X.509 certificate over TLS.** CertOps closes this gap with strict, verifiable last-mile automation.

---

## What It Does Today (Verified Reality)

CertOps operates a deterministic, crash-resilient five-stage pipeline:
1. **Discovery:** Scans target secret stores or host directories and monitors expiration against configurable thresholds (tracked to 4 decimal places to eliminate rounding drift across loop iterations).
2. **Renewal:** Issues certificates via a local Smallstep (`step-ca`) authority using JWK provisioner authentication (`ca_client.py`).
3. **Staging & Rollback Hatch:** Persists pending certificates atomically to database state (`pending_cert_*`). Before overwriting active host files (`local.crt`, `local.key`), it backs up existing files to `.bak` and writes via `.tmp` -> `os.replace` atomic replacement (`deployer.py`).
4. **Service Reload:** Triggers reverse proxy worker reloads directly on target hosts (`docker exec <nginx> nginx -s reload` or IIS Application Pool recycles via WinRM).
5. **Live TLS Handshake Verification:** Never assumes an API write or reload command succeeded. Opens a raw TLS socket (`verify.get_live_cert_info()`) to the target host and port (`VERIFY_HOST:VERIFY_PORT`) to assert that the served SHA-256 certificate fingerprint matches the newly issued artifact.

### Verified Working Connectors
- **Secret Store Connectors:** HashiCorp Vault KV v2 REST (`vault_client.py`), Azure Key Vault (`azurekeyvault.py`).
- **Host Connectors:** SSH / Nginx Host (`host_connector.py` via `paramiko`), WinRM / IIS Host (`host_connector.py` via `pywinrm`).
- **Certificate Authority:** Smallstep (`step-ca` via `ca_client.py`).

---

## What It Explicitly Does Not Do Yet (Known Gaps)

In strict adherence to our **Evidence Over Prose** standard, we state plainly what is currently deferred:
- **No ACME / Public CA in Production Pipeline:** While an `ACMEIssuer` class exists with full unit coverage, production execution currently supports Smallstep (`step-ca`) only. Let's Encrypt / DigiCert / GlobalSign are not yet active in the renewal loop.
- **No Real Payment / Billing Processing:** The dashboard checkout UI (`Pricing.tsx`) is mocked. There is no Stripe, LemonSqueezy, or automated payment processing.
- **No Full Server-Side Multi-Organization Hierarchy:** While all read and mutating API endpoints enforce `X-Tenant-Id` scoping and ownership verification (`require_owned_entity`), self-serve multi-organization creation and cross-org admin consoles are unbuilt.
- **No External Notification Transports:** Notification events (`notifier.py`) are recorded directly into the SQLite `activity_log` table and stdout. Slack, Teams, PagerDuty, and SMTP drivers are scaffolded but inactive.
- **No Real-Time WebSocket / SSE Streaming:** Dashboard progress indicators and scheduler timers rely on client-side polling (`GET /api/scheduler/status`, `GET /api/renewal-log`) rather than live WebSocket (`/api/ws`) push.
- **No Interactive CLI Registration Helper:** Registering an agent with the dashboard requires sending a raw `POST /api/agents/register` request (`curl` / `Invoke-RestMethod`); a convenience command (`certops register --token ...`) is not yet implemented.

---

## Architecture & Repository Split

```
+-----------------------------------------------------------------------------+
|                          CLIENT INFRASTRUCTURE                              |
|                                                                             |
|  +-----------------------------------------------------------------------+  |
|  |                        certops-agent/ (OSS)                           |  |
|  |  [Scheduler] <--> [Celery Worker Pipeline] <--> [Local SQLite DB]     |  |
|  |                                                                       |  |
|  |  Connectors (Direct execution on client network):                     |  |
|  |  [HashiCorp Vault]  [Azure Key Vault]  [SSH/Nginx Host]  [WinRM Host] |  |
|  |  [step-ca Client]                                                     |  |
|  +-----------------------------------------------------------------------+  |
+--------------------------------------|--------------------------------------+
                                       |
                   Telemetry Only (per TELEMETRY_CONTRACT.md)
                   - Strips private keys, credentials, and host configs
                   - Transmits only connector health, cert CN/SAN, and error codes
                                       |
                                       v
+-----------------------------------------------------------------------------+
|                      CERTOPS-HOSTED INFRASTRUCTURE                          |
|                                                                             |
|  +-----------------------------------------------------------------------+  |
|  |                   certops-dashboard/ (Closed Source)                  |  |
|  |  [Ingestion API (/api/telemetry/ingest)] <--> [Multi-Tenant DB]       |  |
|  |  [React / Vite Web UI (frontendNew/)]                                 |  |
|  +-----------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------+
```

- **`certops-agent/` (Apache-2.0 Open Source):** Runs 100% standalone on client infrastructure. It discovers, renews, deploys, reloads, and verifies certificates locally. Private keys and connector credentials **never leave client infrastructure**.
- **`certops-dashboard/` (Closed Source Commercial Tier):** Multi-tenant SaaS dashboard that ingests sanitized telemetry (`agent_telemetry.py`) to display fleet health, renewal timelines, and audit logs across agents without ever accessing client secrets.

---

## Quick-Start (Standalone Agent)

Get the open-source renewal agent running in standalone mode in under 60 seconds:

### POSIX (Linux / macOS)
```bash
git clone https://github.com/Arpitojha1/clm.git certops && cd certops
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python certops-agent/src/main.py --help
```

### Windows (PowerShell)
```powershell
git clone https://github.com/Arpitojha1/clm.git certops; cd certops
python -m venv venv; .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python certops-agent/src/main.py --help
```

For full setup instructions (including local Vault and `step-ca` Docker bootstrap), see [SETUP.md](SETUP.md).  
For standalone agent operations, see [AGENT_USAGE.md](AGENT_USAGE.md).  
For dashboard management and multi-tenancy, see [USAGE.md](USAGE.md).
