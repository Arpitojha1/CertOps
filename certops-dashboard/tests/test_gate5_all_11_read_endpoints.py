"""
Verification test for Phase 2-Close: Read-Side Tenancy Isolation Across All 11 Endpoints.
Asserts that Viewer A (`tenant_A`) and Viewer B (`tenant_B`) cannot read or enumerate each
other's resources across all 11 GET endpoints, and that parameter tampering attempts are ignored.
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json

from fastapi.testclient import TestClient

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))
_sibling = _root.parent / "certops-agent"
if _sibling.exists() and str(_sibling) not in sys.path:
    sys.path.insert(0, str(_sibling))

from src import db
from src.api import app
from src.auth import COOKIE_NAME, _make_token


class TestGate5All11ReadEndpoints(unittest.TestCase):
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

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        self.timestamp = timestamp

        self.admin_email = f"admin_{timestamp}@certops.internal"
        self.viewer_a_email = f"viewer_a_{timestamp}@certops.internal"
        self.viewer_b_email = f"viewer_b_{timestamp}@certops.internal"

        db.create_user(self.admin_email, "$2b$12$fakehash", role="admin", tenant_id="default")
        self.user_a_id = db.create_user(self.viewer_a_email, "$2b$12$fakehash", role="viewer", tenant_id="tenant_A")
        self.user_b_id = db.create_user(self.viewer_b_email, "$2b$12$fakehash", role="viewer", tenant_id="tenant_B")

        # --- Seed Tenant A Entities ---
        self.group_a_id = db.create_group("group_A", "Production Web A", tenant_id="tenant_A")
        self.conn_a_id = db.create_connector(
            name="connector_A",
            category="secret_store",
            renewal_threshold_days=30,
            config=json.dumps({"vault_url": "http://vault-a:8200"}),
            is_active=True,
            tenant_id="tenant_A",
        )
        self.window_a_id = db.create_maintenance_window(
            self.group_a_id, "2026-08-01T00:00:00Z", "2026-08-01T04:00:00Z", "once", tenant_id="tenant_A"
        )
        self.policy_a_id = db.create_notification_policy(self.group_a_id, 30.0, tenant_id="tenant_A")

        expiry_due = (datetime.now(timezone.utc) + timedelta(days=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
        db.upsert_certificate(
            vault_source="hashicorp",
            name="cert_A.crt",
            expiry_utc=expiry_due,
            common_name="a.example.com",
            group_id=self.group_a_id,
            tenant_id="tenant_A",
        )
        db.log_renewal_event(
            cert_id="hashicorp:cert_A.crt",
            event_type="stage_verified",
            message="Verified A",
            success=True,
            tenant_id="tenant_A",
        )
        db.log_activity(
            event_type="group_created",
            actor_user_id=self.user_a_id,
            actor_email=self.viewer_a_email,
            target="group_A",
            details={"group_id": self.group_a_id},
            tenant_id="tenant_A",
        )
        db.log_notification_event(
            cert_id="hashicorp:cert_A.crt",
            event_type="renewal_warning",
            recipient="admin@a.example.com",
            success=True,
            message="Warning A",
            tenant_id="tenant_A",
        )

        # --- Seed Tenant B Entities ---
        self.group_b_id = db.create_group("group_B", "Production Web B", tenant_id="tenant_B")
        self.conn_b_id = db.create_connector(
            name="connector_B",
            category="secret_store",
            renewal_threshold_days=30,
            config=json.dumps({"vault_url": "http://vault-b:8200"}),
            is_active=True,
            tenant_id="tenant_B",
        )
        self.window_b_id = db.create_maintenance_window(
            self.group_b_id, "2026-08-01T00:00:00Z", "2026-08-01T04:00:00Z", "once", tenant_id="tenant_B"
        )
        self.policy_b_id = db.create_notification_policy(self.group_b_id, 30.0, tenant_id="tenant_B")

        db.upsert_certificate(
            vault_source="hashicorp",
            name="cert_B.crt",
            expiry_utc=expiry_due,
            common_name="b.example.com",
            group_id=self.group_b_id,
            tenant_id="tenant_B",
        )
        db.log_renewal_event(
            cert_id="hashicorp:cert_B.crt",
            event_type="stage_verified",
            message="Verified B",
            success=True,
            tenant_id="tenant_B",
        )
        db.log_activity(
            event_type="group_created",
            actor_user_id=self.user_b_id,
            actor_email=self.viewer_b_email,
            target="group_B",
            details={"group_id": self.group_b_id},
            tenant_id="tenant_B",
        )
        db.log_notification_event(
            cert_id="hashicorp:cert_B.crt",
            event_type="renewal_warning",
            recipient="admin@b.example.com",
            success=True,
            message="Warning B",
            tenant_id="tenant_B",
        )

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

    def _cookie(self, email: str) -> dict:
        user = db.get_user_by_email(email)
        token = _make_token(user["id"], user["email"], user["role"], user["tenant_id"])
        return {COOKIE_NAME: token}

    def test_all_11_read_endpoints_isolated(self):
        cookie_a = self._cookie(self.viewer_a_email)
        cookie_b = self._cookie(self.viewer_b_email)
        cookie_admin = self._cookie(self.admin_email)

        # 1. GET /api/certificates
        r_a = self.client.get("/api/certificates", cookies=cookie_a).json()
        r_b = self.client.get("/api/certificates", cookies=cookie_b).json()
        r_admin = self.client.get("/api/certificates", cookies=cookie_admin).json()
        self.assertEqual({c["name"] for c in r_a}, {"cert_A.crt"})
        self.assertEqual({c["name"] for c in r_b}, {"cert_B.crt"})
        self.assertEqual({c["name"] for c in r_admin}, {"cert_A.crt", "cert_B.crt"})

        # 2. GET /api/certificates/due
        r_due_a = self.client.get("/api/certificates/due?threshold_days=30", cookies=cookie_a).json()
        r_due_b = self.client.get("/api/certificates/due?threshold_days=30", cookies=cookie_b).json()
        r_due_admin = self.client.get("/api/certificates/due?threshold_days=30", cookies=cookie_admin).json()
        self.assertEqual({c["name"] for c in r_due_a}, {"cert_A.crt"})
        self.assertEqual({c["name"] for c in r_due_b}, {"cert_B.crt"})
        self.assertEqual({c["name"] for c in r_due_admin}, {"cert_A.crt", "cert_B.crt"})

        # 3. GET /api/certificates/{source}/{name}
        self.assertEqual(self.client.get("/api/certificates/hashicorp/cert_A.crt", cookies=cookie_a).status_code, 200)
        self.assertEqual(self.client.get("/api/certificates/hashicorp/cert_B.crt", cookies=cookie_a).status_code, 404)
        self.assertEqual(self.client.get("/api/certificates/hashicorp/cert_B.crt", cookies=cookie_b).status_code, 200)
        self.assertEqual(self.client.get("/api/certificates/hashicorp/cert_A.crt", cookies=cookie_b).status_code, 404)

        # 4. GET /api/renewal-log
        r_ren_a = self.client.get("/api/renewal-log", cookies=cookie_a).json()
        r_ren_b = self.client.get("/api/renewal-log", cookies=cookie_b).json()
        r_ren_admin = self.client.get("/api/renewal-log", cookies=cookie_admin).json()
        self.assertEqual({l["cert_id"] for l in r_ren_a}, {"hashicorp:cert_A.crt"})
        self.assertEqual({l["cert_id"] for l in r_ren_b}, {"hashicorp:cert_B.crt"})
        self.assertEqual({l["cert_id"] for l in r_ren_admin}, {"hashicorp:cert_A.crt", "hashicorp:cert_B.crt"})

        # 5. GET /api/activity-log
        r_act_a = self.client.get("/api/activity-log?include_renewal_log=false", cookies=cookie_a).json()["items"]
        r_act_b = self.client.get("/api/activity-log?include_renewal_log=false", cookies=cookie_b).json()["items"]
        r_act_admin = self.client.get("/api/activity-log?include_renewal_log=false", cookies=cookie_admin).json()["items"]
        self.assertEqual({i["target"] for i in r_act_a if i["event_type"] == "group_created"}, {"group_A"})
        self.assertEqual({i["target"] for i in r_act_b if i["event_type"] == "group_created"}, {"group_B"})
        self.assertEqual({i["target"] for i in r_act_admin if i["event_type"] == "group_created"}, {"group_A", "group_B"})

        # 6. GET /api/connectors
        r_conn_a = self.client.get("/api/connectors", cookies=cookie_a).json()
        r_conn_b = self.client.get("/api/connectors", cookies=cookie_b).json()
        r_conn_admin = self.client.get("/api/connectors", cookies=cookie_admin).json()
        self.assertEqual({c["name"] for c in r_conn_a}, {"connector_A"})
        self.assertEqual({c["name"] for c in r_conn_b}, {"connector_B"})
        self.assertEqual({c["name"] for c in r_conn_admin}, {"connector_A", "connector_B", "step_ca", "azure", "ssh_host", "hashicorp"})

        # 7. GET /api/groups
        r_grp_a = self.client.get("/api/groups", cookies=cookie_a).json()
        r_grp_b = self.client.get("/api/groups", cookies=cookie_b).json()
        r_grp_admin = self.client.get("/api/groups", cookies=cookie_admin).json()
        self.assertEqual({g["name"] for g in r_grp_a}, {"group_A"})
        self.assertEqual({g["name"] for g in r_grp_b}, {"group_B"})
        self.assertEqual({g["name"] for g in r_grp_admin}, {"group_A", "group_B"})

        # 8. GET /api/maintenance-windows
        r_win_a = self.client.get("/api/maintenance-windows", cookies=cookie_a).json()
        r_win_b = self.client.get("/api/maintenance-windows", cookies=cookie_b).json()
        r_win_admin = self.client.get("/api/maintenance-windows", cookies=cookie_admin).json()
        self.assertEqual({w["group_id"] for w in r_win_a}, {self.group_a_id})
        self.assertEqual({w["group_id"] for w in r_win_b}, {self.group_b_id})
        self.assertEqual({w["group_id"] for w in r_win_admin}, {self.group_a_id, self.group_b_id})

        # 9. GET /api/notification-policies
        r_pol_a = self.client.get("/api/notification-policies", cookies=cookie_a).json()
        r_pol_b = self.client.get("/api/notification-policies", cookies=cookie_b).json()
        r_pol_admin = self.client.get("/api/notification-policies", cookies=cookie_admin).json()
        self.assertEqual({p["group_id"] for p in r_pol_a}, {self.group_a_id})
        self.assertEqual({p["group_id"] for p in r_pol_b}, {self.group_b_id})
        self.assertEqual({p["group_id"] for p in r_pol_admin}, {self.group_a_id, self.group_b_id})

        # 10. GET /api/notification-log
        r_notif_a = self.client.get("/api/notification-log", cookies=cookie_a).json()
        r_notif_b = self.client.get("/api/notification-log", cookies=cookie_b).json()
        r_notif_admin = self.client.get("/api/notification-log", cookies=cookie_admin).json()
        self.assertEqual({n["cert_id"] for n in r_notif_a}, {"hashicorp:cert_A.crt"})
        self.assertEqual({n["cert_id"] for n in r_notif_b}, {"hashicorp:cert_B.crt"})
        self.assertEqual({n["cert_id"] for n in r_notif_admin}, {"hashicorp:cert_A.crt", "hashicorp:cert_B.crt"})

        # 11. GET /api/scheduler/status
        # Note: Tie-breaking by next_renewal_at applies within each scope. Under our exact seeding
        # with 1 due certificate per tenant, next_job strictly evaluates cert_A for A and cert_B for B.
        r_sched_a = self.client.get("/api/scheduler/status", cookies=cookie_a).json()
        r_sched_b = self.client.get("/api/scheduler/status", cookies=cookie_b).json()
        r_sched_admin = self.client.get("/api/scheduler/status", cookies=cookie_admin).json()
        self.assertEqual(r_sched_a["nextJob"]["name"], "cert_A.crt")
        self.assertEqual(r_sched_b["nextJob"]["name"], "cert_B.crt")
        self.assertEqual({l["cert_id"] for l in r_sched_a["recentEvents"]}, {"hashicorp:cert_A.crt"})
        self.assertEqual({l["cert_id"] for l in r_sched_b["recentEvents"]}, {"hashicorp:cert_B.crt"})
        self.assertEqual({l["cert_id"] for l in r_sched_admin["recentEvents"]}, {"hashicorp:cert_A.crt", "hashicorp:cert_B.crt"})

    def test_negative_path_query_parameter_tampering(self):
        """Verify _get_tenant_scope() ignores/overrides client-supplied tenant filters."""
        cookie_a = self._cookie(self.viewer_a_email)

        # Attempt to pass ?tenant_id=tenant_B while authenticated as Viewer A
        r_tamper_cert = self.client.get("/api/certificates?tenant_id=tenant_B", cookies=cookie_a).json()
        self.assertEqual({c["name"] for c in r_tamper_cert}, {"cert_A.crt"}, "Must ignore client-supplied tenant_id query param")

        # Attempt to filter due certificates by Group B while authenticated as Viewer A
        r_tamper_group = self.client.get(f"/api/certificates/due?group_id={self.group_b_id}", cookies=cookie_a).json()
        self.assertEqual(len(r_tamper_group), 0, "Filtering by cross-tenant group_id must return 0 items")


if __name__ == "__main__":
    unittest.main()
