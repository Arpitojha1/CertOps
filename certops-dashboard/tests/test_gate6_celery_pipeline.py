"""
Verification test for Phase 0 Part E: Stage 6 follow-up Celery Task Pipeline.
Asserts that task_deploy_certificate and task_verify_reload execute the real pipeline,
transitioning certificate DB stage pending -> deployed -> verified and writing activity_log entries.
"""

import os
import tempfile
import unittest

from src import db
from src.tasks import app as celery_app
from src.tasks import task_deploy_certificate, task_verify_reload


class TestGate6CeleryPipeline(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()
        os.environ["DB_PATH"] = self.db_path
        celery_app.conf.task_always_eager = True

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def test_celery_pipeline_stage_transitions_and_activity_logs(self):
        print("\n=== TEST CELERY PIPELINE: pending -> deployed -> verified ===")

        # 1. Create stub connector
        db.create_connector(
            name="stub_pipeline_conn",
            category="secret_store",
            renewal_threshold_days=30.0,
            config='{"url": "stub://localhost:8200"}',
            is_active=True,
            db_path=self.db_path,
        )

        # 2. Upsert certificate initially in 'pending' stage
        db.upsert_certificate(
            vault_source="stub_pipeline_conn",
            name="test-pipeline-cert",
            expiry_utc="2027-01-01T00:00:00Z",
            pipeline_stage="pending",
            db_path=self.db_path,
        )

        cert_init = db.get_certificate("stub_pipeline_conn", "test-pipeline-cert", db_path=self.db_path)
        self.assertIsNotNone(cert_init)
        print(f"[INITIAL STATE] cert='test-pipeline-cert' stage='{cert_init['pipeline_stage']}'")
        self.assertEqual(cert_init["pipeline_stage"], "pending")

        # 3. Call task_deploy_certificate synchronously
        deploy_res = task_deploy_certificate("test-pipeline-cert", "stub_pipeline_conn", db_path=self.db_path)
        self.assertTrue(deploy_res["success"])

        cert_after_deploy = db.get_certificate("stub_pipeline_conn", "test-pipeline-cert", db_path=self.db_path)
        print(f"[AFTER DEPLOY] cert='test-pipeline-cert' stage='{cert_after_deploy['pipeline_stage']}'")
        self.assertEqual(cert_after_deploy["pipeline_stage"], "deployed")

        # 4. Call task_verify_reload synchronously
        verify_res = task_verify_reload("test-pipeline-cert", "stub_pipeline_conn", db_path=self.db_path)
        self.assertTrue(verify_res["success"])

        cert_after_verify = db.get_certificate("stub_pipeline_conn", "test-pipeline-cert", db_path=self.db_path)
        print(f"[AFTER VERIFY] cert='test-pipeline-cert' stage='{cert_after_verify['pipeline_stage']}'")
        self.assertEqual(cert_after_verify["pipeline_stage"], "verified")

        # 5. Verify matching activity_log entries
        logs = db.get_activity_logs(limit=50, db_path=self.db_path)["items"]
        deployed_logs = [l for l in logs if l["event_type"] == "certificate_deployed"]
        verified_logs = [l for l in logs if l["event_type"] == "certificate_verified"]

        print(f"[ACTIVITY LOG: DEPLOYED ENTRY] {deployed_logs[0] if deployed_logs else None}")
        print(f"[ACTIVITY LOG: VERIFIED ENTRY] {verified_logs[0] if verified_logs else None}")

        self.assertEqual(len(deployed_logs), 1, "Must have exactly 1 certificate_deployed log entry")
        self.assertEqual(len(verified_logs), 1, "Must have exactly 1 certificate_verified log entry")

        print("[RESULT] PASSED: Celery pipeline eager execution successfully transitioned stages and logged activity")


if __name__ == "__main__":
    unittest.main()
