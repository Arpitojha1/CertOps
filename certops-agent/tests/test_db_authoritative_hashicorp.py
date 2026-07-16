"""
Hermetic test: HashiCorp connector uses DB config over env vars.
The critical fix: removes the 'http://localhost:8200' sentinel check.
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


class TestHashicorpConnectorDBPrecedence(unittest.TestCase):
    def test_hashicorp_connector_db_config_precedence(self):
        """
        When DB config has url='https://db-vault:8200' and token='db-token',
        and env has VAULT_ADDR='http://env-vault:8200' and VAULT_TOKEN='env-token',
        the connector must use DB values.
        """
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            test_db = f.name

        orig_db_path = os.environ.get("CERTOPS_DB_PATH")
        try:
            os.environ["CERTOPS_DB_PATH"] = test_db
            os.environ["SKIP_DEFAULT_CONNECTORS"] = "1"
            db.run_migrations(test_db)

            db_config = {"url": "https://db-vault:8200", "token": "db-secret-token"}
            db.create_connector(
                name="vault-prod",
                category="secret_store",
                renewal_threshold_days=14.0,
                config=json.dumps(db_config),
                is_active=True,
                db_path=test_db,
            )

            os.environ["VAULT_ADDR"] = "http://env-vault:8200"
            os.environ["VAULT_TOKEN"] = "env-secret-token"

            connectors = main.get_active_connectors(db_path=test_db)

            self.assertEqual(len(connectors), 1)
            c = connectors[0]
            self.assertEqual(c.name, "vault-prod")
            self.assertEqual(c.vault_addr, "https://db-vault:8200")
            self.assertEqual(c.vault_token, "db-secret-token")
            print(f"[PASS] Hashicorp connector vault_addr={c.vault_addr} token={c.vault_token[:10]}... (DB values used)")

        finally:
            if orig_db_path is not None:
                os.environ["CERTOPS_DB_PATH"] = orig_db_path
            else:
                os.environ.pop("CERTOPS_DB_PATH", None)
            os.environ.pop("VAULT_ADDR", None)
            os.environ.pop("VAULT_TOKEN", None)
            db.close_db_connection(test_db)
            try:
                os.unlink(test_db)
            except Exception:
                pass

    def test_hashicorp_no_sentinel_override(self):
        """
        The old bug: if DB config had url='http://localhost:8200',
        the sentinel check would override it with VAULT_ADDR from env.
        This test proves the fix: DB value is used even when it equals
        the old sentinel string.
        """
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            test_db = f.name

        try:
            os.environ["CERTOPS_DB_PATH"] = test_db
            os.environ["SKIP_DEFAULT_CONNECTORS"] = "1"
            db.run_migrations(test_db)

            db_config = {"url": "http://localhost:8200", "token": "db-token-for-localhost"}
            db.create_connector(
                name="vault-local",
                category="secret_store",
                renewal_threshold_days=7.0,
                config=json.dumps(db_config),
                is_active=True,
                db_path=test_db,
            )

            os.environ["VAULT_ADDR"] = "http://env-vault-override:8200"

            connectors = main.get_active_connectors(db_path=test_db)

            self.assertEqual(len(connectors), 1)
            c = connectors[0]
            self.assertEqual(c.vault_addr, "http://localhost:8200")
            print("[PASS] Hashicorp sentinel check removed: DB localhost:8200 NOT overridden by env")

        finally:
            os.environ.pop("CERTOPS_DB_PATH", None)
            os.environ.pop("VAULT_ADDR", None)
            os.environ.pop("SKIP_DEFAULT_CONNECTORS", None)
            db.close_db_connection(test_db)
            try:
                os.unlink(test_db)
            except Exception:
                pass

    def test_hashicorp_env_fallback_when_db_missing(self):
        """
        When DB config has no url/token fields, falls back to env vars.
        """
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            test_db = f.name

        try:
            os.environ["CERTOPS_DB_PATH"] = test_db
            os.environ["SKIP_DEFAULT_CONNECTORS"] = "1"
            db.run_migrations(test_db)

            db_config = {}
            db.create_connector(
                name="vault-fallback",
                category="secret_store",
                renewal_threshold_days=7.0,
                config=json.dumps(db_config),
                is_active=True,
                db_path=test_db,
            )

            os.environ["VAULT_ADDR"] = "http://env-fallback:8200"
            os.environ["VAULT_TOKEN"] = "env-fallback-token"

            connectors = main.get_active_connectors(db_path=test_db)

            self.assertEqual(len(connectors), 1)
            c = connectors[0]
            self.assertEqual(c.vault_addr, "http://env-fallback:8200")
            self.assertEqual(c.vault_token, "env-fallback-token")
            print("[PASS] Hashicorp falls back to env when DB config is empty")

        finally:
            os.environ.pop("CERTOPS_DB_PATH", None)
            os.environ.pop("VAULT_ADDR", None)
            os.environ.pop("VAULT_TOKEN", None)
            os.environ.pop("SKIP_DEFAULT_CONNECTORS", None)
            db.close_db_connection(test_db)
            try:
                os.unlink(test_db)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
