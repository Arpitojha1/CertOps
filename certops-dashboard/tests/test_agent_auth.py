import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
import sys
from pathlib import Path
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))
_sibling = _root.parent / "certops-agent"
if _sibling.exists() and str(_sibling) not in sys.path:
    sys.path.insert(0, str(_sibling))

from src import api, auth, db


class TestAgentAuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orig_env = {
            "CERTOPS_DB_PATH": os.environ.get("CERTOPS_DB_PATH"),
            "DB_PATH": os.environ.get("DB_PATH"),
            "JWT_SECRET": os.environ.get("JWT_SECRET"),
            "AGENT_TOKEN_SIGNING_KEY": os.environ.get("AGENT_TOKEN_SIGNING_KEY"),
        }
        cls.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls.db_path = cls.db_file.name
        cls.db_file.close()

        os.environ["CERTOPS_DB_PATH"] = cls.db_path
        os.environ["DB_PATH"] = cls.db_path
        os.environ["JWT_SECRET"] = "test-dashboard-secret-jwt"
        os.environ["AGENT_TOKEN_SIGNING_KEY"] = "test-agent-token-signing-key-12345"

        db.run_migrations(cls.db_path)
        cls.client = TestClient(api.app, raise_server_exceptions=False)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass
        for k, val in cls.orig_env.items():
            if val is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = val

    def setUp(self):
        # Ensure standard keys set for each test unless modified
        os.environ["JWT_SECRET"] = "test-dashboard-secret-jwt"
        os.environ["AGENT_TOKEN_SIGNING_KEY"] = "test-agent-token-signing-key-12345"

    def test_01_valid_agent_token_hits_telemetry_push_successfully(self):
        """Test 1: Valid agent token hits telemetry-push dependency/route successfully."""
        from src import agent_auth

        raw_token, token_rec = agent_auth.create_agent_token(scope="telemetry_push", db_path=self.db_path)
        valid_payload = {"agent_id": "test-agent", "agent_version": "1.0", "timestamp": "2026-07-15T00:00:00Z", "items": []}
        
        response = self.client.post(
            "/api/telemetry/push",
            headers={"Authorization": f"Bearer {raw_token}"},
            json=valid_payload
        )
        self.assertEqual(response.status_code, 202, f"Expected 202, got {response.status_code}: {response.text}")
        data = response.json()
        self.assertEqual(data.get("status"), "accepted")

    def test_02_valid_dashboard_session_cookie_or_jwt_rejected_on_telemetry_push(self):
        """Test 2: Valid dashboard session cookie/JWT with NO agent token is rejected on telemetry-push dependency/route."""
        # Create a valid dashboard session token (for an admin user)
        dashboard_token = auth._make_token(user_id=1, email="admin@example.com", role="admin")
        valid_payload = {"agent_id": "test-agent", "agent_version": "1.0", "timestamp": "2026-07-15T00:00:00Z", "items": []}
        
        # 1. Try sending as cookie with no Authorization header
        resp_cookie = self.client.post(
            "/api/telemetry/push",
            cookies={auth.COOKIE_NAME: dashboard_token},
            json=valid_payload
        )
        self.assertEqual(resp_cookie.status_code, 401, f"Expected 401 when sending dashboard cookie, got {resp_cookie.status_code}")

        # 2. Try sending dashboard JWT inside Authorization Bearer header
        resp_bearer = self.client.post(
            "/api/telemetry/push",
            headers={"Authorization": f"Bearer {dashboard_token}"},
            json=valid_payload
        )
        self.assertIn(resp_bearer.status_code, (401, 403), f"Expected 401/403 when sending dashboard JWT as bearer, got {resp_bearer.status_code}")

    def test_03_valid_agent_token_rejected_on_dashboard_only_route(self):
        """Test 3: Valid agent token is rejected on dashboard-only route."""
        from src import agent_auth

        raw_token, _ = agent_auth.create_agent_token(scope="telemetry_push", db_path=self.db_path)

        # 1. Try hitting dashboard-only endpoint with agent token in cookie
        resp_cookie = self.client.get(
            "/api/certificates",
            cookies={auth.COOKIE_NAME: raw_token}
        )
        self.assertEqual(resp_cookie.status_code, 401, f"Expected 401 on dashboard route with agent cookie, got {resp_cookie.status_code}")

        # 2. Try hitting dashboard-only endpoint with agent token in Authorization header
        resp_header = self.client.get(
            "/api/certificates",
            headers={"Authorization": f"Bearer {raw_token}"}
        )
        self.assertEqual(resp_header.status_code, 401, f"Expected 401 on dashboard route with agent bearer header, got {resp_header.status_code}")

    def test_04_revoked_agent_token_rejected_immediately(self):
        """Test 4: Revoked agent token (revoked_at set) is rejected immediately."""
        from src import agent_auth

        raw_token, _ = agent_auth.create_agent_token(scope="telemetry_push", db_path=self.db_path)
        valid_payload = {"agent_id": "test-agent", "agent_version": "1.0", "timestamp": "2026-07-15T00:00:00Z", "items": []}

        # Verify works initially
        resp1 = self.client.post(
            "/api/telemetry/push",
            headers={"Authorization": f"Bearer {raw_token}"},
            json=valid_payload
        )
        self.assertEqual(resp1.status_code, 202)

        # Revoke the token
        revoked = agent_auth.revoke_agent_token(raw_token=raw_token, db_path=self.db_path)
        self.assertTrue(revoked, "Expected revoke_agent_token to return True")

        # Verify immediately rejected
        resp2 = self.client.post(
            "/api/telemetry/push",
            headers={"Authorization": f"Bearer {raw_token}"},
            json=valid_payload
        )
        self.assertEqual(resp2.status_code, 401, f"Expected 401 after revocation, got {resp2.status_code}: {resp2.text}")

    def test_06_agent_token_includes_tenant_id(self):
        """Test 6: Agent token carries tenant_id and it is returned in validation."""
        from src import agent_auth

        raw_token, token_rec = agent_auth.create_agent_token(
            scope="telemetry_push",
            tenant_id="tenant_alpha",
            db_path=self.db_path
        )
        self.assertEqual(token_rec["tenant_id"], "tenant_alpha")

        # Validate and check tenant_id is in the returned record
        token_data = agent_auth.validate_agent_token(
            authorization=f"Bearer {raw_token}",
            db_path=self.db_path
        )
        self.assertEqual(token_data["record"]["tenant_id"], "tenant_alpha")

    def test_05_token_secret_read_from_agent_token_signing_key_specifically(self):
        """Test 5: Token secret read from AGENT_TOKEN_SIGNING_KEY specifically — test asserts app fails loudly
        if AGENT_TOKEN_SIGNING_KEY is unset. Also assert changing JWT_SECRET alone does not invalidate an agent token and vice versa."""
        from src import agent_auth
        valid_payload = {"agent_id": "test-agent", "agent_version": "1.0", "timestamp": "2026-07-15T00:00:00Z", "items": []}

        # 1. Unset AGENT_TOKEN_SIGNING_KEY -> verify loud failure (RuntimeError when creating or validating)
        os.environ.pop("AGENT_TOKEN_SIGNING_KEY", None)
        with self.assertRaises(RuntimeError, msg="Expected RuntimeError when AGENT_TOKEN_SIGNING_KEY is missing/unset"):
            agent_auth.create_agent_token(scope="telemetry_push", db_path=self.db_path)

        with self.assertRaises(RuntimeError, msg="Expected RuntimeError when validating without AGENT_TOKEN_SIGNING_KEY"):
            agent_auth.validate_agent_token(authorization="Bearer dummy_token", db_path=self.db_path)

        # Also check HTTP request returns 500 or raises RuntimeError when AGENT_TOKEN_SIGNING_KEY is unset
        resp_unset = self.client.post(
            "/api/telemetry/push",
            headers={"Authorization": "Bearer dummy_token"},
            json=valid_payload
        )
        self.assertEqual(resp_unset.status_code, 500, f"Expected 500 loud failure when AGENT_TOKEN_SIGNING_KEY unset, got {resp_unset.status_code}")

        # 2. Set AGENT_TOKEN_SIGNING_KEY and issue a token
        os.environ["AGENT_TOKEN_SIGNING_KEY"] = "agent-key-alpha-999"
        raw_token, _ = agent_auth.create_agent_token(scope="telemetry_push", db_path=self.db_path)

        # Verify works
        resp_alpha = self.client.post(
            "/api/telemetry/push",
            headers={"Authorization": f"Bearer {raw_token}"},
            json=valid_payload
        )
        self.assertEqual(resp_alpha.status_code, 202)

        # 3. Change JWT_SECRET alone -> agent token MUST NOT be invalidated
        os.environ["JWT_SECRET"] = "completely-changed-jwt-secret-888"
        resp_after_jwt_change = self.client.post(
            "/api/telemetry/push",
            headers={"Authorization": f"Bearer {raw_token}"},
            json=valid_payload
        )
        self.assertEqual(resp_after_jwt_change.status_code, 202, "Changing JWT_SECRET invalidated agent token!")

        # 4. Change AGENT_TOKEN_SIGNING_KEY alone -> agent token MUST now be rejected (while JWT_SECRET unchanged)
        os.environ["AGENT_TOKEN_SIGNING_KEY"] = "agent-key-beta-777"
        resp_after_key_change = self.client.post(
            "/api/telemetry/push",
            headers={"Authorization": f"Bearer {raw_token}"},
            json={}
        )
        self.assertEqual(resp_after_key_change.status_code, 401, "Expected 401 after changing AGENT_TOKEN_SIGNING_KEY")

    def test_07_cross_tenant_telemetry_push_rejected(self):
        """Test 7: Agent token scoped to tenant_alpha is REJECTED when payload targets tenant_beta.
        This exercises the actual authorization vulnerability: a valid token must not be
        accepted if the payload targets a different tenant."""
        from src import agent_auth
        from src.routes import telemetry_ingest

        # Create a token scoped to tenant_alpha
        raw_token_alpha, _ = agent_auth.create_agent_token(
            scope="telemetry_push",
            tenant_id="tenant_alpha",
            db_path=self.db_path,
        )

        payload_alpha = {
            "agent_id": "test-agent",
            "agent_version": "1.0",
            "timestamp": "2026-07-15T00:00:00Z",
            "tenant_id": "tenant_alpha",
            "items": [],
        }
        payload_beta = {
            "agent_id": "test-agent",
            "agent_version": "1.0",
            "timestamp": "2026-07-15T00:00:00Z",
            "tenant_id": "tenant_beta",
            "items": [],
        }

        telemetry_ingest.clear_received_payloads()

        # 1. tenant_alpha token + tenant_beta payload MUST be rejected (403)
        resp_cross = self.client.post(
            "/api/telemetry/push",
            headers={"Authorization": f"Bearer {raw_token_alpha}"},
            json=payload_beta,
        )
        self.assertEqual(
            resp_cross.status_code, 403,
            f"Expected 403 for cross-tenant push, got {resp_cross.status_code}: {resp_cross.text}"
        )
        self.assertIn("Tenant mismatch", resp_cross.text)

        # 2. tenant_alpha token + tenant_alpha payload MUST succeed (202)
        resp_same = self.client.post(
            "/api/telemetry/push",
            headers={"Authorization": f"Bearer {raw_token_alpha}"},
            json=payload_alpha,
        )
        self.assertEqual(
            resp_same.status_code, 202,
            f"Expected 202 for same-tenant push, got {resp_same.status_code}: {resp_same.text}"
        )

        # 3. Confirm only the same-tenant payload was stored (cross-tenant was rejected)
        stored = telemetry_ingest.get_received_payloads()
        self.assertEqual(len(stored), 1, f"Expected 1 stored payload (cross-tenant rejected), got {len(stored)}")
        self.assertEqual(stored[0]["payload"]["tenant_id"], "tenant_alpha")
        self.assertEqual(stored[0]["tenant_id"], "tenant_alpha")

        telemetry_ingest.clear_received_payloads()


if __name__ == "__main__":
    unittest.main(verbosity=2)
