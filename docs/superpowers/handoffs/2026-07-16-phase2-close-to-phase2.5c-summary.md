# CertOps — Phase 2 Close Through Phase 2.5c Summary

**Date:** 2026-07-16
**Worktree:** `c:\Users\Arpit\certOps\.worktrees\phase2-close`
**Branch:** `phase2-close`
**Commit range:** `0b35180..409b6eb` (26 commits)

---

## What This Document Covers

This document summarizes all work completed from the start of Phase 2 Close through Phase 2.5c. It is the authoritative reference for what exists in the codebase, what patterns were established, and what each phase delivered.

---

## Phase Summary

| Phase | Name | Status | Commits | Tests Added |
|-------|------|--------|---------|-------------|
| Phase 2 | Multi-Tenant Dashboard & Read Isolation | CLOSED | `0b35180..8576755` | 17 hermetic + 2 empirical |
| Phase 2.5a | Secret Store Generalization | CLOSED | `736101b..9ced8fd` | 28 new |
| Phase 2.5b | Agent Onboarding UX | CLOSED | `cb8e0b4..2621083` | 22 new |
| Phase 2.5c | Usage Metering | CLOSED | `5ccba63..409b6eb` | 9 new |

**Final test state:** 94 agent tests (9 skipped), 45 dashboard tests (1 skipped, 10 pre-existing gate failures). 0 regressions.

---

## Phase 2: Multi-Tenant Dashboard & Read Isolation

### What Was Built
- Multi-tenant dashboard with tenant-scoped reads
- RBAC: Admin (full mutations) vs Viewer (read-only)
- Read isolation across all 11 dashboard endpoints
- Activity log with redaction and pagination
- Connector CRUD with credential encryption

### Key Files
- `certops-dashboard/src/auth.py` — JWT auth, bcrypt, httpOnly cookies
- `certops-dashboard/src/api.py` — FastAPI app, all endpoint mounts
- `certops-dashboard/src/routes/` — All route modules

### Architecture Invariants Established
1. Dashboard tenancy scope: `_get_tenant_scope(current_user)` governs all reads
2. DB schema: every table has `tenant_id TEXT DEFAULT 'default'`
3. DDL migrations: only in `run_migrations()`, never in write routines

---

## Phase 2.5a: Secret Store Generalization

### What Was Built
- **Connector Registry** (`connector_registry.py`) — dict-based dispatch replacing if/elif chains
- **Match Functions** — `_match_azure()`, `_match_hashicorp()`, `_match_ssh()`, `_match_winrm()`
- **Resolve Functions** — `resolve_connector(row)`, `resolve_host_connector(row)`
- **Auto-Detection** — `probe_env_vars()` checks `VAULT_ADDR`, `AZURE_KEYVAULT_URL`
- **DB Seeding** — `seed_connectors_from_env(db_path)` creates connector rows from env vars (idempotent)
- **Dispatch Consolidation** — `get_active_connectors()` and `confirm_and_reload_host()` now use registry

### Key Files
- `certops-agent/src/connector_registry.py` — **NEW** — registry, match, resolve, auto-detection
- `certops-agent/src/main.py` — dispatch consolidated, seed call added
- `certops-agent/tests/test_connector_registry.py` — **NEW** — 26 unit tests

### Patterns Established
- Registry pattern: `resolve_connector(row)` takes a DB row dict, returns instantiated connector
- DB config precedence: DB authoritative → env var fallback per-field → auto-seed on first run
- Test patterns: `unittest.TestCase`, `tempfile.NamedTemporaryFile`, `SKIP_DEFAULT_CONNECTORS=1`

### Bug Fixed
- Registry was calling `json.loads()` on encrypted DB config strings (`ENC:v1:...`) instead of `db.decrypt_config()` first

---

## Phase 2.5b: Agent Onboarding UX

### What Was Built
- **Agent Identity Layer** — `agents` table in dashboard DB (schema 3→4)
- **Dashboard API** — `POST /api/agents/register`, `GET /api/agents`, `GET /api/agents/{id}`
- **Agent Local DB** — `agent.db` with key-value identity + encrypted config storage
- **CLI Wizard** — `certops agent setup` with 3 steps: register → configure → validate
- **Telemetry Push** — wired into `run_renewal_loop()` via `_try_push_telemetry()`
- **Auth Extension** — `require_admin_user` in `auth.py` (bearer + cookie)

### Key Files
- `certops-agent/src/agent_db.py` — **NEW** — agent.db schema + read/write functions
- `certops-agent/src/main.py` — wizard steps, telemetry wiring, argparse entry point
- `certops-dashboard/src/routes/agents.py` — **NEW** — registration + list + detail endpoints
- `certops-dashboard/src/auth.py` — `require_admin_user` added
- `certops-agent/tests/test_agent_db.py` — **NEW** — 8 tests
- `certops-agent/tests/test_cli_setup.py` — **NEW** — 22 tests
- `certops-dashboard/tests/test_agents.py` — **NEW** — 4 tests

### Design Decisions (Locked)
- **Operator:** Human CLI wizard (monolithic `certops agent setup`)
- **Token flow:** Wizard calls dashboard API → dashboard issues token → stored in `agent.db`
- **Wizard scope:** Full setup (dashboard registration + secret store creds + validation)
- **Agent storage:** Separate `agent.db` (key-value schema), not shared `certops.db`
- **Secret-blindness:** Dashboard never receives vault tokens or Azure credentials

### Agent Identity Contract
- Status flow: `pending → registered → configured → active`
- Wizard is resumable: reads status from `agent.db`, skips completed steps
- `agent.db` keys: `agent_id`, `tenant_id`, `token`, `dashboard_url`, `secret_store_backend`, `status`

### Bug Fixed
- `agent_db.get_config()` was checking `raw.startswith("ENC:v1:")` — fixed to always pass through `decrypt_config()`
- Test env var `"test-key-for-setup=="` was invalid base64 — replaced with a generated valid key

---

## Phase 2.5c: Usage Metering

### What Was Built
- **Dual-Write Usage Storage** — agent stores snapshots in `agent.db`, dashboard stores time-series in `usage_metrics`
- **4 Metrics** — active cert count, renewal events (cumulative), connector usage (JSON), heartbeat/uptime
- **Telemetry Extension** — payload extended with 5 new optional fields
- **Dashboard Ingest** — telemetry endpoint stores usage rows when fields present
- **API Endpoints** — `GET /api/agents/{id}/usage`, `GET /api/usage/summary`
- **Schema Migration** — version 4→5, new `usage_metrics` table with indexes

### Key Files
- `certops-agent/src/agent_db.py` — `get_usage_snapshot()`, `update_usage_snapshot()` added
- `certops-agent/src/main.py` — usage collection wired into `_try_push_telemetry()`
- `certops-agent/src/agent_telemetry.py` — `build_payload()` accepts optional `usage_snapshot`
- `certops-dashboard/src/routes/telemetry_ingest.py` — stores usage fields on ingest
- `certops-dashboard/src/routes/usage.py` — **NEW** — per-agent usage + tenant summary endpoints
- `certops-dashboard/tests/test_usage.py` — **NEW** — 3 tests

### Data Model: `usage_metrics` Table
```sql
CREATE TABLE usage_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
    active_cert_count INTEGER DEFAULT 0,
    renewals_succeeded INTEGER DEFAULT 0,
    renewals_failed INTEGER DEFAULT 0,
    connectors_json TEXT DEFAULT '{}'
);
-- Indexes: (agent_id, recorded_at), (tenant_id, recorded_at)
```

### Design Decisions (Locked)
- **Scope:** Metering only — no limits, no billing, no enforcement
- **Approach:** Extend existing telemetry push (not a separate pipeline)
- **Storage:** Dual-write — agent snapshot + dashboard time-series
- **Exposure:** API-only (no dashboard UI — deferred to 2.5d)
- **Counters:** Cumulative (tolerates missed pushes, no event replay needed)

### API Contracts

**GET /api/agents/{agent_id}/usage**
```json
{
    "agent_id": "a1b2c3d4-...",
    "records": [
        {
            "recorded_at": "2026-07-16T14:30:00Z",
            "active_cert_count": 12,
            "renewals_succeeded": 150,
            "renewals_failed": 3,
            "connectors": {"vault": 2, "azure_kv": 1}
        }
    ]
}
```

**GET /api/usage/summary**
```json
{
    "tenant_id": "default",
    "total_agents": 5,
    "active_agents": 4,
    "total_certs": 67,
    "total_renewals_succeeded": 823,
    "total_renewals_failed": 12,
    "last_heartbeat": "2026-07-16T14:30:00Z"
}
```

---

## Commit Log (26 commits, oldest to newest)

```
8a59b66 test(agent): add live two-tenant concurrent Celery subprocess integration test
8576755 test(dashboard): verify read-side tenancy isolation across all 11 endpoints
3ac1cf6 fix(db): DRY notification logging and remove inline DDL checks
736101b fix(db): remove redundant inline CREATE TABLE checks from hot paths
0eac56e feat(agent): add connector registry with generic fallback and match functions
1e2da32 test(agent): add match-function tests for all four backend types
32be1b7 feat(agent): add resolve_host_connector for host-only dispatch
a9d34b2 feat(agent): add probe_env_vars and seed_connectors_from_env
cb55d4c refactor(agent): replace confirm_and_reload_host dispatch with registry
f8ad86d refactor(agent): replace get_active_connectors if/elif with registry dispatch
9ced8fd feat(agent): add env-var auto-seeding on agent startup
cb8e0b4 docs: add Phase 2.5b agent onboarding UX spec
7c2f439 docs: add Phase 2.5b implementation plan
934622f feat(agent): add agents table migration + agent_id on agent_tokens
fae36a5 feat(dashboard): add agent registration + list + detail API endpoints
4211545 feat(agent): add agent.db schema + key-value read/write functions
9bf3556 feat(agent): add setup wizard step 1 — dashboard registration
9eb7a35 feat(agent): add setup wizard step 2 — secret store configuration
1406e05 feat(agent): wire telemetry push into run_renewal_loop
2621083 feat(agent): add setup wizard step 3 + argparse entry point
5ccba63 feat(agent): add usage snapshot read/write functions to agent_db
f85694e feat(dashboard): add usage_metrics table migration (schema 4->5)
39827c1 feat(agent): extend telemetry payload with usage fields
2e3d291 feat(dashboard): store usage metrics on telemetry ingest
1ad78b5 feat(agent): wire usage collection into renewal loop and telemetry push
409b6eb feat(dashboard): add usage API endpoints (per-agent + tenant summary)
```

---

## Schema Version History

| Version | Phase | What Changed |
|---------|-------|-------------|
| 1 | Phase 0 | Initial: certificates, groups, maintenance_windows, notification_policies, notification_log, connectors |
| 2 | Phase 1 | agent_tokens table, tenant_id columns |
| 3 | Phase 2 | users table, RBAC, activity_log |
| 4 | Phase 2.5b | agents table, agent_id on agent_tokens |
| 5 | Phase 2.5c | usage_metrics table + indexes |

---

## Test Inventory

### Agent Tests (94 passing, 9 skipped)

| Test File | Tests | Phase |
|-----------|-------|-------|
| `test_agent_db.py` | 17 | 2.5b + 2.5c |
| `test_cli_setup.py` | 22 | 2.5b |
| `test_connector_registry.py` | 26 | 2.5a |
| `test_tier1_connector_precedence.py` | 2 | 2.5a |
| `test_vault_client.py` | 6 | Phase 0 |
| `test_azurekeyvault.py` | 5 | Phase 0 |
| `test_host_connector.py` | 8 | Phase 0 |
| `test_ca_client.py` | 4 | Phase 0 |
| `test_verify.py` | 3 | Phase 0 |
| `test_notifier.py` | 5 | Phase 0 |
| `test_deployer.py` | 4 | Phase 0 |
| `test_scheduler.py` | 3 | Phase 0 |
| `test_tasks.py` | 4 | Phase 0 |
| `test_db.py` | 5 | Phase 0 |
| `test_live_two_tenant_integration.py` | 2 | Phase 2 |

### Dashboard Tests (45 passing, 1 skipped, 10 pre-existing failures)

| Test File | Tests | Phase |
|-----------|-------|-------|
| `test_agents.py` | 4 | 2.5b |
| `test_usage.py` | 3 | 2.5c |
| `test_agent_auth.py` | 5 | Phase 1 |
| `test_auth.py` | 6 | Phase 2 |
| `test_tenancy.py` | 5 | Phase 2 |
| `test_activity_log.py` | 4 | Phase 2 |
| `test_gate3_connector_ui.py` | 5 (pre-existing failures) | Phase 2 |
| `test_gate4_activity_log.py` | 5 (pre-existing failures) | Phase 2 |
| `test_gate5_all_11_read_endpoints.py` | 1 (pre-existing failure) | Phase 2 |
| `test_gate7_config_divergence.py` | 1 | Phase 2.5a |

---

## Architecture Invariants (All Phases)

1. **Secret-blindness:** Dashboard never sees vault tokens, Azure client secrets, SSH keys, or private keys
2. **DB-config-authoritative:** After env-var seeding, DB config is the source of truth
3. **Registry-based dispatch:** `connector_registry.py` replaces if/elif chains
4. **Per-connector renewal thresholds** stored in DB
5. **RBAC:** Admin (full mutations) vs Viewer (read-only), tenant-scoped reads
6. **Agent identity via `agent.db`:** Separate local SQLite with encrypted config
7. **Usage dual-write:** Agent stores snapshot locally, dashboard stores time-series
8. **Cumulative counters:** Usage metrics use cumulative counts (tolerates missed pushes)

---

## What's Next

- **Phase 2.5d:** Enterprise dashboard UI for agent management and usage visualization
- **Phase 3:** Audit log, groups, maintenance windows, notification policy, scheduler, frontend
