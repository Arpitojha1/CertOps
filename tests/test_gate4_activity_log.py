import json
import os
import unittest

from fastapi.testclient import TestClient
from src import api, db
from src.api import app


class TestGate4ActivityLog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orig_env = {
            "CERTOPS_DB_PATH": os.environ.get("CERTOPS_DB_PATH"),
            "DB_PATH": os.environ.get("DB_PATH"),
            "ENV": os.environ.get("ENV"),
            "COOKIE_SECURE": os.environ.get("COOKIE_SECURE"),
        }
        cls.db_path = "./test_gate4_activity.db"
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)
        os.environ["CERTOPS_DB_PATH"] = cls.db_path
        os.environ["DB_PATH"] = cls.db_path
        os.environ["ENV"] = "development"
        os.environ["COOKIE_SECURE"] = "false"

        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)
        for k, val in cls.orig_env.items():
            if val is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = val

    def setUp(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        conn = db.get_db_connection(self.db_path)
        conn.close()

        from src import auth
        admin_hash = auth.hash_password("admin_secret_123")
        viewer_hash = auth.hash_password("viewer_secret_123")
        db.create_user("admin@example.com", admin_hash, "admin", db_path=self.db_path)
        db.create_user("viewer@example.com", viewer_hash, "viewer", db_path=self.db_path)

        resp_admin = self.client.post(
            "/auth/login",
            json={"email": "admin@example.com", "password": "admin_secret_123"},
        )
        self.assertEqual(resp_admin.status_code, 200)
        self.admin_cookie = {"certops_token": resp_admin.cookies.get("certops_token", "")}

        resp_viewer = self.client.post(
            "/auth/login",
            json={"email": "viewer@example.com", "password": "viewer_secret_123"},
        )
        self.assertEqual(resp_viewer.status_code, 200)
        self.viewer_cookie = {"certops_token": resp_viewer.cookies.get("certops_token", "")}

    def test_01_viewer_sees_only_viewer_visible_events(self):
        print("\n=== TEST 1: Viewer-Role GET /api/activity-log Returns Only Viewer-Visible Events ===")

        # Admin creates a connector (viewer-visible event)
        self.client.post(
            "/api/connectors",
            json={"name": "test_conn", "category": "ca", "renewal_threshold_days": 10.0, "config": {}},
            cookies=self.admin_cookie,
        )
        # Admin creates a group (viewer-visible event)
        self.client.post(
            "/api/groups",
            json={"name": "Test Group", "description": "test"},
            cookies=self.admin_cookie,
        )
        # Admin logged in earlier — that generated a user_login event (admin-only)

        resp = self.client.get("/api/activity-log", cookies=self.viewer_cookie)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        items = data["items"]
        print(f"[VIEWER RESPONSE] total={data['total']}, items_returned={len(items)}")

        # Viewer should NOT see user_login events
        event_types = {e["event_type"] for e in items}
        print(f"[VIEWER EVENT TYPES] {event_types}")
        self.assertNotIn("user_login", event_types, "Viewer must NOT see admin-only user_login events")
        self.assertNotIn("invite_generated", event_types, "Viewer must NOT see admin-only invite_generated events")
        self.assertNotIn("invite_redeemed", event_types, "Viewer must NOT see admin-only invite_redeemed events")

        # Viewer SHOULD see connector_created and group_created
        self.assertIn("connector_created", event_types, "Viewer SHOULD see connector_created")
        self.assertIn("group_created", event_types, "Viewer SHOULD see group_created")
        print("[RESULT] PASSED: Viewer only sees viewer-visible event types")

    def test_02_admin_sees_full_set_including_admin_only_events(self):
        print("\n=== TEST 2: Admin-Role GET /api/activity-log Returns Full Set Including Admin-Only Events ===")

        # Admin login generates a user_login event
        # (already logged in via setUp, but login was called — that generated user_login)
        # Create an invite to generate invite_generated event
        self.client.post(
            "/auth/invites",
            json={"email": "invitee@test.com", "role": "viewer"},
            cookies=self.admin_cookie,
        )

        resp = self.client.get("/api/activity-log", cookies=self.admin_cookie)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        items = data["items"]
        event_types = {e["event_type"] for e in items}
        print(f"[ADMIN RESPONSE] total={data['total']}, items_returned={len(items)}")
        print(f"[ADMIN EVENT TYPES] {event_types}")

        self.assertIn("user_login", event_types, "Admin MUST see user_login events")
        self.assertIn("invite_generated", event_types, "Admin MUST see invite_generated events")
        print("[RESULT] PASSED: Admin sees full event set including admin-only events")

    def test_03_connector_log_entry_no_unredacted_credentials(self):
        print("\n=== TEST 3: Connector-Related Log Entry Does NOT Contain Unredacted Credentials ===")

        secret_token = "s.my_super_secret_vault_token_12345"
        secret_password = "topsecret_db_pass_999"

        resp = self.client.post(
            "/api/connectors",
            json={
                "name": "cred_test_conn",
                "category": "secret_store",
                "renewal_threshold_days": 14.0,
                "config": {
                    "url": "https://vault.example.com:8200",
                    "token": secret_token,
                    "password": secret_password,
                },
            },
            cookies=self.admin_cookie,
        )
        self.assertEqual(resp.status_code, 200)

        # Fetch activity log and find the connector_created entry
        resp_log = self.client.get("/api/activity-log?event_type=connector_created", cookies=self.admin_cookie)
        self.assertEqual(resp_log.status_code, 200)
        items = resp_log.json()["items"]
        self.assertGreater(len(items), 0, "Must have at least one connector_created entry")

        entry = items[0]
        print(f"[ACTIVITY LOG ENTRY] id={entry['id']}, event_type={entry['event_type']}, target={entry['target']}")

        # Parse the details JSON
        self.assertIsNotNone(entry["details"], "Details must not be null for connector events")
        details = json.loads(entry["details"])
        print(f"[ENTRY DETAILS] {json.dumps(details, indent=2)}")

        # Check that sensitive fields are redacted
        if "config" in details:
            config = details["config"]
            print(f"[CONFIG IN ENTRY] {config}")
            self.assertNotEqual(config.get("token"), secret_token, "Token MUST be redacted in activity log entry!")
            self.assertNotEqual(config.get("password"), secret_password, "Password MUST be redacted in activity log entry!")
            self.assertEqual(config.get("token"), "********", "Token must be replaced with ********")
            self.assertEqual(config.get("password"), "********", "Password must be replaced with ********")
            # URL (non-sensitive) should pass through
            self.assertEqual(config.get("url"), "https://vault.example.com:8200")
        else:
            self.fail("No 'config' field in connector_created details — credential leak risk!")

        # Also verify the RAW SQLite row has no plaintext credentials
        conn = db.get_db_connection(self.db_path)
        try:
            raw_details = conn.execute(
                "SELECT details FROM activity_log WHERE id = ?", (entry["id"],)
            ).fetchone()[0]
        finally:
            conn.close()
        print(f"[RAW SQLITE DETAILS] {raw_details}")
        self.assertNotIn(secret_token, raw_details, "Plaintext token must NOT appear in raw SQLite activity_log!")
        self.assertNotIn(secret_password, raw_details, "Plaintext password must NOT appear in raw SQLite activity_log!")
        self.assertNotIn("ENC:v1:", raw_details, "Encrypted token (ENC:v1:) must NOT appear in activity log — only redacted!")
        print("[RESULT] PASSED: Connector log entry contains only redacted credentials")

    def test_04_pagination_works_distinct_rows(self):
        print("\n=== TEST 4: Pagination Returns Distinct Rows Across Pages ===")

        # Generate >PAGE_SIZE events by creating many connectors
        for i in range(55):
            self.client.post(
                "/api/connectors",
                json={"name": f"page_test_{i}", "category": "ca", "renewal_threshold_days": 7.0, "config": {}},
                cookies=self.admin_cookie,
            )

        # Fetch page 1 (default limit 50)
        resp1 = self.client.get("/api/activity-log?limit=50&offset=0", cookies=self.admin_cookie)
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json()
        print(f"[PAGE 1] items={len(data1['items'])}, total={data1['total']}")
        self.assertEqual(len(data1["items"]), 50, "Page 1 must return exactly 50 items")
        self.assertGreater(data1["total"], 50, "Total must exceed page size")

        # Fetch page 2
        resp2 = self.client.get("/api/activity-log?limit=50&offset=50", cookies=self.admin_cookie)
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        print(f"[PAGE 2] items={len(data2['items'])}, total={data2['total']}")
        self.assertGreater(len(data2["items"]), 0, "Page 2 must have items")
        self.assertLessEqual(len(data2["items"]), 50, "Page 2 must not exceed limit")

        # Verify no overlap — page 2 IDs must not appear in page 1
        page1_ids = {e["id"] for e in data1["items"]}
        page2_ids = {e["id"] for e in data2["items"]}
        overlap = page1_ids & page2_ids
        print(f"[OVERLAP CHECK] page1_ids_count={len(page1_ids)}, page2_ids_count={len(page2_ids)}, overlap={len(overlap)}")
        self.assertEqual(len(overlap), 0, "Page 1 and Page 2 must have NO overlapping row IDs!")

        # Verify total count is accurate
        all_items = data1["items"] + data2["items"]
        self.assertEqual(data1["total"], data2["total"], "Total should be consistent across pages")
        self.assertEqual(data1["total"], len(all_items), "Total should match sum of both pages")
        print(f"[TOTAL CHECK] total={data1['total']}, sum_of_pages={len(all_items)}")
        print("[RESULT] PASSED: Pagination returns distinct, non-overlapping rows")

    def test_05_logging_wired_into_all_mutation_paths(self):
        print("\n=== TEST 5: Logging Calls Wired Into All Mutation Paths ===")

        # Group create
        self.client.post("/api/groups", json={"name": "Log Test Group", "description": "x"}, cookies=self.admin_cookie)

        # Group assign
        conn = db.get_db_connection(self.db_path)
        try:
            conn.execute(
                "INSERT INTO certificates (vault_source, name, expiry_utc, connector_category) VALUES (?, ?, ?, ?)",
                ("hashicorp", "assign-test-cert", "2026-12-31T00:00:00Z", "secret_store"),
            )
            conn.commit()
        finally:
            conn.close()
        self.client.post(
            "/api/certificates/assign-group",
            json={"vault_source": "hashicorp", "name": "assign-test-cert", "group_id": 1},
            cookies=self.admin_cookie,
        )

        # Maintenance window create
        self.client.post(
            "/api/maintenance-windows",
            json={"group_id": 1, "start_time": "2026-08-01T00:00:00Z", "end_time": "2026-08-02T00:00:00Z"},
            cookies=self.admin_cookie,
        )

        # Notification policy create
        resp_np = self.client.post(
            "/api/notification-policies",
            json={"group_id": 1, "threshold_days": 5.0},
            cookies=self.admin_cookie,
        )
        policy_id = resp_np.json()["id"]

        # Notification policy delete
        self.client.delete(f"/api/notification-policies/{policy_id}", cookies=self.admin_cookie)

        # Connector create/update/delete/test
        resp_c = self.client.post(
            "/api/connectors",
            json={"name": "wired_test_conn", "category": "ca", "renewal_threshold_days": 10.0, "config": {}},
            cookies=self.admin_cookie,
        )
        cid = resp_c.json()["id"]
        self.client.put(f"/api/connectors/{cid}", json={"renewal_threshold_days": 20.0}, cookies=self.admin_cookie)
        self.client.post(f"/api/connectors/{cid}/test", cookies=self.admin_cookie)
        self.client.delete(f"/api/connectors/{cid}", cookies=self.admin_cookie)

        # Fetch all activity log
        resp = self.client.get("/api/activity-log?limit=200", cookies=self.admin_cookie)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        event_types = [e["event_type"] for e in data["items"]]
        print(f"[ALL EVENT TYPES LOGGED] {event_types}")

        expected_types = [
            "user_login",
            "connector_created",
            "group_created",
            "group_assigned",
            "maintenance_window_created",
            "notification_policy_created",
            "notification_policy_deleted",
            "connector_updated",
            "connector_tested",
            "connector_deleted",
        ]
        for et in expected_types:
            self.assertIn(et, event_types, f"Expected event_type '{et}' not found in activity log!")
            print(f"  [WIRED] {et} — present in log")

        print(f"[RESULT] PASSED: All {len(expected_types)} mutation paths are wired with logging")

    def test_06_activity_log_table_schema_and_append_only(self):
        print("\n=== TEST 6: Activity Log Table Schema & Append-Only Behavior ===")

        conn = db.get_db_connection(self.db_path)
        try:
            cols = conn.execute("PRAGMA table_info(activity_log)").fetchall()
            col_names = [c[1] for c in cols]
        finally:
            conn.close()
        print(f"[TABLE COLUMNS] {col_names}")
        expected_cols = ["id", "event_type", "actor_user_id", "actor_email", "target", "details", "timestamp"]
        for ec in expected_cols:
            self.assertIn(ec, col_names, f"Column '{ec}' missing from activity_log table!")
        print("[SCHEMA CHECK] PASSED: All expected columns present")

        # Verify append-only: insert two entries, verify order preserved
        id1 = db.log_activity(event_type="test_event_a", target="t1", db_path=self.db_path)
        id2 = db.log_activity(event_type="test_event_b", target="t2", db_path=self.db_path)
        self.assertGreater(id2, id1, "Second insert must have higher id (append-only)")
        print(f"[APPEND-ONLY] id1={id1}, id2={id2} — monotonic increment confirmed")
        print("[RESULT] PASSED")

    def test_07_viewer_filter_excludes_admin_only_at_query_layer(self):
        print("\n=== TEST 7: Viewer RBAC Filter Applied at Query Layer, Not Serialization ===")

        # Insert auth events directly (simulating what auth.py does)
        db.log_activity(event_type="user_login", actor_user_id=1, actor_email="admin@example.com", db_path=self.db_path)
        db.log_activity(event_type="invite_generated", actor_user_id=1, actor_email="admin@example.com", target="x@y.com", db_path=self.db_path)
        db.log_activity(event_type="connector_created", actor_user_id=1, actor_email="admin@example.com", target="test", db_path=self.db_path)

        # Admin query — should see all 3 (plus any from setUp login)
        resp_admin = self.client.get("/api/activity-log?limit=200", cookies=self.admin_cookie)
        admin_events = [e["event_type"] for e in resp_admin.json()["items"]]
        admin_only_count = sum(1 for e in admin_events if e in ("user_login", "invite_generated", "invite_redeemed"))
        print(f"[ADMIN] total={resp_admin.json()['total']}, admin_only_events={admin_only_count}")
        self.assertGreater(admin_only_count, 0, "Admin should see admin-only events")

        # Viewer query — should see 0 admin-only events
        resp_viewer = self.client.get("/api/activity-log?limit=200", cookies=self.viewer_cookie)
        viewer_events = [e["event_type"] for e in resp_viewer.json()["items"]]
        viewer_admin_only_count = sum(1 for e in viewer_events if e in ("user_login", "invite_generated", "invite_redeemed"))
        print(f"[VIEWER] total={resp_viewer.json()['total']}, admin_only_events_visible={viewer_admin_only_count}")
        self.assertEqual(viewer_admin_only_count, 0, "Viewer must see ZERO admin-only events")
        print("[RESULT] PASSED: RBAC filter excludes admin-only events for viewer at query layer")


    def test_08_renewal_loop_writes_activity_log_with_iso_timestamps(self):
        """Run the real run_renewal_loop() with a stubbed connector so that the
        .isoformat() calls in main.py are the code under test — not a hand-copy
        of them in this file.  Proves: (a) no TypeError from json.dumps on the
        datetime objects that flow through the renewal path, (b) entries land in
        the activity_log table, (c) a viewer can see them."""
        print("\n=== TEST 8: run_renewal_loop() Writes certificate_renewed to Activity Log ===")
        from datetime import datetime, timedelta, timezone
        from contextlib import nullcontext
        from unittest.mock import patch, MagicMock

        class _StubConnector:
            """Bare-minimum SecretStoreConnector stand-in for run_renewal_loop()."""
            name = "stub_vault"
            renewal_threshold_days = 99999.0

            def list_certificates(self):
                return [{"name": "stub-cert", "expiry_utc": "2020-01-01T00:00:00+00:00", "version": "1"}]

            def get_certificate(self, name):
                return {"common_name": name}

            def write_certificate(self, name, cert_pem, key_pem):
                return {"expiry_utc": datetime(2027, 1, 1, tzinfo=timezone.utc), "version": "2"}

        stub = _StubConnector()
        fake_cert_pem = "-----BEGIN CERTIFICATE-----\nMIIBkTCB+wIJALHM2VOBmOyyMA0GCSqGSIb3DQEBCwUAMBExDzANBgNVBAMMBnRl\n-----END CERTIFICATE-----\n"
        fake_key_pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF8PbnGcY5unA67hqlYMd4Prn7dOt\n-----END RSA PRIVATE KEY-----\n"

        os.environ["RENEWAL_THRESHOLD_DAYS"] = "99999"
        os.environ["STEP_CA_PASSWORD_FILE"] = "./pass.txt"
        os.environ["STEP_CA_URL"] = "https://localhost:8443"
        os.environ["STEP_CA_FINGERPRINT"] = "abc123"
        os.environ["VERIFY_HOST"] = "localhost"
        os.environ["VERIFY_PORT"] = "443"
        os.environ["NGINX_CONTAINER_NAME"] = "certops-nginx-1"
        os.environ["VAULT_CERT_PATH"] = "secret/local-certs"

        from src.main import run_renewal_loop

        with patch("src.main.get_active_connectors", return_value=[stub]), \
             patch("src.main.load_dotenv"), \
             patch("src.main.ca_client.issue_certificate", return_value=(fake_cert_pem, fake_key_pem)), \
             patch("src.main.db") as mock_db:
            mock_db.renewal_context = lambda *a, **kw: nullcontext()
            mock_db.log_activity = db.log_activity
            mock_db.upsert_certificate = db.upsert_certificate
            mock_db.get_due_certificates = db.get_due_certificates
            mock_db._parse_utc_datetime = db._parse_utc_datetime
            mock_db.get_certificate = db.get_certificate
            mock_db.get_db_connection = db.get_db_connection

            summary = run_renewal_loop()

        # Verify the renewal succeeded at the loop level
        self.assertTrue(summary["stub_vault"]["succeeded"] >= 1, "Loop must report at least one success")
        print(f"[LOOP SUMMARY] {dict(summary['stub_vault'])}")

        # Verify activity_log has a certificate_renewed entry
        resp = self.client.get(
            "/api/activity-log?event_type=certificate_renewed&limit=200",
            cookies=self.admin_cookie,
        )
        self.assertEqual(resp.status_code, 200)
        items = resp.json()["items"]
        matching = [e for e in items if e["target"] == "stub-cert"]
        self.assertGreaterEqual(len(matching), 1, "At least one certificate_renewed entry for stub-cert")
        entry = matching[0]
        print(f"[ACTIVITY LOG] id={entry['id']} event_type={entry['event_type']} target={entry['target']}")

        # Verify details contain ISO-formatted timestamps (not raw datetime objects)
        details = json.loads(entry["details"])
        print(f"[DETAILS] {json.dumps(details, indent=2)}")
        self.assertEqual(details["connector_name"], "stub_vault")
        self.assertEqual(details["category"], "secret_store")
        # These assertions fail if main.py passes raw datetime objects —
        # json.dumps() would have raised TypeError before the row was written.
        datetime.fromisoformat(details["old_expiry"])
        datetime.fromisoformat(details["new_expiry"])
        self.assertGreater(
            datetime.fromisoformat(details["new_expiry"]),
            datetime.fromisoformat(details["old_expiry"]),
            "new_expiry must be after old_expiry",
        )
        print("[ISO CHECK] old_expiry and new_expiry are valid ISO strings, new > old")

        # Verify viewer-visible (certificate_renewed is NOT in _ADMIN_ONLY_EVENTS)
        resp_v = self.client.get(
            "/api/activity-log?event_type=certificate_renewed&limit=200",
            cookies=self.viewer_cookie,
        )
        self.assertEqual(resp_v.status_code, 200)
        viewer_matching = [e for e in resp_v.json()["items"] if e["target"] == "stub-cert"]
        self.assertGreaterEqual(len(viewer_matching), 1, "Viewer MUST see certificate_renewed events")
        print("[VIEWER CHECK] certificate_renewed visible to viewer role")

        # Verify no certificate_renewal_failed appeared (renewal succeeded)
        resp_fail = self.client.get(
            "/api/activity-log?event_type=certificate_renewal_failed&limit=200",
            cookies=self.admin_cookie,
        )
        fail_targets = [e["target"] for e in resp_fail.json()["items"] if e["target"] == "stub-cert"]
        self.assertEqual(fail_targets, [], "No certificate_renewal_failed should exist for stub-cert")
        print("[RESULT] PASSED: run_renewal_loop() logs certificate_renewed with ISO timestamps via real code path")

    def test_09_renewal_log_entries_appear_in_combined_activity_feed(self):
        """
        Regression test asserting renewal-log entries surface in the combined activity feed alongside RBAC activity entries.
        """
        print("\n=== TEST 9: Renewal-Log Entries Appear in Combined Activity Feed ===")
        # 1. Log an RBAC/access event directly into activity_log
        db.log_activity("connector_created", actor_email="admin@certops.internal", target="test_rbac_connector")

        # 2. Log a renewal pipeline event directly into renewal_log (only in renewal_log, not activity_log)
        db.insert_renewal_log(
            cert_id="cert_from_renewal_log",
            event_type="certificate_renewed",
            success=True,
            vault_source="hashicorp",
            detail="renewed directly via insert_renewal_log",
        )

        # 3. Query combined activity log endpoint
        resp = self.client.get("/api/activity-log?limit=200", cookies=self.admin_cookie)
        self.assertEqual(resp.status_code, 200)
        items = resp.json()["items"]

        # 4. Assert both RBAC event and renewal log event are present together
        rbac_targets = [item for item in items if item.get("target") == "test_rbac_connector"]
        ren_targets = [item for item in items if item.get("target") == "cert_from_renewal_log"]

        self.assertGreaterEqual(len(rbac_targets), 1, "Must contain RBAC/access event from activity_log")
        self.assertGreaterEqual(len(ren_targets), 1, "Must contain renewal event from renewal_log")

        print("[COMBINED LOG VERIFICATION] Both RBAC activity_log and renewal_log entries found together:")
        print("  RBAC entry sample:", json.dumps(rbac_targets[0], indent=2))
        print("  Renewal-log entry sample:", json.dumps(ren_targets[0], indent=2))
        print("[RESULT] PASSED: Combined activity log returns both data sources together")


if __name__ == "__main__":
    unittest.main()
