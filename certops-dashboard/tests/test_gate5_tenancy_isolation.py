"""
Verification test for Phase 0 Part D: Stage 5 follow-up RBAC / Tenancy isolation.
Asserts that Viewer A cannot read or enumerate Certificate B belonging to Viewer B,
and that Admin can see both across all scopes.

Fixes applied:
- Clear CERTOPS_DB_PATH (which shadows DB_PATH) to ensure temp DB isolation
- Reset connection pool in setUp() to avoid stale connections
- Use timestamped emails/certificates for guaranteed uniqueness across parallel runs
- Added zero-overlap assertions that catch tenant-scoped crossing holes
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

        # CRITICAL: _normalize_db_path() checks CERTOPS_DB_PATH first, then DB_PATH.
        # .env sets CERTOPS_DB_PATH=c:\Users\Arpit\certOps\certops.db via load_dotenv().
        # We must clear it so DB_PATH is actually respected.
        if "CERTOPS_DB_PATH" in os.environ:
            self._orig_certops_db_path = os.environ["CERTOPS_DB_PATH"]
        else:
            self._orig_certops_db_path = None
        os.environ["CERTOPS_DB_PATH"] = self.db_path
        os.environ["DB_PATH"] = self.db_path

        db.reset_db_connections()
        db.run_migrations(self.db_path)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

        admin_email = f"admin_{timestamp}@certops.internal"
        viewer_a_email = f"viewer_a_{timestamp}@certops.internal"
        viewer_b_email = f"viewer_b_{timestamp}@certops.internal"

        db.create_user(admin_email, "$2b$12$fakehash", role="admin", tenant_id="default")
        db.create_user(viewer_a_email, "$2b$12$fakehash", role="viewer", tenant_id="tenant_A")
        db.create_user(viewer_b_email, "$2b$12$fakehash", role="viewer", tenant_id="tenant_B")

        db.upsert_certificate(
            vault_source="hashicorp",
            name=f"tenant_a_cert_1_{timestamp}",
            expiry_utc="2027-01-01T00:00:00Z",
            common_name="a.example.com",
            tenant_id="tenant_A",
        )

        db.upsert_certificate(
            vault_source="hashicorp",
            name=f"tenant_b_cert_1_{timestamp}",
            expiry_utc="2027-01-01T00:00:00Z",
            common_name="b.example.com",
            tenant_id="tenant_B",
        )

        db.upsert_certificate(
            vault_source="hashicorp",
            name=f"tenant_a_cert_2_{timestamp}",
            expiry_utc="2027-01-01T00:00:00Z",
            common_name="extra.example.com",
            tenant_id="tenant_A",
        )

        db.upsert_certificate(
            vault_source="hashicorp",
            name=f"tenant_b_cert_2_{timestamp}",
            expiry_utc="2027-01-01T00:00:00Z",
            common_name="extra2.example.com",
            tenant_id="tenant_B",
        )

        self.client = TestClient(app)

    def tearDown(self):
        db.close_db_connection(self.db_path)
        # Restore original env vars
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

    def test_tenancy_isolation_list_and_get(self):
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

        tenant_a_cert_1 = f"tenant_a_cert_1_{timestamp}"
        tenant_a_cert_2 = f"tenant_a_cert_2_{timestamp}"
        tenant_b_cert_1 = f"tenant_b_cert_1_{timestamp}"
        tenant_b_cert_2 = f"tenant_b_cert_2_{timestamp}"

        viewer_a_email = f"viewer_a_{timestamp}@certops.internal"
        viewer_b_email = f"viewer_b_{timestamp}@certops.internal"
        admin_email = f"admin_{timestamp}@certops.internal"

        cookie_a = self._login_cookie(viewer_a_email)
        cookie_b = self._login_cookie(viewer_b_email)
        cookie_admin = self._login_cookie(admin_email)

        resp_a = self.client.get("/api/certificates", cookies=cookie_a)
        self.assertEqual(resp_a.status_code, 200)
        viewer_A_results = resp_a.json()

        resp_b = self.client.get("/api/certificates", cookies=cookie_b)
        self.assertEqual(resp_b.status_code, 200)
        viewer_B_results = resp_b.json()

        resp_admin = self.client.get("/api/certificates", cookies=cookie_admin)
        self.assertEqual(resp_admin.status_code, 200)
        admin_results = resp_admin.json()

        print(f"[TENANCY RESULT] len(viewer_A) == {len(viewer_A_results)}")
        print(f"[TENANCY RESULT] len(viewer_B) == {len(viewer_B_results)}")
        print(f"[TENANCY RESULT] len(admin) == {len(admin_results)}")

        # Viewer A must see exactly 2 tenant_A certificates
        viewer_A_cert_names = {c["name"] for c in viewer_A_results}
        self.assertEqual(len(viewer_A_results), 2, "Viewer A must see exactly 2 certificates")
        self.assertEqual(viewer_A_cert_names, {tenant_a_cert_1, tenant_a_cert_2})

        # Viewer A CANNOT see any tenant_B certificates
        viewer_A_tenant_b = [c for c in viewer_A_results if c["name"].startswith("tenant_b_")]
        self.assertEqual(len(viewer_A_tenant_b), 0,
            f"CRITICAL: Viewer A saw {len(viewer_A_tenant_b)} tenant_B certs: {[c['name'] for c in viewer_A_tenant_b]}")

        # Viewer B must see exactly 2 tenant_B certificates
        viewer_B_cert_names = {c["name"] for c in viewer_B_results}
        self.assertEqual(len(viewer_B_results), 2, "Viewer B must see exactly 2 certificates")
        self.assertEqual(viewer_B_cert_names, {tenant_b_cert_1, tenant_b_cert_2})

        # Viewer B CANNOT see any tenant_A certificates
        viewer_B_tenant_a = [c for c in viewer_B_results if c["name"].startswith("tenant_a_")]
        self.assertEqual(len(viewer_B_tenant_a), 0,
            f"CRITICAL: Viewer B saw {len(viewer_B_tenant_a)} tenant_A certs: {[c['name'] for c in viewer_B_tenant_a]}")

        # Admin must see all 4 certificates (both tenants)
        admin_cert_names = {c["name"] for c in admin_results}
        self.assertEqual(len(admin_results), 4, "Admin must see all 4 certificates")
        self.assertEqual(admin_cert_names, {tenant_a_cert_1, tenant_a_cert_2, tenant_b_cert_1, tenant_b_cert_2})

        # Direct GET access control
        resp_get_b_by_a = self.client.get(f"/api/certificates/hashicorp/{tenant_b_cert_1}", cookies=cookie_a)
        self.assertEqual(resp_get_b_by_a.status_code, 404, "Viewer A accessing tenant_B cert must 404")

        resp_get_a_by_b = self.client.get(f"/api/certificates/hashicorp/{tenant_a_cert_1}", cookies=cookie_b)
        self.assertEqual(resp_get_a_by_b.status_code, 404, "Viewer B accessing tenant_A cert must 404")

        print("[RESULT] PASSED: RBAC / Tenancy isolation enforced at query layer")


if __name__ == "__main__":
    unittest.main()
