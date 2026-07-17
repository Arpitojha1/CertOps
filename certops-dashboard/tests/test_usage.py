"""Tests for the usage metering system."""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

import sys
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))
_sibling = _root.parent / "certops-agent"
if _sibling.exists() and str(_sibling) not in sys.path:
    sys.path.insert(0, str(_sibling))

os.environ["SKIP_DEFAULT_CONNECTORS"] = "1"
os.environ["CERTOPS_CONFIG_ENCRYPTION_KEY"] = "test-key-for-usage=="
os.environ["AGENT_TOKEN_SIGNING_KEY"] = "test-agent-token-key-for-usage"

from src import api, db
from fastapi.testclient import TestClient
from src.routes.telemetry_ingest import register_agent_token, clear_received_payloads


class TestUsageIngest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        os.environ["CERTOPS_DB_PATH"] = self.db_path
        db.run_migrations(self.db_path)
        register_agent_token("test-usage-token", scope="telemetry_push")
        clear_received_payloads()

    def tearDown(self):
        db.close_db_connection(self.db_path)
        os.environ.pop("CERTOPS_DB_PATH", None)
        register_agent_token("test-usage-token", revoked=True)
        clear_received_payloads()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_usage_stored_on_ingest(self):
        from fastapi.testclient import TestClient
        client = TestClient(api.app)
        payload = {
            "agent_id": "test-agent-id",
            "agent_version": "2.5c",
            "timestamp": "2026-07-16T14:30:00Z",
            "items": [],
            "active_cert_count": 12,
            "renewals_succeeded": 150,
            "renewals_failed": 3,
            "connectors": {"vault": 2, "azure_kv": 1},
            "last_heartbeat": "2026-07-16T14:30:00Z",
        }
        resp = client.post(
            "/api/telemetry/ingest",
            json=payload,
            headers={"Authorization": "Bearer test-usage-token"},
        )
        self.assertEqual(resp.status_code, 202)
        # Check usage_metrics table
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT * FROM usage_metrics WHERE agent_id = ?",
            ("test-agent-id",),
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)


class TestUsageAPI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        os.environ["CERTOPS_DB_PATH"] = self.db_path
        os.environ["JWT_SECRET"] = "test-jwt-secret-usage"
        db.run_migrations(self.db_path)
        from datetime import datetime, timezone
        from auth import hash_password
        conn = db.get_db_connection(self.db_path)
        conn.execute(
            "INSERT INTO users (email, password_hash, role, created_at, tenant_id) VALUES (?, ?, ?, ?, ?)",
            ("admin@test.com", hash_password("testpass123"), "admin", datetime.now(timezone.utc).isoformat(), "default"),
        )
        conn.commit()
        conn.close()
        self.client = TestClient(api.app)

    def tearDown(self):
        db.close_db_connection(self.db_path)
        os.environ.pop("CERTOPS_DB_PATH", None)
        os.environ.pop("JWT_SECRET", None)
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _admin_token(self):
        from auth import _make_token
        conn = db.get_db_connection(self.db_path)
        row = conn.execute("SELECT id FROM users WHERE email = ?", ("admin@test.com",)).fetchone()
        conn.close()
        return _make_token(row[0], "admin@test.com", "admin", "default")

    def test_get_agent_usage(self):
        token = self._admin_token()
        db.insert_usage_metric(
            self.db_path, "agent-1", "default", 10, 50, 2, {"vault": 1}
        )
        resp = self.client.get(
            "/api/agents/agent-1/usage",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["agent_id"], "agent-1")
        self.assertEqual(len(data["records"]), 1)
        self.assertEqual(data["records"][0]["active_cert_count"], 10)

    def test_get_tenant_summary(self):
        token = self._admin_token()
        db.insert_usage_metric(
            self.db_path, "agent-1", "default", 10, 50, 2, {"vault": 1}
        )
        db.insert_usage_metric(
            self.db_path, "agent-2", "default", 20, 100, 5, {"azure_kv": 1}
        )
        resp = self.client.get(
            "/api/usage/summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total_agents"], 2)
        self.assertEqual(data["total_certs"], 30)
