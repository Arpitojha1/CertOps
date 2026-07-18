import os
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


class TestGate2RBACAuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orig_env = {
            "CERTOPS_DB_PATH": os.environ.get("CERTOPS_DB_PATH"),
            "DB_PATH": os.environ.get("DB_PATH"),
            "COOKIE_SECURE": os.environ.get("COOKIE_SECURE"),
            "ENV": os.environ.get("ENV"),
        }
        cls.db_path = "test_gate2_auth.db"
        from conftest import _safe_remove_db
        _safe_remove_db(cls.db_path)
        os.environ["CERTOPS_DB_PATH"] = cls.db_path
        os.environ["DB_PATH"] = cls.db_path
        db.run_migrations(cls.db_path)

        # Seed admin and viewer users
        admin_pass_hash = auth.hash_password("admin_secret_123")
        viewer_pass_hash = auth.hash_password("viewer_secret_123")
        db.create_user("admin@example.com", admin_pass_hash, "admin", db_path=cls.db_path)
        db.create_user("viewer@example.com", viewer_pass_hash, "viewer", db_path=cls.db_path)

        cls.client = TestClient(api.app)

    @classmethod
    def tearDownClass(cls):
        from conftest import _safe_remove_db
        _safe_remove_db(cls.db_path)
        for k, val in cls.orig_env.items():
            if val is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = val

    def test_01_admin_login_receives_httponly_cookie(self):
        print("\n=== TEST 1: Admin Login & httpOnly Cookie Verification ===")
        resp = self.client.post(
            "/auth/login",
            json={"email": "admin@example.com", "password": "admin_secret_123"},
        )
        self.assertEqual(resp.status_code, 200)
        cookie_header = resp.headers.get("set-cookie", "")
        print(f"[SET-COOKIE HEADER RECEIVED] {cookie_header}")
        self.assertIn("certops_token=", cookie_header)
        self.assertIn("HttpOnly", cookie_header)
        self.assertIn("SameSite=strict", cookie_header)

    def test_02_viewer_rejected_on_mutating_actions(self):
        print("\n=== TEST 2: Viewer Mutating Action Rejection Verification ===")
        # 1. Login as viewer
        login_resp = self.client.post(
            "/auth/login",
            json={"email": "viewer@example.com", "password": "viewer_secret_123"},
        )
        self.assertEqual(login_resp.status_code, 200)

        # 2. Viewer attempts mutating action (POST /api/groups)
        resp = self.client.post(
            "/api/groups",
            json={"name": "Attacker Group", "description": "Should fail"},
        )
        print(f"[VIEWER MUTATING ATTEMPT] POST /api/groups -> status {resp.status_code}: {resp.json()}")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"], "Admin access required")

    def test_03_admin_invite_flow_and_new_user_signup(self):
        print("\n=== TEST 3: Admin Invite Flow & New User Signup ===")
        # 1. Login as admin
        admin_login = self.client.post(
            "/auth/login",
            json={"email": "admin@example.com", "password": "admin_secret_123"},
        )
        self.assertEqual(admin_login.status_code, 200)

        # 2. Admin generates invite link stub
        invite_resp = self.client.post(
            "/auth/invites",
            json={"email": "newdev@example.com", "role": "viewer", "expires_in_hours": 24},
        )
        self.assertEqual(invite_resp.status_code, 200)
        invite_data = invite_resp.json()
        print(f"[ADMIN INVITE GENERATED] email='{invite_data['email']}', invite_url='{invite_data['invite_url']}'")

        # 3. Logout admin client so cookies are clear
        self.client.cookies.clear()

        # 4. New user registers using the invite token
        signup_resp = self.client.post(
            "/auth/register-with-invite",
            json={"token": invite_data["invite_token"], "password": "newdev_secure_pass"},
        )
        self.assertEqual(signup_resp.status_code, 200)
        signup_data = signup_resp.json()
        print(f"[INVITE SIGNUP COMPLETED] New user created: {signup_data}")
        self.assertEqual(signup_data["email"], "newdev@example.com")
        self.assertEqual(signup_data["role"], "viewer")

        # Verify new user received httpOnly cookie on signup
        cookie_header = signup_resp.headers.get("set-cookie", "")
        self.assertIn("certops_token=", cookie_header)
        self.assertIn("HttpOnly", cookie_header)

    def test_04_route_by_route_rbac_audit_table(self):
        print("\n=== TEST 4: Full Route-by-Route RBAC Classification Audit ===")
        print(f"{'METHOD':<8} {'PATH':<45} {'CLASSIFICATION':<18} {'DEPENDENCY GATE'}")
        print("-" * 105)

        route_classifications = []
        for route in api.app.routes:
            if not hasattr(route, "path"):
                continue
            path = route.path
            methods = list(route.methods - {"HEAD", "OPTIONS"}) if hasattr(route, "methods") else ["ANY"]
            method = methods[0] if methods else "ANY"

            # Check dependencies
            deps = [d.dependency.__name__ for d in getattr(route, "dependencies", []) if hasattr(d.dependency, "__name__")]
            # Also check parameter defaults and nested dependencies for Depends
            if hasattr(route, "dependant"):
                def _collect_deps(dependant):
                    names = []
                    for dep in dependant.dependencies:
                        if hasattr(dep.call, "__name__"):
                            names.append(dep.call.__name__)
                        names.extend(_collect_deps(dep))
                    return names
                deps.extend(_collect_deps(route.dependant))

            if "require_admin" in deps or any(d.startswith("require_plan_") for d in deps):
                classification = "Admin-Only"
                gate = "Depends(require_admin)" + (" + require_plan" if any(d.startswith("require_plan_") for d in deps) else "")
            elif "get_current_user" in deps:
                classification = "Viewer-Allowed"
                gate = "Depends(get_current_user)"
            elif path in ("/api/health", "/auth/login", "/auth/logout", "/auth/register-with-invite"):
                classification = "Public"
                gate = "Public / Token-Validated"
            elif path in ("/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"):
                classification = "Framework / Public"
                gate = "OpenAPI Metadata"
            else:
                classification = "UNCLASSIFIED"
                gate = f"Deps: {deps}"

            print(f"{method:<8} {path:<45} {classification:<18} {gate}")
            route_classifications.append((method, path, classification))
            self.assertNotEqual(classification, "UNCLASSIFIED", f"Route {method} {path} left unclassified!")

    def test_05_secure_cookie_when_env_flag_set(self):
        print("\n=== TEST 5: Secure Cookie Flag Negative & Positive Conditional Verification ===")

        # --- Negative Case: ENV unset/development and COOKIE_SECURE unset/false (dev HTTP loop) ---
        os.environ["ENV"] = "development"
        os.environ["COOKIE_SECURE"] = "false"
        try:
            resp_dev = self.client.post(
                "/auth/login",
                json={"email": "admin@example.com", "password": "admin_secret_123"},
            )
            self.assertEqual(resp_dev.status_code, 200)
            header_dev = resp_dev.headers.get("set-cookie", "")
            print(f"[NEGATIVE CASE (DEV HTTP)] Set-Cookie: {header_dev}")
            cookie_parts_dev = [part.strip().lower() for part in header_dev.split(";")]
            self.assertNotIn("secure", cookie_parts_dev, "Secure flag should be ABSENT in dev mode so HTTP login works!")
            self.assertIn("samesite=strict", cookie_parts_dev)

            # --- Positive Case 1: ENV=production ---
            os.environ["ENV"] = "production"
            os.environ["COOKIE_SECURE"] = "false"
            resp_prod = self.client.post(
                "/auth/login",
                json={"email": "admin@example.com", "password": "admin_secret_123"},
            )
            self.assertEqual(resp_prod.status_code, 200)
            header_prod = resp_prod.headers.get("set-cookie", "")
            print(f"[POSITIVE CASE (ENV=production)] Set-Cookie: {header_prod}")
            cookie_parts_prod = [part.strip().lower() for part in header_prod.split(";")]
            self.assertIn("secure", cookie_parts_prod, "Secure flag MUST be present when ENV=production!")

            # --- Positive Case 2: COOKIE_SECURE=true ---
            os.environ["ENV"] = "development"
            os.environ["COOKIE_SECURE"] = "true"
            resp_secure = self.client.post(
                "/auth/login",
                json={"email": "admin@example.com", "password": "admin_secret_123"},
            )
            self.assertEqual(resp_secure.status_code, 200)
            header_secure = resp_secure.headers.get("set-cookie", "")
            print(f"[POSITIVE CASE (COOKIE_SECURE=true)] Set-Cookie: {header_secure}")
            cookie_parts_secure = [part.strip().lower() for part in header_secure.split(";")]
            self.assertIn("secure", cookie_parts_secure, "Secure flag MUST be present when COOKIE_SECURE=true!")
        finally:
            os.environ["ENV"] = "development"
            os.environ["COOKIE_SECURE"] = "false"


if __name__ == "__main__":
    unittest.main()
