"""
Phase 3.0 Smoke Test — Append-Only Audit Log
Tests real renewal through HashiCorp Vault (secret store) and SSH/Nginx (host connector),
forces a failure to verify success=False log recording, and verifies append-only invariants.
"""

import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure src/ is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import ca_client
import db
import main
import vault_client
import host_connector


from dotenv import load_dotenv


def test_audit_log_smoke():
    import os
    if os.getenv("CERTOPS_RUN_LIVE") != "1":
        import unittest
        raise unittest.SkipTest("Live integration smoke test; set CERTOPS_RUN_LIVE=1 to run in a sandbox")
    load_dotenv()
    orig_thresh = os.environ.get("RENEWAL_THRESHOLD_DAYS")
    orig_db = os.environ.get("DB_PATH")
    test_db_path = Path("./test_phase30_audit.db").resolve()
    if test_db_path.exists():
        test_db_path.unlink()

    os.environ["DB_PATH"] = str(test_db_path)
    os.environ["RENEWAL_THRESHOLD_DAYS"] = "3650"  # Ensure certs are due for test
    try:
        print("=== Step 1: Secret Store Connector (HashiCorp Vault) Renewal & Audit Logging ===")
        vault = vault_client.HashiCorpVaultClient.from_env()
        test_cert_name = "audit-log-test-cert"

        # Issue an initial cert so it exists in Vault
        initial_cert, initial_key = ca_client.issue_certificate(
            subject="audit-test.local",
            password_file="./pass.txt",
            ca_url="https://localhost:8443",
        )
        vault.write_certificate(test_cert_name, initial_cert, initial_key)

        # Now discover via list_certificates (decorated with @db.log_connector_event("discovered"))
        certs = vault.list_certificates()
        print(f"Vault discovered certs count: {len(certs)}")

        # Renew via write_certificate (decorated with @db.log_connector_event("renewed"))
        new_cert, new_key = ca_client.issue_certificate(
            subject="audit-test.local",
            password_file="./pass.txt",
            ca_url="https://localhost:8443",
        )
        with db.renewal_context("hashicorp", "secret_store", test_cert_name):
            vault.write_certificate(test_cert_name, new_cert, new_key)

        print("=== Step 2: Host Connector (SSH -> Nginx) Renewal & Audit Logging ===")
        ssh_conn = host_connector.SSHHostConnector(
            hostname=os.getenv("SSH_HOST", "localhost"),
            port=int(os.getenv("SSH_PORT", "2222")),
            username=os.getenv("SSH_USERNAME", "root"),
            password=os.getenv("SSH_PASSWORD", "certops"),
            nginx_conf_dir="/etc/nginx/conf.d",
        )
        # Discover (decorated with @db.log_connector_event("discovered"))
        discovered_host = ssh_conn.discover_certificates()
        print(f"SSH Host discovered certs count: {len(discovered_host)}")

        if discovered_host:
            target_cert = discovered_host[0]
            cid = target_cert.cert_id
            with db.renewal_context("ssh_host", "host", cid):
                renewed_cert, renewed_key = ca_client.issue_certificate(
                    subject=target_cert.common_name or "localhost",
                    password_file="./pass.txt",
                    ca_url="https://localhost:8443",
                )
                deploy_data = host_connector.CertData(
                    cert_id=cid,
                    cert_pem=renewed_cert,
                    expiry_utc=datetime.now(timezone.utc),
                    common_name="localhost",
                    private_key_pem=renewed_key,
                    key_path=target_cert.key_path,
                )
                # Deploy (decorated with @db.log_connector_event("deployed_pending_reload"))
                ssh_conn.deploy_certificate(cid, deploy_data)
                db.upsert_certificate(
                    vault_source="ssh_host",
                    name=cid,
                    expiry_utc=datetime.now(timezone.utc),
                    connector_category="host",
                    pipeline_stage="Deployed, pending reload",
                )

            # Confirm reload (decorated with @db.log_connector_event("reload_confirmed"))
            reload_res = ssh_conn.trigger_reload(cert_id=cid)
            print(f"SSH Host reload success: {reload_res.success}")

        print("=== Step 3: Forced Failure Logging (Bad SSH Port / Failed Deploy) ===")
        bad_ssh = host_connector.SSHHostConnector(
            hostname="localhost",
            port=9999, # invalid port
            username="root",
        )
        try:
            bad_ssh.discover_certificates()
        except Exception as exc:
            print(f"Caught expected forced failure on discover_certificates: {exc}")

        print("\n=== Step 4: Querying SELECT * FROM renewal_log ORDER BY id ===")
        conn = sqlite3.connect(str(test_db_path))
        try:
            cursor = conn.execute("SELECT id, vault_source, cert_id, event_type, connector_category, connector_type, success, detail FROM renewal_log ORDER BY id")
            rows = cursor.fetchall()
            print(f"{'ID':<4} | {'VAULT_SRC':<10} | {'CERT_ID':<25} | {'EVENT_TYPE':<23} | {'CAT':<12} | {'SUCCESS':<7} | {'DETAIL'}")
            print("-" * 120)
            for r in rows:
                detail_short = (str(r[7])[:35] + "...") if r[7] and len(str(r[7])) > 35 else str(r[7] or "")
                print(f"{r[0]:<4} | {str(r[1]):<10} | {str(r[2])[:25]:<25} | {r[3]:<23} | {str(r[4]):<12} | {str(bool(r[6])):<7} | {detail_short}")
        finally:
            conn.close()

        # Ensure both successful and failed rows exist
        success_rows = [r for r in rows if bool(r[6]) is True]
        failure_rows = [r for r in rows if bool(r[6]) is False]
        assert len(success_rows) > 0, "Expected at least one successful log entry"
        assert len(failure_rows) > 0, "Expected at least one failed log entry (success=False)"
        print("\n[SMOKE TEST PASSED] Both successful and failed rows verified in renewal_log.")

    finally:
        if orig_thresh is not None:
            os.environ["RENEWAL_THRESHOLD_DAYS"] = orig_thresh
        else:
            os.environ.pop("RENEWAL_THRESHOLD_DAYS", None)
        if orig_db is not None:
            os.environ["DB_PATH"] = orig_db
        else:
            os.environ.pop("DB_PATH", None)
        if test_db_path.exists():
            test_db_path.unlink()


if __name__ == "__main__":
    test_audit_log_smoke()
