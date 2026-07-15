"""
Integration test for Tier 1 Issue 1:
Proves that task_renew_certificate -> task_deploy_certificate -> task_verify_reload
perform actual certificate issuance, DB staging, deployment, Nginx reload,
live TLS verification, and staging cleanup.
"""

import os
import tempfile
import unittest
from pathlib import Path
import sys
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))
_sibling = _root.parent / "certops-dashboard"
if _sibling.exists() and str(_sibling) not in sys.path:
    sys.path.insert(0, str(_sibling))

from src import db, tasks, verify


LIVE = os.getenv("CERTOPS_RUN_LIVE") == "1"


@unittest.skipUnless(LIVE, "Live integration test; set CERTOPS_RUN_LIVE=1 to run in a sandbox")
class TestTier1TasksIntegration(unittest.TestCase):
    def test_full_tasks_pipeline_closed_loop(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            test_db = f.name
        db.run_migrations(test_db)

        try:
            cert_id = "local-certs"
            vault_source = "hashicorp"

            # Stage 1: Renew certificate
            res1 = tasks.task_renew_certificate(vault_source, cert_id, db_path=test_db)
            self.assertEqual(res1["stage"], "Issued pending deploy")

            cert_rec = db.get_certificate(vault_source, cert_id, db_path=test_db)
            self.assertIsNotNone(cert_rec)
            self.assertEqual(cert_rec["pipeline_stage"], "Issued pending deploy")
            pending_pem = cert_rec.get("pending_cert_pem")
            self.assertIsNotNone(pending_pem)
            self.assertIn("BEGIN CERTIFICATE", pending_pem)

            # Idempotency check on Stage 1
            res1_repeat = tasks.task_renew_certificate(vault_source, cert_id, db_path=test_db)
            self.assertEqual(res1_repeat["stage"], "Issued pending deploy")

            # Stage 2: Deploy certificate
            payload = {"vault_source": vault_source, "cert_id": cert_id, "db_path": test_db}
            res2 = tasks.task_deploy_certificate(payload)
            self.assertEqual(res2["stage"], "Deployed pending reload")

            cert_rec2 = db.get_certificate(vault_source, cert_id, db_path=test_db)
            self.assertEqual(cert_rec2["pipeline_stage"], "Deployed pending reload")

            # Stage 3: Verify reload against live TLS endpoint
            res3 = tasks.task_verify_reload(payload)
            self.assertEqual(res3["stage"], "Reload confirmed")

            cert_rec3 = db.get_certificate(vault_source, cert_id, db_path=test_db)
            self.assertEqual(cert_rec3["pipeline_stage"], "Reload confirmed")
            self.assertIsNone(cert_rec3.get("pending_cert_pem"), "pending_cert_pem should be cleared on Reload confirmed")

            # Verify live served cert fingerprint matches
            _, live_fp = verify.get_live_cert_info("localhost", 443)
            _, expected_fp = verify.get_pem_cert_info(pending_pem)
            self.assertEqual(live_fp, expected_fp, "Live Nginx served certificate fingerprint does not match issued cert")

        finally:
            db.close_db_connection(test_db)
            if Path(test_db).exists():
                Path(test_db).unlink()


if __name__ == "__main__":
    unittest.main(verbosity=2)
