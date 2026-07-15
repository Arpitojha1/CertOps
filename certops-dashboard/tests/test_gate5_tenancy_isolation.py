"""
Verification test for Phase 0 Part D: Stage 5 follow-up RBAC / Tenancy isolation.
Asserts that Viewer A cannot read or enumerate Certificate B belonging to Viewer B,
and that Admin can see both across all scopes.
"""

import json
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


class TestGate5TenancyIsolation(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()
        os.environ["DB_PATH"] = self.db_path
        db.run_migrations(self.db_path)

        # Create Admin, Viewer A (tenant_A), and Viewer B (tenant_B)
        db.create_user("admin@certops.internal", "$2b$12$fakehash", role="admin", tenant_id="default")
        db.create_user("viewer_a@certops.internal", "$2b$12$fakehash", role="viewer", tenant_id="tenant_A")
        db.create_user("viewer_b@certops.internal", "$2b$12$fakehash", role="viewer", tenant_id="tenant_B")

        # Upsert Certificate A scoped to tenant_A
        db.upsert_certificate(
            vault_source="hashicorp",
            name="cert-A",
            expiry_utc="2027-01-01T00:00:00Z",
            common_name="a.example.com",
            tenant_id="tenant_A",
        )

        # Upsert Certificate B scoped to tenant_B
        db.upsert_certificate(
            vault_source="hashicorp",
            name="cert-B",
            expiry_utc="2027-01-01T00:00:00Z",
            common_name="b.example.com",
            tenant_id="tenant_B",
        )

        self.client = TestClient(app)

    def tearDown(self):
        db.close_db_connection(self.db_path)
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def _login_cookie(self, email: str) -> dict:
        # Bypass password check for hermetic test speed by directly constructing token via auth
        from src import auth
        user = db.get_user_by_email(email)
        token = auth._make_token(user["id"], user["email"], user["role"], user["tenant_id"])
        return {COOKIE_NAME: token}

    def test_tenancy_isolation_list_and_get(self):
        print("\n=== TEST TENANCY ISOLATION: Viewer A vs Viewer B vs Admin ===")

        cookie_a = self._login_cookie("viewer_a@certops.internal")
        cookie_b = self._login_cookie("viewer_b@certops.internal")
        cookie_admin = self._login_cookie("admin@certops.internal")

        # 1. Viewer A lists certificates
        resp_a = self.client.get("/api/certificates", cookies=cookie_a)
        self.assertEqual(resp_a.status_code, 200)
        viewer_A_results = resp_a.json()

        # 2. Viewer B lists certificates
        resp_b = self.client.get("/api/certificates", cookies=cookie_b)
        self.assertEqual(resp_b.status_code, 200)
        viewer_B_results = resp_b.json()

        # 3. Admin lists certificates
        resp_admin = self.client.get("/api/certificates", cookies=cookie_admin)
        self.assertEqual(resp_admin.status_code, 200)
        admin_results = resp_admin.json()

        print(f"[TENANCY RESULT] len(viewer_A_results) == {len(viewer_A_results)}")
        print(f"[TENANCY RESULT] len(viewer_B_results) == {len(viewer_B_results)}")
        print(f"[TENANCY RESULT] len(admin_results) == {len(admin_results)}")

        self.assertEqual(len(viewer_A_results), 1, "Viewer A must see exactly 1 certificate")
        self.assertEqual(viewer_A_results[0]["name"], "cert-A")

        self.assertEqual(len(viewer_B_results), 1, "Viewer B must see exactly 1 certificate")
        self.assertEqual(viewer_B_results[0]["name"], "cert-B")

        self.assertEqual(len(admin_results), 2, "Admin must see both certificates across all tenants")
        admin_cert_names = {c["name"] for c in admin_results}
        self.assertEqual(admin_cert_names, {"cert-A", "cert-B"})

        # 4. Verify direct GET access control
        resp_get_b_by_a = self.client.get("/api/certificates/hashicorp/cert-B", cookies=cookie_a)
        self.assertEqual(resp_get_b_by_a.status_code, 404, "Viewer A accessing cert-B must receive 404")

        resp_get_a_by_b = self.client.get("/api/certificates/hashicorp/cert-A", cookies=cookie_b)
        self.assertEqual(resp_get_a_by_b.status_code, 404, "Viewer B accessing cert-A must receive 404")

        print("[TENANCY DIRECT ACCESS CHECK] Viewer A -> cert-B returned 404; Viewer B -> cert-A returned 404")
        print("[RESULT] PASSED: RBAC / Tenancy isolation enforced at query layer")


if __name__ == "__main__":
    unittest.main()
