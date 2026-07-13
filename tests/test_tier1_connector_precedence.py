import os
import tempfile
import unittest
from pathlib import Path
from src import db, main, vault_client


class TestTier1ConnectorPrecedence(unittest.TestCase):
    def test_db_connector_precedence(self):
        """
        Proves that get_active_connectors() reads active connectors authoritative
        from DB 'connectors' table, overriding conflicting env vars.
        Falls back to env vars only when DB table is empty.
        """
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            test_db = f.name

        orig_db_path = os.environ.get("CERTOPS_DB_PATH")
        orig_conn1 = os.environ.get("CONNECTOR_1_TYPE")
        orig_vault_addr = os.environ.get("VAULT_ADDR")
        orig_vault_token = os.environ.get("VAULT_TOKEN")

        try:
            os.environ["CERTOPS_DB_PATH"] = test_db
            os.environ["CONNECTOR_1_TYPE"] = "hashicorp"
            os.environ["VAULT_ADDR"] = "http://env-vault:8200"
            os.environ["VAULT_TOKEN"] = "env-token"

            # Case 1: Empty DB table -> falls back to env vars
            connectors_env = main.get_active_connectors()
            self.assertGreaterEqual(len(connectors_env), 1)
            self.assertTrue(any(getattr(c, "vault_addr", None) == "http://env-vault:8200" for c in connectors_env))

            # Case 2: Create DB record -> DB config wins over env vars
            db.create_connector(
                name="db_hashicorp",
                category="secret_store",
                renewal_threshold_days=5.0,
                config='{"url": "http://db-authoritative-vault:8200", "token": "db-token"}',
                is_active=True,
                db_path=test_db,
            )

            connectors_db = main.get_active_connectors()
            self.assertEqual(len(connectors_db), 1)
            self.assertEqual(connectors_db[0].name, "db_hashicorp")
            self.assertEqual(getattr(connectors_db[0], "vault_addr", None), "http://db-authoritative-vault:8200")

        finally:
            if orig_db_path is not None:
                os.environ["CERTOPS_DB_PATH"] = orig_db_path
            else:
                os.environ.pop("CERTOPS_DB_PATH", None)
            if orig_conn1 is not None:
                os.environ["CONNECTOR_1_TYPE"] = orig_conn1
            else:
                os.environ.pop("CONNECTOR_1_TYPE", None)
            if orig_vault_addr is not None:
                os.environ["VAULT_ADDR"] = orig_vault_addr
            else:
                os.environ.pop("VAULT_ADDR", None)
            if orig_vault_token is not None:
                os.environ["VAULT_TOKEN"] = orig_vault_token
            else:
                os.environ.pop("VAULT_TOKEN", None)

            if Path(test_db).exists():
                Path(test_db).unlink()


if __name__ == "__main__":
    unittest.main(verbosity=2)
