"""
Hermetic tests for connector_registry: resolve, match, auto-detect, seed.
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

from src import connector_registry


class TestGenericConnectorFallback(unittest.TestCase):
    def test_unknown_category_returns_generic_connector(self):
        row = {
            "name": "mystery-connector",
            "category": "unknown_type",
            "config": "{}",
            "renewal_threshold_days": 7.0,
        }
        c = connector_registry.resolve_connector(row)
        self.assertEqual(c.name, "mystery-connector")
        self.assertEqual(c.category, "unknown_type")
        self.assertEqual(c.renewal_threshold_days, 7.0)


class TestAzureMatch(unittest.TestCase):
    def setUp(self):
        self._orig = {k: os.environ.get(k) for k in ["AZURE_KEYVAULT_URL", "AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"]}
        os.environ["AZURE_KEYVAULT_URL"] = "https://env-vault.vault.azure.net"
        os.environ["AZURE_TENANT_ID"] = "env-tenant"
        os.environ["AZURE_CLIENT_ID"] = "env-client"
        os.environ["AZURE_CLIENT_SECRET"] = "env-secret"

    def tearDown(self):
        for k, v in self._orig.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_category_azure_matches(self):
        row = {"name": "my-azure", "category": "azure", "config": "{}", "renewal_threshold_days": 30.0}
        with patch("src.azurekeyvault.CertificateClient"):
            c = connector_registry.resolve_connector(row)
        self.assertEqual(c.name, "my-azure")
        self.assertEqual(c.vault_url, "https://env-vault.vault.azure.net")

    def test_name_contains_azure_matches(self):
        row = {"name": "azure-prod-kv", "category": "secret_store", "config": "{}", "renewal_threshold_days": 30.0}
        with patch("src.azurekeyvault.CertificateClient"):
            c = connector_registry.resolve_connector(row)
        self.assertEqual(c.name, "azure-prod-kv")

    def test_config_provider_azure_matches(self):
        row = {"name": "custom-name", "category": "other", "config": json.dumps({"provider": "azure", "keyvault_url": "https://x.vault.azure.net", "tenant_id": "t", "client_id": "c", "client_secret": "s"}), "renewal_threshold_days": 30.0}
        with patch("src.azurekeyvault.CertificateClient"):
            c = connector_registry.resolve_connector(row)
        self.assertEqual(c.name, "custom-name")


class TestHashicorpMatch(unittest.TestCase):
    def setUp(self):
        self._orig = {k: os.environ.get(k) for k in ["VAULT_ADDR", "VAULT_TOKEN"]}
        os.environ["VAULT_ADDR"] = "http://env-vault:8200"
        os.environ["VAULT_TOKEN"] = "env-token-123"

    def tearDown(self):
        for k, v in self._orig.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_category_secret_store_matches(self):
        row = {"name": "vault-main", "category": "secret_store", "config": "{}", "renewal_threshold_days": 14.0}
        c = connector_registry.resolve_connector(row)
        self.assertEqual(c.name, "vault-main")
        self.assertEqual(c.vault_addr, "http://env-vault:8200")

    def test_category_hashicorp_matches(self):
        row = {"name": "hc-prod", "category": "hashicorp", "config": "{}", "renewal_threshold_days": 14.0}
        c = connector_registry.resolve_connector(row)
        self.assertEqual(c.name, "hc-prod")

    def test_name_contains_vault_matches(self):
        row = {"name": "my-vault-connector", "category": "other", "config": "{}", "renewal_threshold_days": 14.0}
        c = connector_registry.resolve_connector(row)
        self.assertEqual(c.name, "my-vault-connector")

    def test_db_config_overrides_env(self):
        row = {"name": "vault-db", "category": "secret_store", "config": json.dumps({"url": "https://db-vault:8200", "token": "db-token"}), "renewal_threshold_days": 14.0}
        c = connector_registry.resolve_connector(row)
        self.assertEqual(c.vault_addr, "https://db-vault:8200")
        self.assertEqual(c.vault_token, "db-token")


class TestSSHMatch(unittest.TestCase):
    def test_category_ssh_host_matches(self):
        row = {"name": "web-ssh", "category": "ssh_host", "config": "{}", "renewal_threshold_days": 7.0}
        c = connector_registry.resolve_connector(row)
        self.assertEqual(c.name, "web-ssh")

    def test_name_contains_ssh_matches(self):
        row = {"name": "my-ssh-host", "category": "other", "config": "{}", "renewal_threshold_days": 7.0}
        c = connector_registry.resolve_connector(row)
        self.assertEqual(c.name, "my-ssh-host")


class TestWinrmMatch(unittest.TestCase):
    def test_category_winrm_host_matches(self):
        row = {"name": "iis-winrm", "category": "winrm_host", "config": "{}", "renewal_threshold_days": 7.0}
        c = connector_registry.resolve_connector(row)
        self.assertEqual(c.name, "iis-winrm")

    def test_name_contains_winrm_matches(self):
        row = {"name": "my-winrm-server", "category": "other", "config": "{}", "renewal_threshold_days": 7.0}
        c = connector_registry.resolve_connector(row)
        self.assertEqual(c.name, "my-winrm-server")


class TestResolveHostConnector(unittest.TestCase):
    def test_ssh_host_resolves(self):
        row = {"name": "web-ssh", "category": "ssh_host", "config": "{}", "renewal_threshold_days": 7.0}
        c = connector_registry.resolve_host_connector(row)
        self.assertEqual(c.name, "web-ssh")

    def test_winrm_host_resolves(self):
        row = {"name": "iis-winrm", "category": "winrm_host", "config": "{}", "renewal_threshold_days": 7.0}
        c = connector_registry.resolve_host_connector(row)
        self.assertEqual(c.name, "iis-winrm")

    def test_secret_store_raises(self):
        row = {"name": "vault-main", "category": "secret_store", "config": "{}", "renewal_threshold_days": 14.0}
        with self.assertRaises(RuntimeError):
            connector_registry.resolve_host_connector(row)

    def test_azure_raises(self):
        row = {"name": "azure-kv", "category": "azure", "config": "{}", "renewal_threshold_days": 30.0}
        with self.assertRaises(RuntimeError):
            connector_registry.resolve_host_connector(row)
