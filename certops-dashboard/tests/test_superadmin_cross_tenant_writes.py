# certops-dashboard/tests/test_superadmin_cross_tenant_writes.py
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
import sys

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))
_sibling = _root.parent / "certops-agent"
if _sibling.exists() and str(_sibling) not in sys.path:
    sys.path.insert(0, str(_sibling))

from fastapi.testclient import TestClient
from src import api, db
from auth import hash_password, _make_token


class TestSuperAdminCrossTenantWrites(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        os.environ["CERTOPS_DB_PATH"] = self.db_path
        os.environ["JWT_SECRET"] = "test-superadmin-writes-secret"
        db.run_migrations(self.db_path)

        conn = db.get_db_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO users (email, password_hash, role, created_at, tenant_id) VALUES (?, ?, ?, ?, ?)",
            ("super@default.com", hash_password("pass"), "admin", now, "default"),
        )
        conn.execute(
            "INSERT INTO users (email, password_hash, role, created_at, tenant_id) VALUES (?, ?, ?, ?, ?)",
            ("admin@tenant-a.com", hash_password("pass"), "admin", now, "tenant_A"),
        )
        conn.execute(
            "INSERT INTO users (email, password_hash, role, created_at, tenant_id) VALUES (?, ?, ?, ?, ?)",
            ("admin@tenant-b.com", hash_password("pass"), "admin", now, "tenant_B"),
        )
        conn.commit()
        conn.close()

        # Create connector and policy belonging to tenant_A
        self.group_a_id = db.create_group("group_a", tenant_id="tenant_A", db_path=self.db_path)
        self.conn_a_id = db.create_connector(
            name="conn_a", category="hashicorp", renewal_threshold_days=15,
            config='{"url": "http://a"}', is_active=True, db_path=self.db_path, tenant_id="tenant_A"
        )
        self.policy_a_id = db.create_notification_policy(
            group_id=self.group_a_id, threshold_days=30, db_path=self.db_path, tenant_id="tenant_A"
        )
        self.client = TestClient(api.app)

    def tearDown(self):
        db.close_db_connection(self.db_path)
        os.environ.pop("CERTOPS_DB_PATH", None)
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _get_token(self, email: str, role: str, tenant_id: str) -> str:
        conn = db.get_db_connection(self.db_path)
        row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()
        return _make_token(row[0], email, role, tenant_id)

    def test_superadmin_can_update_and_delete_cross_tenant_resources(self):
        token = self._get_token("super@default.com", "admin", "default")
        cookies = {"certops_token": token}

        # Superadmin updates connector in tenant_A
        resp = self.client.put(
            f"/api/connectors/{self.conn_a_id}",
            json={"name": "conn_a_updated", "renewal_threshold_days": 20},
            cookies=cookies,
        )
        self.assertEqual(resp.status_code, 200, f"Superadmin denied update: {resp.text}")
        self.assertEqual(resp.json()["name"], "conn_a_updated")

        # Superadmin deletes notification policy in tenant_A
        resp = self.client.delete(f"/api/notification-policies/{self.policy_a_id}", cookies=cookies)
        self.assertEqual(resp.status_code, 200, f"Superadmin denied delete: {resp.text}")

        # Superadmin deletes connector in tenant_A
        resp = self.client.delete(f"/api/connectors/{self.conn_a_id}", cookies=cookies)
        self.assertEqual(resp.status_code, 200, f"Superadmin denied connector delete: {resp.text}")

    def test_tenant_admin_cannot_update_or_delete_other_tenant_resources(self):
        token = self._get_token("admin@tenant-b.com", "admin", "tenant_B")
        cookies = {"certops_token": token}

        resp = self.client.put(
            f"/api/connectors/{self.conn_a_id}",
            json={"name": "hacked"},
            cookies=cookies,
        )
        self.assertEqual(resp.status_code, 403)

        resp = self.client.delete(f"/api/connectors/{self.conn_a_id}", cookies=cookies)
        self.assertEqual(resp.status_code, 403)

        resp = self.client.delete(f"/api/notification-policies/{self.policy_a_id}", cookies=cookies)
        self.assertEqual(resp.status_code, 403)


if __name__ == "__main__":
    unittest.main()
