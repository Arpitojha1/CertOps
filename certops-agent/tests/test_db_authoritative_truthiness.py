# certops-agent/tests/test_db_authoritative_truthiness.py
import os
import unittest
from pathlib import Path
import sys

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))

from src.azurekeyvault import AzureKeyVaultClient
from src.host_connector import SSHHostConnector, WinRMHostConnector
from src.vault_client import HashiCorpVaultClient
from src import connector_registry


class TestDBAuthoritativeTruthiness(unittest.TestCase):
    def setUp(self):
        os.environ["AZURE_KEYVAULT_URL"] = "https://env.vault.azure.net"
        os.environ["AZURE_TENANT_ID"] = "env-tenant"
        os.environ["AZURE_CLIENT_ID"] = "env-client"
        os.environ["AZURE_CLIENT_SECRET"] = "env-secret"
        os.environ["SSH_HOST"] = "env-ssh-host"
        os.environ["SSH_PASSWORD"] = "env-ssh-pass"
        os.environ["WINRM_PASSWORD"] = "env-winrm-pass"
        os.environ["VAULT_ADDR"] = "http://env-vault:8200"
        os.environ["VAULT_TOKEN"] = "env-vault-token"

    def tearDown(self):
        for var in [
            "AZURE_KEYVAULT_URL", "AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET",
            "SSH_HOST", "SSH_PASSWORD", "WINRM_PASSWORD", "VAULT_ADDR", "VAULT_TOKEN",
        ]:
            os.environ.pop(var, None)

    def test_azure_from_config_respects_empty_string(self):
        # If DB explicitly has client_secret="", it must NOT fall back to env-secret
        config = {
            "keyvault_url": "https://db.vault.azure.net",
            "tenant_id": "db-tenant",
            "client_id": "db-client",
            "client_secret": "",
        }
        with self.assertRaises(RuntimeError) as ctx:
            AzureKeyVaultClient.from_config(config)
        self.assertIn("client_secret", str(ctx.exception))

    def test_ssh_from_config_respects_empty_password(self):
        config = {"hostname": "db-host", "password": ""}
        conn = SSHHostConnector.from_config(config)
        self.assertEqual(conn.hostname, "db-host")
        self.assertEqual(conn.password, "", "DB value '' was ignored for os.getenv('SSH_PASSWORD')")

    def test_winrm_from_config_respects_empty_password(self):
        config = {"hostname": "db-winrm", "password": ""}
        conn = WinRMHostConnector.from_config(config)
        self.assertEqual(conn.hostname, "db-winrm")
        self.assertEqual(conn.password, "", "DB value '' was ignored for os.getenv('WINRM_PASSWORD')")

    def test_registry_resolve_hashicorp_respects_empty_token(self):
        row = {
            "name": "test-vault",
            "category": "hashicorp",
            "config": {"url": "http://db-vault:8200", "token": ""},
            "renewal_threshold_days": 10,
        }
        with self.assertRaises(RuntimeError) as ctx:
            connector_registry.resolve_connector(row)
        self.assertIn("VAULT_TOKEN not set", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
