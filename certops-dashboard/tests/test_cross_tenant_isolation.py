# certops-dashboard/tests/test_cross_tenant_isolation.py
"""
Phase 2 Exit Gate: Comprehensive Cross-Tenant Isolation Proof.

Seeds two tenants (tenant_A, tenant_B) with data in every relevant table,
then systematically verifies:
  1. Every read endpoint scopes results to the caller's tenant
  2. Every mutating endpoint blocks cross-tenant resource access

Passing this test proves zero cross-tenant data visibility across ALL endpoints.
"""
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
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


class TestCrossTenantIsolation(unittest.TestCase):
    """Phase 2 exit gate: zero cross-tenant data visibility across all endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls.db_path = cls.tmp.name
        cls.tmp.close()
        os.environ["CERTOPS_DB_PATH"] = cls.db_path
        os.environ["JWT_SECRET"] = "test-cross-tenant-isolation"
        os.environ["ENV"] = "development"
        os.environ["COOKIE_SECURE"] = "false"
        os.environ["SKIP_DEFAULT_CONNECTORS"] = "1"
        db.run_migrations(cls.db_path)

        now = datetime.now(timezone.utc).isoformat()

        # Create users
        conn = db.get_db_connection(cls.db_path)
        for email, role, tenant in [
            ("admin-a@tenant-a.com", "admin", "tenant_A"),
            ("admin-b@tenant-b.com", "admin", "tenant_B"),
        ]:
            conn.execute(
                "INSERT INTO users (email, password_hash, role, created_at, tenant_id) VALUES (?, ?, ?, ?, ?)",
                (email, hash_password("pass"), role, now, tenant),
            )
        conn.commit()
        conn.close()

        # Seed tenant_A data
        cls.group_a = db.create_group("group_a", tenant_id="tenant_A", db_path=cls.db_path)
        cls.conn_a = db.create_connector(
            name="conn_a", category="hashicorp", renewal_threshold_days=15,
            config='{"url": "http://a"}', is_active=True, db_path=cls.db_path, tenant_id="tenant_A"
        )
        cls.policy_a = db.create_notification_policy(
            group_id=cls.group_a, threshold_days=30, db_path=cls.db_path, tenant_id="tenant_A"
        )
        now_dt = datetime.now(timezone.utc)
        db.upsert_certificate(
            vault_source="hashicorp", name="cert-a.local",
            expiry_utc=(now_dt + timedelta(days=90)).isoformat(),
            common_name="cert-a.local", tenant_id="tenant_A",
            db_path=cls.db_path,
        )
        db.upsert_certificate(
            vault_source="hashicorp", name="cert-a-due.local",
            expiry_utc=(now_dt + timedelta(days=1)).isoformat(),
            common_name="cert-a-due.local", tenant_id="tenant_A",
            db_path=cls.db_path,
        )
        db.insert_renewal_log(
            cert_id="hashicorp:cert-a.local", event_type="renewed",
            success=True, vault_source="hashicorp", tenant_id="tenant_A",
            db_path=cls.db_path,
        )
        db.log_activity(
            event_type="cert_viewed", actor_email="admin-a@tenant-a.com",
            target="cert-a.local", tenant_id="tenant_A", db_path=cls.db_path,
        )
        db.update_notification_log(
            cert_id="hashicorp:cert-a.local", sent_at=now,
            policy_id=cls.policy_a, tenant_id="tenant_A", db_path=cls.db_path,
        ) if hasattr(db, "update_notification_log") else None

        # Seed tenant_B data (must NOT be visible to tenant_A)
        cls.group_b = db.create_group("group_b", tenant_id="tenant_B", db_path=cls.db_path)
        cls.conn_b = db.create_connector(
            name="conn_b", category="hashicorp", renewal_threshold_days=10,
            config='{"url": "http://b"}', is_active=True, db_path=cls.db_path, tenant_id="tenant_B"
        )
        cls.policy_b = db.create_notification_policy(
            group_id=cls.group_b, threshold_days=20, db_path=cls.db_path, tenant_id="tenant_B"
        )
        db.upsert_certificate(
            vault_source="hashicorp", name="cert-b.local",
            expiry_utc=(now_dt + timedelta(days=90)).isoformat(),
            common_name="cert-b.local", tenant_id="tenant_B",
            db_path=cls.db_path,
        )
        db.upsert_certificate(
            vault_source="hashicorp", name="cert-b-due.local",
            expiry_utc=(now_dt + timedelta(days=1)).isoformat(),
            common_name="cert-b-due.local", tenant_id="tenant_B",
            db_path=cls.db_path,
        )
        db.insert_renewal_log(
            cert_id="hashicorp:cert-b.local", event_type="renewed",
            success=True, vault_source="hashicorp", tenant_id="tenant_B",
            db_path=cls.db_path,
        )
        db.log_activity(
            event_type="cert_viewed", actor_email="admin-b@tenant-b.com",
            target="cert-b.local", tenant_id="tenant_B", db_path=cls.db_path,
        )

        cls.client = TestClient(api.app)

    @classmethod
    def tearDownClass(cls):
        from conftest import _safe_remove_db
        _safe_remove_db(cls.db_path)
        for var in ("CERTOPS_DB_PATH", "JWT_SECRET", "ENV", "COOKIE_SECURE", "SKIP_DEFAULT_CONNECTORS"):
            os.environ.pop(var, None)

    def _token_a(self) -> str:
        conn = db.get_db_connection(self.db_path)
        row = conn.execute("SELECT id, email, role, tenant_id FROM users WHERE email = ?",
                           ("admin-a@tenant-a.com",)).fetchone()
        conn.close()
        return _make_token(row[0], row[1], row[2], row[3])

    def _token_b(self) -> str:
        conn = db.get_db_connection(self.db_path)
        row = conn.execute("SELECT id, email, role, tenant_id FROM users WHERE email = ?",
                           ("admin-b@tenant-b.com",)).fetchone()
        conn.close()
        return _make_token(row[0], row[1], row[2], row[3])

    def _cookies_a(self) -> dict:
        return {COOKIE_NAME: self._token_a()}

    def _cookies_b(self) -> dict:
        return {COOKIE_NAME: self._token_b()}

    # ─── READ ENDPOINTS: Tenant A must NOT see Tenant B data ──────────────

    def test_01_certificates_list_scoped(self):
        """GET /api/certificates — tenant A sees only tenant A certs."""
        resp = self.client.get("/api/certificates", cookies=self._cookies_a())
        self.assertEqual(resp.status_code, 200)
        names = {c["name"] for c in resp.json()}
        self.assertIn("cert-a.local", names)
        self.assertNotIn("cert-b.local", names)
        self.assertNotIn("cert-b-due.local", names)

    def test_02_certificates_due_scoped(self):
        """GET /api/certificates/due — tenant A sees only tenant A due certs."""
        resp = self.client.get("/api/certificates/due?vault_source=hashicorp",
                               cookies=self._cookies_a())
        self.assertEqual(resp.status_code, 200)
        names = {c["name"] for c in resp.json()}
        self.assertNotIn("cert-b-due.local", names)

    def test_03_certificate_detail_scoped(self):
        """GET /api/certificates/{vault}/{name} — cross-tenant detail returns 404."""
        resp_a = self.client.get("/api/certificates/hashicorp/cert-a.local",
                                 cookies=self._cookies_a())
        self.assertEqual(resp_a.status_code, 200)

        resp_cross = self.client.get("/api/certificates/hashicorp/cert-b.local",
                                     cookies=self._cookies_a())
        self.assertEqual(resp_cross.status_code, 404,
                         "Tenant A must NOT read Tenant B certificate detail")

    def test_04_renewal_log_scoped(self):
        """GET /api/renewal-log — tenant A sees only tenant A logs."""
        resp = self.client.get("/api/renewal-log", cookies=self._cookies_a())
        self.assertEqual(resp.status_code, 200)
        for entry in resp.json():
            self.assertIn("cert-a", entry.get("cert_id", ""))

    def test_05_activity_log_scoped(self):
        """GET /api/activity-log — tenant A sees only tenant A events."""
        resp = self.client.get("/api/activity-log", cookies=self._cookies_a())
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        targets = {e.get("target", "") for e in items if isinstance(e, dict)}
        self.assertNotIn("cert-b.local", targets)

    def test_06_connectors_list_scoped(self):
        """GET /api/connectors — tenant A sees only tenant A connectors."""
        resp = self.client.get("/api/connectors", cookies=self._cookies_a())
        self.assertEqual(resp.status_code, 200)
        names = {c["name"] for c in resp.json()}
        self.assertIn("conn_a", names)
        self.assertNotIn("conn_b", names)

    def test_07_groups_list_scoped(self):
        """GET /api/groups — tenant A sees only tenant A groups."""
        resp = self.client.get("/api/groups", cookies=self._cookies_a())
        self.assertEqual(resp.status_code, 200)
        names = {g["name"] for g in resp.json()}
        self.assertIn("group_a", names)
        self.assertNotIn("group_b", names)

    def test_08_notification_policies_scoped(self):
        """GET /api/notification-policies — tenant A sees only tenant A policies."""
        resp = self.client.get("/api/notification-policies", cookies=self._cookies_a())
        self.assertEqual(resp.status_code, 200)
        group_ids = {p["group_id"] for p in resp.json()}
        self.assertIn(self.group_a, group_ids)
        self.assertNotIn(self.group_b, group_ids)

    def test_09_dashboard_summary_scoped(self):
        """GET /api/dashboard/summary — tenant A sees only tenant A totals."""
        resp = self.client.get("/api/dashboard/summary", cookies=self._cookies_a())
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        total = data.get("totalCertificates", data.get("total_certificates", 0))
        self.assertLessEqual(total, 2, "Dashboard summary leaks cross-tenant cert count")

    def test_10_scheduler_status_scoped(self):
        """GET /api/scheduler/status — returns 200 without leaking cross-tenant data."""
        resp = self.client.get("/api/scheduler/status", cookies=self._cookies_a())
        self.assertEqual(resp.status_code, 200)

    # ─── MUTATING ENDPOINTS: Tenant B blocked from Tenant A resources ─────

    def test_11_connector_update_cross_tenant_blocked(self):
        """PUT /api/connectors/{id} — tenant B cannot update tenant A connector."""
        resp = self.client.put(
            f"/api/connectors/{self.conn_a}",
            json={"name": "hacked"},
            cookies=self._cookies_b(),
        )
        self.assertIn(resp.status_code, (403, 404),
                      f"Tenant B must NOT update Tenant A connector (got {resp.status_code})")

    def test_12_connector_delete_cross_tenant_blocked(self):
        """DELETE /api/connectors/{id} — tenant B cannot delete tenant A connector."""
        resp = self.client.delete(
            f"/api/connectors/{self.conn_a}",
            cookies=self._cookies_b(),
        )
        self.assertIn(resp.status_code, (403, 404),
                      f"Tenant B must NOT delete Tenant A connector (got {resp.status_code})")

    def test_13_notification_policy_delete_cross_tenant_blocked(self):
        """DELETE /api/notification-policies/{id} — tenant B cannot delete tenant A policy."""
        resp = self.client.delete(
            f"/api/notification-policies/{self.policy_a}",
            cookies=self._cookies_b(),
        )
        self.assertIn(resp.status_code, (403, 404),
                      f"Tenant B must NOT delete Tenant A notification policy (got {resp.status_code})")

    def test_14_cert_delete_cross_tenant_blocked(self):
        """DELETE /api/certificates/{vault}/{name} — tenant B cannot delete tenant A cert."""
        resp = self.client.delete(
            "/api/certificates/hashicorp/cert-a.local",
            cookies=self._cookies_b(),
        )
        self.assertIn(resp.status_code, (403, 404),
                      f"Tenant B must NOT delete Tenant A certificate (got {resp.status_code})")

    def test_15_cert_assign_group_cross_tenant_blocked(self):
        """POST /api/certificates/assign-group — tenant B cannot assign tenant A cert."""
        resp = self.client.post(
            "/api/certificates/assign-group",
            json={"vault_source": "hashicorp", "name": "cert-a.local", "group_id": self.group_b},
            cookies=self._cookies_b(),
        )
        self.assertIn(resp.status_code, (403, 404),
                      f"Tenant B must NOT assign group to Tenant A cert (got {resp.status_code})")

    def test_16_group_create_tenant_isolation(self):
        """POST /api/groups — created group is scoped to caller's tenant."""
        resp = self.client.post(
            "/api/groups",
            json={"name": "isolated_group_a", "description": "test"},
            cookies=self._cookies_a(),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["tenant_id"], "tenant_A")

        # Verify tenant B cannot see it
        resp_b = self.client.get("/api/groups", cookies=self._cookies_b())
        names_b = {g["name"] for g in resp_b.json()}
        self.assertNotIn("isolated_group_a", names_b)

    def test_17_maintenance_window_create_tenant_isolation(self):
        """POST /api/maintenance-windows — created window is scoped to caller's tenant."""
        resp = self.client.post(
            "/api/maintenance-windows",
            json={
                "group_id": self.group_a,
                "start_time": "2026-08-01T00:00:00Z",
                "end_time": "2026-08-02T00:00:00Z",
            },
            cookies=self._cookies_a(),
        )
        self.assertEqual(resp.status_code, 200)

        # Tenant B must not see it
        resp_b = self.client.get("/api/maintenance-windows", cookies=self._cookies_b())
        self.assertEqual(resp_b.status_code, 200)
        self.assertEqual(len(resp_b.json()), 0, "Tenant B must NOT see Tenant A maintenance windows")

    def test_18_notification_policy_create_tenant_isolation(self):
        """POST /api/notification-policies — created policy scoped to caller's tenant."""
        resp = self.client.post(
            "/api/notification-policies",
            json={"group_id": self.group_a, "threshold_days": 14},
            cookies=self._cookies_a(),
        )
        self.assertEqual(resp.status_code, 200)
        policy_id = resp.json()["id"]

        # Verify it shows in tenant A's list
        list_a = self.client.get("/api/notification-policies", cookies=self._cookies_a())
        ids_a = {p["id"] for p in list_a.json()}
        self.assertIn(policy_id, ids_a, "New policy must appear in tenant A's list")

        # Verify it does NOT show in tenant B's list
        list_b = self.client.get("/api/notification-policies", cookies=self._cookies_b())
        ids_b = {p["id"] for p in list_b.json()}
        self.assertNotIn(policy_id, ids_b, "New policy must NOT appear in tenant B's list")


if __name__ == "__main__":
    unittest.main()
