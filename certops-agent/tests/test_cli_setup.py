"""Tests for the CLI setup wizard steps."""
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))

os.environ["SKIP_DEFAULT_CONNECTORS"] = "1"
os.environ["CERTOPS_CONFIG_ENCRYPTION_KEY"] = "esLNRAOgYV_cuE1EYjj-Rvp_HjKyasnke1M8FvrKopY="

from agent_db import init_agent_db, get_identity, get_status


class TestSetupStep1Registration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        os.environ["AGENT_DB_PATH"] = self.db_path

    def tearDown(self):
        os.environ.pop("AGENT_DB_PATH", None)
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_register_step_writes_identity(self):
        from main import _setup_register
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "agent_id": "test-agent-id",
            "tenant_id": "default",
            "token": "test-jwt-token",
            "status": "pending",
        }
        with patch("main.requests.post", return_value=mock_resp):
            _setup_register(
                dashboard_url="https://dashboard.test.com",
                admin_email="admin@test.com",
                admin_password="testpass",
                agent_name="test-agent",
                db_path=self.db_path,
            )
        self.assertEqual(get_identity("agent_id", self.db_path), "test-agent-id")
        self.assertEqual(get_identity("token", self.db_path), "test-jwt-token")
        self.assertEqual(get_identity("dashboard_url", self.db_path), "https://dashboard.test.com")
        self.assertEqual(get_status(self.db_path), "registered")

    def test_register_step_handles_failure(self):
        from main import _setup_register
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"detail": "Invalid credentials"}
        with patch("main.requests.post", return_value=mock_resp):
            with self.assertRaises(SystemExit):
                _setup_register(
                    dashboard_url="https://dashboard.test.com",
                    admin_email="admin@test.com",
                    admin_password="wrong",
                    agent_name="test-agent",
                    db_path=self.db_path,
                )
        self.assertEqual(get_status(self.db_path), "pending")


class TestSetupStep2Configure(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        os.environ["AGENT_DB_PATH"] = self.db_path
        from agent_db import init_agent_db, set_identity, set_status
        init_agent_db(self.db_path)
        set_identity("agent_id", "test-agent-id", self.db_path)
        set_status("registered", self.db_path)

    def tearDown(self):
        os.environ.pop("AGENT_DB_PATH", None)
        os.environ.pop("VAULT_ADDR", None)
        os.environ.pop("VAULT_TOKEN", None)
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_configure_vault(self):
        from main import _setup_configure
        with patch("main.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_get.return_value = mock_resp
            _setup_configure(
                backend="vault",
                credentials={"vault_addr": "https://vault.test:8200", "vault_token": "s.test123"},
                db_path=self.db_path,
            )
        from agent_db import get_config, get_status
        self.assertEqual(get_config("vault_addr", self.db_path), "https://vault.test:8200")
        self.assertEqual(get_config("vault_token", self.db_path), "s.test123")
        self.assertEqual(get_status(self.db_path), "configured")

    def test_configure_skip(self):
        from main import _setup_configure
        _setup_configure(backend=None, credentials={}, db_path=self.db_path)
        from agent_db import get_status
        self.assertEqual(get_status(self.db_path), "configured")


class TestTelemetryWiring(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        os.environ["AGENT_DB_PATH"] = self.db_path
        from agent_db import init_agent_db, set_identity, set_status
        init_agent_db(self.db_path)
        set_identity("agent_id", "test-agent-id", self.db_path)
        set_identity("token", "test-jwt-token", self.db_path)
        set_identity("dashboard_url", "https://dashboard.test.com", self.db_path)
        set_status("active", self.db_path)

    def tearDown(self):
        os.environ.pop("AGENT_DB_PATH", None)
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_telemetry_push_called_when_agent_db_exists(self):
        from main import _try_push_telemetry
        mock_client = MagicMock()
        mock_client.push.return_value = (202, {"status": "accepted"})
        with patch("main.AgentTelemetryClient", return_value=mock_client):
            _try_push_telemetry({"total": 1, "succeeded": 1}, self.db_path)
        mock_client.push.assert_called_once()

    def test_telemetry_push_skipped_when_no_agent_db(self):
        from main import _try_push_telemetry
        _try_push_telemetry({"total": 1, "succeeded": 1}, "./nonexistent.db")
        # No error, just skipped


if __name__ == "__main__":
    unittest.main()
