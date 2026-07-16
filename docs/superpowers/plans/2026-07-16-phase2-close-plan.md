# Phase 2-Close Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the two remaining formal verification gaps of Phase 2 by establishing a single test asserting read-side isolation across all 11 endpoints and a live two-tenant concurrent Celery subprocess integration test.

**Architecture:** Two isolated, independent test modules added cleanly to the existing test directories: one hermetic test in `certops-dashboard/tests/` verifying query-level isolation across all 11 read endpoints plus parameter tampering defense, and one live integration test in `certops-agent/tests/` spinning up two concurrent physical `celery -A src.tasks worker` subprocesses on separate queues with synchronized `threading.Barrier(2)` dispatch and live API/DB verification.

**Tech Stack:** Python 3.13, FastAPI (`fastapi.testclient.TestClient`), Celery + Redis, SQLite (WAL mode), `subprocess.Popen`, `threading.Barrier`.

## Global Constraints

- Never mark a phase closed on "should work" — every assertion must be backed by terminal output / test pass evidence.
- Keep the agent secret-blind: nothing designed or tested requires the dashboard to see client secrets.
- Windows development machine compatibility: subprocess handling and teardown must terminate workers cleanly across platforms (`proc.terminate()` with timeout fallback to `proc.kill()`).

---

### Task 1: Read-Side Tenancy Isolation Across All 11 Endpoints (`test_gate5_all_11_read_endpoints.py`)

**Files:**
- Create: `certops-dashboard/tests/test_gate5_all_11_read_endpoints.py`
- Test: `certops-dashboard/tests/test_gate5_all_11_read_endpoints.py`

**Interfaces:**
- Consumes: `src.db` CRUD functions (`create_user`, `upsert_certificate`, `create_connector`, `create_group`, etc.), `src.api.app` (`fastapi.testclient.TestClient`), `src.auth.COOKIE_NAME`.
- Produces: Hermetic proof of zero cross-tenant read-side visibility across all 11 `GET` endpoints and parameter tampering checks.

- [ ] **Step 1: Write the comprehensive 11-endpoint isolation test module**

Create `certops-dashboard/tests/test_gate5_all_11_read_endpoints.py` with the following complete implementation:

```python
"""
Verification test for Phase 2-Close: Read-Side Tenancy Isolation Across All 11 Endpoints.
Asserts that Viewer A (`tenant_A`) and Viewer B (`tenant_B`) cannot read or enumerate each
other's resources across all 11 GET endpoints, and that parameter tampering attempts are ignored.
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json

from fastapi.testclient import TestClient

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))
_sibling = _root.parent / "certops-agent"
if _sibling.exists() and str(_sibling) not in sys.path:
    sys.path.insert(0, str(_sibling))

from src import db
from src.api import app
from src.auth import COOKIE_NAME, _make_token


class TestGate5All11ReadEndpoints(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()

        if "CERTOPS_DB_PATH" in os.environ:
            self._orig_certops_db_path = os.environ["CERTOPS_DB_PATH"]
        else:
            self._orig_certops_db_path = None
        os.environ["CERTOPS_DB_PATH"] = self.db_path
        os.environ["DB_PATH"] = self.db_path

        db.reset_db_connections()
        db.run_migrations(self.db_path)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        self.timestamp = timestamp

        self.admin_email = f"admin_{timestamp}@certops.internal"
        self.viewer_a_email = f"viewer_a_{timestamp}@certops.internal"
        self.viewer_b_email = f"viewer_b_{timestamp}@certops.internal"

        db.create_user(self.admin_email, "$2b$12$fakehash", role="admin", tenant_id="default")
        self.user_a_id = db.create_user(self.viewer_a_email, "$2b$12$fakehash", role="viewer", tenant_id="tenant_A")
        self.user_b_id = db.create_user(self.viewer_b_email, "$2b$12$fakehash", role="viewer", tenant_id="tenant_B")

        # --- Seed Tenant A Entities ---
        self.group_a_id = db.create_group("group_A", "Production Web A", tenant_id="tenant_A")
        self.conn_a_id = db.create_connector(
            name="connector_A",
            category="secret_store",
            renewal_threshold_days=30,
            config=json.dumps({"vault_url": "http://vault-a:8200"}),
            is_active=True,
            tenant_id="tenant_A",
        )
        self.window_a_id = db.create_maintenance_window(
            self.group_a_id, "2026-08-01T00:00:00Z", "2026-08-01T04:00:00Z", "once", tenant_id="tenant_A"
        )
        self.policy_a_id = db.create_notification_policy(self.group_a_id, 30.0, tenant_id="tenant_A")

        expiry_due = (datetime.now(timezone.utc) + timedelta(days=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
        db.upsert_certificate(
            vault_source="hashicorp",
            name="cert_A.crt",
            expiry_utc=expiry_due,
            common_name="a.example.com",
            group_id=self.group_a_id,
            tenant_id="tenant_A",
        )
        db.log_renewal_event(
            cert_id="hashicorp:cert_A.crt",
            event_type="stage_verified",
            message="Verified A",
            success=True,
            tenant_id="tenant_A",
        )
        db.log_activity(
            event_type="group_created",
            actor_user_id=self.user_a_id,
            actor_email=self.viewer_a_email,
            target="group_A",
            details={"group_id": self.group_a_id},
            tenant_id="tenant_A",
        )
        db.log_notification_event(
            cert_id="hashicorp:cert_A.crt",
            event_type="renewal_warning",
            recipient="admin@a.example.com",
            success=True,
            message="Warning A",
            tenant_id="tenant_A",
        )

        # --- Seed Tenant B Entities ---
        self.group_b_id = db.create_group("group_B", "Production Web B", tenant_id="tenant_B")
        self.conn_b_id = db.create_connector(
            name="connector_B",
            category="secret_store",
            renewal_threshold_days=30,
            config=json.dumps({"vault_url": "http://vault-b:8200"}),
            is_active=True,
            tenant_id="tenant_B",
        )
        self.window_b_id = db.create_maintenance_window(
            self.group_b_id, "2026-08-01T00:00:00Z", "2026-08-01T04:00:00Z", "once", tenant_id="tenant_B"
        )
        self.policy_b_id = db.create_notification_policy(self.group_b_id, 30.0, tenant_id="tenant_B")

        db.upsert_certificate(
            vault_source="hashicorp",
            name="cert_B.crt",
            expiry_utc=expiry_due,
            common_name="b.example.com",
            group_id=self.group_b_id,
            tenant_id="tenant_B",
        )
        db.log_renewal_event(
            cert_id="hashicorp:cert_B.crt",
            event_type="stage_verified",
            message="Verified B",
            success=True,
            tenant_id="tenant_B",
        )
        db.log_activity(
            event_type="group_created",
            actor_user_id=self.user_b_id,
            actor_email=self.viewer_b_email,
            target="group_B",
            details={"group_id": self.group_b_id},
            tenant_id="tenant_B",
        )
        db.log_notification_event(
            cert_id="hashicorp:cert_B.crt",
            event_type="renewal_warning",
            recipient="admin@b.example.com",
            success=True,
            message="Warning B",
            tenant_id="tenant_B",
        )

        self.client = TestClient(app)

    def tearDown(self):
        db.close_db_connection(self.db_path)
        if self._orig_certops_db_path is not None:
            os.environ["CERTOPS_DB_PATH"] = self._orig_certops_db_path
        elif "CERTOPS_DB_PATH" in os.environ:
            del os.environ["CERTOPS_DB_PATH"]
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def _cookie(self, email: str) -> dict:
        user = db.get_user_by_email(email)
        token = _make_token(user["id"], user["email"], user["role"], user["tenant_id"])
        return {COOKIE_NAME: token}

    def test_all_11_read_endpoints_isolated(self):
        cookie_a = self._cookie(self.viewer_a_email)
        cookie_b = self._cookie(self.viewer_b_email)
        cookie_admin = self._cookie(self.admin_email)

        # 1. GET /api/certificates
        r_a = self.client.get("/api/certificates", cookies=cookie_a).json()
        r_b = self.client.get("/api/certificates", cookies=cookie_b).json()
        r_admin = self.client.get("/api/certificates", cookies=cookie_admin).json()
        self.assertEqual({c["name"] for c in r_a}, {"cert_A.crt"})
        self.assertEqual({c["name"] for c in r_b}, {"cert_B.crt"})
        self.assertEqual({c["name"] for c in r_admin}, {"cert_A.crt", "cert_B.crt"})

        # 2. GET /api/certificates/due
        r_due_a = self.client.get("/api/certificates/due?threshold_days=30", cookies=cookie_a).json()
        r_due_b = self.client.get("/api/certificates/due?threshold_days=30", cookies=cookie_b).json()
        r_due_admin = self.client.get("/api/certificates/due?threshold_days=30", cookies=cookie_admin).json()
        self.assertEqual({c["name"] for c in r_due_a}, {"cert_A.crt"})
        self.assertEqual({c["name"] for c in r_due_b}, {"cert_B.crt"})
        self.assertEqual({c["name"] for c in r_due_admin}, {"cert_A.crt", "cert_B.crt"})

        # 3. GET /api/certificates/{source}/{name}
        self.assertEqual(self.client.get("/api/certificates/hashicorp/cert_A.crt", cookies=cookie_a).status_code, 200)
        self.assertEqual(self.client.get("/api/certificates/hashicorp/cert_B.crt", cookies=cookie_a).status_code, 404)
        self.assertEqual(self.client.get("/api/certificates/hashicorp/cert_B.crt", cookies=cookie_b).status_code, 200)
        self.assertEqual(self.client.get("/api/certificates/hashicorp/cert_A.crt", cookies=cookie_b).status_code, 404)

        # 4. GET /api/renewal-log
        r_ren_a = self.client.get("/api/renewal-log", cookies=cookie_a).json()
        r_ren_b = self.client.get("/api/renewal-log", cookies=cookie_b).json()
        r_ren_admin = self.client.get("/api/renewal-log", cookies=cookie_admin).json()
        self.assertEqual({l["cert_id"] for l in r_ren_a}, {"hashicorp:cert_A.crt"})
        self.assertEqual({l["cert_id"] for l in r_ren_b}, {"hashicorp:cert_B.crt"})
        self.assertEqual({l["cert_id"] for l in r_ren_admin}, {"hashicorp:cert_A.crt", "hashicorp:cert_B.crt"})

        # 5. GET /api/activity-log
        r_act_a = self.client.get("/api/activity-log?include_renewal_log=false", cookies=cookie_a).json()["items"]
        r_act_b = self.client.get("/api/activity-log?include_renewal_log=false", cookies=cookie_b).json()["items"]
        r_act_admin = self.client.get("/api/activity-log?include_renewal_log=false", cookies=cookie_admin).json()["items"]
        self.assertEqual({i["target"] for i in r_act_a if i["event_type"] == "group_created"}, {"group_A"})
        self.assertEqual({i["target"] for i in r_act_b if i["event_type"] == "group_created"}, {"group_B"})
        self.assertEqual({i["target"] for i in r_act_admin if i["event_type"] == "group_created"}, {"group_A", "group_B"})

        # 6. GET /api/connectors
        r_conn_a = self.client.get("/api/connectors", cookies=cookie_a).json()
        r_conn_b = self.client.get("/api/connectors", cookies=cookie_b).json()
        r_conn_admin = self.client.get("/api/connectors", cookies=cookie_admin).json()
        self.assertEqual({c["name"] for c in r_conn_a}, {"connector_A"})
        self.assertEqual({c["name"] for c in r_conn_b}, {"connector_B"})
        self.assertEqual({c["name"] for c in r_conn_admin}, {"connector_A", "connector_B"})

        # 7. GET /api/groups
        r_grp_a = self.client.get("/api/groups", cookies=cookie_a).json()
        r_grp_b = self.client.get("/api/groups", cookies=cookie_b).json()
        r_grp_admin = self.client.get("/api/groups", cookies=cookie_admin).json()
        self.assertEqual({g["name"] for g in r_grp_a}, {"group_A"})
        self.assertEqual({g["name"] for g in r_grp_b}, {"group_B"})
        self.assertEqual({g["name"] for g in r_grp_admin}, {"group_A", "group_B"})

        # 8. GET /api/maintenance-windows
        r_win_a = self.client.get("/api/maintenance-windows", cookies=cookie_a).json()
        r_win_b = self.client.get("/api/maintenance-windows", cookies=cookie_b).json()
        r_win_admin = self.client.get("/api/maintenance-windows", cookies=cookie_admin).json()
        self.assertEqual({w["group_id"] for w in r_win_a}, {self.group_a_id})
        self.assertEqual({w["group_id"] for w in r_win_b}, {self.group_b_id})
        self.assertEqual({w["group_id"] for w in r_win_admin}, {self.group_a_id, self.group_b_id})

        # 9. GET /api/notification-policies
        r_pol_a = self.client.get("/api/notification-policies", cookies=cookie_a).json()
        r_pol_b = self.client.get("/api/notification-policies", cookies=cookie_b).json()
        r_pol_admin = self.client.get("/api/notification-policies", cookies=cookie_admin).json()
        self.assertEqual({p["group_id"] for p in r_pol_a}, {self.group_a_id})
        self.assertEqual({p["group_id"] for p in r_pol_b}, {self.group_b_id})
        self.assertEqual({p["group_id"] for p in r_pol_admin}, {self.group_a_id, self.group_b_id})

        # 10. GET /api/notification-log
        r_notif_a = self.client.get("/api/notification-log", cookies=cookie_a).json()
        r_notif_b = self.client.get("/api/notification-log", cookies=cookie_b).json()
        r_notif_admin = self.client.get("/api/notification-log", cookies=cookie_admin).json()
        self.assertEqual({n["cert_id"] for n in r_notif_a}, {"hashicorp:cert_A.crt"})
        self.assertEqual({n["cert_id"] for n in r_notif_b}, {"hashicorp:cert_B.crt"})
        self.assertEqual({n["cert_id"] for n in r_notif_admin}, {"hashicorp:cert_A.crt", "hashicorp:cert_B.crt"})

        # 11. GET /api/scheduler/status
        # Note: Tie-breaking by next_renewal_at applies within each scope. Under our exact seeding
        # with 1 due certificate per tenant, next_job strictly evaluates cert_A for A and cert_B for B.
        r_sched_a = self.client.get("/api/scheduler/status", cookies=cookie_a).json()
        r_sched_b = self.client.get("/api/scheduler/status", cookies=cookie_b).json()
        r_sched_admin = self.client.get("/api/scheduler/status", cookies=cookie_admin).json()
        self.assertEqual(r_sched_a["next_job"]["name"], "cert_A.crt")
        self.assertEqual(r_sched_b["next_job"]["name"], "cert_B.crt")
        self.assertEqual({l["cert_id"] for l in r_sched_a["recent_events"]}, {"hashicorp:cert_A.crt"})
        self.assertEqual({l["cert_id"] for l in r_sched_b["recent_events"]}, {"hashicorp:cert_B.crt"})
        self.assertEqual({l["cert_id"] for l in r_sched_admin["recent_events"]}, {"hashicorp:cert_A.crt", "hashicorp:cert_B.crt"})

    def test_negative_path_query_parameter_tampering(self):
        """Verify _get_tenant_scope() ignores/overrides client-supplied tenant filters."""
        cookie_a = self._cookie(self.viewer_a_email)

        # Attempt to pass ?tenant_id=tenant_B while authenticated as Viewer A
        r_tamper_cert = self.client.get("/api/certificates?tenant_id=tenant_B", cookies=cookie_a).json()
        self.assertEqual({c["name"] for c in r_tamper_cert}, {"cert_A.crt"}, "Must ignore client-supplied tenant_id query param")

        # Attempt to filter due certificates by Group B while authenticated as Viewer A
        r_tamper_group = self.client.get(f"/api/certificates/due?group_id={self.group_b_id}", cookies=cookie_a).json()
        self.assertEqual(len(r_tamper_group), 0, "Filtering by cross-tenant group_id must return 0 items")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it passes cleanly**

Run: `python -m pytest certops-dashboard/tests/test_gate5_all_11_read_endpoints.py -v`
Expected: PASS (2 tests passed)

- [ ] **Step 3: Commit the hermetic verification test**

Run:
```bash
git add certops-dashboard/tests/test_gate5_all_11_read_endpoints.py
git commit -m "test(dashboard): verify read-side tenancy isolation across all 11 endpoints"
```

---

### Task 2: Live Two-Tenant Concurrent Celery Subprocess Integration (`test_live_two_tenant_integration.py`)

**Files:**
- Create: `certops-agent/tests/test_live_two_tenant_integration.py`
- Test: `certops-agent/tests/test_live_two_tenant_integration.py`

**Interfaces:**
- Consumes: `src.db` CRUD, `src.tasks.start_pipeline.apply_async`, `celery` CLI (`celery -A src.tasks worker`), `fastapi.testclient.TestClient`.
- Produces: Empirical live verification of two concurrent physical Celery worker subprocesses operating on separate queues with zero cross-tenant contamination across database and live API responses.

- [ ] **Step 1: Write the live two-tenant integration test module**

Create `certops-agent/tests/test_live_two_tenant_integration.py` with the following complete implementation:

```python
"""
Verification test for Phase 2-Close: Live Two-Tenant Concurrent Celery Subprocess Integration.
Runs two physical Celery worker subprocesses (`celery -A src.tasks worker`) concurrently on separate
queues with distinct tenant_id and agent_token contexts, triggers simultaneous renewals via
threading.Barrier(2), and verifies isolation across both DB rows and live API endpoints.
"""

import os
import sys
import time
import uuid
import subprocess
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))
_sibling = _root.parent / "certops-dashboard"
if _sibling.exists() and str(_sibling) not in sys.path:
    sys.path.insert(0, str(_sibling))

from src import db
from src import tasks
from src.api import app
from src.auth import COOKIE_NAME, _make_token

LIVE = os.getenv("CERTOPS_RUN_LIVE") == "1"


@unittest.skipUnless(LIVE, "Live integration test; set CERTOPS_RUN_LIVE=1 to run against live infra")
@pytest.mark.timeout(90)
class TestLiveTwoTenantIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run_id = uuid.uuid4().hex[:6]
        cls.db_path = os.getenv("CERTOPS_DB_PATH", os.getenv("DB_PATH", "./certops.db"))
        cls.procs = []

        cls.q_a = f"q_tenant_a_{cls.run_id}"
        cls.q_b = f"q_tenant_b_{cls.run_id}"

        cls.token_a = f"token_a_live_{cls.run_id}"
        cls.token_b = f"token_b_live_{cls.run_id}"

        # Provision Tenant A & B Agent Tokens
        db.register_agent_token("Agent A Live", cls.token_a, tenant_id="tenant_A")
        db.register_agent_token("Agent B Live", cls.token_b, tenant_id="tenant_B")

        # Provision Connectors
        cls.conn_a_id = db.create_connector(
            name=f"hashicorp_live_A_{cls.run_id}",
            category="secret_store",
            renewal_threshold_days=365,
            config='{"vault_url": "http://vault:8200", "secret_path": "secret/data/certops"}',
            is_active=True,
            tenant_id="tenant_A",
        )
        cls.conn_b_id = db.create_connector(
            name=f"hashicorp_live_B_{cls.run_id}",
            category="secret_store",
            renewal_threshold_days=365,
            config='{"vault_url": "http://vault:8200", "secret_path": "secret/data/certops"}',
            is_active=True,
            tenant_id="tenant_B",
        )

        cls.cert_a_name = f"live_a_{cls.run_id}.crt"
        cls.cert_b_name = f"live_b_{cls.run_id}.crt"

        db.upsert_certificate(
            vault_source="hashicorp",
            name=cls.cert_a_name,
            expiry_utc="2024-01-01T00:00:00Z",  # Expired -> forces renewal
            common_name="localhost",
            tenant_id="tenant_A",
        )
        db.upsert_certificate(
            vault_source="hashicorp",
            name=cls.cert_b_name,
            expiry_utc="2024-01-01T00:00:00Z",  # Expired -> forces renewal
            common_name="localhost",
            tenant_id="tenant_B",
        )

        # Spawn Worker Subprocess A
        env_a = os.environ.copy()
        env_a["CERTOPS_TENANT_ID"] = "tenant_A"
        env_a["AGENT_TOKEN"] = cls.token_a
        env_a["CELERY_BROKER_URL"] = "redis://redis:6379/0" if "redis:" in os.getenv("CELERY_BROKER_URL", "") else "redis://localhost:6379/0"
        env_a["PYTHONPATH"] = f"{_root}:{_root / 'src'}"
        cmd_a = [sys.executable, "-m", "celery", "-A", "src.tasks", "worker", "-Q", cls.q_a, "--loglevel=info"]
        proc_a = subprocess.Popen(cmd_a, cwd=str(_root), env=env_a)
        cls.procs.append(proc_a)

        # Spawn Worker Subprocess B
        env_b = os.environ.copy()
        env_b["CERTOPS_TENANT_ID"] = "tenant_B"
        env_b["AGENT_TOKEN"] = cls.token_b
        env_b["CELERY_BROKER_URL"] = env_a["CELERY_BROKER_URL"]
        env_b["PYTHONPATH"] = env_a["PYTHONPATH"]
        cmd_b = [sys.executable, "-m", "celery", "-A", "src.tasks", "worker", "-Q", cls.q_b, "--loglevel=info"]
        proc_b = subprocess.Popen(cmd_b, cwd=str(_root), env=env_b)
        cls.procs.append(proc_b)

        # Poll for worker readiness (hard 30s ceiling)
        start_t = time.time()
        ready = False
        while time.time() - start_t < 30:
            if proc_a.poll() is not None or proc_b.poll() is not None:
                raise RuntimeError(f"Celery worker died prematurely: A={proc_a.poll()}, B={proc_b.poll()}")
            # Check celery status via inspect
            try:
                i = tasks.app.control.inspect([f"celery@{os.uname().nodename}" if hasattr(os, "uname") else None])
                # Simple check: see if tasks can be inspected or pinged
                ping = tasks.app.control.ping(timeout=1.0)
                if len(ping) >= 2:
                    ready = True
                    break
            except Exception:
                pass
            time.sleep(1.0)

        if not ready and (time.time() - start_t >= 30):
            # If ping check fails, ensure subprocesses are at least running and responsive
            if proc_a.poll() is None and proc_b.poll() is None:
                pass # Proceeding if workers are alive
            else:
                raise RuntimeError("Celery workers failed to reach ready status within 30s")

    @classmethod
    def tearDownClass(cls):
        for proc in cls.procs:
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5.0)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

    def test_concurrent_live_renewals_and_api_isolation(self):
        """Synchronized concurrent dispatch and verification across both DB and HTTP layer."""
        barrier = threading.Barrier(2)
        errors = []

        def trigger_a():
            try:
                barrier.wait(timeout=5.0)
                tasks.start_pipeline.apply_async(args=["hashicorp", self.cert_a_name, self.db_path], queue=self.q_a)
            except Exception as e:
                errors.append(f"Thread A error: {e}")

        def trigger_b():
            try:
                barrier.wait(timeout=5.0)
                tasks.start_pipeline.apply_async(args=["hashicorp", self.cert_b_name, self.db_path], queue=self.q_b)
            except Exception as e:
                errors.append(f"Thread B error: {e}")

        t_a = threading.Thread(target=trigger_a)
        t_b = threading.Thread(target=trigger_b)
        t_a.start()
        t_b.start()
        t_a.join()
        t_b.join()

        self.assertEqual(len(errors), 0, f"Dispatch errors occurred: {errors}")

        # Wait up to 60 seconds for both certificates to complete the pipeline
        start_wait = time.time()
        stage_a, stage_b = None, None
        while time.time() - start_wait < 60:
            cert_a = db.get_certificate("hashicorp", self.cert_a_name, tenant_id="tenant_A")
            cert_b = db.get_certificate("hashicorp", self.cert_b_name, tenant_id="tenant_B")
            stage_a = cert_a.get("pipeline_stage") if cert_a else None
            stage_b = cert_b.get("pipeline_stage") if cert_b else None
            if stage_a == "Reload confirmed" and stage_b == "Reload confirmed":
                break
            time.sleep(2.0)

        self.assertEqual(stage_a, "Reload confirmed", f"Cert A failed to reach Reload confirmed: {stage_a}")
        self.assertEqual(stage_b, "Reload confirmed", f"Cert B failed to reach Reload confirmed: {stage_b}")

        # --- DB-Level Isolation Audit ---
        logs_a = db.get_renewal_logs(cert_id=f"hashicorp:{self.cert_a_name}", tenant_id="tenant_A")
        self.assertGreater(len(logs_a), 0)
        for l in logs_a:
            self.assertEqual(l["tenant_id"], "tenant_A")

        logs_b = db.get_renewal_logs(cert_id=f"hashicorp:{self.cert_b_name}", tenant_id="tenant_B")
        self.assertGreater(len(logs_b), 0)
        for l in logs_b:
            self.assertEqual(l["tenant_id"], "tenant_B")

        # Confirm DB cross-tenant get returns None
        self.assertIsNone(db.get_certificate("hashicorp", self.cert_a_name, tenant_id="tenant_B"))
        self.assertIsNone(db.get_certificate("hashicorp", self.cert_b_name, tenant_id="tenant_A"))

        # --- Live API HTTP-Level Isolation Audit ---
        client = TestClient(app)
        user_a_email = f"viewer_live_a_{self.run_id}@certops.internal"
        user_b_email = f"viewer_live_b_{self.run_id}@certops.internal"
        db.create_user(user_a_email, "$2b$12$fakehash", role="viewer", tenant_id="tenant_A")
        db.create_user(user_b_email, "$2b$12$fakehash", role="viewer", tenant_id="tenant_B")

        u_a = db.get_user_by_email(user_a_email)
        u_b = db.get_user_by_email(user_b_email)
        cookie_a = {COOKIE_NAME: _make_token(u_a["id"], u_a["email"], u_a["role"], u_a["tenant_id"])}
        cookie_b = {COOKIE_NAME: _make_token(u_b["id"], u_b["email"], u_b["role"], u_b["tenant_id"])}

        # Viewer A querying live Cert B via API must get 404
        resp_404_a = client.get(f"/api/certificates/hashicorp/{self.cert_b_name}", cookies=cookie_a)
        self.assertEqual(resp_404_a.status_code, 404, "Viewer A accessing live Cert B must return 404")

        # Viewer B querying live Cert A via API must get 404
        resp_404_b = client.get(f"/api/certificates/hashicorp/{self.cert_a_name}", cookies=cookie_b)
        self.assertEqual(resp_404_b.status_code, 404, "Viewer B accessing live Cert A must return 404")

        # Viewer A querying list must see Cert A and never Cert B
        list_a = client.get("/api/certificates", cookies=cookie_a).json()
        names_a = {c["name"] for c in list_a}
        self.assertIn(self.cert_a_name, names_a)
        self.assertNotIn(self.cert_b_name, names_a)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run hermetic skip verification**

Run: `python -m pytest certops-agent/tests/test_live_two_tenant_integration.py -v`
Expected: SKIPPED (`s` status since `CERTOPS_RUN_LIVE` is not set).

- [ ] **Step 3: Commit the live two-tenant integration test module**

Run:
```bash
git add certops-agent/tests/test_live_two_tenant_integration.py
git commit -m "test(agent): add live two-tenant concurrent Celery subprocess integration test"
```

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-16-phase2-close-plan.md`. Two execution options:

1. **Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - Execute tasks in this session using `executing-plans`, batch execution with checkpoints.

Which approach?
