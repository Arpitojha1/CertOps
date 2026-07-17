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

        orig_skip = os.environ.get("SKIP_DEFAULT_CONNECTORS")

        try:
            os.environ["CERTOPS_DB_PATH"] = test_db
            os.environ["SKIP_DEFAULT_CONNECTORS"] = "1"
            db.run_migrations(test_db)
            os.environ["CONNECTOR_1_TYPE"] = "hashicorp"
            os.environ["VAULT_ADDR"] = "http://env-vault:8200"
            os.environ["VAULT_TOKEN"] = "env-token"

            # Case 1: Empty DB table -> returns [] (DB-authoritative; no env-var fallback)
            conns = main.get_active_connectors()
            self.assertEqual(conns, [], "DB-authoritative: Empty DB table must return [] regardless of env vars")

            # Case 2: DB table has rows -> returns those rows sorted
            db.create_connector("db-vault", "secret_store", 14.0, '{"url":"https://db-vault:8200","token":"db-token"}', True, db_path=test_db)
            conns = main.get_active_connectors()
            self.assertEqual(len(conns), 1)
            self.assertEqual(conns[0].name, "db-vault")
            self.assertEqual(getattr(conns[0], "vault_addr", None), "https://db-vault:8200")

        finally:
            if orig_db_path is not None:
                os.environ["CERTOPS_DB_PATH"] = orig_db_path
            else:
                os.environ.pop("CERTOPS_DB_PATH", None)

            if orig_skip is not None:
                os.environ["SKIP_DEFAULT_CONNECTORS"] = orig_skip
            else:
                os.environ.pop("SKIP_DEFAULT_CONNECTORS", None)

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

            db.close_db_connection(test_db)
            if Path(test_db).exists():
                Path(test_db).unlink()


class TestEnvVarSeedCreatesDBRow(unittest.TestCase):
    def test_vault_env_seed_creates_connector_then_db_is_authoritative(self):
        """
        Setting VAULT_ADDR + VAULT_TOKEN and running get_active_connectors
        should auto-create a 'hashicorp' connector in DB on first call,
        then subsequent calls use the DB-stored config (not env vars).
        """
        import json as _json
        from src import connector_registry

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            test_db = f.name

        orig_db_path = os.environ.get("CERTOPS_DB_PATH")
        try:
            os.environ["CERTOPS_DB_PATH"] = test_db
            os.environ["SKIP_DEFAULT_CONNECTORS"] = "1"
            db.run_migrations(test_db)

            self.assertIsNone(db.get_connector_by_name("hashicorp", db_path=test_db))

            os.environ["VAULT_ADDR"] = "http://env-vault:8200"
            os.environ["VAULT_TOKEN"] = "env-secret-token"

            seeded = connector_registry.seed_connectors_from_env(db_path=test_db)
            self.assertEqual(seeded, ["hashicorp"])

            row = db.get_connector_by_name("hashicorp", db_path=test_db)
            self.assertIsNotNone(row)
            cfg = db.decrypt_config(row["config"])
            self.assertEqual(cfg["url"], "http://env-vault:8200")
            self.assertEqual(cfg["token"], "env-secret-token")

            os.environ["VAULT_ADDR"] = "http://changed-vault:8200"
            os.environ["VAULT_TOKEN"] = "changed-token"

            connectors = main.get_active_connectors(db_path=test_db)
            self.assertEqual(len(connectors), 1)
            c = connectors[0]
            self.assertEqual(c.vault_addr, "http://env-vault:8200")
            self.assertEqual(c.vault_token, "env-secret-token")

        finally:
            if orig_db_path is not None:
                os.environ["CERTOPS_DB_PATH"] = orig_db_path
            else:
                os.environ.pop("CERTOPS_DB_PATH", None)
            os.environ.pop("VAULT_ADDR", None)
            os.environ.pop("VAULT_TOKEN", None)
            os.environ.pop("SKIP_DEFAULT_CONNECTORS", None)
            db.close_db_connection(test_db)
            try:
                os.unlink(test_db)
            except Exception:
                pass

    def test_azure_env_seed_creates_connector(self):
        from src import connector_registry
        from unittest.mock import patch, MagicMock

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            test_db = f.name

        orig_db_path = os.environ.get("CERTOPS_DB_PATH")
        try:
            os.environ["CERTOPS_DB_PATH"] = test_db
            os.environ["SKIP_DEFAULT_CONNECTORS"] = "1"
            db.run_migrations(test_db)

            os.environ["AZURE_KEYVAULT_URL"] = "https://env-vault.vault.azure.net"
            os.environ["AZURE_TENANT_ID"] = "env-tenant"
            os.environ["AZURE_CLIENT_ID"] = "env-client"
            os.environ["AZURE_CLIENT_SECRET"] = "env-secret"

            seeded = connector_registry.seed_connectors_from_env(db_path=test_db)
            self.assertEqual(seeded, ["azure"])

            row = db.get_connector_by_name("azure", db_path=test_db)
            self.assertIsNotNone(row)
            self.assertEqual(row["category"], "azure")

        finally:
            if orig_db_path is not None:
                os.environ["CERTOPS_DB_PATH"] = orig_db_path
            else:
                os.environ.pop("CERTOPS_DB_PATH", None)
            for var in ["AZURE_KEYVAULT_URL", "AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "SKIP_DEFAULT_CONNECTORS"]:
                os.environ.pop(var, None)
            db.close_db_connection(test_db)
            try:
                os.unlink(test_db)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
