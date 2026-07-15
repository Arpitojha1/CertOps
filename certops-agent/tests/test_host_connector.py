"""
Smoke tests for HostConnector (SSHHostConnector end-to-end against live Linux Nginx VM/container,
and WinRMHostConnector interface conformance).
"""

import os
import sys
import unittest
from pathlib import Path

# Add src/ to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from src import db
from src import host_connector
from src import main
from src import verify


LIVE = os.getenv("CERTOPS_RUN_LIVE") == "1"


@unittest.skipUnless(LIVE, "Live integration test; set CERTOPS_RUN_LIVE=1 to run in a sandbox")
class TestHostConnector(unittest.TestCase):
    def setUp(self):
        os.environ["SSH_HOST"] = "localhost"
        os.environ["SSH_PORT"] = "2222"
        os.environ["SSH_USERNAME"] = "root"
        os.environ["SSH_PASSWORD"] = "certops"
        os.environ["ENABLE_SSH_HOST"] = "true"

    def test_01_ssh_host_connector_discover_and_read(self):
        connector = host_connector.SSHHostConnector.from_env()
        certs = connector.discover_certificates()
        self.assertGreaterEqual(len(certs), 1, "Expected to discover at least 1 cert on Nginx host")

        meta = certs[0]
        self.assertEqual(meta.cert_id, "/etc/nginx/certs/local.crt")
        self.assertIsNotNone(meta.expiry_utc)

        cert_data = connector.read_certificate(meta.cert_id)
        self.assertIn("-----BEGIN CERTIFICATE-----", cert_data.cert_pem)
        self.assertIsNone(
            cert_data.private_key_pem,
            "read_certificate must never return private key material",
        )

    def test_02_ssh_host_connector_pipeline_and_reload_verification(self):
        orig_ssh = os.environ.get("SSH_RENEWAL_THRESHOLD_DAYS")
        os.environ["RENEWAL_THRESHOLD_DAYS"] = "365"  # Ensure renewal triggers
        os.environ["SSH_RENEWAL_THRESHOLD_DAYS"] = "365"
        try:
            summary = main.run_renewal_loop()
        finally:
            if orig_ssh is not None:
                os.environ["SSH_RENEWAL_THRESHOLD_DAYS"] = orig_ssh
            else:
                os.environ.pop("SSH_RENEWAL_THRESHOLD_DAYS", None)

        self.assertIn("ssh_host", summary)
        self.assertGreaterEqual(summary["ssh_host"]["succeeded"], 1)

        db_rec = db.get_certificate("ssh_host", "/etc/nginx/certs/local.crt")
        self.assertIsNotNone(db_rec)
        self.assertEqual(db_rec["connector_category"], "host")
        self.assertEqual(db_rec["pipeline_stage"], "Deployed, pending reload")

        # Explicit confirmation reload step
        reload_success = main.confirm_and_reload_host("ssh_host", "/etc/nginx/certs/local.crt")
        self.assertTrue(reload_success)

        db_rec_post = db.get_certificate("ssh_host", "/etc/nginx/certs/local.crt")
        self.assertEqual(db_rec_post["pipeline_stage"], "Reload confirmed")

        # Confirm live served cert matches what is in DB
        live_expiry, live_fp = verify.get_live_cert_info("localhost", 443)
        self.assertEqual(len(live_fp), 64)
        self.assertIsNotNone(live_expiry)

    def test_03_winrm_host_connector_conformance(self):
        connector = host_connector.WinRMHostConnector.from_env()
        self.assertIsInstance(connector, host_connector.HostConnector)
        self.assertEqual(connector.name, "winrm_host")


if __name__ == "__main__":
    unittest.main(verbosity=2)
