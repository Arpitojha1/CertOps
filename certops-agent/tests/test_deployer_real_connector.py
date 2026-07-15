"""
TDD tests for Item 3 — deployer.py must call real connector methods.

Four tests, two per function, one per connector category branch:
  1. run_deploy_pipeline (host category)   -> connector.deploy_certificate() called
  2. run_deploy_pipeline (secret_store)    -> connector.write_certificate() called
  3. run_verify_pipeline (host category)   -> connector.trigger_reload() + verify.get_live_cert_info() called
  4. run_verify_pipeline (secret_store)    -> connector.get_certificate() read-back called

All tests use temporary SQLite DBs and mock the connector object / live-TLS verify call
so no live I/O is required.  They assert the CALL happened, not only the DB side-effect.
RED phase: these tests will FAIL against the current deployer.py because it never calls
any connector method.  After implementing the real branching they turn GREEN.
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
from src.deployer import run_deploy_pipeline, run_verify_pipeline
from src.host_connector import CertData, ReloadResult


def _make_temp_db() -> str:
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    db.run_migrations(f.name)
    return f.name


def _seed_cert_and_connector(db_path: str, category: str, conn_name: str) -> None:
    """Creates a connector and a certificate with staged pending cert PEM in the DB."""
    db.create_connector(
        name=conn_name,
        category=category,
        renewal_threshold_days=30.0,
        config='{}',
        is_active=True,
        db_path=db_path,
    )
    db.upsert_certificate(
        vault_source=conn_name,
        name="tls-cert-01",
        expiry_utc="2027-06-01T00:00:00Z",
        connector_category=category,
        pipeline_stage="Issued pending deploy",
        db_path=db_path,
    )
    db.stage_pending_cert(
        vault_source=conn_name,
        name="tls-cert-01",
        cert_pem="-----BEGIN CERTIFICATE-----\nFAKE_PEM\n-----END CERTIFICATE-----\n",
        key_pem="-----BEGIN PRIVATE KEY-----\nFAKE_KEY\n-----END PRIVATE KEY-----\n",
        pipeline_stage="Issued pending deploy",
        db_path=db_path,
    )


class TestDeployPipelineHostConnector(unittest.TestCase):
    """Test 1: HostConnector deploy path MUST call connector.deploy_certificate()."""

    def setUp(self):
        self.db_path = _make_temp_db()
        _seed_cert_and_connector(self.db_path, "host", "ssh_host_test")

    def tearDown(self):
        db.close_db_connection(self.db_path)
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def test_deploy_pipeline_host_calls_deploy_certificate(self):
        """
        run_deploy_pipeline for a host-category connector MUST invoke
        connector.deploy_certificate(cert_id, cert_data) with the staged cert.
        Asserts the call happened — not just that the DB stage changed.
        """
        mock_connector = MagicMock()
        mock_connector.name = "ssh_host_test"
        mock_connector.deploy_certificate = MagicMock(return_value=None)

        with patch("src.deployer.get_active_connectors_by_name",
                   return_value=mock_connector):
            result = run_deploy_pipeline("tls-cert-01", "ssh_host_test",
                                        db_path=self.db_path)

        # The call must have happened
        mock_connector.deploy_certificate.assert_called_once()
        call_args = mock_connector.deploy_certificate.call_args
        cert_id_arg = call_args[0][0]
        cert_data_arg = call_args[0][1]
        self.assertEqual(cert_id_arg, "tls-cert-01")
        self.assertIsInstance(cert_data_arg, CertData)
        self.assertIn("FAKE_PEM", cert_data_arg.cert_pem)

        # DB stage should also be updated
        rec = db.get_certificate("ssh_host_test", "tls-cert-01", db_path=self.db_path)
        self.assertEqual(rec["pipeline_stage"], "deployed",
                         "Pipeline stage must be 'deployed' after successful deploy")
        self.assertTrue(result["success"])

        print(f"[TEST 1 PASS] deploy_certificate() called once with cert_id='{cert_id_arg}'")


class TestDeployPipelineSecretStore(unittest.TestCase):
    """Test 2: SecretStoreConnector deploy path MUST call connector.write_certificate()."""

    def setUp(self):
        self.db_path = _make_temp_db()
        _seed_cert_and_connector(self.db_path, "secret_store", "hashicorp_test")

    def tearDown(self):
        db.close_db_connection(self.db_path)
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def test_deploy_pipeline_secret_store_calls_write_certificate(self):
        """
        run_deploy_pipeline for a secret_store-category connector MUST invoke
        connector.write_certificate(cert_id, cert_pem, key_pem) with the staged cert.
        """
        mock_connector = MagicMock()
        mock_connector.name = "hashicorp_test"
        mock_connector.write_certificate = MagicMock(return_value={
            "name": "tls-cert-01",
            "version": "2",
            "expiry_utc": datetime(2027, 6, 1, tzinfo=timezone.utc),
        })

        with patch("src.deployer.get_active_connectors_by_name",
                   return_value=mock_connector):
            result = run_deploy_pipeline("tls-cert-01", "hashicorp_test",
                                        db_path=self.db_path)

        # write_certificate must have been called, NOT deploy_certificate
        mock_connector.write_certificate.assert_called_once()
        # deploy_certificate must NOT have been called (wrong method for secret_store)
        mock_connector.deploy_certificate.assert_not_called()

        call_args = mock_connector.write_certificate.call_args
        self.assertEqual(call_args[0][0], "tls-cert-01")
        self.assertIn("FAKE_PEM", call_args[0][1])  # cert_pem

        rec = db.get_certificate("hashicorp_test", "tls-cert-01", db_path=self.db_path)
        self.assertEqual(rec["pipeline_stage"], "deployed")
        self.assertTrue(result["success"])

        print(f"[TEST 2 PASS] write_certificate() called once for secret_store connector")


class TestVerifyPipelineHostConnector(unittest.TestCase):
    """Test 3: HostConnector verify path MUST call trigger_reload() + live TLS verify."""

    def setUp(self):
        self.db_path = _make_temp_db()
        _seed_cert_and_connector(self.db_path, "host", "ssh_host_test")
        # Advance to deployed stage so verify can proceed
        db.update_pipeline_stage("ssh_host_test", "tls-cert-01", "deployed",
                                 db_path=self.db_path)

    def tearDown(self):
        db.close_db_connection(self.db_path)
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def test_verify_pipeline_host_calls_trigger_reload_and_live_tls(self):
        """
        run_verify_pipeline for a host-category connector MUST invoke:
          1. connector.trigger_reload(cert_id)
          2. verify.get_live_cert_info(host, port)  to confirm fingerprint
        """
        mock_connector = MagicMock()
        mock_connector.name = "ssh_host_test"
        mock_connector.trigger_reload = MagicMock(
            return_value=ReloadResult(success=True, output="nginx reloaded OK")
        )
        # read_certificate returns the expected cert so we can get expected fingerprint
        mock_connector.read_certificate = MagicMock(
            return_value=CertData(
                cert_id="tls-cert-01",
                cert_pem="-----BEGIN CERTIFICATE-----\nFAKE_PEM\n-----END CERTIFICATE-----\n",
                expiry_utc=datetime(2027, 6, 1, tzinfo=timezone.utc),
            )
        )

        fake_expiry = datetime(2027, 6, 1, tzinfo=timezone.utc)
        fake_fp = "aabbccddeeff"

        with patch("src.deployer.get_active_connectors_by_name",
                   return_value=mock_connector), \
             patch("src.verify.get_pem_cert_info",
                   return_value=(fake_expiry, fake_fp)), \
             patch("src.verify.get_live_cert_info",
                   return_value=(fake_expiry, fake_fp)) as mock_live_tls:
            result = run_verify_pipeline("tls-cert-01", "ssh_host_test",
                                        db_path=self.db_path)

        # trigger_reload must have been called
        mock_connector.trigger_reload.assert_called_once()
        # live TLS verify must have been called
        mock_live_tls.assert_called_once()

        rec = db.get_certificate("ssh_host_test", "tls-cert-01", db_path=self.db_path)
        self.assertEqual(rec["pipeline_stage"], "verified")
        self.assertTrue(result["success"])

        # activity log entry must record verification method
        logs = db.get_activity_logs(limit=50, db_path=self.db_path)["items"]
        verified_logs = [l for l in logs if l["event_type"] == "certificate_verified"]
        self.assertTrue(len(verified_logs) >= 1)
        import json
        details = json.loads(verified_logs[0]["details"])
        self.assertEqual(details.get("verification_method"), "live_tls",
                         "Activity log must record verification_method=live_tls for host connector")

        print(f"[TEST 3 PASS] trigger_reload() + get_live_cert_info() both called; "
              f"verification_method=live_tls logged")


class TestVerifyPipelineSecretStore(unittest.TestCase):
    """Test 4: SecretStoreConnector verify path MUST call get_certificate() read-back."""

    def setUp(self):
        self.db_path = _make_temp_db()
        _seed_cert_and_connector(self.db_path, "secret_store", "hashicorp_test")
        db.update_pipeline_stage("hashicorp_test", "tls-cert-01", "deployed",
                                 db_path=self.db_path)

    def tearDown(self):
        db.close_db_connection(self.db_path)
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def test_verify_pipeline_secret_store_calls_get_certificate_readback(self):
        """
        run_verify_pipeline for a secret_store connector MUST invoke:
          connector.get_certificate(cert_id) and compare returned fingerprint
          against what was staged. No live TLS call is made.
        """
        fake_expiry = datetime(2027, 6, 1, tzinfo=timezone.utc)
        fake_fp = "aabbccddeeff"

        mock_connector = MagicMock()
        mock_connector.name = "hashicorp_test"
        mock_connector.get_certificate = MagicMock(return_value={
            "name": "tls-cert-01",
            "cert_pem": "-----BEGIN CERTIFICATE-----\nFAKE_PEM\n-----END CERTIFICATE-----\n",
            "expiry_utc": fake_expiry,
        })
        # trigger_reload must NOT be called for secret_store
        mock_connector.trigger_reload = MagicMock()

        with patch("src.deployer.get_active_connectors_by_name",
                   return_value=mock_connector), \
             patch("src.verify.get_pem_cert_info",
                   return_value=(fake_expiry, fake_fp)), \
             patch("src.verify.get_live_cert_info") as mock_live_tls:
            result = run_verify_pipeline("tls-cert-01", "hashicorp_test",
                                        db_path=self.db_path)

        # get_certificate (read-back) must be called
        mock_connector.get_certificate.assert_called_once()
        # trigger_reload must NOT be called
        mock_connector.trigger_reload.assert_not_called()
        # live TLS must NOT be called
        mock_live_tls.assert_not_called()

        rec = db.get_certificate("hashicorp_test", "tls-cert-01", db_path=self.db_path)
        self.assertEqual(rec["pipeline_stage"], "verified")
        self.assertTrue(result["success"])

        # activity log must record verification_method=readback
        logs = db.get_activity_logs(limit=50, db_path=self.db_path)["items"]
        verified_logs = [l for l in logs if l["event_type"] == "certificate_verified"]
        self.assertTrue(len(verified_logs) >= 1)
        import json
        details = json.loads(verified_logs[0]["details"])
        self.assertEqual(details.get("verification_method"), "readback",
                         "Activity log must record verification_method=readback for secret_store")

        print(f"[TEST 4 PASS] get_certificate() read-back called; "
              f"trigger_reload not called; verification_method=readback logged")


if __name__ == "__main__":
    unittest.main()
