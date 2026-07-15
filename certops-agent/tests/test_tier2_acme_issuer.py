"""
Tier 2 Test: CA-Agnostic Issuer Abstraction & ACME Support
Verifies CAIssuer interface compliance, StepCAIssuer, ACMEIssuer CLI construction, and factory resolution.
"""
import os
import unittest
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))
_sibling = _root.parent / "certops-dashboard"
if _sibling.exists() and str(_sibling) not in sys.path:
    sys.path.insert(0, str(_sibling))

from src import issuers


class TestTier2ACMEIssuer(unittest.TestCase):
    def test_factory_resolves_stepca_issuer(self):
        issuer = issuers.get_issuer("step-ca", password_file="./pass.txt", ca_url="https://localhost:8443")
        self.assertIsInstance(issuer, issuers.CAIssuer)
        self.assertIsInstance(issuer, issuers.StepCAIssuer)
        self.assertEqual(issuer.ca_url, "https://localhost:8443")

    def test_factory_resolves_acme_issuer(self):
        issuer = issuers.get_issuer(
            "acme",
            directory_url="https://acme-staging-v02.api.letsencrypt.org/directory",
            contact_email="admin@certops.internal",
        )
        self.assertIsInstance(issuer, issuers.CAIssuer)
        self.assertIsInstance(issuer, issuers.ACMEIssuer)
        self.assertEqual(issuer.directory_url, "https://acme-staging-v02.api.letsencrypt.org/directory")
        self.assertEqual(issuer.contact_email, "admin@certops.internal")

    def test_factory_invalid_type_raises(self):
        with self.assertRaises(ValueError):
            issuers.get_issuer("unknown_ca")

    def test_stepca_issuer_delegates_to_ca_client(self):
        issuer = issuers.StepCAIssuer(password_file="./pass.txt", ca_url="https://localhost:8443")
        with patch("src.ca_client.issue_certificate", return_value=("CERT_PEM", "KEY_PEM")) as mock_issue:
            cert, key = issuer.issue_certificate("test.example.com")
            self.assertEqual((cert, key), ("CERT_PEM", "KEY_PEM"))
            mock_issue.assert_called_once_with(
                subject="test.example.com",
                password_file="./pass.txt",
                ca_url="https://localhost:8443",
                fingerprint=None,
            )

    def test_acme_issuer_command_construction(self):
        issuer = issuers.ACMEIssuer(
            directory_url="https://acme.internal/directory",
            contact_email="ops@internal",
            standalone=True,
            http_listen=":18080",
        )

        fake_cert = "-----BEGIN CERTIFICATE-----\nACME_CERT\n-----END CERTIFICATE-----"
        fake_key = "-----BEGIN PRIVATE KEY-----\nACME_KEY\n-----END PRIVATE KEY-----"

        def _fake_run(cmd, capture_output=True, text=True, check=False):
            # Locate cert and key paths in cmd arguments
            cert_path = cmd[4]
            key_path = cmd[5]
            with open(cert_path, "w", encoding="utf-8") as fc:
                fc.write(fake_cert)
            with open(key_path, "w", encoding="utf-8") as fk:
                fk.write(fake_key)
            return MagicMock(returncode=0, stdout="Issued", stderr="")

        with patch("src.ca_client._find_step_binary", return_value="/usr/bin/step"), \
             patch("subprocess.run", side_effect=_fake_run) as mock_run:
            cert, key = issuer.issue_certificate("acme-app.example.com")
            self.assertEqual(cert, fake_cert)
            self.assertEqual(key, fake_key)

            cmd = mock_run.call_args[0][0]
            self.assertEqual(cmd[0], "/usr/bin/step")
            self.assertEqual(cmd[1:4], ["ca", "certificate", "acme-app.example.com"])
            self.assertIn("--acme", cmd)
            self.assertIn("https://acme.internal/directory", cmd)
            self.assertIn("--contact", cmd)
            self.assertIn("ops@internal", cmd)
            self.assertIn("--standalone", cmd)
            self.assertIn("--http-listen", cmd)
            self.assertIn(":18080", cmd)


if __name__ == "__main__":
    unittest.main()
