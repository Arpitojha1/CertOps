# Contributing to CertOps

We welcome contributions to the open-source `certops-agent` engine (`certops-agent/`) and shared root utilities! Please read this guide to understand our testing procedures and strict **Evidence Over Prose** engineering philosophy before submitting a pull request.

---

## 1. Repository Split & Scope of Contributions

- **Open-Source Scope (`certops-agent/` & Root Utilities):** You may submit pull requests for any bug fix, connector implementation, CA issuer abstraction, or verification logic inside `certops-agent/src/`, `certops-agent/tests/`, and root files (`README.md`, `SETUP.md`, `AGENT_USAGE.md`).
- **Closed-Source Scope (`certops-dashboard/`):** Pull requests modifying the commercial dashboard server (`certops-dashboard/src/`) or UI (`certops-dashboard/frontendNew/`) are accepted only from authorized maintainers. External PRs targeting `certops-dashboard/` without prior issue coordination will be closed.

---

## 2. Running the Test Suite

Before committing code, you must verify that both the open-source agent suite (`certops-agent/tests/`) and the dashboard integration suite (`certops-dashboard/tests/`) pass cleanly with zero regressions.

### POSIX (bash)
```bash
source venv/bin/activate
# Run agent unit & integration suite
pytest certops-agent/tests/ -v --tb=short

# Run dashboard API & RBAC suite
pytest certops-dashboard/tests/ -v --tb=short
```

### Windows (PowerShell)
```powershell
.\venv\Scripts\Activate.ps1
# Run agent unit & integration suite
pytest certops-agent/tests/ -v --tb=short

# Run dashboard API & RBAC suite
pytest certops-dashboard/tests/ -v --tb=short
```

### Verified Baseline Pass Counts (as of July 18, 2026)
When executed against a clean environment with valid credentials:
- **Dashboard Suite (`pytest certops-dashboard/tests/`):**
  ```
  ================ 74 passed, 1 skipped, 189 warnings in 35.61s =================
  ```
  *(100% pass across all 74 executed dashboard endpoints, RBAC boundaries, and multi-tenant isolation gates).*

- **Agent Suite (`pytest certops-agent/tests/`):**
  ```
  ============ 3 failed, 107 passed, 6 warnings in 115.64s (0:01:55) ============
  ```
  *(Note: Exactly 107 tests pass out of the box. The 3 failures (`test_core_loop.py::test_02...`, `test_live_two_tenant_integration.py...`, `test_multi_cert_loop.py...`) occur only when the live Azure Key Vault service principal secret (`AZURE_CLIENT_SECRET`) in `.env` is expired (`AADSTS7000222`). When Azure credentials are valid or live Key Vault tests are skipped, exactly **110 agent tests pass**).*

---

## 3. The "Evidence Over Prose" Gate Discipline

CertOps enforces a strict, non-negotiable engineering standard across all code reviews and phase exit gates: **Evidence Over Prose.**

### What This Means for Contributors
- **Never claim a feature works without raw command output.** If you add a new connector or fix a bug, your pull request description must include actual terminal execution output (`pytest` logs, `curl` responses, or `docker exec` output) demonstrating that the code ran and succeeded on a physical host.
- **Never mock what can be verified against a real service.** If adding a secret store connector, test it against a local Docker container or live dev instance. Do not rely solely on `unittest.mock.MagicMock` for core lifecycle verification.
- **No aspirational claims.** If your feature handles 80% of a workflow and leaves edge cases unhandled, document the exact unhandled cases right in the PR and code docstrings. Never describe a scaffolded class or stubbed API endpoint as "complete."

---

## 4. Verified Engineering Conventions & Code Style

We enforce four strict architectural conventions across all source code:

1. **Explicit Type Annotations:** All Python functions across `certops-agent/src/` must include explicit type hints (`arg: str | None -> dict[str, Any]`).
2. **Standard Library Preference:** Always prefer standard library modules (`ssl`, `socket`, `hashlib`, `urllib`) and existing dependencies (`requests`, `paramiko`, `pywinrm`) over introducing new third-party packages to `requirements.txt`.
3. **Atomic File Replacement with Rollback Hatch:** Never write target certificate files directly in-place (`open(path, 'w')`). Always write to a temporary file (`.tmp`), create a backup of the existing file (`.bak`), and use `os.replace()` to ensure atomic replacement without race conditions during Nginx reads (`deployer.py`).
4. **Idempotent DDL Schema Migrations:** All database schema changes must be versioned via `PRAGMA user_version` inside `db.run_migrations()`, ensuring safe, idempotent execution across concurrent processes (`main.py` and `api.py`).
