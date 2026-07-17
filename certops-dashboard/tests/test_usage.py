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
