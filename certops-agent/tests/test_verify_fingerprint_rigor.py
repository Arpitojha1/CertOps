"""
TDD tests for Step 3: Fingerprint Verification Rigor & Fail-Loud Default.

Asserts:
1. When live/readback fingerprint == expected fingerprint -> fingerprint_match is True, stage='verified'.
2. When live/readback fingerprint != expected fingerprint -> fingerprint_match is False, stage='verify_failed'.
3. When expected_fingerprint is missing/unresolvable (e.g., pending_cert_pem=None) -> pipeline fails (`success=False`, stage='verify_failed'), NEVER defaulting to match (`fingerprint_match=True`).
"""

import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))
_sibling = _root.parent / "certops-dashboard"
if _sibling.exists() and str(_sibling) not in sys.path:
    sys.path.insert(0, str(_sibling))

from src import db
from src.deployer import run_verify_pipeline
from src.host_connector import ReloadResult


def _make_temp_db() -> str:
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    db.run_migrations(f.name)
    return f.name


class TestVerifyFingerprintRigor(unittest.TestCase):

    def setUp(self):
        self.db_path = _make_temp_db()
        # Seed two connectors: host and secret_store
        db.create_connector("ssh_test", "host", 30.0, "{}", True, db_path=self.db_path)
        db.create_connector("vault_test", "secret_store", 30.0, "{}", True, db_path=self.db_path)

    def tearDown(self):
        db.close_db_connection(self.db_path)
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def test_1_matching_fingerprint_becomes_verified(self):
        """
        Test 1: When live/readback fp equals expected fp, fingerprint_match is True and stage becomes verified.
        """
        db.upsert_certificate("ssh_test", "cert-match", "2027-06-01T00:00:00Z",
                              connector_category="host", pipeline_stage="deployed", db_path=self.db_path)
        db.stage_pending_cert("ssh_test", "cert-match", "PEM_DATA", "KEY_DATA", "deployed", db_path=self.db_path)

        mock_connector = MagicMock()
        mock_connector.name = "ssh_test"
        mock_connector.trigger_reload = MagicMock(return_value=ReloadResult(success=True, output="reloaded"))

        fake_expiry = datetime(2027, 6, 1, tzinfo=timezone.utc)
        fake_fp = "abc123expected"

        with patch("src.deployer.get_active_connectors_by_name", return_value=mock_connector), \
             patch("src.verify.get_pem_cert_info", return_value=(fake_expiry, fake_fp)), \
             patch("src.verify.get_live_cert_info", return_value=(fake_expiry, fake_fp)):
            result = run_verify_pipeline("cert-match", "ssh_test", db_path=self.db_path)

        rec = db.get_certificate("ssh_test", "cert-match", db_path=self.db_path)
        self.assertEqual(rec["pipeline_stage"], "verified")
        self.assertTrue(result["success"])

        logs = db.get_activity_logs(limit=20, db_path=self.db_path)["items"]
        verified_logs = [l for l in logs if l["event_type"] == "certificate_verified" and "cert-match" in l["target"]]
        self.assertEqual(len(verified_logs), 1)
        import json
        details = json.loads(verified_logs[0]["details"])
        self.assertTrue(details.get("fingerprint_match"))
        self.assertEqual(details.get("expected_fingerprint"), fake_fp)
        self.assertEqual(details.get("live_fingerprint"), fake_fp)

    def test_2_mismatched_fingerprint_fails_verification(self):
        """
        Test 2: When live/readback fp does NOT equal expected fp, fingerprint_match is False and stage is verify_failed.
        """
        db.upsert_certificate("vault_test", "cert-mismatch", "2027-06-01T00:00:00Z",
                              connector_category="secret_store", pipeline_stage="deployed", db_path=self.db_path)
        db.stage_pending_cert("vault_test", "cert-mismatch", "PEM_EXPECTED", "KEY_DATA", "deployed", db_path=self.db_path)

        mock_connector = MagicMock()
        mock_connector.name = "vault_test"
        mock_connector.get_certificate = MagicMock(return_value={"cert_pem": "PEM_READBACK"})

        fake_expiry = datetime(2027, 6, 1, tzinfo=timezone.utc)

        def mock_get_pem_cert_info(pem_str):
            if pem_str == "PEM_EXPECTED":
                return (fake_expiry, "expected_fp_hash")
            elif pem_str == "PEM_READBACK":
                return (fake_expiry, "different_readback_hash")
            return (fake_expiry, "unknown")

        with patch("src.deployer.get_active_connectors_by_name", return_value=mock_connector), \
             patch("src.verify.get_pem_cert_info", side_effect=mock_get_pem_cert_info):
            result = run_verify_pipeline("cert-mismatch", "vault_test", db_path=self.db_path)

        rec = db.get_certificate("vault_test", "cert-mismatch", db_path=self.db_path)
        self.assertEqual(rec["pipeline_stage"], "verify_failed")
        self.assertFalse(result["success"])

        logs = db.get_activity_logs(limit=20, db_path=self.db_path)["items"]
        failed_logs = [l for l in logs if l["event_type"] == "certificate_verify_failed" and "cert-mismatch" in l["target"]]
        self.assertEqual(len(failed_logs), 1)

    def test_3_missing_expected_fingerprint_fails_loudly(self):
        """
        Test 3 (RED BEFORE FIX): When expected_fingerprint is missing (pending_cert_pem is None/empty),
        the verify stage MUST FAIL (`success=False`, `stage='verify_failed'`) rather than defaulting to True/verified.
        """
        # Create certificate WITHOUT staging pending_cert_pem (pending_cert_pem will be None)
        db.upsert_certificate("ssh_test", "cert-null-expected", "2027-06-01T00:00:00Z",
                              connector_category="host", pipeline_stage="deployed", db_path=self.db_path)

        mock_connector = MagicMock()
        mock_connector.name = "ssh_test"
        mock_connector.trigger_reload = MagicMock(return_value=ReloadResult(success=True, output="reloaded"))

        fake_expiry = datetime(2027, 6, 1, tzinfo=timezone.utc)
        fake_fp = "live_fp_only"

        with patch("src.deployer.get_active_connectors_by_name", return_value=mock_connector), \
             patch("src.verify.get_live_cert_info", return_value=(fake_expiry, fake_fp)):
            result = run_verify_pipeline("cert-null-expected", "ssh_test", db_path=self.db_path)

        rec = db.get_certificate("ssh_test", "cert-null-expected", db_path=self.db_path)
        # MUST NOT BE VERIFIED when expected_fingerprint is missing
        self.assertEqual(rec["pipeline_stage"], "verify_failed",
                         "Pipeline stage must be 'verify_failed' when expected_fingerprint is missing, not 'verified'")
        self.assertFalse(result["success"],
                         "run_verify_pipeline must return success=False when expected_fingerprint is missing")


if __name__ == "__main__":
    unittest.main()
