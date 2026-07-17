"""
Hermetic test: WinRM connector uses DB config over env vars.
"""

import json
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

from src import db, main
from src.host_connector import WinRMHostConnector


class TestWinRMConnectorDBPrecedence(unittest.TestCase):
    def test_winrm_connector_uses_db_config_over_env(self):
        """
        When DB config has hostname='db-winrm-host' and env has WINRM_HOST='env-winrm-host',
        the connector must use the DB value.
        """
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            test_db = f.name

        orig_db_path = os.environ.get("CERTOPS_DB_PATH")
        try:
            os.environ["CERTOPS_DB_PATH"] = test_db
            os.environ["SKIP_DEFAULT_CONNECTORS"] = "1"
            db.run_migrations(test_db)

            db_config = {
                "hostname": "db-winrm-host",
                "port": 5986,
                "username": "db-admin",
                "password": "db-pass-123",
                "auth_type": "kerberos",
                "iis_site_name": "DB-Web-App",
            }
            db.create_connector(
                name="winrm-prod",
                category="winrm_host",
                renewal_threshold_days=21.0,
                config=json.dumps(db_config),
                is_active=True,
                db_path=test_db,
            )

            os.environ["WINRM_HOST"] = "env-winrm-host"
            os.environ["WINRM_PORT"] = "5985"
            os.environ["WINRM_USERNAME"] = "env-admin"
            os.environ["WINRM_PASSWORD"] = "env-pass"
            os.environ["WINRM_AUTH_TYPE"] = "ntlm"
            os.environ["WINRM_IIS_SITE_NAME"] = "Env-Web-Site"

            connectors = main.get_active_connectors(db_path=test_db)

            self.assertEqual(len(connectors), 1)
            c = connectors[0]
            self.assertEqual(c.name, "winrm-prod")
            self.assertEqual(c.hostname, "db-winrm-host")
            self.assertEqual(c.port, 5986)
            self.assertEqual(c.username, "db-admin")
            self.assertEqual(c.password, "db-pass-123")
            self.assertEqual(c.auth_type, "kerberos")
            self.assertEqual(c.iis_site_name, "DB-Web-App")
            print(f"[PASS] WinRM connector hostname={c.hostname} auth={c.auth_type} (DB values used)")

        finally:
            if orig_db_path is not None:
                os.environ["CERTOPS_DB_PATH"] = orig_db_path
            else:
                os.environ.pop("CERTOPS_DB_PATH", None)
            for var in ["WINRM_HOST", "WINRM_PORT", "WINRM_USERNAME", "WINRM_PASSWORD",
                        "WINRM_AUTH_TYPE", "WINRM_IIS_SITE_NAME", "SKIP_DEFAULT_CONNECTORS"]:
                os.environ.pop(var, None)
            db.close_db_connection(test_db)
            try:
                os.unlink(test_db)
            except Exception:
                pass

    def test_winrm_from_config_fallback_to_env(self):
        """
        When DB config is missing a field, from_config falls back to env for that field.
        """
        try:
            os.environ["WINRM_PORT"] = "5986"
            os.environ["WINRM_USERNAME"] = "env-user"
            os.environ["WINRM_PASSWORD"] = "env-pass"

            db_config = {"hostname": "db-winrm-only"}
            c = WinRMHostConnector.from_config(db_config)

            self.assertEqual(c.hostname, "db-winrm-only")
            self.assertEqual(c.port, 5986)
            self.assertEqual(c.username, "env-user")
            self.assertEqual(c.password, "env-pass")
            print("[PASS] WinRM from_config falls back to env for missing fields")

        finally:
            for var in ["WINRM_PORT", "WINRM_USERNAME", "WINRM_PASSWORD"]:
                os.environ.pop(var, None)

    def test_winrm_from_config_no_env_override(self):
        """
        When DB config has a value, env var must NOT override it.
        """
        try:
            os.environ["WINRM_HOST"] = "env-host-override"
            os.environ["WINRM_PORT"] = "1234"

            db_config = {"hostname": "db-host", "port": "5986"}
            c = WinRMHostConnector.from_config(db_config)

            self.assertEqual(c.hostname, "db-host")
            self.assertEqual(c.port, 5986)
            print("[PASS] WinRM from_config: env vars do NOT override DB values")

        finally:
            os.environ.pop("WINRM_HOST", None)
            os.environ.pop("WINRM_PORT", None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
