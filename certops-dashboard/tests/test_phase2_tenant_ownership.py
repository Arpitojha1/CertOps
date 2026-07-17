"""
Phase 2: Tenant Ownership Validation Tests
Verifies that mutating endpoints enforce tenant ownership at the admin layer:
- Cross-tenant resource mutations between tenant admins are rejected (403)
- Tenant admins can mutate their own resources
- Global admin (tenant=default) can mutate any tenant's resources
- Viewers are blocked at RBAC layer (require_admin) regardless of tenant
"""

import os
import tempfile
import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))
_sibling = _root.parent / "certops-agent"
if _sibling.exists() and str(_sibling) not in sys.path:
    sys.path.insert(0, str(_sibling))

from src import db
from src.api import app
from src.auth import COOKIE_NAME


class TestPhase2TenantOwnership(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()

        if "CERTOPS_DB_PATH" in os.environ:
            self._orig_certops_db_path = os.environ["CERTOPS_DB_PATH"]
        else:
            self._orig_certops_db_path = None
        os.environ["CERTOPS_DB_PATH"] = self.db_path
        os.environ["DB_PATH"] = self.db_path

        db.reset_db_connections()
        db.run_migrations(self.db_path)

        self.ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

        # Global admin (tenant=default), tenant admins, and one viewer
        self.global_admin_email = f"gadmin_{self.ts}@certops.internal"
        self.admin_a_email = f"admin_a_{self.ts}@certops.internal"
        self.admin_b_email = f"admin_b_{self.ts}@certops.internal"
        self.viewer_a_email = f"viewer_a_{self.ts}@certops.internal"

        db.create_user(self.global_admin_email, "$2b$12$fakehash", role="admin", tenant_id="default")
        db.create_user(self.admin_a_email, "$2b$12$fakehash", role="admin", tenant_id="tenant_A")
        db.create_user(self.admin_b_email, "$2b$12$fakehash", role="admin", tenant_id="tenant_B")
        db.create_user(self.viewer_a_email, "$2b$12$fakehash", role="viewer", tenant_id="tenant_A")

        # Certs for each tenant
        self.cert_a = f"cert_a_{self.ts}"
        self.cert_b = f"cert_b_{self.ts}"
        db.upsert_certificate("hashicorp", self.cert_a, "2027-01-01T00:00:00Z", "a.example.com", tenant_id="tenant_A")
        db.upsert_certificate("hashicorp", self.cert_b, "2027-01-01T00:00:00Z", "b.example.com", tenant_id="tenant_B")

        # Groups for each tenant
        self.group_a = db.create_group("group_a", tenant_id="tenant_A")
        self.group_b = db.create_group("group_b", tenant_id="tenant_B")

        # Connectors for each tenant
        self.connector_a = f"conn_a_{self.ts}"
        self.connector_b = f"conn_b_{self.ts}"
        db.create_connector(self.connector_a, "acme", 30, tenant_id="tenant_A")
        db.create_connector(self.connector_b, "acme", 30, tenant_id="tenant_B")

        self.client = TestClient(app)

    def tearDown(self):
        db.close_db_connection(self.db_path)
        if self._orig_certops_db_path is not None:
            os.environ["CERTOPS_DB_PATH"] = self._orig_certops_db_path
        elif "CERTOPS_DB_PATH" in os.environ:
            del os.environ["CERTOPS_DB_PATH"]
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def _login_cookie(self, email: str) -> dict:
        from src import auth
        user = db.get_user_by_email(email)
        token = auth._make_token(user["id"], user["email"], user["role"], user["tenant_id"])
        return {COOKIE_NAME: token}

    # ── assign-group ────────────────────────────────────────────────────────

    def test_01_assign_group_cross_tenant_rejected(self):
        """Tenant-A admin cannot assign Tenant-B's cert."""
        cookie = self._login_cookie(self.admin_a_email)
        resp = self.client.post("/api/certificates/assign-group", json={
            "vault_source": "hashicorp", "name": self.cert_b, "group_id": self.group_a,
        }, cookies=cookie)
        self.assertEqual(resp.status_code, 403)

    def test_02_assign_group_own_tenant_allowed(self):
        """Tenant-A admin can assign their own cert to their own group."""
        cookie = self._login_cookie(self.admin_a_email)
        resp = self.client.post("/api/certificates/assign-group", json={
            "vault_source": "hashicorp", "name": self.cert_a, "group_id": self.group_a,
        }, cookies=cookie)
        self.assertEqual(resp.status_code, 200)

    def test_03_assign_group_global_admin_bypass(self):
        """Global admin can assign any tenant's cert."""
        cookie = self._login_cookie(self.global_admin_email)
        resp = self.client.post("/api/certificates/assign-group", json={
            "vault_source": "hashicorp", "name": self.cert_a, "group_id": self.group_a,
        }, cookies=cookie)
        self.assertEqual(resp.status_code, 200)

    def test_04_assign_group_viewer_blocked_by_rbac(self):
        """Viewer is blocked by require_admin regardless of tenant."""
        cookie = self._login_cookie(self.viewer_a_email)
        resp = self.client.post("/api/certificates/assign-group", json={
            "vault_source": "hashicorp", "name": self.cert_a, "group_id": self.group_a,
        }, cookies=cookie)
        self.assertEqual(resp.status_code, 403)

    # ── maintenance windows ─────────────────────────────────────────────────

    def test_05_maintenance_cross_tenant_rejected(self):
        """Tenant-A admin cannot create maintenance window for Tenant-B's group."""
        cookie = self._login_cookie(self.admin_a_email)
        resp = self.client.post("/api/maintenance-windows", json={
            "group_id": self.group_b, "start_time": "2027-06-01T00:00:00Z", "end_time": "2027-06-02T00:00:00Z",
        }, cookies=cookie)
        self.assertEqual(resp.status_code, 403)

    def test_06_maintenance_own_tenant_allowed(self):
        """Tenant-A admin can create maintenance window for their own group."""
        cookie = self._login_cookie(self.admin_a_email)
        resp = self.client.post("/api/maintenance-windows", json={
            "group_id": self.group_a, "start_time": "2027-06-01T00:00:00Z", "end_time": "2027-06-02T00:00:00Z",
        }, cookies=cookie)
        self.assertEqual(resp.status_code, 200)

    # ── notification policies ───────────────────────────────────────────────

    def test_07_notification_cross_tenant_rejected(self):
        """Tenant-A admin cannot create notification policy for Tenant-B's group."""
        cookie = self._login_cookie(self.admin_a_email)
        resp = self.client.post("/api/notification-policies", json={
            "group_id": self.group_b, "threshold_days": 30,
        }, cookies=cookie)
        self.assertEqual(resp.status_code, 403)

    def test_08_notification_own_tenant_allowed(self):
        """Tenant-A admin can create notification policy for their own group."""
        cookie = self._login_cookie(self.admin_a_email)
        resp = self.client.post("/api/notification-policies", json={
            "group_id": self.group_a, "threshold_days": 30,
        }, cookies=cookie)
        self.assertEqual(resp.status_code, 200)

    # ── confirm-reload ──────────────────────────────────────────────────────

    def test_09_confirm_reload_cross_tenant_rejected(self):
        """Tenant-A admin cannot confirm-reload on Tenant-B's connector."""
        cookie = self._login_cookie(self.admin_a_email)
        resp = self.client.post("/api/host/confirm-reload", json={
            "connector_name": self.connector_b, "cert_id": self.cert_b,
        }, cookies=cookie)
        self.assertEqual(resp.status_code, 403)

    def test_10_confirm_reload_own_tenant_allowed(self):
        """Tenant-A admin can confirm-reload on their own connector (may 500 if unreachable)."""
        cookie = self._login_cookie(self.admin_a_email)
        resp = self.client.post("/api/host/confirm-reload", json={
            "connector_name": self.connector_a, "cert_id": self.cert_a,
        }, cookies=cookie)
        self.assertNotEqual(resp.status_code, 403)

    def test_11_confirm_reload_global_admin_bypass(self):
        """Global admin can confirm-reload on any connector."""
        cookie = self._login_cookie(self.global_admin_email)
        resp = self.client.post("/api/host/confirm-reload", json={
            "connector_name": self.connector_a, "cert_id": self.cert_a,
        }, cookies=cookie)
        self.assertNotEqual(resp.status_code, 403)


if __name__ == "__main__":
    unittest.main()
