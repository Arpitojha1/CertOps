# CertOps — Session Context & Architectural Handover

**See `CertOps_Master_Roadmap.md` for *why*. This file is for *how*, and for logging gate evidence.**

This document summarizes the exact state of the CertOps project as of Phase 1 completion. Read this before starting any task to understand what has been built, verified, and decided.

---

## 1. Project Overview & Philosophy

CertOps is a vault-to-CA automation bridge designed for strict secret hygiene and end-to-end verification:
- Discovers certificates stored in a secret store (HashiCorp Vault).
- Monitors expiration against a configurable threshold.
- Renews certificates via a Certificate Authority (`step-ca`).
- Writes renewed certificates back to Vault as a new secret version.
- Reads the renewed cert out of Vault, atomically deploys it to disk, reloads the reverse proxy (Nginx), and **verifies via a live TLS handshake** that the served cert matches the newly issued fingerprint.

Per `AGENTS.md`, the project adheres strictly to the **Ponytail Rule** (lazy senior dev reflex: reuse standard library and existing dependencies, avoid unnecessary complexity, fail loudly on errors).

---

## 2. Current Implementation State (Phase 1 — Verified Complete)

All core modules and smoke tests are built and verified against **real running services** (no fakes or mocks):

- `src/vault_client.py`:
  - Implements `read_certificate(vault_addr, vault_token, path)` and `write_certificate(vault_addr, vault_token, path, cert_pem, key_pem)`.
  - Uses `requests` against Vault KV v2 REST API (`/v1/secret/data/...`). Automatically normalizes paths like `secret/local-certs` to `secret/data/local-certs`.
  - Expects and stores payload keys: `data.data.certificate` and `data.data.private_key`.

- `src/ca_client.py`:
  - Implements `issue_certificate(subject, password_file, ca_url, fingerprint)`.
  - Locates `step.exe` CLI and invokes `step ca certificate <subject> <crt> <key> --provisioner-password-file <password_file> --force` inside a temporary directory (`tempfile.TemporaryDirectory`).
  - Returns raw PEM strings `(cert_pem, key_pem)`.

- `src/verify.py`:
  - Implements `get_live_cert_info(host, port=443)` and `get_pem_cert_info(cert_pem)`.
  - Uses standard library `ssl` (`verify_mode = ssl.CERT_NONE`, `check_hostname = False`) and `socket` to connect to `host:port` without relying on Windows OS root trust stores.
  - Returns `(expiry_utc: datetime, sha256_fingerprint_hex: str)` where the fingerprint is the SHA-256 digest of the DER-encoded X.509 certificate.

- `src/main.py`:
  - Implements `run_renewal_loop()` orchestrating the end-to-end chain:
    1. Reads `.env` configuration.
    2. Reads current cert from Vault (`VAULT_CERT_PATH`).
    3. Checks remaining lifetime against `RENEWAL_THRESHOLD_DAYS`. Formats printed `remaining_days` to 4 decimal places (`:.4f`) so elapsed time across consecutive runs is accurately visible without rounding artifacts. If remaining days `> threshold`, logs cleanly and exits 0.
    4. Issues new cert via `ca_client.issue_certificate(...)`.
    5. Writes new cert/key version to Vault via `vault_client.write_certificate(...)`.
    6. Reads new cert/key back out of Vault (`read_certificate`).
    7. Creates `.bak` backup copies of `DEPLOY_CERT_PATH` / `DEPLOY_KEY_PATH`, then deploys new files atomically (`write to .tmp` -> `os.replace`).
    8. Triggers `docker exec <NGINX_CONTAINER_NAME> nginx -s reload`.
    9. Verifies the live served certificate at `VERIFY_HOST:VERIFY_PORT` matches the newly issued SHA-256 fingerprint and expiry. Includes a brief retry loop (up to 5s at 0.5s intervals) to account for asynchronous Nginx worker process reload propagation.

- `tests/test_core_loop.py`:
  - Standard `unittest` smoke tests (`TestCoreLoopSmoke`) running against live Vault, `step-ca`, and Nginx.
  - Verifies both renewal trigger + live verification (`test_01`) and clean short-circuiting when outside threshold (`test_02`).

---

## 3. Key Architectural & Design Decisions

1. **HashiCorp Vault over Cloud Key Vaults (Phase 1)**:
   - Vault dev mode via Docker Compose provides deterministic, zero-cost, locally reproducible secret management.
   - KV v2 engine (`secret/data/...`) is used to support versioned secret history.
   - Standardized secret field names: `"certificate"` and `"private_key"`.

2. **Smallstep (`step-ca`) Integration**:
   - Standalone `step-ca` runs natively on Windows host (`https://localhost:8443`).
   - Uses JWK provisioner (`admin`) authenticated via a password file (`pass.txt`).
   - CLI bootstrap trust is handled via root CA fingerprint matching (`STEP_CA_FINGERPRINT`).

3. **Live Infrastructure Verification over API Trust**:
   - Never assume a successful API write or proxy reload means deployment succeeded. `main.py` opens a real TLS socket to Nginx and verifies the served certificate fingerprint.

4. **Atomic File Replacement & Rollback Hatch**:
   - Files read by Nginx (`local.crt`, `local.key`) are never written in-place mid-read.
   - Existing files are backed up to `local.crt.bak` / `local.key.bak` before atomic replacement (`local.crt.tmp` -> `os.replace`).

---

## 4. Environment Specifics & Configuration (`.env`)

- **OS**: Windows host executing Python scripts directly (`venv`).
- **Containers (`docker-compose.yml`)**:
  - `certops-vault-1` (`hashicorp/vault:latest`): Port `8200`, dev root token `root`.
  - `certops-nginx-1` (`nginx:alpine`): Port `443`, bind-mounts workspace root `./` to `/etc/nginx/certs:ro`. Reload command: `docker exec certops-nginx-1 nginx -s reload`.
  - `certops-postgres-1` / `certops-redis-1`: Ports `5432` / `6379` (running, schema not yet implemented).
- **CA Service**:
  - `step-ca` native process on Windows listening on `https://localhost:8443`.

### Key `.env` Values
```ini
VAULT_ADDR=http://localhost:8200
VAULT_TOKEN=root
VAULT_CERT_PATH=secret/local-certs

STEP_CA_PASSWORD_FILE=./pass.txt
STEP_CA_URL=https://localhost:8443
STEP_CA_FINGERPRINT=

NGINX_CONTAINER_NAME=certops-nginx-1
DEPLOY_CERT_PATH=./local.crt
DEPLOY_KEY_PATH=./local.key

RENEWAL_THRESHOLD_DAYS=2
VERIFY_HOST=localhost
VERIFY_PORT=443
```

---

## 5. Explicitly Out of Scope (Do NOT Build Prematurely)

To maintain scope discipline per `AGENTS.md`, do **not** build or leave speculative placeholders for:
- Certificate groups or inventory abstractions.
- Maintenance windows or scheduler daemons.
- Notification / alerting policies.
- DigiCert / external commercial CA connectors.

---

## 6. Completed Build State (as of Phase 4 session — 2026-07-12)

### Retroactive decisions applied this session (per AGENTS.md instructions):

**Phase 3.5 waiver**: `src/api.py` (FastAPI bridge) is approved. The Phase 3.5 check-in it skipped is waived.

**Phase 3.4 note (append, not overwrite)**: `db.py`'s `timedelta` import bug fix is confirmed correct. The Phase 3.4 "smoke test confirmed" status predates this fix — the scheduler's write path was unverified until now.

**Live-renewal smoke test PAUSED**: Docker/Vault/step-ca services not running on this machine. This smoke test was NOT run. See RUNBOOK.md → Known Limitations.

### What was built this session:

**Backend (Python):**
- `src/db.py` — Added `users` table (id, email, password_hash, role, created_at). Added `create_user`, `get_user_by_email`, `get_user_by_id`.
- `src/auth.py` — Full JWT auth layer using PyJWT + bcrypt. `POST /auth/login`, `GET /auth/me`, `POST /auth/logout`, `POST /auth/signup` (admin-only). JWT in httpOnly cookie. `get_current_user` and `require_admin` FastAPI dependencies.
- `src/api.py` — Replaced stub CORS with env-var `ALLOWED_ORIGINS`. Added `allow_credentials=True`. Mounted auth router. Applied `get_current_user` to all GET routes; `require_admin` to all mutating routes (POST groups, POST maintenance-windows, POST notification-policies, POST assign-group, POST host/confirm-reload). Added `DELETE /api/notification-policies/{id}`. Added `event_type`/`success` filter params to `GET /api/renewal-log`.
- `src/seed_admin.py` — One-time seed script reading `ADMIN_EMAIL`/`ADMIN_PASSWORD` from env. Never commits credentials.
- `requirements.txt` — Added `bcrypt`, `PyJWT`.
- `.env.example` — Added `JWT_SECRET`, `JWT_EXPIRE_HOURS`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `COOKIE_SECURE`, `ALLOWED_ORIGINS`, `API_PORT`.

**Frontend (React/TypeScript):**
- `vite.config.ts` — Added proxy: `/api/*` and `/auth/*` → `http://localhost:8000`. Eliminates CORS complexity for dev.
- `src/lib/api.ts` — Central axios instance, `withCredentials: true`, 401 interceptor redirects to `/`.
- `src/contexts/AuthContext.tsx` — Real auth: `GET /auth/me` on mount restores session from cookie; `login()` calls `POST /auth/login`; `logout()` calls `POST /auth/logout`. Exposes `isLoading`, `role`.
- `src/pages/LandingPage.tsx` — Real login dialog with error handling, redirects to `/dashboard` on success.
- `src/pages/DashboardHome.tsx` — Fetches from `GET /api/certificates`, derives stats from live data.
- `src/pages/CertificatesPage.tsx` — Fetches from `GET /api/certificates`, real filters, passes full cert object to modal.
- `src/components/CertificateDetailModal.tsx` — Fetches `GET /api/renewal-log?cert_id=...` for per-cert timeline; admin-only reload confirmation via `POST /api/host/confirm-reload`.
- `src/pages/ActivityPage.tsx` — Fetches `GET /api/renewal-log` with `event_type`/`success` filters.
- `src/pages/GroupsPage.tsx` — Fetches groups + maintenance windows + notification policies. Admin CRUD for groups, windows, policies.
- `src/pages/NotificationsPage.tsx` (NEW) — Policy management (list/create/delete, admin-gated) + notification history table.
- `src/pages/SchedulerPage.tsx` (NEW) — Next job, upcoming queue, recent events from `GET /api/scheduler/status`.
- `src/components/Sidebar.tsx` — Added Notifications and Scheduler nav items.
- `src/App.tsx` — Added routes for `/notifications` and `/scheduler`; `ProtectedRoute` now handles `isLoading` spinner.

### Design decisions:
- Vite proxy (not CORS allow-all) keeps cookies same-origin during dev.
- `samesite="lax"` cookie; `secure` is env-controlled (`COOKIE_SECURE`), defaults false for localhost.
- `require_admin` enforced at FastAPI Depends layer — not UI-side hiding.
- No new packages added to frontend (axios already existed).
- Scheduler view shows honest data only — no workflow IDs, no fake in-progress state.

## 7. Immediate Next Steps

- Run `python src/seed_admin.py` after setting `ADMIN_EMAIL`/`ADMIN_PASSWORD` in `.env` to create the first admin account.
- On the primary dev machine: run the live-renewal smoke test (see RUNBOOK.md Known Limitations).
- ConnectorsPage still uses mockData — not in wiring scope for this session.

---

## 21. Stage 4 Pre-Coding Architectural Decisions (Activity Log RBAC)

### 1. Event Granularity & Viewer Visibility

| Event Type | Description | Viewer Visible? | Rationale |
|---|---|---|---|
| `certificate_renewed` | Certificate successfully renewed | Yes | Core ops data, viewer needs to see renewal status |
| `certificate_renewal_failed` | Certificate renewal attempt failed | Yes | Core ops data, failure visibility critical for viewers |
| `connector_created` | Admin created a new connector | Yes | Config is redacted before storage (see #2 below) |
| `connector_updated` | Admin updated connector settings | Yes | Config is redacted before storage |
| `connector_deleted` | Admin deleted a connector | Yes | No config in payload, just name/id |
| `connector_tested` | Admin tested connector connectivity | Yes | No config in payload, just test result |
| `group_created` | Admin created a group | Yes | No sensitive data |
| `group_assigned` | Certificate assigned to a group | Yes | No sensitive data |
| `maintenance_window_created` | Admin created a maintenance window | Yes | No sensitive data |
| `notification_policy_created` | Admin created notification policy | Yes | No sensitive data |
| `notification_policy_deleted` | Admin deleted notification policy | Yes | No sensitive data |
| `user_login` | User authenticated successfully | **Admin only** | Auth event — email visible but no credential |
| `invite_generated` | Admin generated an invite link | **Admin only** | Auth event — could reveal internal email roster |
| `invite_redeemed` | New user registered via invite | **Admin only** | Auth event — reveals internal user onboarding |

Decision: The `_ADMIN_ONLY_EVENTS` set in `db.py` will contain `{"user_login", "invite_generated", "invite_redeemed"}`. All other event types are viewer-visible. The RBAC filter is applied at the query layer (SQL `WHERE event_type NOT IN (...)` for viewers, no filter for admins) so unprivileged data never enters the API response serialization path.

### 2. Redaction Path for Connector-Related Log Entries

Connector CRUD log entries store a `details` JSON payload. For create/update events, this payload includes the connector `config` dict. The redaction path is:

1. The API endpoint receives the raw config from the `CreateConnectorRequest`/`UpdateConnectorRequest` Pydantic model.
2. Before calling `db.log_activity(...)`, the endpoint passes the config through `db.redact_config(config_dict)` — the **same function** used by `_serialize_connector()` in `GET /api/connectors`.
3. The redacted dict is serialized into the `details` JSON column at write time. The plaintext config is never stored in the activity_log table.

This is a **single redaction path** — no separate serialization for logging. The same `_SENSITIVE_KEY_SUBSTRINGS` matching applies. The test in `test_gate4_activity_log.py` will confirm no `ENC:v1:` ciphertext or plaintext credential appears in activity log entries.

### 3. Retention & Pagination

- **Pagination**: Required from day one. `GET /api/activity-log` accepts `limit` (default 50, max 200) and `offset` (default 0) query params. Response includes `total` count alongside the `items` array so the frontend knows when to show/hide "Load More".
- **Retention/pruning**: Deferred explicitly. No automatic deletion, no TTL, no archival. Add a `ponytail:` comment in `db.py` noting this as a future operational requirement when the table grows large.

---

## 8. Stage 0 Diagnostic — Overdue Certificate Root Cause Diagnosis

### 1. Code Path Responsible for Overdue / Renewal-Due Status
- **UI / API Status Computation:** `src/api.py` — `_status_for(cert: dict[str, Any], now_utc: datetime | None = None) -> str` (lines 51–68), invoked by `_serialize_cert` (lines 70–93) on `GET /api/certificates` and `GET /api/certificates/{vault_source}/{name}`.
- **Backend Renewal Loop Evaluation:** `src/db.py` — `get_due_certificates(...)` (lines 293–349), invoked by `src/main.py`.

### 2. Sample Evidence for 3 Overdue Certificates
Compared at `now_utc = 2026-07-12T15:14:38.551223+00:00 (UTC)`:

| Cert Name | Source | Actual NotAfter (Cert) | DB Cached Expiry (`expiry_utc`) | Renewal Threshold | Remaining Days | Evaluated Status |
|---|---|---|---|---|---|---|
| `audit-log-test-cert` | Vault (`hashicorp`) | `2026-07-12T08:14:03+00:00` (UTC) | `2026-07-12T08:14:03+00:00` (UTC) | `2.0` days (default) | `-0.292` days | `overdue` (`remaining_days <= 0`) |
| `hc-due-01` | Vault (`hashicorp`) | `2026-07-12T08:22:40+00:00` (UTC) | `2026-07-12T08:22:40+00:00` (UTC) | `7.0` days (stored) | `-0.286` days | `overdue` (`remaining_days <= 0`) |
| `/etc/nginx/certs/local.crt` | Local Disk (`ssh_host`) | `2026-07-12T08:14:10+00:00` (UTC) | `2026-07-12T08:14:10+00:00` (UTC) | `2.0` days (default) | `-0.291` days | `overdue` (`remaining_days <= 0`) |

### 3. Step-CA Validity vs. Threshold Mismatch (Root Cause A)
- `step-ca` defaults to issuing certificates with a **24-hour (1.0 day)** validity period (`src/ca_client.py` does not pass `--not-after`).
- However, `RENEWAL_THRESHOLD_DAYS` defaults to `2.0` days, and some cert rows use `7.0` days.
- **Root Cause Contributor:** When a certificate is issued with a 1.0-day total lifetime, its `remaining_days` (1.0) is immediately `< threshold_days` (2.0 or 7.0), causing newly issued certificates to be classified as `due_soon` immediately upon issuance. Furthermore, because step-ca certificates expire in 24 hours, if renewal is not run every <24 hours, the certificates expire (`remaining_days <= 0`) and appear as `overdue`.

### 4. Timezone Awareness Check
- Both `now_utc = datetime.now(timezone.utc)` and `expiry_utc = _parse_utc_datetime(...)` use explicit `timezone.utc`-aware datetimes. No naive vs. timezone-aware mismatch exists in this comparison.

### 5. Live vs. DB Cache Check (Root Cause B)
- API and UI status queries evaluate against the **DB cache** (`certificates` table), not live against the certificate files or Vault secret store on read. If an out-of-band reissue occurs or the renewal job has not executed within the 24-hour window, the DB cache reflects the expired `expiry_utc`.

---

## 15. Gate 0.5 Verification Evidence (Per-Connector Thresholds & Mismatch Resolution)

Per-connector thresholds have been implemented across all connectors (`HashiCorpVaultClient`, `AzureKeyVaultClient`, `SSHHostConnector`, `WinRMHostConnector`) and persisted cleanly in `certops.db` upon upsert.

### Open Architectural Note (Deferred to Later Phase)
As noted in the Gate 0.5 requirements: a fixed day-count threshold is fragile across CAs with wildly different validity windows (e.g., 24-hour vs 90-day certs). A percentage-of-lifetime threshold (e.g., renew when <= 33% validity remains) is more robust and works unmodified across CAs. This is deferred to a future phase to maintain scope discipline.

### Gate 0.5 Raw Verification Output

```
=== GATE 0.5 VERIFICATION EVIDENCE ===
Cert: hc-due-01                  | Expiry: 2026-07-13 15:32:32 | Stored Thresh:  0.25 | Evaluated Status: healthy
Cert: /etc/nginx/certs/local.crt | Expiry: 2026-07-13 15:32:26 | Stored Thresh:  0.25 | Evaluated Status: reload_confirmed
Cert: audit-log-test-cert        | Expiry: 2026-07-13 15:24:38 | Stored Thresh:  0.25 | Evaluated Status: healthy
```

All 10 automated smoke and regression tests (`test_multi_cert_loop.py`, `test_host_connector.py`, etc.) pass (`Ran 10 tests in 59.669s - OK`).

---

## 16. Gate 1 Verification Evidence (Celery + Redis Three-Stage Pipeline & Crash Recovery)

- `docker-compose.yml` updated with `celery_worker` service alongside `redis`.
- `src/tasks.py` models the 3-stage host pipeline (`Renewed` -> `Deployed pending reload` -> `Reload confirmed`) as chained Celery tasks (`task_renew_certificate`, `task_deploy_certificate`, `task_verify_reload`) with state persisted to SQLite (`certops.db`) at each stage transition.
- **Automatic Startup Recovery Hook**: Wired `@worker_ready.connect` signal (`on_worker_ready` in `src/tasks.py`, lines 194-205) so that whenever a Celery worker process starts up, it automatically queries `certops.db` and resumes any in-flight pipelines interrupted by a crash without human intervention.
- **Real Subprocess Kill Proof**: Verified via standalone real OS subprocess kill demonstration (`python tests/demo_real_celery_kill_and_resume.py`).

### Gate 1 Raw Verification Output (Real Subprocess Kill & Automatic Startup Recovery)

```
================================================================================
GATE 1 REAL SUBPROCESS KILL & AUTO-RESUME ON WORKER STARTUP PROOF
================================================================================

[STEP 1] Seeded in-flight pipeline state in SQLite DB ('real_crash_demo.db'):
         cert='cert-real-crash-01' -> pipeline_stage='Deployed pending reload'

[STEP 2] Spawning Real Celery Worker Subprocess #1...
         Worker Subprocess #1 started with real OS PID: 64332

[STEP 3] Forcibly killing Worker Subprocess #1 (PID 64332) with kill()...
         Worker #1 terminated (exit code: 1).
         DB state while worker is dead: cert='cert-real-crash-01' -> pipeline_stage='Deployed pending reload'

[STEP 4] Spawning BRAND NEW Celery Worker Subprocess #2 to prove AUTOMATIC startup recovery...
         Worker Subprocess #2 started with real OS PID: 42612
         Waiting 4 seconds for @worker_ready signal to trigger auto-resume on startup...

[STEP 5] RAW DB QUERY AFTER WORKER #2 STARTUP:
         cert='cert-real-crash-01' -> pipeline_stage='Reload confirmed'

================================================================================
REAL SUBPROCESS KILL & AUTOMATIC STARTUP RECOVERY PROOF PASSED!
Worker Subprocess #1 (PID 64332) killed -> Worker Subprocess #2 (PID 42612)
automatically resumed pipeline on startup via @worker_ready signal without human intervention.
================================================================================
```

All 11 automated unit and regression tests pass (`Ran 11 tests in 51.774s - OK`).

---

## 17. Stage 2 Pre-Coding Architectural Decisions & Clarifications

Before implementing RBAC / Auth foundation, we resolve the two architectural questions:

### 1. Invite Link Delivery Mechanism (Stub vs. Real Email)
- **Decision**: We implement a secure **invite link stub** where admin-generated invite links/tokens are returned via the API payload and logged securely for admin distribution (`/api/auth/invites`).
- **Rationale**: Adding live SMTP/email provider infrastructure in this phase violates scope discipline. Live email delivery will be plugged into this token generation flow in a later notification stage.

### 2. Tenant & Team Scoping ("Admin's team gets the same dashboard")
- **Decision**: All authenticated users within the organization share **one unified connector inventory and activity log**, strictly gated by role (`admin` vs. `viewer`).
- **Rationale**: Multi-tenant or granular per-team connector partitioning beyond role gating (`admin` vs `viewer`) adds premature complexity and is out of scope for Phase 3.

---

## 18. Gate 2 Verification Evidence (RBAC Foundation & Auth UX)

- **JWT in httpOnly Cookies**: `certops_token` cookie configured with `HttpOnly`, `SameSite=lax`, and secure attributes (`src/auth.py`).
- **bcrypt Password Hashing**: Hashed passwords stored via `bcrypt.hashpw` (`src/auth.py`).
- **CORS Configured Explicitly**: Locked to `ALLOWED_ORIGINS` env configuration without wildcard (`src/api.py`).
- **Two Roles Enforced**: `admin` (full mutations) vs `viewer` (read-only).
- **Admin-Only Invite Flow**: Admins generate invite links (`POST /auth/invites`), new users sign up via invite token (`POST /auth/register-with-invite`), open unauthenticated self-registration disabled.

### Gate 2 Raw Verification Output (`python -m unittest -v tests/test_gate2_rbac_auth.py`)

```
=== TEST 1: Admin Login & httpOnly Cookie Verification ===
[SET-COOKIE HEADER RECEIVED] certops_token=eyJhbGciOiJIUzI1NiIsIn...; HttpOnly; Max-Age=86400; Path=/; SameSite=lax

=== TEST 2: Viewer Mutating Action Rejection Verification ===
[VIEWER MUTATING ATTEMPT] POST /api/groups -> status 403: {'detail': 'Admin access required'}

=== TEST 3: Admin Invite Flow & New User Signup ===
[ADMIN INVITE GENERATED] email='newdev@example.com', invite_url='/signup?token=lOH5Qpf-EOBYahNGRYqWB29IsPnNQH6QT4XmFN5SkC0'
[INVITE SIGNUP COMPLETED] New user created: {'id': 3, 'email': 'newdev@example.com', 'role': 'viewer'}

=== TEST 4: Full Route-by-Route RBAC Classification Audit ===
METHOD   PATH                                          CLASSIFICATION     DEPENDENCY GATE
---------------------------------------------------------------------------------------------------------
GET      /openapi.json                                 Framework / Public OpenAPI Metadata
GET      /docs                                         Framework / Public OpenAPI Metadata
GET      /docs/oauth2-redirect                         Framework / Public OpenAPI Metadata
GET      /redoc                                        Framework / Public OpenAPI Metadata
GET      /api/health                                   Public             Public / Token-Validated
GET      /api/certificates                             Viewer-Allowed     Depends(get_current_user)
GET      /api/certificates/due                         Viewer-Allowed     Depends(get_current_user)
GET      /api/certificates/{vault_source}/{name}       Viewer-Allowed     Depends(get_current_user)
GET      /api/renewal-log                              Viewer-Allowed     Depends(get_current_user)
GET      /api/groups                                   Viewer-Allowed     Depends(get_current_user)
POST     /api/groups                                   Admin-Only         Depends(require_admin)
POST     /api/certificates/assign-group                Admin-Only         Depends(require_admin)
GET      /api/maintenance-windows                      Viewer-Allowed     Depends(get_current_user)
POST     /api/maintenance-windows                      Admin-Only         Depends(require_admin)
GET      /api/notification-policies                    Viewer-Allowed     Depends(get_current_user)
POST     /api/notification-policies                    Admin-Only         Depends(require_admin)
DELETE   /api/notification-policies/{policy_id}        Admin-Only         Depends(require_admin)
GET      /api/notification-log                         Viewer-Allowed     Depends(get_current_user)
GET      /api/scheduler/status                         Viewer-Allowed     Depends(get_current_user)
POST     /api/host/confirm-reload                      Admin-Only         Depends(require_admin)
```

All 16 automated integration/regression tests pass (`Ran 16 tests in 51.042s - OK`).

---

## 19. Gate 2 Hardening Evidence

1. **Invite Token Logging Redaction (`src/auth.py`)**:
   - `logger.info("Admin created invite for email='%s', role='%s', token_ref='***%s'", body.email, body.role, token[-6:])`
   - Verified output: `2026-07-12 22:10:51,414 [INFO] Admin created invite for email='newdev@example.com', role='viewer', token_ref='***jVYsm0'`. Plaintext token is only returned in the API response JSON body.
2. **`Secure` Cookie Flag Negative & Positive Verification (`src/auth.py` / `test_05`)**:
   - Configured dynamically: `secure = os.getenv("ENV", "").lower() == "production" or os.getenv("COOKIE_SECURE", "false").lower() in ("true", "1", "yes")`.
   - Verified Dev HTTP Negative Case (`ENV=development`, `COOKIE_SECURE=false`): `[NEGATIVE CASE (DEV HTTP)] Set-Cookie: certops_token=...; HttpOnly; Max-Age=86400; Path=/; SameSite=strict` (`Secure` absent so local HTTP dev login works).
   - Verified Production Positive Case (`ENV=production`): `[POSITIVE CASE (ENV=production)] Set-Cookie: certops_token=...; HttpOnly; Max-Age=86400; Path=/; SameSite=strict; Secure`.
   - Verified Explicit Secure Flag (`COOKIE_SECURE=true`): `[POSITIVE CASE (COOKIE_SECURE=true)] Set-Cookie: certops_token=...; HttpOnly; Max-Age=86400; Path=/; SameSite=strict; Secure`.
3. **`SameSite=strict` Policy (`src/auth.py`)**:
   - Changed from default `lax` to explicit `strict` (`"samesite": "strict"`), because CertOps has no third-party OAuth redirect flows requiring `lax` and interacts directly between frontend and API.
4. **Bcrypt Cost Factor (`src/auth.py`)**:
   - Explicit `bcrypt.gensalt(rounds=12)` work factor configured in `hash_password`. Hashing and verification confirmed passing.
5. **Test Isolation (`tests/test_gate2_rbac_auth.py`)**:
   - `setUpClass` and `tearDownClass` record original environment variables (`CERTOPS_DB_PATH`, `DB_PATH`, `COOKIE_SECURE`, `ENV`) and restore them completely on teardown while removing isolated `test_gate2_auth.db`.
   - Verified standalone execution: `python -m unittest -v tests/test_gate2_rbac_auth.py` -> `Ran 5 tests in 1.443s - OK`.

---

## 20. Gate 3 Verification Evidence (Connector UI & Per-Connector Renewal Thresholds)

- **Per-Connector Schema (`connectors` table in `src/db.py`)**: Stores `id`, `name`, `category`, nullable `renewal_threshold_days REAL NULL`, `config`, and `is_active`. Default connectors default `renewal_threshold_days` to `NULL` so environment (`RENEWAL_THRESHOLD_DAYS`) applies unless explicitly configured per-connector by an Admin.
- **Per-Connector Renewal Evaluation (`db.get_due_certificates`)**: Dynamically resolves `cert_threshold = float(row[7]) if row[7] is not None else conn_map.get(row[0], threshold_days)`.
- **Connector Management Endpoints (`src/api.py`)**:
  - `GET /api/connectors` (`Depends(get_current_user)`) — available to any authenticated viewer/admin.
  - `POST /api/connectors` (`Depends(require_admin)`) — create connector.
  - `PUT/PATCH /api/connectors/{connector_id}` (`Depends(require_admin)`) — update connector settings & per-connector renewal threshold.
  - `DELETE /api/connectors/{connector_id}` (`Depends(require_admin)`) — delete connector.
  - `POST /api/connectors/{connector_id}/test` (`Depends(require_admin)`) — verify connectivity.
- **UI Integration (`ConnectorsPage.tsx`)**: Fully dynamic dashboard loading real connectors, displaying per-connector renewal threshold badges, with Admin modal for editing per-connector thresholds (`PUT /api/connectors/{id}`) and testing live connectivity (`POST /api/connectors/{id}/test`).

### Gate 3 Raw Verification Output (`python -m unittest -v tests/test_gate3_connector_ui.py`)

```
=== TEST 1: Viewer Can List Connectors But Rejected On Mutating Endpoints ===
[VIEWER LIST CONNECTORS] Found 4 default connector(s).
[VIEWER CREATE ATTEMPT] POST /api/connectors -> status 403: {'detail': 'Admin access required'}
[VIEWER UPDATE ATTEMPT] PUT /api/connectors/2 -> status 403: {'detail': 'Admin access required'}
[VIEWER DELETE ATTEMPT] DELETE /api/connectors/2 -> status 403: {'detail': 'Admin access required'}

=== TEST 2: Admin Connector CRUD & Test Connectivity ===
[ADMIN CREATED CONNECTOR] id=5, name='digicert_ca', threshold=14.0d
[ADMIN UPDATED CONNECTOR] id=5, new threshold=21.0d
[ADMIN TEST CONNECTOR] success=True, msg='[STUB] Simulated connectivity test for connector 'digicert_ca' (ca). External live probe stubbed pending integration.'
[ADMIN DELETED CONNECTOR] id=5

=== TEST 3: Per-Connector Renewal Threshold Dynamically Controls Certificate Due Status ===
[CONNECTOR THRESHOLD SET] 'hashicorp' threshold = 5.0 days. Cert lifetime = 10.0 days.
[CHECK DUE CERTS AT 5.0d THRESHOLD] Count due = 0
[CONNECTOR THRESHOLD UPDATED] 'hashicorp' threshold = 15.0 days. Cert lifetime = 10.0 days.
[CHECK DUE CERTS AT 15.0d THRESHOLD] Count due = 1
  -> Due cert name='app.certops.local', daysRemaining=10.00, effective_threshold=15.0d

=== TEST 4: Hardening Evidence (Encryption at Rest, Redaction, Stub Labeling, Fresh Init, Cascade Block) ===
[1. RAW SQLITE CONFIG AT REST] {"url": "https://vault.example.com:8200", "token": "ENC:v1:gAAAAABqU83DHGFT3KgUOrI-_zxF9K44nkUkAz48zZ8QLu78XkkPwbAGMiNfyqrpUIBi86BQeoXRPUm2gZfCYEXTSXcjtr01n40YbIl0Jdvzlf2LdRIoLNw=", "password": "ENC:v1:gAAAAABqU83DvuoL-Xlza1k8AAJTcjUxLjmw55XA1QYfmxjVSknA0q2ty0Buzg-7sZWuEf1N50mO9bqEjZYquWA53BJVMDbpGw=="}
[2. FIELD-LEVEL REDACTION IN GET RESPONSE] config = {'url': 'https://vault.example.com:8200', 'token': '********', 'password': '********'}
[3. HONEST STUB LABELING] {'success': True, 'is_stub': True, 'message': "[STUB] Simulated connectivity test for connector 'encrypted_vault' (secret_store). External live probe stubbed pending integration."}
[4. CLEAN FRESH DB INITIALIZATION] Initialized 4 default connector(s): [('hashicorp', None), ('azure', None), ('ssh_host', None), ('step_ca', None)]
[5. CASCADE DELETE SAFETY BLOCKING] DELETE /api/connectors/1 -> status 409: {'detail': "Cannot delete connector 'hashicorp': 1 certificate(s) are currently tracked under this connector."}
```

Full regression suite execution (`python -m unittest -v tests/test_core_loop.py tests/test_gate2_rbac_auth.py tests/test_gate3_connector_ui.py`) passes cleanly (`Ran 11 tests in 11.515s - OK`) with zero regressions.

- **Operational Note on Key Rotation**: Key rotation for `CERTOPS_CONFIG_ENCRYPTION_KEY` in general requires a one-time re-encryption migration (decrypt existing rows under old key, re-encrypt under new key) as a known operational cost.

---

## 22. Gate 4 Verification Evidence (Activity Log RBAC)

### What was built:

**Backend (Python):**
- `src/db.py` — Added `activity_log` table (id, event_type, actor_user_id, actor_email, target, details JSON, timestamp). Added `log_activity()` append-only insertion, `get_activity_logs()` paginated query with RBAC filtering via `_ADMIN_ONLY_EVENTS` set. Ponytail comment noting no retention policy yet.
- `src/api.py` — Added `GET /api/activity-log` endpoint with `limit`/`offset` pagination (max 200) and admin-only event filtering based on `current_user.role`. Added `_actor_from_user()` helper. Wired `db.log_activity()` into all 8 mutating endpoints: connector create/update/delete/test, group create, assign-group, maintenance window create, notification policy create/delete.
- `src/auth.py` — Wired `db.log_activity()` into 3 auth events: `user_login` (login endpoint), `invite_generated` (create_invite endpoint), `invite_redeemed` (register_with_invite endpoint). Changed `_: dict = Depends(require_admin)` to `current_user: dict = Depends(require_admin)` where actor info extraction is needed.

**Frontend (React/TypeScript):**
- `frontend/client/src/pages/ActivityPage.tsx` — Full rewrite to use `GET /api/activity-log` with pagination. Response shape: `{items: [...], total: int}`. Supports event type filter, "Load More" button for pagination (50 items per page). Event icons and badges mapped for all 15 event types. Shows actor email and formatted details.

**Tests:**
- `tests/test_gate4_activity_log.py` — 7 test methods covering all acceptance criteria.

### Gate 4 Raw Verification Output (`python -m unittest -v tests/test_gate4_activity_log.py`)

```
=== TEST 1: Viewer-Role GET /api/activity-log Returns Only Viewer-Visible Events ===
[VIEWER RESPONSE] total=2, items_returned=2
[VIEWER EVENT TYPES] {'group_created', 'connector_created'}
[RESULT] PASSED: Viewer only sees viewer-visible event types

=== TEST 2: Admin-Role GET /api/activity-log Returns Full Set Including Admin-Only Events ===
[ADMIN RESPONSE] total=3, items_returned=3
[ADMIN EVENT TYPES] {'invite_generated', 'user_login'}
[RESULT] PASSED: Admin sees full event set including admin-only events

=== TEST 3: Connector-Related Log Entry Does NOT Contain Unredacted Credentials ===
[ACTIVITY LOG ENTRY] id=3, event_type=connector_created, target=cred_test_conn
[ENTRY DETAILS] {
  "name": "cred_test_conn",
  "category": "secret_store",
  "config": {
    "url": "https://vault.example.com:8200",
    "token": "********",
    "password": "********"
  }
}
[CONFIG IN ENTRY] {'url': 'https://vault.example.com:8200', 'token': '********', 'password': '********'}
[RAW SQLITE DETAILS] {"name": "cred_test_conn", "category": "secret_store", "config": {"url": "https://vault.example.com:8200", "token": "********", "password": "********"}}
[RESULT] PASSED: Connector log entry contains only redacted credentials

=== TEST 4: Pagination Returns Distinct Rows Across Pages ===
[PAGE 1] items=50, total=57
[PAGE 2] items=7, total=57
[OVERLAP CHECK] page1_ids_count=50, page2_ids_count=7, overlap=0
[TOTAL CHECK] total=57, sum_of_pages=57
[RESULT] PASSED: Pagination returns distinct, non-overlapping rows

=== TEST 5: Logging Calls Wired Into All Mutation Paths ===
[ALL EVENT TYPES LOGGED] ['connector_deleted', 'connector_tested', 'connector_updated', 'connector_created', 'notification_policy_deleted', 'notification_policy_created', 'maintenance_window_created', 'group_assigned', 'group_created', 'user_login', 'user_login']
  [WIRED] user_login — present in log
  [WIRED] connector_created — present in log
  [WIRED] group_created — present in log
  [WIRED] group_assigned — present in log
  [WIRED] maintenance_window_created — present in log
  [WIRED] notification_policy_created — present in log
  [WIRED] notification_policy_deleted — present in log
  [WIRED] connector_updated — present in log
  [WIRED] connector_tested — present in log
  [WIRED] connector_deleted — present in log
[RESULT] PASSED: All 10 mutation paths are wired with logging

=== TEST 6: Activity Log Table Schema & Append-Only Behavior ===
[TABLE COLUMNS] ['id', 'event_type', 'actor_user_id', 'actor_email', 'target', 'details', 'timestamp']
[SCHEMA CHECK] PASSED: All expected columns present
[APPEND-ONLY] id1=3, id2=4 — monotonic increment confirmed
[RESULT] PASSED

=== TEST 7: Viewer RBAC Filter Applied at Query Layer, Not Serialization ===
[ADMIN] total=5, admin_only_events=4
[VIEWER] total=1, admin_only_events_visible=0
[RESULT] PASSED: RBAC filter excludes admin-only events for viewer at query layer

Ran 7 tests in 17.312s
OK
```

### Updated RBAC Route Audit Table (from Gate 2 test_04, now including activity-log):

```
GET      /api/activity-log                             Viewer-Allowed     Depends(get_current_user)
```

`GET /api/activity-log` is classified as `Viewer-Allowed` at the route level. RBAC filtering of admin-only event types is applied at the **query layer** inside `db.get_activity_logs()` (SQL `WHERE event_type NOT IN (...)` for non-admin callers), not at the serialization layer. This means unprivileged event types never enter the response pipeline at all.

### Full Regression Suite (Ran 16 tests in 30.605s - OK):

- `test_gate2_rbac_auth.py` (5 tests) — All pass. Route audit table now shows 27 endpoints including `GET /api/activity-log`.
- `test_gate3_connector_ui.py` (4 of 5 tests) — All pass. test_05 (SSH live connection) excluded per pre-existing known limitation (no SSH server running).
- `test_gate4_activity_log.py` (7 tests) — All pass.

### Files Changed:
- `src/db.py` — `activity_log` table DDL + `log_activity()` + `get_activity_logs()` + `_ADMIN_ONLY_EVENTS`
- `src/api.py` — `GET /api/activity-log` endpoint + `_actor_from_user()` + logging in 8 mutation endpoints
- `src/auth.py` — Logging in 3 auth endpoints (login, create_invite, register_with_invite)
- `frontend/client/src/pages/ActivityPage.tsx` — Full rewrite for real API + pagination
- `tests/test_gate4_activity_log.py` — New test file with 7 acceptance tests (now 8 with §22 renewal-event test)
- `session_context.md` — This file

---

## 23. Core Documents Generation (2026-07-14)

Generated the standing set of tracked documents per `CertOps_Master_Roadmap.md`.
All documents reflect actual current state (Phase 0, Stage 2 complete), not
aspirational end-state.

| Document | Status | Notes |
|---|---|---|
| `session_context.md` pointer | Done | Added top-of-file pointer to roadmap ("why" vs "how") |
| `TELEMETRY_CONTRACT.md` | Done | Phase 1 design doc. Two explicit lists (crosses wire / never crosses wire). Agent auth separation as hard requirement. Sign-off framing included. Awaiting maintainer review before any agent→cloud code. |
| `PRD.md` | Done | Problem statement, non-goals, two-product shape, personas, current pipeline status (all 7 stages working), honest differentiators, phase-gated scope table, success metrics from Phase 4. |
| `TRD.md` | Done | System components with exact method surfaces, data model (all tables with columns), pipeline state machine with crash-recovery behavior, security model (Fernet isolation, RBAC), CA support (step-ca only), known architectural debt table reconciled against gate evidence. tenant_id noted as not yet added. |
| `ARCHITECTURE.md` | Done | Mermaid-style diagrams of agent/dashboard boundary, pipeline stages with crash-recovery resume points, data flow for single cert renewal. Callout box referencing TRD §6 for current reality vs. intended design. |
| `RUNBOOK.md` | Updated | Appended: step-ca .vlog corruption recovery, Celery worker crash recovery (by crash point), SQLite hygiene (WAL mode, migration notes, backup command). |
| `SECURITY.md` | Done | Zero-key-exposure design intent (current guarantees vs. gaps), responsible disclosure placeholder, known gaps table, secrets handling rules (PAT incident referenced). |
| `AGENTS.md` | Updated | Added: gate discipline, pre-coding questions, secrets discipline (PAT incident referenced), RBAC/tenant scoping convention `(tenant_id, user)` as standing rule. |
| `CONTRIBUTING.md` | Skeleton | Explicitly marked placeholder. License pending (MIT vs Apache-2.0). Pre-commit secret scanning noted as required. PR process TBD before Phase 3. |

### Documents still marked placeholder/pending:
- `CONTRIBUTING.md` — license decision pending, PR process TBD
- `TELEMETRY_CONTRACT.md` — requires maintainer sign-off
- `SECURITY.md` — disclosure email placeholder

### Found during Stage 4:
No new bugs found. The existing `test_core_loop.py` test_01 fails when step-ca is not running (`No connection could be made because the target machine actively refused it`) — this is a pre-existing known limitation documented in RUNBOOK.md, not a regression.

---

## 22. Renewal-Event Activity Log Wiring (Regression Fix)

### Problem
`ActivityPage.tsx` was switched from `/api/renewal-log` to `/api/activity-log`, but the renewal pipeline in `main.py` never called `db.log_activity()`. Only `renewal_log` (the low-level audit table) was written to during renewals, so the viewer-facing activity page showed zero certificate renewal events.

### Fix: Option 1 — Wire `db.log_activity()` into the renewal pipeline
Five `db.log_activity()` call sites added to `src/main.py` `run_renewal_loop()`, one at each renewal outcome point:

| # | Path | Event Type | Location (main.py) |
|---|---|---|---|
| 1 | Host — maintenance window hold | `certificate_renewed` | `log_activity(...)` after `summary[c_name]["succeeded"] += 1`, before `continue` |
| 2 | Host — fully deployed | `certificate_renewed` | `log_activity(...)` after `summary[c_name]["succeeded"] += 1` |
| 3 | Host — exception | `certificate_renewal_failed` | `log_activity(...)` after `summary[c_name]["failed"] += 1` |
| 4 | Secret store — success | `certificate_renewed` | `log_activity(...)` after `summary[c_name]["succeeded"] += 1` |
| 5 | Secret store — exception | `certificate_renewal_failed` | `log_activity(...)` after `summary[c_name]["failed"] += 1` |

All calls pass `actor_user_id=None`, `actor_email=None` (system-generated events). The `details` dict includes `connector_name`, `category` (`"host"` or `"secret_store"`), and on success: `old_expiry` / `new_expiry` as ISO strings; on failure: `error` as string.

### Bug Caught: datetime Serialization
`existing_data.expiry_utc`, `new_expiry`, `dt`, and `write_res["expiry_utc"]` are all `datetime` objects, not ISO strings. Passing them directly into the `details` dict would cause `json.dumps()` inside `log_activity()` to raise `TypeError: Object of type datetime is not JSON serializable` on the very first successful renewal. All three success-path call sites were fixed to call `.isoformat()` before passing expiry values.

### Test Evidence
`test_gate4_activity_log.py::test_08_renewal_loop_writes_activity_log_with_iso_timestamps` — exercises the **real `run_renewal_loop()`** with a stubbed SecretStoreConnector, proving the `.isoformat()` calls in main.py are the code under test:

- (a) `run_renewal_loop()` completes with `succeeded=1, failed=0` and a `certificate_renewed` entry exists in `activity_log`
- (b) `old_expiry` and `new_expiry` in the details dict are valid ISO strings (parsed back via `datetime.fromisoformat()`)
- (c) Viewer role sees the `certificate_renewed` entry
- (d) No `certificate_renewal_failed` entry exists for the stub cert

**Stash/rerun proof** (raw datetime objects pre-fix vs .isoformat() post-fix):

Pre-fix (`.isoformat()` removed from main.py):
```
ERROR: Certificate processing failed for name='stub-cert' in 'stub_vault': Object of type datetime is not JSON serializable
[LOOP SUMMARY] {'succeeded': 1, 'skipped': 0, 'failed': 1}
FAIL: 0 not greater than or equal to 1 : At least one certificate_renewed entry for stub-cert
```
The `TypeError` inside `log_activity()` was caught by the `except Exception` handler, silently downgrading the renewal to `failed=1` — the exact regression the user reported.

Post-fix (`.isoformat()` restored):
```
[LOOP SUMMARY] {'succeeded': 1, 'skipped': 0, 'failed': 0}
[ACTIVITY LOG] id=3 event_type=certificate_renewed target=stub-cert
[DETAILS] {"old_expiry": "2020-01-01T00:00:00+00:00", "new_expiry": "2027-01-01T00:00:00+00:00"}
[RESULT] PASSED
```

Full suite: 8 tests in `test_gate4_activity_log.py`, all pass.

### Files Changed
- `src/main.py` — 5 `db.log_activity()` call sites + `.isoformat()` conversions
- `tests/test_gate4_activity_log.py` — test_08 added

---

## Phase 0 — Part A Gate Evidence: Test Suite Hermeticity

### Changes Made
1. Verified `test_05_credential_encryption_roundtrip_and_decrypted_creds_used` in `tests/test_gate3_connector_ui.py` is hermetic using mocked `paramiko.SSHClient` and `_make_self_signed_pem()`.
2. Quarantined genuinely-live integration tests behind `CERTOPS_RUN_LIVE=1` + `unittest.skipUnless`:
   - `tests/test_host_connector.py`
   - `tests/test_multi_cert_loop.py`
   - `tests/test_audit_log.py`
   - `tests/test_core_loop.py`
   - `tests/test_celery_crash_recovery.py`
   - `tests/test_tier1_tasks_integration.py`
   - Confirmed `demo_real_celery_kill_and_resume.py` is excluded from default `unittest discover`.
3. Made SSH command execution timeouts env-overridable via `SSH_TIMEOUT_SECONDS` (`default="10"`) in `src/host_connector.py::_exec_command`.
4. Replaced `time.sleep(1.2)` restart recovery delay in `tests/test_scheduler.py` with `0.1s` bounded poll loop.

### Before/After Timing Comparison
- **Before**: Full suite `python -m unittest discover -s tests -p "test_*.py" -v` took **48.954s** with 1 failure and 2 errors due to live network calls attempting to connect to non-running `step-ca` (`localhost:8443`).
- **After**: Full suite `python -m unittest discover -s tests -p "test_*.py" -v` completed in **37.415s** with `OK (skipped=8)`, 0 failures, 0 errors, running completely offline and hermetically.

### Hermeticity Confirmation
Confirmed explicitly: No commands or tests ran against real cert paths, port 443, or real Vault/Azure/CA endpoints on this machine during the default test run. All live integration tests correctly reported `skipped`.

---

## Phase 0 — Part B Gate Evidence: Verify Fernet Key Isolation

### 1. No Crypto-Key Derivation from `JWT_SECRET`
Confirmed via grep search across `src/` for `JWT_SECRET`:
- `src/auth.py:24`: `JWT_SECRET = os.getenv("JWT_SECRET", ...)` (used exclusively for signing JWT auth tokens)
- Completely removed `JWT_SECRET`-derived Fernet fallback from `src/db.py::_get_fernet()`.

### 2. Loud Startup Warning & Ephemeral Dev Key Fallback
If `CERTOPS_CONFIG_ENCRYPTION_KEY` is not set (`None` or `""`), `_get_fernet()` emits a loud, unmissable banner to stdout/stderr and logger:
```
********************************************************************************
CRITICAL SECURITY WARNING: CERTOPS_CONFIG_ENCRYPTION_KEY is not set!
Using an ephemeral in-memory Fernet key for local dev convenience.
Encrypted credentials will NOT persist across process restarts.
Do NOT use in production! Generate a key with:
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
********************************************************************************
```
Uses `Fernet.generate_key()` in memory instead of deriving from `JWT_SECRET`.

### 3. `.env.example` Placeholder Fails Loudly if Used Verbatim
Set `.env.example`:
```ini
CERTOPS_CONFIG_ENCRYPTION_KEY=REPLACE_WITH_FERNET_KEY_DO_NOT_USE_UNCHANGED
```
Terminal verification running `_get_fernet()` with this placeholder:
```
ValueError: Invalid CERTOPS_CONFIG_ENCRYPTION_KEY provided: Fernet key must be 32 url-safe base64-encoded bytes.
```

---

## Phase 0 — Part C Gate Evidence: Restore Renewal Log Data Source

### Changes Made
1. Restored `/api/renewal-log` fetch and merge in `ActivityPage.tsx` alongside `/api/activity-log`, deduplicating by timestamp+target so both sources render together.
2. Updated `GET /api/activity-log` in `src/api.py` (`include_renewal_log: bool = True`) to merge normalized `renewal_log` rows into the activity feed at the query API layer.
3. Added `test_09_renewal_log_entries_appear_in_combined_activity_feed` in `tests/test_gate4_activity_log.py`.

### Gate Evidence (Raw Output of Combined Feed)
Ran `python -m unittest tests.test_gate4_activity_log -k test_09`:
```json
=== TEST 9: Renewal-Log Entries Appear in Combined Activity Feed ===
[COMBINED LOG VERIFICATION] Both RBAC activity_log and renewal_log entries found together:
  RBAC entry sample: {
    "id": 3,
    "event_type": "connector_created",
    "actor_user_id": null,
    "actor_email": "admin@certops.internal",
    "target": "test_rbac_connector",
    "details": null,
    "timestamp": "2026-07-13T19:40:16.159461+00:00"
  }
  Renewal-log entry sample: {
    "id": -100001,
    "event_type": "certificate_renewed",
    "actor_user_id": null,
    "actor_email": "system (renewal pipeline)",
    "target": "cert_from_renewal_log",
    "details": "{\"source\": \"renewal_log\", \"connector\": \"hashicorp\", \"category\": null, \"old_expiry\": null, \"new_expiry\": null, \"success\": 1, \"detail\": \"renewed directly via insert_renewal_log\"}",
    "timestamp": "2026-07-13T19:40:16.169223+00:00"
```

---

## Phase 0 — Part D Gate Evidence: RBAC & Tenancy Isolation at Query Layer

### Changes Made
1. Added `tenant_id` column (`DEFAULT 'default'`) to `certificates`, `connectors`, and `users` tables, including idempotent runtime column migrations for existing databases in `src/db.py`.
2. Updated base read queries (`list_all_certificates`, `get_due_certificates`, `get_certificate`, `list_connectors`, `get_connector`, `get_connector_by_name`) to accept optional `tenant_id` scope parameter.
3. Added `_get_tenant_scope` helper in `src/api.py` so that non-admin (`viewer`) users automatically query with their assigned `tenant_id` scope, while admins query across all tenant scopes (`None`).
4. Created `tests/test_gate5_tenancy_isolation.py` asserting strict multi-tenant isolation.

### Gate Evidence (Raw Output of Isolation Test)
Ran `python -m unittest tests.test_gate5_tenancy_isolation -v`:
```
=== TEST TENANCY ISOLATION: Viewer A vs Viewer B vs Admin ===
[TENANCY RESULT] len(viewer_A_results) == 1
[TENANCY RESULT] len(viewer_B_results) == 1
[TENANCY RESULT] len(admin_results) == 2
```

---

## Phase 0 — Part E Gate Evidence: Celery Task Dispatch Pipeline Execution

### Changes Made
1. Created `src/deployer.py` with `run_deploy_pipeline` and `run_verify_pipeline` helper functions to inspect connector configs, transition `certificates.pipeline_stage` (`deployed`, `deploy_failed`, `verified`, `verify_failed`), and append structured records to `activity_log`.
2. Updated `task_deploy_certificate` and `task_verify_reload` in `src/tasks.py` to call `deployer.run_deploy_pipeline` and `deployer.run_verify_pipeline`, supporting flexible dict/positional arguments.
3. Created `tests/test_gate6_celery_pipeline.py` verifying eager synchronous Celery task pipeline execution.

### Gate Evidence (Raw Output of Celery Pipeline Test)
Ran `python -m unittest tests.test_gate6_celery_pipeline -v`:
```
=== TEST CELERY PIPELINE: pending -> deployed -> verified ===
[INITIAL STATE] cert='test-pipeline-cert' stage='pending'
[AFTER DEPLOY] cert='test-pipeline-cert' stage='deployed'
[AFTER VERIFY] cert='test-pipeline-cert' stage='verified'
[ACTIVITY LOG: DEPLOYED ENTRY] {'id': 1, 'event_type': 'certificate_deployed', 'actor_user_id': None, 'actor_email': None, 'target': 'stub_pipeline_conn/test-pipeline-cert', 'details': '{"cert_id": "test-pipeline-cert", "connector": "stub_pipeline_conn", "status": "deployed"}', 'timestamp': '2026-07-13T19:51:40.523141+00:00'}
[ACTIVITY LOG: VERIFIED ENTRY] {'id': 2, 'event_type': 'certificate_verified', 'actor_user_id': None, 'actor_email': None, 'target': 'stub_pipeline_conn/test-pipeline-cert', 'details': '{"cert_id": "test-pipeline-cert", "connector": "stub_pipeline_conn", "status": "verified"}', 'timestamp': '2026-07-13T19:51:40.568000+00:00'}
[RESULT] PASSED: Celery pipeline eager execution successfully transitioned stages and logged activity
```

---

## Phase 0 — Part F Gate Evidence: Config Divergence & Authoritative DB Source

### Changes Made
1. Replaced `get_active_connectors()` in `src/main.py` to query strictly from `db.list_connectors(active_only=True)` in the SQLite database, removing all environment variable discovery fallback paths (`CONNECTOR_N_TYPE`, `VAULT_ADDR`, `AZURE_KEYVAULT_URL`, `ENABLE_SSH_HOST`, `ENABLE_WINRM_HOST`).
2. Updated `run_renewal_loop(db_path=None)` in `src/main.py` so that if `active_connectors` is empty (`0 rows`), it exits cleanly with `0 checked, 0 renewed` rather than attempting environment variable discovery.
3. Added `bootstrap_default_connectors(db_path=None)` in `src/db.py` and called it during FastAPI application startup (`@app.on_event("startup")`) in `src/api.py`.
4. Verified via `grep_search` that zero references to `CONNECTOR_` remain in `src/`.
5. Created `tests/test_gate7_config_divergence.py` verifying that when the `connectors` table is empty (`0 rows`), `run_renewal_loop` performs 0 actions even when legacy environment variables like `CONNECTOR_1_TYPE=hashicorp` are set.

### Gate Evidence (Raw Output of Config Divergence Test)
Ran `python -m unittest tests.test_gate7_config_divergence -v`:
```
=== TEST CONFIG DIVERGENCE: DB Authoritative Source ===
[DB STATE] len(active_connectors) == 0

======================================================================
RENEWAL LOOP SUMMARY: 0 checked, 0 renewed (no active connectors in DB)
======================================================================
[RENEWAL LOOP RESULT] summary == {}
[SUMMARY ACTIONS] checked=0 succeeded=0 skipped=0 failed=0
[RESULT] PASSED: 0 checked, 0 renewed when DB connectors table is empty despite CONNECTOR_1_TYPE=hashicorp in os.environ
```

---

## Gate G: SQLite Hygiene (`run_migrations` & `PRAGMA user_version`)

### Changes Made
1. Extracted all table creations and idempotent column migrations from `get_db_connection()` into `run_migrations(db_path_or_conn=None)` in `src/db.py`.
2. Guarded `run_migrations` with `PRAGMA user_version` (`CURRENT_SCHEMA_VERSION = 1`). If `PRAGMA user_version >= CURRENT_SCHEMA_VERSION`, `run_migrations` returns immediately without running any schema inspection or DDL.
3. Called `db.run_migrations()` explicitly at FastAPI startup (`src/api.py`) and Celery worker ready (`src/tasks.py:on_worker_ready`).
4. Included `# ponytail: manual PRAGMA user_version check is sufficient for additive schema changes; deferred Alembic until complex migrations needed.` comment.

### Gate G Evidence (Raw Terminal Output)
Ran 20 iterations of `get_db_connection(tmp)` in a loop:
```
--- Running 20 loop iterations of get_db_connection() ---
[DB MIGRATION] Running DB schema migrations (version 0 -> 1)
--- Loop complete ---
```
Regression test suite output:
```
Ran 21 tests in 30.349s

OK (skipped=2)
```

---

## Gate H: Start `RenewalScheduler` from FastAPI Lifecycle

### Architectural Decision
- Selected **Option (b)**: `RenewalScheduler.job_callback` is wired to a logging-only shim (`_event_driven_scheduler_callback`) that records `RenewalScheduler due job detected; Celery Beat owns actual triggering.`.
- Celery Beat continues to own periodic due-cert scanning and pipeline triggering to prevent double-triggering.

### Changes Made
1. Added `@app.on_event("startup")` instantiation of `RenewalScheduler` (`sched.start()`) stored on `app.state.scheduler`.
2. Added `@app.on_event("shutdown")` cleanup hook calling `sched.stop()`.
3. Updated `GET /api/scheduler/status` to return `isRunning: bool` reflecting whether the in-process event-driven scheduler thread is alive.

### Gate H Evidence (Raw Log Output)
Ran FastAPI lifecycle startup, hit `GET /api/scheduler/status`, and executed shutdown:
```
2026-07-14 01:39:59,481 [INFO] RenewalScheduler started (event-driven mode, DB-backed recovery).
2026-07-14 01:39:59,490 [INFO] RenewalScheduler due job detected; Celery Beat owns actual triggering.
--- STARTING SERVER ---
--- HITTING GET /api/scheduler/status ---
STATUS: 200
RESPONSE: {
  "isRunning": true,
  "nextJob": ...,
  "upcoming": ...,
  "recentEvents": ...
}
--- STOPPING SERVER ---
2026-07-14 01:40:09,287 [INFO] RenewalScheduler stopped.
--- SERVER STOPPED ---
```

---

## Gate 5: Live Pipeline + Worker Kill

> Gate 5 (live pipeline + worker kill): PENDING — could not run, step-ca service not available on this machine (`https://localhost:8443` actively refused connection). Must be run on primary dev machine before TRD.md's Celery-pipeline debt row can be upgraded from "Partially verified" to "Resolved."

---

## Phase 2 Outstanding Technical Debt: Incomplete Multi-Tenant Read Scoping (Gate 5 Audit Gap)

> [!WARNING]
> **Explicit Open Item for Phase 2 Multi-Tenancy Exit Criteria**
> Currently, `tenant_id` filtering is wired into only 4 read endpoints (`GET /api/certificates`, `GET /api/certificates/due`, `GET /api/certificates/{vault_source}/{name}`, `GET /api/connectors`).

### Unscoped Read Endpoints (Must be scoped before Phase 2 completion)
The following 7 authenticated GET endpoints currently return global data across all tenants and must be updated to filter by `_get_tenant_scope(current_user)`:
1. `GET /api/activity-log`
2. `GET /api/renewal-log`
3. `GET /api/groups`
4. `GET /api/maintenance-windows`
5. `GET /api/notification-policies`
6. `GET /api/notification-log`
7. `GET /api/scheduler/status`

Additionally, all mutating endpoints (`POST`, `PUT`, `PATCH`, `DELETE`) currently enforce `require_admin` role but do not verify that the target entity belongs to the caller's `tenant_id` or `org_id`.

---

## Stage 2 Pre-Coding Questions

### 1. Roles
- **Confirmed Role Set for v1**: `admin` and `viewer` only. No third role is implied in the codebase.
- **Existing references to roles/permissions in codebase** (grep output across `src/`):
  ```
  src/api.py:136:    if current_user.get("role") == "admin":
  src/api.py:203:    is_admin = current_user.get("role") == "admin"
  src/auth.py:47:def _make_token(user_id: int, email: str, role: str, tenant_id: str = "default") -> str:
  src/auth.py:49:    payload = {"sub": str(user_id), "email": email, "role": role, "tenant_id": tenant_id, "exp": expire}
  src/auth.py:77:    if current_user.get("role") != "admin":
  src/auth.py:90:    role: str = "viewer"
  src/auth.py:99:    token = _make_token(user["id"], user["email"], user["role"], tenant_id=tid)
  src/auth.py:102:    return {"id": user["id"], "email": user["email"], "role": user["role"], "tenant_id": tid}
  src/auth.py:123:    if body.role not in ("admin", "viewer"):
  src/auth.py:143:    if body.role not in ("admin", "viewer"):
  src/db.py:180:                role TEXT NOT NULL DEFAULT 'viewer',
  src/db.py:295:    role: str = "viewer",
  src/seed_admin.py:38:uid = db.create_user(ADMIN_EMAIL, auth.hash_password(ADMIN_PASSWORD), role="admin")
  ```
- **Proposed Role Set**: Exactly `admin` (full read + mutating access) and `viewer` (read-only access).

### 2. Session Mechanism
- **Selected Mechanism**: **JWT (stateless)** signed with HMAC-SHA256 (`HS256`) using dedicated secret `JWT_SECRET`, stored in an HTTP-only, `SameSite=Strict` cookie (`certops_token`).
- **Why**: `JWT_SECRET` is already documented in `.env.example`, `RUNBOOK.md`, and implemented in `src/auth.py`.
- **Grep output for `JWT_SECRET` references across repository**:
  ```
  .env.example:6:JWT_SECRET=change-me-to-a-random-256-bit-hex-string
  RUNBOOK.md:14:Required env vars: `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `JWT_SECRET`.
  src/auth.py:24:JWT_SECRET = os.getenv("JWT_SECRET", "change-me-before-any-external-access")
  src/auth.py:50:    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
  src/auth.py:55:        data = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
  ```

### 3. Password Storage
- **Confirmed Hashing Library/Algorithm**: `bcrypt` (`bcrypt.hashpw` with salt rounds=12).
- **Relevant dependency file contents (`requirements.txt`)**:
  ```
  azure-identity
  azure-keyvault-certificates
  bcrypt
  cryptography
  fastapi
  paramiko
  PyJWT
  python-dotenv
  pywinrm
  requests
  uvicorn[standard]
  celery
  redis
  ```
  Both `bcrypt` (line 3) and `PyJWT` (line 7) are already installed dependencies.

### 4. Tenant Column State
- **Live Schema Output** from `sqlite_master` in `certops.db` confirming `tenant_id` is already present on `users`, `certificates`, and `connectors`:
  ```sql
  CREATE TABLE users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              email TEXT UNIQUE NOT NULL,
              password_hash TEXT NOT NULL,
              role TEXT NOT NULL DEFAULT 'viewer',
              created_at TEXT NOT NULL
          , tenant_id TEXT DEFAULT 'default')
  ```
  ```sql
  CREATE TABLE certificates (
              vault_source TEXT NOT NULL,
              name TEXT NOT NULL,
              ...
              tenant_id TEXT DEFAULT 'default',
              PRIMARY KEY (vault_source, name)
          )
  ```
  ```sql
  CREATE TABLE connectors (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT UNIQUE NOT NULL,
              category TEXT NOT NULL,
              ...
              tenant_id TEXT DEFAULT 'default')
  ```

### 5. Existing Auth Code
- **Verbatim current implementation** of `get_current_user` and `require_admin` in `src/auth.py` (lines 70–80):
  ```python
  def get_current_user(token: Optional[str] = Cookie(default=None, alias=COOKIE_NAME)) -> dict:
      if not token:
          raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
      return _decode_token(token)


  def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
      if current_user.get("role") != "admin":
          raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
      return current_user
  ```

### 6. Endpoint Inventory
Complete list of all API endpoints across `src/auth.py` and `src/api.py`, categorized by method, read vs. mutating, and minimum protection level required per Stage 2:

| Endpoint | Method | Type | Current Protection | Target Stage 2 Protection Level |
|---|---|---|---|---|
| `/auth/login` | POST | Mutating | Public | Public (Authentication Endpoint) |
| `/auth/me` | GET | Read | `get_current_user` | `require_authenticated` (`get_current_user`) |
| `/auth/logout` | POST | Mutating | Public | Public / Clear Cookie |
| `/auth/signup` | POST | Mutating | `require_admin` | `require_admin` |
| `/auth/invites` | POST | Mutating | `require_admin` | `require_admin` |
| `/auth/register-with-invite` | POST | Mutating | Public | Public (Invite redemption) |
| `/api/health` | GET | Read | Public | Public / Health probe |
| `/api/certificates` | GET | Read | `get_current_user` | `require_authenticated` + Tenant Scoped |
| `/api/certificates/due` | GET | Read | `get_current_user` | `require_authenticated` + Tenant Scoped |
| `/api/certificates/{vault_source}/{name}` | GET | Read | `get_current_user` | `require_authenticated` + Tenant Scoped |
| `/api/renewal-log` | GET | Read | `get_current_user` | `require_authenticated` + Tenant Scoped |
| `/api/activity-log` | GET | Read | `get_current_user` | `require_authenticated` + Tenant Scoped |
| `/api/connectors` | GET | Read | `get_current_user` | `require_authenticated` + Tenant Scoped |
| `/api/connectors` | POST | Mutating | `require_admin` | `require_admin` + Tenant Scoped |
| `/api/connectors/{connector_id}` | PUT | Mutating | `require_admin` | `require_admin` + Tenant Scoped |
| `/api/connectors/{connector_id}` | PATCH | Mutating | `require_admin` | `require_admin` + Tenant Scoped |
| `/api/connectors/{connector_id}` | DELETE | Mutating | `require_admin` | `require_admin` + Tenant Scoped |
| `/api/connectors/{connector_id}/test` | POST | Mutating | `require_admin` | `require_admin` + Tenant Scoped |
| `/api/groups` | GET | Read | `get_current_user` | `require_authenticated` + Tenant Scoped |
| `/api/groups` | POST | Mutating | `require_admin` | `require_admin` + Tenant Scoped |
| `/api/certificates/assign-group` | POST | Mutating | `require_admin` | `require_admin` + Tenant Scoped |
| `/api/maintenance-windows` | GET | Read | `get_current_user` | `require_authenticated` + Tenant Scoped |
| `/api/maintenance-windows` | POST | Mutating | `require_admin` | `require_admin` + Tenant Scoped |
| `/api/notification-policies` | GET | Read | `get_current_user` | `require_authenticated` + Tenant Scoped |
| `/api/notification-policies` | POST | Mutating | `require_admin` | `require_admin` + Tenant Scoped |
| `/api/notification-policies/{policy_id}` | DELETE | Mutating | `require_admin` | `require_admin` + Tenant Scoped |
| `/api/notification-log` | GET | Read | `get_current_user` | `require_authenticated` + Tenant Scoped |
| `/api/scheduler/status` | GET | Read | `get_current_user` | `require_authenticated` + Tenant Scoped |
| `/api/host/confirm-reload` | POST | Mutating | `require_admin` | `require_admin` + Tenant Scoped |

---

---

## Gate H: Start `RenewalScheduler` from FastAPI Lifecycle

### Architectural Decision
- Selected **Option (b)**: `RenewalScheduler.job_callback` is wired to a logging-only shim (`_event_driven_scheduler_callback`) that records `RenewalScheduler due job detected; Celery Beat owns actual triggering.`.
- Celery Beat continues to own periodic due-cert scanning and pipeline triggering to prevent double-triggering.

### Changes Made
1. Added `@app.on_event("startup")` instantiation of `RenewalScheduler` (`sched.start()`) stored on `app.state.scheduler`.
2. Added `@app.on_event("shutdown")` cleanup hook calling `sched.stop()`.
3. Updated `GET /api/scheduler/status` to return `isRunning: bool` reflecting whether the in-process event-driven scheduler thread is alive.

### Gate H Evidence (Raw Log Output)
Ran FastAPI lifecycle startup, hit `GET /api/scheduler/status`, and executed shutdown:
```
2026-07-14 01:39:59,481 [INFO] RenewalScheduler started (event-driven mode, DB-backed recovery).
2026-07-14 01:39:59,490 [INFO] RenewalScheduler due job detected; Celery Beat owns actual triggering.
--- STARTING SERVER ---
--- HITTING GET /api/scheduler/status ---
STATUS: 200
RESPONSE: {
  "isRunning": true,
  "nextJob": ...,
  "upcoming": ...,
  "recentEvents": ...
}
--- STOPPING SERVER ---
2026-07-14 01:40:09,287 [INFO] RenewalScheduler stopped.
--- SERVER STOPPED ---
```

---

## Gate 5: Live Pipeline + Worker Kill

> Gate 5 (live pipeline + worker kill): PENDING — could not run, step-ca service not available on this machine (`https://localhost:8443` actively refused connection). Must be run on primary dev machine before TRD.md's Celery-pipeline debt row can be upgraded from "Partially verified" to "Resolved."

---

## Phase 2 Outstanding Technical Debt: Incomplete Multi-Tenant Read Scoping (Gate 5 Audit Gap)

> [!WARNING]
> **Explicit Open Item for Phase 2 Multi-Tenancy Exit Criteria**
> Currently, `tenant_id` filtering is wired into only 4 read endpoints (`GET /api/certificates`, `GET /api/certificates/due`, `GET /api/certificates/{vault_source}/{name}`, `GET /api/connectors`).

### Unscoped Read Endpoints (Must be scoped before Phase 2 completion)
The following 7 authenticated GET endpoints currently return global data across all tenants and must be updated to filter by `_get_tenant_scope(current_user)`:
1. `GET /api/activity-log`
2. `GET /api/renewal-log`
3. `GET /api/groups`
4. `GET /api/maintenance-windows`
5. `GET /api/notification-policies`
6. `GET /api/notification-log`
7. `GET /api/scheduler/status`

Additionally, all mutating endpoints (`POST`, `PUT`, `PATCH`, `DELETE`) currently enforce `require_admin` role but do not verify that the target entity belongs to the caller's `tenant_id` or `org_id`.

---

## Stage 2 Pre-Coding Questions

### 1. Roles
- **Confirmed Role Set for v1**: `admin` and `viewer` only. No third role is implied in the codebase.
- **Existing references to roles/permissions in codebase** (grep output across `src/`):
  ```
  src/api.py:136:    if current_user.get("role") == "admin":
  src/api.py:203:    is_admin = current_user.get("role") == "admin"
  src/auth.py:47:def _make_token(user_id: int, email: str, role: str, tenant_id: str = "default") -> str:
  src/auth.py:49:    payload = {"sub": str(user_id), "email": email, "role": role, "tenant_id": tenant_id, "exp": expire}
  src/auth.py:77:    if current_user.get("role") != "admin":
  src/auth.py:90:    role: str = "viewer"
  src/auth.py:99:    token = _make_token(user["id"], user["email"], user["role"], tenant_id=tid)
  src/auth.py:102:    return {"id": user["id"], "email": user["email"], "role": user["role"], "tenant_id": tid}
  src/auth.py:123:    if body.role not in ("admin", "viewer"):
  src/auth.py:143:    if body.role not in ("admin", "viewer"):
  src/db.py:180:                role TEXT NOT NULL DEFAULT 'viewer',
  src/db.py:295:    role: str = "viewer",
  src/seed_admin.py:38:uid = db.create_user(ADMIN_EMAIL, auth.hash_password(ADMIN_PASSWORD), role="admin")
  ```
- **Proposed Role Set**: Exactly `admin` (full read + mutating access) and `viewer` (read-only access).

### 2. Session Mechanism
- **Selected Mechanism**: **JWT (stateless)** signed with HMAC-SHA256 (`HS256`) using dedicated secret `JWT_SECRET`, stored in an HTTP-only, `SameSite=Strict` cookie (`certops_token`).
- **Why**: `JWT_SECRET` is already documented in `.env.example`, `RUNBOOK.md`, and implemented in `src/auth.py`.
- **Grep output for `JWT_SECRET` references across repository**:
  ```
  .env.example:6:JWT_SECRET=change-me-to-a-random-256-bit-hex-string
  RUNBOOK.md:14:Required env vars: `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `JWT_SECRET`.
  src/auth.py:24:JWT_SECRET = os.getenv("JWT_SECRET", "change-me-before-any-external-access")
  src/auth.py:50:    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
  src/auth.py:55:        data = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
  ```

### 3. Password Storage
- **Confirmed Hashing Library/Algorithm**: `bcrypt` (`bcrypt.hashpw` with salt rounds=12).
- **Relevant dependency file contents (`requirements.txt`)**:
  ```
  azure-identity
  azure-keyvault-certificates
  bcrypt
  cryptography
  fastapi
  paramiko
  PyJWT
  python-dotenv
  pywinrm
  requests
  uvicorn[standard]
  celery
  redis
  ```
  Both `bcrypt` (line 3) and `PyJWT` (line 7) are already installed dependencies.

### 4. Tenant Column State
- **Live Schema Output** from `sqlite_master` in `certops.db` confirming `tenant_id` is already present on `users`, `certificates`, and `connectors`:
  ```sql
  CREATE TABLE users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              email TEXT UNIQUE NOT NULL,
              password_hash TEXT NOT NULL,
              role TEXT NOT NULL DEFAULT 'viewer',
              created_at TEXT NOT NULL
          , tenant_id TEXT DEFAULT 'default')
  ```
  ```sql
  CREATE TABLE certificates (
              vault_source TEXT NOT NULL,
              name TEXT NOT NULL,
              ...
              tenant_id TEXT DEFAULT 'default',
              PRIMARY KEY (vault_source, name)
          )
  ```
  ```sql
  CREATE TABLE connectors (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT UNIQUE NOT NULL,
              category TEXT NOT NULL,
              ...
              tenant_id TEXT DEFAULT 'default')
  ```

### 5. Existing Auth Code
- **Verbatim current implementation** of `get_current_user` and `require_admin` in `src/auth.py` (lines 70–80):
  ```python
  def get_current_user(token: Optional[str] = Cookie(default=None, alias=COOKIE_NAME)) -> dict:
      if not token:
          raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
      return _decode_token(token)


  def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
      if current_user.get("role") != "admin":
          raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
      return current_user
  ```

### 6. Endpoint Inventory
Complete list of all API endpoints across `src/auth.py` and `src/api.py`, categorized by method, read vs. mutating, and minimum protection level required per Stage 2:

| Endpoint | Method | Type | Current Protection | Target Stage 2 Protection Level |
|---|---|---|---|---|
| `/auth/login` | POST | Mutating | Public | Public (Authentication Endpoint) |
| `/auth/me` | GET | Read | `get_current_user` | `require_authenticated` (`get_current_user`) |
| `/auth/logout` | POST | Mutating | Public | Public / Clear Cookie |
| `/auth/signup` | POST | Mutating | `require_admin` | `require_admin` |
| `/auth/invites` | POST | Mutating | `require_admin` | `require_admin` |
| `/auth/register-with-invite` | POST | Mutating | Public | Public (Invite redemption) |
| `/api/health` | GET | Read | Public | Public / Health probe |
| `/api/certificates` | GET | Read | `get_current_user` | `require_authenticated` + Tenant Scoped |
| `/api/certificates/due` | GET | Read | `get_current_user` | `require_authenticated` + Tenant Scoped |
| `/api/certificates/{vault_source}/{name}` | GET | Read | `get_current_user` | `require_authenticated` + Tenant Scoped |
| `/api/renewal-log` | GET | Read | `get_current_user` | `require_authenticated` + Tenant Scoped |
| `/api/activity-log` | GET | Read | `get_current_user` | `require_authenticated` + Tenant Scoped |
| `/api/connectors` | GET | Read | `get_current_user` | `require_authenticated` + Tenant Scoped |
| `/api/connectors` | POST | Mutating | `require_admin` | `require_admin` + Tenant Scoped |
| `/api/connectors/{connector_id}` | PUT | Mutating | `require_admin` | `require_admin` + Tenant Scoped |
| `/api/connectors/{connector_id}` | PATCH | Mutating | `require_admin` | `require_admin` + Tenant Scoped |
| `/api/connectors/{connector_id}` | DELETE | Mutating | `require_admin` | `require_admin` + Tenant Scoped |
| `/api/connectors/{connector_id}/test` | POST | Mutating | `require_admin` | `require_admin` + Tenant Scoped |
| `/api/groups` | GET | Read | `get_current_user` | `require_authenticated` + Tenant Scoped |
| `/api/groups` | POST | Mutating | `require_admin` | `require_admin` + Tenant Scoped |
| `/api/certificates/assign-group` | POST | Mutating | `require_admin` | `require_admin` + Tenant Scoped |
| `/api/maintenance-windows` | GET | Read | `get_current_user` | `require_authenticated` + Tenant Scoped |
| `/api/maintenance-windows` | POST | Mutating | `require_admin` | `require_admin` + Tenant Scoped |
| `/api/notification-policies` | GET | Read | `get_current_user` | `require_authenticated` + Tenant Scoped |
| `/api/notification-policies` | POST | Mutating | `require_admin` | `require_admin` + Tenant Scoped |
| `/api/notification-policies/{policy_id}` | DELETE | Mutating | `require_admin` | `require_admin` + Tenant Scoped |
| `/api/notification-log` | GET | Read | `get_current_user` | `require_authenticated` + Tenant Scoped |
| `/api/scheduler/status` | GET | Read | `get_current_user` | `require_authenticated` + Tenant Scoped |
| `/api/host/confirm-reload` | POST | Mutating | `require_admin` | `require_admin` + Tenant Scoped |

---

## Track D Remediation (v2) — Raw Evidence Log

### Step 1: Repo Hygiene & `.gitignore` Evidence
**Updated `.gitignore` Block:**
```text
# Debug/verification scratch — not part of the permanent suite
.superpowers/sdd/verify_*.py
.superpowers/sdd/*.diff
.superpowers/sdd/*.md
phase0_exit_gate_report_*.md
*.debug.md
*.db-shm
*.db-wal
```

**Confirmed Untracked Files Check (`git status` showing zero debug/scratch items staged or untracked):**
```text
Untracked files:
  (use "git add <file>..." to include in what will be committed)
	TELEMETRY_CONTRACT.md
```
All one-off verification scripts (`verify_*.py`), task runner diffs/reports (`.superpowers/sdd/`), and temporary SQLite write-ahead/shared-memory logs are cleanly ignored without deleting them from disk.

### Step 2: Finding 3 — Duplicated `agent_auth.py` Consolidation
**Design Decision:** Option A (Dashboard-Only).
- **Architectural Rationale:** The agent execution module (`certops-agent/`) acts purely as an HTTP client when pushing telemetry. It reads its scoped token (`AGENT_TOKEN_SIGNING_KEY` / bearer token) and transmits it via `AgentTelemetryClient` in `agent_telemetry.py`. Only the central server (`certops-dashboard/`) requires token verification, signing, revocation checking (`agent_tokens` SQLite table), and FastAPI dependency injection (`require_agent_token_or_db`).
- **Repo State Verification:** `certops-agent/src/agent_auth.py` has been completely removed (`git rm`). The sole authoritative implementation resides in `certops-dashboard/src/agent_auth.py` (`6449 bytes`). Zero duplicate or drift-prone auth logic exists across the package boundaries.

### Step 3: Finding 4 — Real Boot Checks (`uvicorn` + `Celery worker`)
**Real `uvicorn` Boot Output (`certops-dashboard/src/api:app`):**
Verified live uvicorn server boot on `http://127.0.0.1:8099`, confirmed public endpoint `GET /api/health` returns `200 OK`, confirmed protected endpoint `GET /api/certificates` enforces RBAC with `401 Unauthorized` when requested without cookie/JWT, and verified clean lifecycle startup (`sched.start()`) and shutdown (`sched.stop()`):
```text
INFO:     Started server process [33868]
INFO:     Waiting for application startup.
2026-07-15 08:37:11,495 [INFO] RenewalScheduler started (event-driven mode, DB-backed recovery).
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8099 (Press CTRL+C to quit)
================================================================================
CERTOPS-DASHBOARD REAL UVICORN BOOT & HTTP ENDPOINT VERIFICATION
================================================================================

[STEP 1] uvicorn server starting on http://127.0.0.1:8099...
[SCHEDULER SLEEP] Next job 'live-vault-cert-01' scheduled at 2026-10-10T00:00:00+00:00 (in 7505568.50s). Zero-polling sleep activated (capped at 3600s).
[STEP 2] uvicorn server booted successfully! Testing real HTTP request...
INFO:     127.0.0.1:63094 - "GET /api/health HTTP/1.1" 200 OK
[STEP 3a] HTTP GET /api/health -> Status: 200
          Response body: {"status":"ok"}
INFO:     127.0.0.1:63095 - "GET /api/certificates HTTP/1.1" 401 Unauthorized
INFO:     Shutting down
INFO:     Waiting for application shutdown.
2026-07-15 08:37:11,716 [INFO] RenewalScheduler stopped.
INFO:     Application shutdown complete.
INFO:     Finished server process [33868]
[STEP 3b] HTTP GET /api/certificates without cookie -> Status: 401 (Expected RBAC enforcement)

SUCCESS: Real uvicorn boot, public endpoint serving (200), and RBAC enforcement (401) PASSED.
[STEP 4] Shutting down uvicorn server cleanly...
uvicorn server shut down.
```

**Real Celery Worker Subprocess Boot Output (`certops-agent/src/tasks.py`):**
Verified live `celery worker` startup (`--pool=solo`) inside `certops-agent/`, confirming clean connection to Redis broker (`redis://localhost:6379/0`), registration of all four core pipeline tasks, and successful triggering of the `@worker_ready` auto-resume handler:
```text
 -------------- celery@Arpits-Lappy v5.6.3 (recovery)
--- ***** ----- 
-- ******* ---- Windows-11-10.0.26200-SP0 2026-07-15 08:42:02
- *** --- * --- 
- ** ---------- [config]
- ** ---------- .> app:         certops:0x1f570528590
- ** ---------- .> transport:   redis://localhost:6379/0
- ** ---------- .> results:     redis://localhost:6379/0
- *** --- * --- .> concurrency: 12 (solo)
-- ******* ---- .> task events: OFF (enable -E to monitor tasks in this worker)
--- ***** ----- 
 -------------- [queues]
                .> celery           exchange=celery(direct) key=celery
                

[tasks]
  . tasks.check_and_trigger_renewals
  . tasks.deploy_certificate
  . tasks.renew_certificate
  . tasks.verify_reload

[2026-07-15 08:42:02,373: INFO/MainProcess] Connected to redis://localhost:6379/0
[2026-07-15 08:42:02,398: INFO/MainProcess] mingle: searching for neighbors
[2026-07-15 08:42:03,497: INFO/MainProcess] mingle: all alone
[2026-07-15 08:42:03,554: INFO/MainProcess] Celery worker ready signal triggered. Scanning DB for interrupted pipelines...
[2026-07-15 08:42:03,560: WARNING/MainProcess] [DB MIGRATION] Running DB schema migrations (version 0 -> 2)
[2026-07-15 08:42:03,560: INFO/MainProcess] Running DB schema migrations (version 0 -> 2)
[2026-07-15 08:42:03,573: INFO/MainProcess] Worker startup auto-resume complete. Resumed 0 pipeline(s).
[2026-07-15 08:42:03,573: INFO/MainProcess] celery@Arpits-Lappy ready.
```

### Step 4: Finding 2 — Literal Track C Payload & Contract Diff Evidence
**Verbatim Captured JSON Payload from Real Push Client (`agent_telemetry.build_payload()`):**
```json
{
  "agent_id": "agent-prod-us-east-1",
  "agent_version": "1.0.0",
  "timestamp": "2026-07-15T03:12:47.789353+00:00",
  "items": [
    {
      "connector_type": "vault",
      "connector_opaque_id": "conn-vault-sha256-a1b2",
      "connector_health": "ok",
      "connector_status": "Healthy secret store connection",
      "error_code": null,
      "cert_cn": "vault-cert.local",
      "cert_san": [
        "www.vault-cert.local",
        "api.vault-cert.local"
      ],
      "expiry_utc": "2028-07-12T03:12:47.789321+00:00",
      "renewal_stage": "healthy"
    },
    {
      "connector_type": "azure_kv",
      "connector_opaque_id": "conn-azure-sha256-c3d4",
      "connector_health": "ok",
      "connector_status": "Healthy Azure KV connection",
      "error_code": null,
      "cert_cn": "azure-cert.local",
      "cert_san": [],
      "expiry_utc": "2026-08-14T03:12:47.789321+00:00",
      "renewal_stage": "healthy"
    },
    {
      "connector_type": "ssh",
      "connector_opaque_id": "conn-ssh-sha256-e5f6",
      "connector_health": "ok",
      "connector_status": "SSH deploy check passed",
      "error_code": null,
      "cert_cn": "ssh-host.local",
      "cert_san": [
        "host1.local"
      ],
      "expiry_utc": "2026-07-25T03:12:47.789321+00:00",
      "renewal_stage": "due_soon"
    },
    {
      "connector_type": "winrm",
      "connector_opaque_id": "conn-winrm-sha256-7890",
      "connector_health": "error",
      "connector_status": "Connection timed out during host check",
      "error_code": "ERR_CONNECTION_TIMEOUT",
      "cert_cn": "winrm-host.local",
      "cert_san": [],
      "expiry_utc": "2026-07-16T03:12:47.789321+00:00",
      "renewal_stage": "overdue"
    }
  ]
}
```

**Programmatic Contract Diff Output (Field-by-Field Audit against `TELEMETRY_CONTRACT.md`):**
```text
Allow-list check violations count: 0
  -> 0 allow-list violations
Deny-list check violations count: 0
  -> 0 deny-list violations

SUCCESS: 0 violations. Real payload matches TELEMETRY_CONTRACT exactly.
```
All fields present are strictly allow-listed (`agent_id`, `agent_version`, `timestamp`, `items`, `connector_type`, `connector_opaque_id`, `connector_health`, `connector_status`, `error_code`, `cert_cn`, `cert_san`, `expiry_utc`, `renewal_stage`). Zero deny-listed patterns (`PRIVATE KEY`, `secret/data/`, passwords, IP addresses, raw hostnames, stack traces) cross the wire.


