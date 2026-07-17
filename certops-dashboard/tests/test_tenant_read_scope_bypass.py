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
from auth import hash_password, _make_token, COOKIE_NAME


class TestTenantReadScopeBypass(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        os.environ["CERTOPS_DB_PATH"] = self.db_path
        os.environ["JWT_SECRET"] = "test-tenant-read-bypass-secret"
        db.run_migrations(self.db_path)

        conn = db.get_db_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        # Create users: global super-admin and tenant_A admin
        conn.execute(
            "INSERT INTO users (email, password_hash, role, created_at, tenant_id) VALUES (?, ?, ?, ?, ?)",
            ("super@default.com", hash_password("pass"), "admin", now, "default"),
        )
        conn.execute(
            "INSERT INTO users (email, password_hash, role, created_at, tenant_id) VALUES (?, ?, ?, ?, ?)",
            ("admin@tenant-a.com", hash_password("pass"), "admin", now, "tenant_A"),
        )
        # Create certificates: one in tenant_A, one in tenant_B
        conn.execute(
            "INSERT INTO certificates (vault_source, name, expiry_utc, tenant_id) VALUES (?, ?, ?, ?)",
            ("vault_a", "cert-a.local", now, "tenant_A"),
        )
        conn.execute(
            "INSERT INTO certificates (vault_source, name, expiry_utc, tenant_id) VALUES (?, ?, ?, ?)",
            ("vault_b", "cert-b.local", now, "tenant_B"),
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

    def _get_token(self, email: str, role: str, tenant_id: str) -> str:
        conn = db.get_db_connection(self.db_path)
        row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()
        return _make_token(row[0], email, role, tenant_id)

    def test_global_superadmin_reads_all_certificates(self):
        token = self._get_token("super@default.com", "admin", "default")
        self.client.cookies.set(COOKIE_NAME, token)
        resp = self.client.get("/api/certificates")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        names = {c["name"] for c in data}
        self.assertIn("cert-a.local", names)
        self.assertIn("cert-b.local", names)

    def test_tenant_admin_cannot_read_other_tenant_certificates(self):
        token = self._get_token("admin@tenant-a.com", "admin", "tenant_A")
        self.client.cookies.set(COOKIE_NAME, token)
        resp = self.client.get("/api/certificates")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        names = {c["name"] for c in data}
        self.assertIn("cert-a.local", names)
        # Tenant A admin must NOT see cert-b.local from Tenant B
        self.assertNotIn("cert-b.local", names, "Tenant admin bypassed read isolation and viewed another tenant's certificate!")


if __name__ == "__main__":
    unittest.main()
