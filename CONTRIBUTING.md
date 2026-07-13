# Contributing to CertOps

> **PLACEHOLDER — finalize before public repo (Phase 3).**
> This file exists as a skeleton. License, dev setup, and check requirements
> will be completed before the repository goes public.

---

## License

**[PENDING — MIT or Apache-2.0]**

The agent will be open-sourced under either MIT or Apache-2.0. The final
choice must be made before the repo goes public and before any external
contributions exist. Once chosen and contributions are received, the license
must never be changed (this is the Terraform/OpenTofu problem — license
changes after contributions exist destroy contributor trust).

Apache-2.0 provides an explicit patent grant clause (mild extra protection,
standard for infrastructure tooling). MIT provides maximum simplicity. Either
is fine — the important part is picking one before Phase 3 and not changing it.

**Decision needed from maintainers before Phase 3.**

---

## Development setup

1. Clone the repository.
2. Copy `.env.example` to `.env` and fill in required values.
3. Start Docker Desktop and bring up services:
   ```powershell
   docker compose up -d
   ```
4. Start `step-ca` (see `RUNBOOK.md` for the exact command).
5. Create a Python virtual environment and install dependencies:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   pip install -r requirements.txt
   ```
6. Seed the admin account:
   ```powershell
   python src/seed_admin.py
   ```
7. Start the API server:
   ```powershell
   python -m uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload
   ```
8. Start the frontend dev server:
   ```powershell
   cd frontend/client && npm run dev
   ```

See `RUNBOOK.md` for full startup sequence and known friction points.

---

## Pre-commit requirements

- **Secret scanning (GitGuardian):** required CI check before the repo goes
  public. Non-negotiable. No secrets in source, no secrets in git history.
- **No secrets in diffs:** review `git diff --cached` before every commit.
  A PAT was previously leaked in a chat session — treat secrets with zero
  tolerance.

---

## Code conventions

- **Ponytail Rule:** see `AGENTS.md` for the full anti-overengineering
  ruleset. Reuse standard library and existing dependencies before adding new
  ones. Fail loud, not gracefully.
- **Python 3.11+**, plain `venv` (no Poetry, no pipx).
- **Type hints** on all new function signatures.
- **`ponytail:` comments** for intentional shortcuts with known ceilings.
- **Gate discipline:** raw evidence required before any stage/phase closes.
  No walkthrough narratives as evidence.

---

## Pull request process

> **[PENDING — finalize before Phase 3]**

TBD: PR template, review requirements, CI checks, merge strategy.

---

## Reporting issues

> **[PENDING — finalize before Phase 3]**

TBD: issue templates, security disclosure process (see `SECURITY.md` for
the disclosure policy).
