# CertOps — Phase 2-Close Design Specification

**Date:** 2026-07-16  
**Status:** Approved by Human Partner (with refinement revisions)  
**Topic:** Closing the existing Phase 2 gaps (Read-Side Isolation & Live Two-Tenant Integration)  
**Governing Rule:** Phase 2-Close must be fully verified and closed before Phase 2.5a (or any subsequent phase) is initiated.

---

## 1. Overview & Goal

Phase 2 implemented the foundation for a multi-tenant dashboard and agent ecosystem: `tenant_id` database columns across all tables, scoped agent authentication (`agent_auth.py`), and RBAC/tenant scoping in the FastAPI API (`_get_tenant_scope()`). While 17 hermetic tests verified mutating endpoints and individual isolation examples, two formal verification gaps remained from the Phase 2 exit gate criteria:

1. **Read-Side Isolation Across All 11 Endpoints**: A single, comprehensive test asserting that Viewer A cannot read or enumerate entities belonging to Viewer B across all 11 read (`GET`) endpoints simultaneously.
2. **Live Two-Tenant Concurrent Celery Subprocess Integration**: A live end-to-end test against running infrastructure where two simulated tenants run two physical Celery worker subprocesses concurrently, triggering simultaneous pipelines and pushing telemetry without cross-tenant contamination.

Closing these two gaps fulfills the Phase 2 exit gate completely, bringing Phase 2 to **CLOSED** status with the same empirical rigor as Phase 0 and Phase 1.

---

## 2. Architecture & Approach

To preserve clean separation of concerns and maintain the stability of existing baseline suites (`test_gate5_tenancy_isolation.py` and `test_core_loop.py`), we create two dedicated test modules:

1. `certops-dashboard/tests/test_gate5_all_11_read_endpoints.py` (Hermetic test)
2. `certops-agent/tests/test_live_two_tenant_integration.py` (Live integration test)

---

## 3. Section 1: Read-Side Tenancy Isolation (`test_gate5_all_11_read_endpoints.py`)

### 3.1 Data Seeding Strategy
Using `tempfile.NamedTemporaryFile` and isolated connection pooling (`db.reset_db_connections()`), the test provisions:

- **Users**:
  - `admin@certops.internal` (`role="admin"`, `tenant_id="default"`)
  - `viewer_a@certops.internal` (`role="viewer"`, `tenant_id="tenant_A"`)
  - `viewer_b@certops.internal` (`role="viewer"`, `tenant_id="tenant_B"`)

- **Tenant A Entities (`tenant_id="tenant_A"`)**:
  - Group: `group_A` ("production_web_A")
  - Connector: `connector_A` ("vault_connector_A", category="secret_store")
  - Maintenance Window: `window_A` (linked to `group_A`)
  - Notification Policy: `policy_A` (linked to `group_A`, `threshold_days=30`)
  - Certificate: `cert_A` (`name="tenant_a_cert.crt"`, `common_name="a.example.com"`, linked to `group_A`, `expiry_utc` set to 15 days from now so it is returned by `/due`)
  - Renewal Log: `ren_log_A` (for `cert_A`, `event_type="stage_verified"`)
  - Activity Log: `act_log_A` (`event_type="group_created"`, `target="production_web_A"`)
  - Notification Log: `notif_log_A` (for `cert_A`)

- **Tenant B Entities (`tenant_id="tenant_B"`)**:
  - Group: `group_B` ("production_web_B")
  - Connector: `connector_B` ("vault_connector_B", category="secret_store")
  - Maintenance Window: `window_B` (linked to `group_B`)
  - Notification Policy: `policy_B` (linked to `group_B`, `threshold_days=30`)
  - Certificate: `cert_B` (`name="tenant_b_cert.crt"`, `common_name="b.example.com"`, linked to `group_B`, `expiry_utc` set to 15 days from now so it is returned by `/due`)
  - Renewal Log: `ren_log_B` (for `cert_B`, `event_type="stage_verified"`)
  - Activity Log: `act_log_B` (`event_type="group_created"`, `target="production_web_B"`)
  - Notification Log: `notif_log_B` (for `cert_B`)

### 3.2 The 11-Endpoint Verification Matrix
The test executes HTTP `GET` requests via `fastapi.testclient.TestClient` across all 11 endpoints and asserts exact data visibility:

| # | Endpoint | Viewer A (`tenant_A`) Must See | Viewer B (`tenant_B`) Must See | Admin (`default`) Must See |
|---|---|---|---|---|
| 1 | `GET /api/certificates` | Exactly 1 (`cert_A`) | Exactly 1 (`cert_B`) | Exactly 2 (`cert_A`, `cert_B`) |
| 2 | `GET /api/certificates/due` | Exactly 1 (`cert_A`) | Exactly 1 (`cert_B`) | Exactly 2 (`cert_A`, `cert_B`) |
| 3 | `GET /api/certificates/hashicorp/{name}` | `cert_A` -> 200<br>`cert_B` -> **404** | `cert_B` -> 200<br>`cert_A` -> **404** | Both -> 200 |
| 4 | `GET /api/renewal-log` | Exactly 1 (`ren_log_A`) | Exactly 1 (`ren_log_B`) | Exactly 2 (`ren_log_A`, `ren_log_B`) |
| 5 | `GET /api/activity-log` | Only A entries (`tenant_id=="tenant_A"`) | Only B entries (`tenant_id=="tenant_B"`) | All A + B entries |
| 6 | `GET /api/connectors` | Exactly 1 (`connector_A`) | Exactly 1 (`connector_B`) | Exactly 2 (`connector_A`, `connector_B`) |
| 7 | `GET /api/groups` | Exactly 1 (`group_A`) | Exactly 1 (`group_B`) | Exactly 2 (`group_A`, `group_B`) |
| 8 | `GET /api/maintenance-windows` | Exactly 1 (`window_A`) | Exactly 1 (`window_B`) | Exactly 2 (`window_A`, `window_B`) |
| 9 | `GET /api/notification-policies` | Exactly 1 (`policy_A`) | Exactly 1 (`policy_B`) | Exactly 2 (`policy_A`, `policy_B`) |
| 10 | `GET /api/notification-log` | Exactly 1 (`notif_log_A`) | Exactly 1 (`notif_log_B`) | Exactly 2 (`notif_log_A`, `notif_log_B`) |
| 11 | `GET /api/scheduler/status` | Next job evaluates `cert_A` only;<br>Recent logs contain `ren_log_A` only | Next job evaluates `cert_B` only;<br>Recent logs contain `ren_log_B` only | Next job evaluates both;<br>Recent logs contain both |

*Note on Endpoint #11 (`/api/scheduler/status`)*: The assertion that the single `next_job` evaluates exclusively `cert_A` for Viewer A and `cert_B` for Viewer B holds under this exact seeding (one due certificate per tenant). With multiple due certificates, tie-breaking by `next_renewal_at` applies within the tenant scope.

### 3.3 Negative-Path Query Parameter Tampering Assertions
To verify that `_get_tenant_scope()` strictly overrides any client-supplied parameters and never naively trusts query strings:
- The test issues `GET /api/certificates?tenant_id=tenant_B` authenticated as `Viewer A` and asserts the response returns only `cert_A` (zero `tenant_B` records).
- The test issues `GET /api/certificates/due?group_id={group_B_id}` authenticated as `Viewer A` and asserts the response is empty (`[]`) or returns only `cert_A` if scoped, verifying no cross-tenant group filter bleeding occurs.

---

## 4. Section 2: Live Two-Tenant Concurrent Celery Subprocess Integration (`test_live_two_tenant_integration.py`)

### 4.1 Live Infrastructure Preconditions & Hard Overall Timeout
- The test is gated by `@unittest.skipUnless(os.getenv("CERTOPS_RUN_LIVE") == "1", "requires live infra")`.
- Requires running Docker Compose services: `redis` (port 6379), `vault` (port 8200), `step-ca` (or local ca wrapper), and `nginx` (port 443).
- **Hard Overall Test Timeout**: To prevent indefinite blocking in CI/dev environments if external services stall, the test enforces a hard 90-second overall timeout (`@pytest.mark.timeout(90)` or explicit `threading.Event.wait(timeout=90)` during pipeline execution).

### 4.2 Idempotent Multi-Tenant Provisioning & Setup
To guarantee no unique constraint collisions across repeated runs or after previous crashes:
- `setUpClass` (or `setUp`) executes an explicit cleanup of any existing entities matching the run's target names, OR assigns a unique timestamp/UUID suffix (`_live_{run_id}`) to all seeded entities.
- In the shared live database (`certops.db`):
  - **Tenant A**:
    - Scoped agent token: `token_A_live_{run_id}` (`agent_tokens` table, `tenant_id="tenant_A"`).
    - Secret store connector: `hashicorp_live_A_{run_id}` (`vault_source="hashicorp"`, `tenant_id="tenant_A"`).
    - Certificate record: `tenant_a_live_{run_id}.crt` (`common_name="localhost"`, `expiry_utc="2024-01-01T00:00:00Z"` so it requires immediate renewal).
  - **Tenant B**:
    - Scoped agent token: `token_B_live_{run_id}` (`agent_tokens` table, `tenant_id="tenant_B"`).
    - Secret store connector: `hashicorp_live_B_{run_id}` (`vault_source="hashicorp"`, `tenant_id="tenant_B"`).
    - Certificate record: `tenant_b_live_{run_id}.crt` (`common_name="localhost"`, `expiry_utc="2024-01-01T00:00:00Z"` so it requires immediate renewal).

### 4.3 Concurrent Physical Subprocess Orchestration & Readiness Timeout
To simulate two independent agent instances operating simultaneously without thread interference:
- **Worker Subprocess A**: Launched via `subprocess.Popen` running `celery -A src.tasks worker -Q tenant_a_{run_id}_q --loglevel=info`.
  - Environment variables: `CERTOPS_TENANT_ID="tenant_A"`, `AGENT_TOKEN="token_A_live_{run_id}"`, `CELERY_BROKER_URL="redis://localhost:6379/0"`.
- **Worker Subprocess B**: Launched via `subprocess.Popen` running `celery -A src.tasks worker -Q tenant_b_{run_id}_q --loglevel=info`.
  - Environment variables: `CERTOPS_TENANT_ID="tenant_B"`, `AGENT_TOKEN="token_B_live_{run_id}"`, `CELERY_BROKER_URL="redis://localhost:6379/0"`.
- **Concrete Readiness Timeout**: The test polls `celery -A src.tasks status` (or inspects worker ping/redis heartbeats) with a **hard 30-second ceiling** (1-second polling intervals). If either worker fails to report ready within 30 seconds, the test aborts immediately with `RuntimeError("Celery workers failed to reach ready status within 30s")`.

### 4.4 True Synchronized Concurrent Dispatch (`threading.Barrier`)
To capture race conditions and cross-tenant contamination under genuine concurrency rather than sequential dispatch:
- Two Python worker threads are spawned, one targeting Worker A (`tenant_a_{run_id}_q`) and one targeting Worker B (`tenant_b_{run_id}_q`).
- Both threads wait on a shared `threading.Barrier(2)`.
- Upon release from the barrier at the exact millisecond, both threads invoke `tasks.start_pipeline.apply_async(...)` simultaneously.
- Both pipelines execute all 3 Celery stages:
  - **Stage 1 (Renew)**: `step-ca` issues fresh X.509 certs.
  - **Stage 2 (Deploy)**: Certs written to Vault and local disk.
  - **Stage 3 (Verify)**: Trigger Nginx reload, verify via live TLS fingerprint handshake against `localhost:443`, push telemetry to `POST /api/telemetry/ingest`.

### 4.5 Post-Execution Audit & Live-API-Level Isolation Assertions
After both pipelines complete and reach `pipeline_stage == "Reload confirmed"`:
1. **Database Audit**: Inspection confirms every `renewal_log` and `activity_log` generated during Worker A's execution has `tenant_id == "tenant_A"`, and Worker B's logs have `tenant_id == "tenant_B"`.
2. **Live-API-Level Isolation Assertions**: To verify the full live HTTP application stack (not just the database layer) matches Section 3's behavior:
   - Authenticating against the live dashboard API (`GET /api/certificates/hashicorp/tenant_a_live_{run_id}.crt`) using `Viewer B` credentials (`or token_B_live`) returns **404 Not Found**.
   - Authenticating against the live dashboard API (`GET /api/certificates/hashicorp/tenant_b_live_{run_id}.crt`) using `Viewer A` credentials (`or token_A_live`) returns **404 Not Found**.
   - Authenticating with each viewer against `GET /api/certificates` returns strictly their own live-renewed certificate (`cert_A` for A, `cert_B` for B).

### 4.6 Cross-Platform Teardown & Subprocess Safety
- Subprocess handles (`proc_a`, `proc_b`) are tracked inside `setUpClass`/`setUp`.
- Whether running on Linux CI containers or on the primary Windows development machine (`c:\Users\Arpit\certOps`), `tearDownClass`/`tearDown` ensures clean process termination (`proc.terminate()`, waiting up to 5s, falling back to `proc.kill()` if unresponsive), preventing orphaned python/celery processes from lingering across platforms.

---

## 5. Verification Plan

1. **Self-Review (Completed Inline)**:
   - Checked for placeholders or TBD items: None.
   - Checked internal consistency: All review feedback items explicitly incorporated.
   - Checked timing rules: 30s readiness timeout, 90s overall pipeline timeout, `threading.Barrier(2)` concurrent dispatch.
2. **Commit Design Doc**: Commit this specification file (`docs/superpowers/specs/2026-07-16-phase2-close-design.md`).
3. **User Approval**: Await final human partner confirmation.
4. **Implementation Plan**: Once approved, invoke `superpowers:writing-plans` to generate the implementation plan for Phase 2-Close.
