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
        if not LIVE:
            return
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
        if not getattr(cls, "procs", None):
            return
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
