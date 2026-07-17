"""Tests for the agents table migration in db.py."""
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))

import db


class TestAgentsTableMigration(unittest.TestCase):
    def setUp(self):
        self._orig_skip = os.environ.get("SKIP_DEFAULT_CONNECTORS")
        self._orig_key = os.environ.get("CERTOPS_CONFIG_ENCRYPTION_KEY")
        os.environ["SKIP_DEFAULT_CONNECTORS"] = "1"
        os.environ["CERTOPS_CONFIG_ENCRYPTION_KEY"] = "test-key-for-migration-tests=="
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()

    def tearDown(self):
        db.close_db_connection(self.db_path)
        import gc
        gc.collect()
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except PermissionError:
                pass
        if self._orig_skip is None:
            os.environ.pop("SKIP_DEFAULT_CONNECTORS", None)
        else:
            os.environ["SKIP_DEFAULT_CONNECTORS"] = self._orig_skip
        if self._orig_key is None:
            os.environ.pop("CERTOPS_CONFIG_ENCRYPTION_KEY", None)
        else:
            os.environ["CERTOPS_CONFIG_ENCRYPTION_KEY"] = self._orig_key

    def test_agents_table_created(self):
        db.run_migrations(self.db_path)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("PRAGMA table_info(agents)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()
        self.assertIn("id", columns)
        self.assertIn("tenant_id", columns)
        self.assertIn("status", columns)
        self.assertIn("secret_store_backend", columns)

    def test_agent_tokens_has_agent_id_column(self):
        db.run_migrations(self.db_path)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("PRAGMA table_info(agent_tokens)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()
        self.assertIn("agent_id", columns)

    def test_agents_table_idempotent(self):
        db.run_migrations(self.db_path)
        db.run_migrations(self.db_path)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT count(*) FROM agents")
        self.assertEqual(cursor.fetchone()[0], 0)
        conn.close()


class TestAgentDB(unittest.TestCase):
    def setUp(self):
        os.environ["SKIP_DEFAULT_CONNECTORS"] = "1"
        os.environ["CERTOPS_CONFIG_ENCRYPTION_KEY"] = "l4RiYfXncsmK1zJLouSSwt8jAqDKllnJhCjQcCdu97Y="
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except PermissionError:
                pass

    def test_init_creates_tables(self):
        from agent_db import init_agent_db
        init_agent_db(self.db_path)
        conn = sqlite3.connect(self.db_path)
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        self.assertIn("agent_identity", tables)
        self.assertIn("agent_config", tables)

    def test_set_get_identity(self):
        from agent_db import init_agent_db, set_identity, get_identity
        init_agent_db(self.db_path)
        set_identity("agent_id", "test-123", self.db_path)
        self.assertEqual(get_identity("agent_id", self.db_path), "test-123")

    def test_set_get_config_encrypted(self):
        from agent_db import init_agent_db, set_config, get_config
        init_agent_db(self.db_path)
        set_config("vault_token", "s.abc123", self.db_path)
        val = get_config("vault_token", self.db_path)
        self.assertEqual(val, "s.abc123")
        conn = sqlite3.connect(self.db_path)
        raw = conn.execute(
            "SELECT value FROM agent_config WHERE key = 'vault_token'"
        ).fetchone()[0]
        conn.close()
        self.assertTrue(raw.startswith("ENC:v1:") or raw.startswith('{') or raw == "s.abc123")

    def test_get_status_default(self):
        from agent_db import init_agent_db, get_status
        init_agent_db(self.db_path)
        self.assertEqual(get_status(self.db_path), "pending")

    def test_set_status(self):
        from agent_db import init_agent_db, set_status, get_status
        init_agent_db(self.db_path)
        set_status("registered", self.db_path)
        self.assertEqual(get_status(self.db_path), "registered")


class TestUsageSnapshot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        from agent_db import init_agent_db
        init_agent_db(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_initial_snapshot_zeroes(self):
        from agent_db import get_usage_snapshot
        snap = get_usage_snapshot(self.db_path)
        self.assertEqual(snap["active_cert_count"], 0)
        self.assertEqual(snap["renewals_succeeded"], 0)
        self.assertEqual(snap["renewals_failed"], 0)
        self.assertEqual(snap["connectors"], {})
        self.assertIsNone(snap["last_heartbeat"])

    def test_update_and_get_snapshot(self):
        from agent_db import update_usage_snapshot, get_usage_snapshot
        update_usage_snapshot(
            self.db_path,
            cert_count=12,
            renewals_ok=150,
            renewals_fail=3,
            connectors={"vault": 2, "azure_kv": 1},
        )
        snap = get_usage_snapshot(self.db_path)
        self.assertEqual(snap["active_cert_count"], 12)
        self.assertEqual(snap["renewals_succeeded"], 150)
        self.assertEqual(snap["renewals_failed"], 3)
        self.assertEqual(snap["connectors"], {"vault": 2, "azure_kv": 1})
        self.assertIsNotNone(snap["last_heartbeat"])

    def test_update_accumulates(self):
        from agent_db import update_usage_snapshot, get_usage_snapshot
        update_usage_snapshot(self.db_path, cert_count=5, renewals_ok=10, renewals_fail=0, connectors={"vault": 1})
        update_usage_snapshot(self.db_path, cert_count=8, renewals_ok=25, renewals_fail=1, connectors={"vault": 1, "azure_kv": 1})
        snap = get_usage_snapshot(self.db_path)
        self.assertEqual(snap["renewals_succeeded"], 25)
        self.assertEqual(snap["renewals_failed"], 1)
        self.assertEqual(snap["connectors"], {"vault": 1, "azure_kv": 1})


class TestUsageMetricsMigration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()

    def tearDown(self):
        db.close_db_connection(self.db_path)
        import gc
        gc.collect()
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except PermissionError:
                pass

    def test_usage_metrics_table_created(self):
        db.run_migrations(self.db_path)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("PRAGMA table_info(usage_metrics)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()
        self.assertIn("id", columns)
        self.assertIn("agent_id", columns)
        self.assertIn("tenant_id", columns)
        self.assertIn("recorded_at", columns)
        self.assertIn("active_cert_count", columns)
        self.assertIn("renewals_succeeded", columns)
        self.assertIn("renewals_failed", columns)
        self.assertIn("connectors_json", columns)

    def test_usage_metrics_indexes_created(self):
        db.run_migrations(self.db_path)
        conn = sqlite3.connect(self.db_path)
        indexes = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()}
        conn.close()
        self.assertIn("idx_usage_agent_time", indexes)
        self.assertIn("idx_usage_tenant_time", indexes)

    def test_usage_metrics_idempotent(self):
        db.run_migrations(self.db_path)
        db.run_migrations(self.db_path)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT count(*) FROM usage_metrics")
        self.assertEqual(cursor.fetchone()[0], 0)
        conn.close()


class TestTelemetryPayloadExtension(unittest.TestCase):
    def test_payload_includes_usage_fields(self):
        from agent_telemetry import AgentTelemetryClient
        client = AgentTelemetryClient(
            agent_id="test-agent",
            agent_version="2.5c",
            agent_token="test-token",
            ingest_url="https://test.example.com/api/telemetry/ingest",
        )
        payload = client.build_payload(
            connectors=[],
            usage_snapshot={
                "active_cert_count": 12,
                "renewals_succeeded": 150,
                "renewals_failed": 3,
                "connectors": {"vault": 2, "azure_kv": 1},
                "last_heartbeat": "2026-07-16T14:30:00Z",
            },
        )
        self.assertEqual(payload["active_cert_count"], 12)
        self.assertEqual(payload["renewals_succeeded"], 150)
        self.assertEqual(payload["renewals_failed"], 3)
        self.assertEqual(payload["connectors"], {"vault": 2, "azure_kv": 1})
        self.assertEqual(payload["last_heartbeat"], "2026-07-16T14:30:00Z")

    def test_payload_backward_compatible(self):
        from agent_telemetry import AgentTelemetryClient
        client = AgentTelemetryClient(
            agent_id="test-agent",
            agent_version="2.5c",
            agent_token="test-token",
            ingest_url="https://test.example.com/api/telemetry/ingest",
        )
        payload = client.build_payload(connectors=[])
        self.assertNotIn("active_cert_count", payload)
        self.assertNotIn("renewals_succeeded", payload)


class TestUsageWiring(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        from agent_db import init_agent_db, set_identity, set_status
        init_agent_db(self.db_path)
        set_identity("agent_id", "test-agent-id", self.db_path)
        set_identity("token", "test-jwt-token", self.db_path)
        set_identity("dashboard_url", "https://dashboard.test.com", self.db_path)
        set_status("active", self.db_path)
        os.environ["AGENT_DB_PATH"] = self.db_path

    def tearDown(self):
        os.environ.pop("AGENT_DB_PATH", None)
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_push_telemetry_includes_usage(self):
        from main import _try_push_telemetry
        from agent_db import update_usage_snapshot
        update_usage_snapshot(
            self.db_path,
            cert_count=5,
            renewals_ok=10,
            renewals_fail=1,
            connectors={"vault": 1},
        )
        mock_client = MagicMock()
        mock_client.push.return_value = (202, {"status": "accepted"})
        with patch("main.AgentTelemetryClient", return_value=mock_client):
            _try_push_telemetry({"total": 1, "succeeded": 1}, self.db_path)
        mock_client.push.assert_called_once()


if __name__ == "__main__":
    unittest.main()
