"""Tests for the agents table migration in db.py."""
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
