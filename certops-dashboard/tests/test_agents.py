"""Tests for the agents registration and listing API."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import sys
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))
_sibling = _root.parent / "certops-agent"
if _sibling.exists() and str(_sibling) not in sys.path:
    sys.path.insert(0, str(_sibling))

from src import api, auth, db


class TestAgentsAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._set_vars = [
            "SKIP_DEFAULT_CONNECTORS",
            "CERTOPS_CONFIG_ENCRYPTION_KEY",
            "JWT_SECRET",
            "AGENT_TOKEN_SIGNING_KEY",
        ]
        cls._saved_vars = {k: os.environ.get(k) for k in cls._set_vars}
        os.environ["SKIP_DEFAULT_CONNECTORS"] = "1"
        os.environ["CERTOPS_CONFIG_ENCRYPTION_KEY"] = "test-key-for-agents=="
        os.environ["JWT_SECRET"] = "test-jwt-secret-for-agents"
        os.environ["AGENT_TOKEN_SIGNING_KEY"] = "test-agent-token-signing-key-for-agents"
        cls.orig_env = {
            "CERTOPS_DB_PATH": os.environ.get("CERTOPS_DB_PATH"),
            "DB_PATH": os.environ.get("DB_PATH"),
        }
        cls.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls.db_path = cls.tmp.name
        cls.tmp.close()
        os.environ["CERTOPS_DB_PATH"] = cls.db_path
        db.run_migrations(cls.db_path)
        db.create_user("admin@test.com", auth.hash_password("testpass123"), "admin", "default", db_path=cls.db_path)
        cls.client = TestClient(api.app, raise_server_exceptions=True)

    @classmethod
    def tearDownClass(cls):
        db.close_db_connection(cls.db_path)
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass
        for k, val in cls.orig_env.items():
            if val is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = val
        for k, val in cls._saved_vars.items():
            if val is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = val

    def _admin_token(self):
        conn = db.get_db_connection(self.db_path)
        try:
            row = conn.execute("SELECT id FROM users WHERE email = ?", ("admin@test.com",)).fetchone()
        finally:
            conn.close()
        return auth._make_token(row[0], "admin@test.com", "admin", "default")

    def test_register_agent(self):
        token = self._admin_token()
        resp = self.client.post(
            "/api/agents/register",
            json={"name": "test-agent"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("agent_id", data)
        self.assertEqual(data["tenant_id"], "default")
        self.assertIn("token", data)
        self.assertEqual(data["status"], "pending")

    def test_list_agents(self):
        token = self._admin_token()
        self.client.post(
            "/api/agents/register",
            json={"name": "agent-1"},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = self.client.get(
            "/api/agents",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 200)
        agents = resp.json()
        self.assertGreaterEqual(len(agents), 1)
        names = [a["name"] for a in agents]
        self.assertIn("agent-1", names)

    def test_get_agent_detail(self):
        token = self._admin_token()
        reg = self.client.post(
            "/api/agents/register",
            json={"name": "detail-agent"},
            headers={"Authorization": f"Bearer {token}"},
        )
        agent_id = reg.json()["agent_id"]
        resp = self.client.get(
            f"/api/agents/{agent_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "detail-agent")

    def test_register_requires_admin(self):
        resp = self.client.post(
            "/api/agents/register",
            json={"name": "no-auth"},
        )
        self.assertIn(resp.status_code, [401, 403, 422])


if __name__ == "__main__":
    unittest.main(verbosity=2)
