# CertOps — An Honest Build Narrative & Engineering History

This document provides the factual engineering changelog of CertOps, extracted directly from git commit logs (`git rev-list --all --count`) and project review records. It documents how the project started, where it pivoted, what broke along the way, and the exact state of the system today. We publish our self-caught mistakes and false starts because visible engineering honesty is our core credibility asset.

---

## 1. Where It Started (July 13, 2026)

CertOps began on July 13, 2026 (`2026-07-13 b85a175 Init`) not as a multi-tenant commercial SaaS platform, but as a lean, single-tenant command-line utility designed to solve a very specific homelab and internal server pain point: **automating the last mile between HashiCorp Vault secret storage and Nginx TLS reloads without running Kubernetes.**

The initial commits focused entirely on core pipeline mechanics and crash resilience:
- `2026-07-13 f47e3e6`: `fix(tier1): wire real connector logic, DB staging, and beat task idempotency with full integration tests`
- `2026-07-13 cb4356b`: `test(tier2): verify SQLite WAL mode and busy_timeout concurrency safety under 10-worker load`
- `2026-07-13 7138d78`: `feat(tier2): implement CA-agnostic ACME and step-ca issuer abstractions`

In this early iteration, all state lived in a single local database (`certops.db`), connectors were configured via ad-hoc `.env` variables (`CONNECTOR_1_TYPE`), and verification was a local socket check against localhost.

---

## 2. The Real Pivots: From Monolith to Two-Tier Product

As the project matured and external audits (Gemini, GPT-5.6, Claude Sonnet 5) reviewed the architecture (`2026-07-14 4095697`), a fundamental tension emerged: **an automated renewal agent running on sensitive client servers must never require inbound network access or expose private keys to a hosted cloud dashboard.**

This forced three structural pivots visible in the commit history:

### Pivot A: The Agent / Dashboard Code Boundary Split (`2026-07-15 cff66d6`)
- **Commit:** `refactor: consolidate agent_auth.py to dashboard-only`
- **The Problem:** A unified codebase meant the client agent imported user authentication (`auth.py`), JWT secrets (`JWT_SECRET`), and web API routes (`api.py`). If compromised, the agent footprint contained code capable of interacting with user accounts.
- **The Pivot:** The repository was physically partitioned into `certops-agent/` (open source, self-contained, Apache-2.0) and `certops-dashboard/` (closed source commercial SaaS). A strict `TELEMETRY_CONTRACT.md` was written before any cross-network code existed (`2026-07-15 e6ec0ae`), ensuring the agent pushes only sanitized health status (`agent_telemetry.py`) via per-agent tokens (`AGENT_TOKEN`), without ever exposing private keys, connector configs, or internal IP addresses.

### Pivot B: Database-Authoritative Connectors & Multi-Tenancy (`2026-07-16 0021742`)
- **Commits:** `2026-07-16 0021742 Phase 0 close-out: DB-authoritative connectors...`, `2026-07-16 57c8939 feat(api): add require_owned_entity helper for tenant ownership validation`
- **The Problem:** The dashboard UI wrote connector configurations into the `connectors` database table, but `main.py` discovered active connectors by reading `.env` variables (`CONNECTOR_N_TYPE`). The UI did not actually control what the renewal loop executed. Furthermore, a hosted dashboard without tenant data isolation (`tenant_id`) was a critical security risk.
- **The Pivot:** We eliminated environment variable connector discovery from `main.py:100-140`. The agent renewal loop now reads strictly from DB-authoritative records (`db.list_connectors(active_only=True)`). Concurrently, `X-Tenant-Id` scoping and ownership verification (`require_owned_entity`) were woven across all 11 read and mutating API endpoints (`2026-07-16 d82930a`).

### Pivot C: Server-Side Entitlement Gating & Schema v7 (`2026-07-18 efdea96`)
- **Commit:** `feat(entitlements): implement server-side plan tier gating, schema migration v7, and UX audit wiring`
- **The Problem:** The modern frontend (`frontendNew/`) rendered commercial upgrade gates (`Upgrade.tsx`), but the backend API accepted requests to `/api/enterprise/*` from any authenticated administrator (`require_admin`). Entitlements were enforced purely by client-side UI hiding.
- **The Pivot:** We upgraded the database schema (`user_version: 7`) to introduce a `plan` column (`Starter`/`Professional`/`Enterprise`) on the `users` table, implemented a `require_plan("Enterprise")` FastAPI dependency in `auth.py`, and applied it across all 10 enterprise endpoints, ensuring strict server-side 403 enforcement before shipping. Concurrently, we cleaned up directory debt by archiving stale development plans (`docs/archive/`) and deleting the deprecated legacy frontend (`2026-07-18 4da87dc`).

---

## 3. Self-Caught False Positives & Remediation (What Broke Along the Way)

A project that claims a spotless build history without catching its own mistakes is not trustworthy. During our rigorous phase exit audits, our own verification loops caught four major false-positive gate closures before they reached production users:

1. **The celery status-flip illusion (`deployer.py` remediation):**
   - **What happened:** Early Celery tasks (`task_deploy_certificate`, `task_verify_reload`) updated the database column (`pipeline_stage = 'Reload confirmed'`) upon completion, but did not actually invoke `connector.deploy_certificate()` or `verify.get_live_cert_info()` on disk. The "crash-resilient pipeline" was a state machine wrapped around mock steps.
   - **The fix:** We refactored `deployer.py` and `tasks.py:128-154` (`2026-07-16 0021742`) to wire real connector methods and live TLS verification directly into the Celery execution path.

2. **The ephemeral Fernet key lockout risk (`db.py:552`):**
   - **What happened:** To encrypt connector credentials at rest in SQLite, early code derived a fallback Fernet key from `os.getenv("JWT_SECRET", "default_secret")`. If the server restarted with a different ephemeral fallback key, all stored Azure and SSH credentials became unreadable (`InvalidToken`).
   - **The fix:** We separated symmetric encryption keys from JWT authentication keys entirely (`_EPHEMERAL_DEV_FERNET_KEY_SINGLETON`), enforcing that production deployments provide an explicit, dedicated `FERNET_KEY` or fail loudly on boot with clear warning documentation.

3. **Test suite database migration pollution (`2026-07-16 9dbe298`):**
   - **What happened:** When schema versioning (`PRAGMA user_version`) was introduced in `db.run_migrations()`, running isolated pytest suites created temporary in-memory databases that skipped table creation for `renewal_log`, causing `sqlite3.OperationalError: no such table: renewal_log` across two core agent tests.
   - **The fix:** In `2026-07-16 9dbe298` (`fix(db): add CREATE TABLE IF NOT EXISTS safety net in insert_renewal_log`), we added strict DDL table verification checks inside `insert_renewal_log` and `run_migrations()` to guarantee safety across temporary test database isolation (`2026-07-18 d28701b`).

4. **WinError 32 / SQLite file locking on Windows teardown (`2026-07-17 8cd3929`):**
   - **What happened:** On Windows, when `pytest` finished running API integration tests, attempting to delete temporary database files (`certops.db-wal`, `certops.db-shm`) raised `WinError 32: The process cannot access the file because it is being used by another process`.
   - **The fix:** In commit `2026-07-17 8cd3929` (`fix(db): wrap all sqlite3 connection access in agent_db.py with try-finally closures`), we wrapped all SQLite connection creation points with strict `try-finally` context closures and `_db_conn` pooled locking (`RLock`), eliminating Windows teardown crashes (`2026-07-18 fb63be9`).

---

## 4. Current State Stated Plainly (Where We Are Today)

As of July 18, 2026, CertOps stands at **Phase 3 Public Release Readiness** per `CertOps_Master_Roadmap.md`:
- `certops-agent` is an open-source, Apache-2.0 licensed, 100% standalone renewal engine capable of discovering, renewing (`step-ca`), deploying (Vault, Azure KV, SSH, WinRM), and verifying certificates with zero dependency on a dashboard.
- `certops-dashboard` is a functional, multi-tenant commercial SaaS dashboard (`frontendNew/`) backed by strict `X-Tenant-Id` ownership scoping, httpOnly JWT cookies, and server-side `require_plan("Enterprise")` tier gating.
- **What is not ready:** ACME (`Let's Encrypt`) public CA wiring, real payment processing (`Pricing.tsx` is mocked), self-serve multi-organization creation, real-time WebSocket push, and external notification drivers remain explicitly scheduled for Phase 4+.
