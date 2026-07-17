"""
Hermetic test: Azure connector uses DB config over env vars.
Mocks the Azure SDK so no live network is needed.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))
_sibling = _root.parent / "certops-dashboard"
if _sibling.exists() and str(_sibling) not in sys.path:
    sys.path.insert(0, str(_sibling))

from src import db, main
from src.azurekeyvault import AzureKeyVaultClient


class TestAzureConnectorDBPrecedence(unittest.TestCase):
    def test_azure_connector_uses_db_config_over_env(self):
        """
        When DB config has keyvault_url='https://db-vault.vault.azure.net'
        and env has AZURE_KEYVAULT_URL='https://env-vault.vault.azure.net',
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
                "keyvault_url": "https://db-vault.vault.azure.net",
                "tenant_id": "db-tenant-id-12345",
                "client_id": "db-client-id-67890",
                "client_secret": "db-client-secret-abcdef",
            }
            db.create_connector(
                name="azure-prod",
                category="azure",
                renewal_threshold_days=30.0,
                config=json.dumps(db_config),
                is_active=True,
                db_path=test_db,
            )

            os.environ["AZURE_KEYVAULT_URL"] = "https://env-vault.vault.azure.net"
            os.environ["AZURE_TENANT_ID"] = "env-tenant-id"
            os.environ["AZURE_CLIENT_ID"] = "env-client-id"
            os.environ["AZURE_CLIENT_SECRET"] = "env-client-secret"

            with patch("src.azurekeyvault.CertificateClient") as mock_cc:
                mock_cc.return_value = MagicMock()
                connectors = main.get_active_connectors(db_path=test_db)

            self.assertEqual(len(connectors), 1)
            c = connectors[0]
            self.assertEqual(c.name, "azure-prod")
            self.assertEqual(c.vault_url, "https://db-vault.vault.azure.net")
            cred = c.credential
            self.assertEqual(cred._tenant_id, "db-tenant-id-12345")
            self.assertEqual(cred._client_id, "db-client-id-67890")
            print(f"[PASS] Azure connector vault_url={c.vault_url} (DB value used, not env)")

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

    def test_azure_from_config_fallback_to_env(self):
        """
        When DB config is missing a field (e.g. tenant_id), from_config
        should fall back to env for that specific field only.
        """
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            test_db = f.name

        try:
            os.environ["CERTOPS_DB_PATH"] = test_db
            os.environ["SKIP_DEFAULT_CONNECTORS"] = "1"
            db.run_migrations(test_db)

            db_config = {
                "keyvault_url": "https://db-vault.vault.azure.net",
                "client_id": "db-client-id",
                "client_secret": "db-client-secret",
            }

            os.environ["AZURE_TENANT_ID"] = "env-tenant-id-fallback"

            with patch("src.azurekeyvault.CertificateClient"):
                c = AzureKeyVaultClient.from_config(db_config)

            self.assertEqual(c.vault_url, "https://db-vault.vault.azure.net")
            cred = c.credential
            self.assertEqual(cred._tenant_id, "env-tenant-id-fallback")
            print("[PASS] Azure from_config falls back to env for missing tenant_id")

        finally:
            for var in ["CERTOPS_DB_PATH", "AZURE_TENANT_ID", "SKIP_DEFAULT_CONNECTORS"]:
                os.environ.pop(var, None)
            db.close_db_connection(test_db)
            try:
                os.unlink(test_db)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
