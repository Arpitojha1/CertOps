import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import sys
from pathlib import Path
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))
_sibling = _root.parent / "certops-agent"
if _sibling.exists() and str(_sibling) not in sys.path:
    sys.path.insert(0, str(_sibling))

from src import api, db
from src.api import app
from src.host_connector import SSHHostConnector


def _make_self_signed_pem() -> str:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import Encoding
    from datetime import datetime, timedelta, timezone

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "local.test")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=825))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(Encoding.PEM).decode("utf-8")



class TestGate3ConnectorUIAndThresholds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orig_env = {
            "CERTOPS_DB_PATH": os.environ.get("CERTOPS_DB_PATH"),
            "DB_PATH": os.environ.get("DB_PATH"),
            "ENV": os.environ.get("ENV"),
            "COOKIE_SECURE": os.environ.get("COOKIE_SECURE"),
        }
        cls.db_path = "./test_gate3_connectors.db"
        from conftest import _safe_remove_db
        _safe_remove_db(cls.db_path)
        os.environ["CERTOPS_DB_PATH"] = cls.db_path
        os.environ["DB_PATH"] = cls.db_path
        os.environ["ENV"] = "development"
        os.environ["COOKIE_SECURE"] = "false"
        db.run_migrations(cls.db_path)

        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        from conftest import _safe_remove_db
        _safe_remove_db(cls.db_path)
        for k, val in cls.orig_env.items():
            if val is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = val

    def setUp(self):
        # Reset DB before each test
        from conftest import _safe_remove_db
        _safe_remove_db(self.db_path)
        db.run_migrations(self.db_path)

        from src import auth
        admin_pass_hash = auth.hash_password("admin_secret_123")
        viewer_pass_hash = auth.hash_password("viewer_secret_123")
        db.create_user("admin@example.com", admin_pass_hash, "admin", db_path=self.db_path)
        db.create_user("viewer@example.com", viewer_pass_hash, "viewer", db_path=self.db_path)

        # Login admin and viewer sessions
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

    def test_01_viewer_can_list_but_rejected_on_mutating_connectors(self):
        print("\n=== TEST 1: Viewer Can List Connectors But Rejected On Mutating Endpoints ===")

        # Viewer can read connectors list
        resp_list = self.client.get("/api/connectors", cookies=self.viewer_cookie)
        self.assertEqual(resp_list.status_code, 200)
        connectors = resp_list.json()
        print(f"[VIEWER LIST CONNECTORS] Found {len(connectors)} default connector(s).")
        self.assertGreaterEqual(len(connectors), 4)

        # Viewer cannot create connector
        resp_post = self.client.post(
            "/api/connectors",
            json={
                "name": "unauthorized_ca",
                "category": "ca",
                "renewal_threshold_days": 10.0,
            },
            cookies=self.viewer_cookie,
        )
        print(f"[VIEWER CREATE ATTEMPT] POST /api/connectors -> status {resp_post.status_code}: {resp_post.json()}")
        self.assertEqual(resp_post.status_code, 403)

        # Viewer cannot update connector
        first_id = connectors[0]["id"]
        resp_put = self.client.put(
            f"/api/connectors/{first_id}",
            json={"renewal_threshold_days": 99.0},
            cookies=self.viewer_cookie,
        )
        print(f"[VIEWER UPDATE ATTEMPT] PUT /api/connectors/{first_id} -> status {resp_put.status_code}: {resp_put.json()}")
        self.assertEqual(resp_put.status_code, 403)

        # Viewer cannot delete connector
        resp_del = self.client.delete(
            f"/api/connectors/{first_id}",
            cookies=self.viewer_cookie,
        )
        print(f"[VIEWER DELETE ATTEMPT] DELETE /api/connectors/{first_id} -> status {resp_del.status_code}: {resp_del.json()}")
        self.assertEqual(resp_del.status_code, 403)

    def test_02_admin_connector_crud_and_test_connectivity(self):
        print("\n=== TEST 2: Admin Connector CRUD & Test Connectivity ===")

        # Create new connector
        payload = {
            "name": "digicert_ca",
            "category": "ca",
            "renewal_threshold_days": 14.0,
            "config": {"url": "https://digicert.example.com/api"},
            "is_active": True,
        }
        resp_create = self.client.post("/api/connectors", json=payload, cookies=self.admin_cookie)
        self.assertEqual(resp_create.status_code, 200)
        created = resp_create.json()
        print(f"[ADMIN CREATED CONNECTOR] id={created['id']}, name='{created['name']}', threshold={created['renewalThresholdDays']}d")
        self.assertEqual(created["name"], "digicert_ca")
        self.assertEqual(created["renewalThresholdDays"], 14.0)

        # Update connector threshold
        cid = created["id"]
        resp_update = self.client.put(
            f"/api/connectors/{cid}",
            json={"renewal_threshold_days": 21.0},
            cookies=self.admin_cookie,
        )
        self.assertEqual(resp_update.status_code, 200)
        updated = resp_update.json()
        print(f"[ADMIN UPDATED CONNECTOR] id={cid}, new threshold={updated['renewalThresholdDays']}d")
        self.assertEqual(updated["renewalThresholdDays"], 21.0)

        # Test connector connectivity
        resp_test = self.client.post(f"/api/connectors/{cid}/test", cookies=self.admin_cookie)
        self.assertEqual(resp_test.status_code, 200)
        test_out = resp_test.json()
        print(f"[ADMIN TEST CONNECTOR] success={test_out['success']}, msg='{test_out['message']}'")
        self.assertTrue(test_out["success"])

        # Delete connector
        resp_del = self.client.delete(f"/api/connectors/{cid}", cookies=self.admin_cookie)
        self.assertEqual(resp_del.status_code, 200)
        print(f"[ADMIN DELETED CONNECTOR] id={cid}")

    def test_03_per_connector_renewal_threshold_controls_due_status(self):
        print("\n=== TEST 3: Per-Connector Renewal Threshold Dynamically Controls Certificate Due Status ===")

        # 1. Insert a certificate under connector 'hashicorp' expiring in exactly 10 days
        expiry_dt = datetime.now(timezone.utc) + timedelta(days=10)
        db.upsert_certificate(
            vault_source="hashicorp",
            name="app.certops.local",
            expiry_utc=expiry_dt.isoformat(),
            common_name="app.certops.local",
            connector_category="secret_store",
            db_path=self.db_path,
        )

        # Find the 'hashicorp' connector ID
        connectors = self.client.get("/api/connectors", cookies=self.admin_cookie).json()
        hashicorp_conn = next(c for c in connectors if c["name"] == "hashicorp")
        cid = hashicorp_conn["id"]

        # 2. Set hashicorp connector threshold to 5.0 days (< 10 days remaining)
        self.client.put(
            f"/api/connectors/{cid}",
            json={"renewal_threshold_days": 5.0},
            cookies=self.admin_cookie,
        )
        print(f"[CONNECTOR THRESHOLD SET] 'hashicorp' threshold = 5.0 days. Cert lifetime = 10.0 days.")

        resp_due1 = self.client.get("/api/certificates/due?vault_source=hashicorp", cookies=self.viewer_cookie)
        due_certs1 = resp_due1.json()
        print(f"[CHECK DUE CERTS AT 5.0d THRESHOLD] Count due = {len(due_certs1)}")
        self.assertEqual(len(due_certs1), 0, "Cert expiring in 10 days should NOT be due when connector threshold is 5 days!")

        # 3. Now update hashicorp connector threshold to 15.0 days (> 10 days remaining)
        self.client.put(
            f"/api/connectors/{cid}",
            json={"renewal_threshold_days": 15.0},
            cookies=self.admin_cookie,
        )
        print(f"[CONNECTOR THRESHOLD UPDATED] 'hashicorp' threshold = 15.0 days. Cert lifetime = 10.0 days.")

        resp_due2 = self.client.get("/api/certificates/due?vault_source=hashicorp", cookies=self.viewer_cookie)
        due_certs2 = resp_due2.json()
        print(f"[CHECK DUE CERTS AT 15.0d THRESHOLD] Count due = {len(due_certs2)}")
        self.assertEqual(len(due_certs2), 1, "Cert expiring in 10 days MUST be due when connector threshold is updated to 15 days!")
        cert_out = due_certs2[0]
        print(f"  -> Due cert name='{cert_out['name']}', daysRemaining={cert_out['daysRemaining']:.2f}, effective_threshold={cert_out['renewalThresholdDays']}d")
        self.assertEqual(cert_out["renewalThresholdDays"], 15.0)

    def test_04_hardening_evidence_verification(self):
        print("\n=== TEST 4: Hardening Evidence (Encryption at Rest, Redaction, Stub Labeling, Fresh Init, Cascade Block) ===")

        # 1. Credential Encryption at Rest & 2. Field-Level Redaction
        resp = self.client.post(
            "/api/connectors",
            json={
                "name": "encrypted_vault",
                "category": "secret_store",
                "renewal_threshold_days": 14.0,
                "config": {
                    "url": "https://vault.example.com:8200",
                    "token": "s.supersecrettoken12345",
                    "password": "secretpassword",
                },
            },
            cookies=self.admin_cookie,
        )
        self.assertEqual(resp.status_code, 200)
        created = resp.json()
        cid = created["id"]

        # Inspect RAW SQLite database row to verify encryption at rest
        conn = db.get_db_connection(self.db_path)
        try:
            raw_row = conn.execute("SELECT config FROM connectors WHERE id = ?", (cid,)).fetchone()
            raw_cfg_str = raw_row[0]
        finally:
            conn.close()
        print(f"[1. RAW SQLITE CONFIG AT REST] {raw_cfg_str}")
        self.assertIn("ENC:v1:", raw_cfg_str, "Raw SQLite config MUST be encrypted at rest!")
        self.assertNotIn("s.supersecrettoken12345", raw_cfg_str, "Plaintext token MUST NOT appear in SQLite raw config!")

        # Verify internal backend decryption works
        decrypted = db.decrypt_config(raw_cfg_str)
        self.assertEqual(decrypted["token"], "s.supersecrettoken12345")

        # 2. Verify GET /api/connectors redacts sensitive fields for viewer/api response
        resp_get = self.client.get("/api/connectors", cookies=self.viewer_cookie)
        found = [c for c in resp_get.json() if c["id"] == cid][0]
        print(f"[2. FIELD-LEVEL REDACTION IN GET RESPONSE] config = {found['config']}")
        self.assertEqual(found["config"]["token"], "********")
        self.assertEqual(found["config"]["password"], "********")
        self.assertEqual(found["config"]["url"], "https://vault.example.com:8200")

        # 3. Honest Stub Labeling on Test Connection
        resp_test = self.client.post(f"/api/connectors/{cid}/test", cookies=self.admin_cookie)
        test_data = resp_test.json()
        print(f"[3. HONEST STUB LABELING] {test_data}")
        self.assertTrue(test_data.get("is_stub"), "Test connection MUST explicitly state is_stub=True")
        self.assertIn("[STUB]", test_data["message"])

        # 4. Clean Schema Initialization from Fresh DB
        fresh_db_path = "test_fresh_init_gate3.db"
        if os.path.exists(fresh_db_path):
            os.remove(fresh_db_path)
        db.run_migrations(fresh_db_path)
        try:
            conn_fresh = db.get_db_connection(fresh_db_path)
            rows = conn_fresh.execute("SELECT name, renewal_threshold_days FROM connectors").fetchall()
            conn_fresh.close()
            print(f"[4. CLEAN FRESH DB INITIALIZATION] Initialized {len(rows)} default connector(s): {rows}")
            self.assertEqual(len(rows), 4)
            for row in rows:
                self.assertIsNone(row[1], f"Default connector {row[0]} threshold should be None on fresh init")
        finally:
            db.close_db_connection(fresh_db_path)
            if os.path.exists(fresh_db_path):
                os.remove(fresh_db_path)

        # 5. Cascade Delete Blocking
        conn_test = db.get_db_connection(self.db_path)
        try:
            conn_test.execute(
                "INSERT INTO certificates (vault_source, name, expiry_utc, version, common_name, connector_category) VALUES (?, ?, ?, ?, ?, ?)",
                ("hashicorp", "dep-cert-01", "2026-08-01T00:00:00Z", "1", "dep.certops.local", "secret_store"),
            )
            conn_test.commit()
        finally:
            conn_test.close()

        resp_block = self.client.delete("/api/connectors/1", cookies=self.admin_cookie)
        print(f"[5. CASCADE DELETE SAFETY BLOCKING] DELETE /api/connectors/1 -> status {resp_block.status_code}: {resp_block.json()}")
        self.assertEqual(resp_block.status_code, 409)
        self.assertIn("certificate(s) are currently tracked under this connector", resp_block.json()["detail"])

    def test_05_credential_encryption_roundtrip_and_decrypted_creds_used(self):
        print("\n=== TEST 5: Credential Encryption Round-Trip & Decrypted Creds Reach SSH Transport (mocked) ===")
        resp = self.client.post(
            "/api/connectors",
            json={
                "name": "live_ssh_test",
                "category": "host",
                "renewal_threshold_days": 30.0,
                "config": {
                    "hostname": "test-host.invalid",
                    "port": 2222,
                    "username": "root",
                    "password": "certops",
                    "nginx_conf_dir": "/etc/nginx/certs",
                },
            },
            cookies=self.admin_cookie,
        )
        self.assertEqual(resp.status_code, 200)
        cid = resp.json()["id"]

        # 5A. Ciphertext at rest
        conn = db.get_db_connection(self.db_path)
        try:
            raw_cfg_str = conn.execute("SELECT config FROM connectors WHERE id = ?", (cid,)).fetchone()[0]
        finally:
            conn.close()
        print(f"[5A. RAW SQLITE CIPHERTEXT AT REST] {raw_cfg_str}")
        self.assertIn("ENC:v1:", raw_cfg_str)
        self.assertNotIn("certops", raw_cfg_str)

        # 5B. Decryption round-trip
        db_connector = db.get_connector(cid, db_path=self.db_path)
        decrypted_cfg = db.decrypt_config(db_connector["config"])
        print(f"[5B. DECRYPTED CONFIG FOR BACKEND RUNTIME] password='{decrypted_cfg['password']}'")
        self.assertEqual(decrypted_cfg["password"], "certops")

        # 5C. Prove the DECRYPTED creds are what the connector would use, WITHOUT any live host.
        #     Mock paramiko.SSHClient so discover_certificates() runs fully offline.
        fake_pem = _make_self_signed_pem()  # in-memory, no disk, no network, no real certs

        mock_client = MagicMock()
        # exec_command -> (stdin, stdout, stderr); stdout yields the nginx ssl_certificate line
        def _fake_exec(cmd, timeout=None):
            out = MagicMock()
            if "ssl_certificate_key" in cmd:
                out.read.return_value = b""
            elif "ssl_certificate" in cmd:
                out.read.return_value = b"/etc/nginx/certs/local.conf:1:    ssl_certificate /etc/nginx/certs/local.crt;\n"
            else:
                out.read.return_value = b""
            out.channel.recv_exit_status.return_value = 0
            err = MagicMock(); err.read.return_value = b""
            return (MagicMock(), out, err)
        mock_client.exec_command.side_effect = _fake_exec

        # SFTP file read -> our in-memory PEM
        fake_file = MagicMock()
        fake_file.read.return_value = fake_pem.encode("utf-8")
        fake_file.__enter__ = lambda s: fake_file
        fake_file.__exit__ = lambda s, *a: False
        mock_client.open_sftp.return_value.open.return_value = fake_file

        with patch("src.host_connector.paramiko.SSHClient", return_value=mock_client):
            ssh_connector = SSHHostConnector.from_config(decrypted_cfg)
            discovered = ssh_connector.discover_certificates()

        # The decrypted password must have been passed to the transport
        _, connect_kwargs = mock_client.connect.call_args
        self.assertEqual(connect_kwargs.get("password"), "certops")
        print(f"[5C. MOCKED ROUND-TRIP DISCOVERED CERTS] {discovered}")
        self.assertGreaterEqual(len(discovered), 1,
                                "Must discover host cert using decrypted SSH credentials (mocked transport)!")


if __name__ == "__main__":
    unittest.main()
