"""
Orchestrates the multi-vault and multi-host certificate renewal loop.
Processes SecretStoreConnectors (HashiCorp Vault, Azure Key Vault) and HostConnectors (SSH/Nginx, WinRM/IIS).
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

if __package__ is None or __package__ == "":
    import azurekeyvault
    import ca_client
    import db
    import host_connector
    import notifier
    import vault_client
    import verify
else:
    from . import azurekeyvault, ca_client, db, host_connector, notifier, vault_client, verify

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("paramiko").setLevel(logging.WARNING)


class RenewalSummary(dict):
    """
    Holds per-connector summary statistics and evaluates to True if at least one cert succeeded.
    """
    def __bool__(self) -> bool:
        return any(
            isinstance(v, dict) and v.get("succeeded", 0) > 0 for v in self.values()
        )


def atomic_deploy_file(dest_path: str, content: str, make_backup: bool = True) -> None:
    """
    Writes content to dest_path atomically using a temporary file and os.replace.
    Optionally creates a .bak copy of existing destination file before overwrite.
    """
    dest = Path(dest_path).resolve()
    if make_backup and dest.exists():
        backup_path = dest.with_name(f"{dest.name}.bak")
        shutil.copy2(dest, backup_path)

    tmp_path = dest.with_name(f"{dest.name}.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)

    os.replace(tmp_path, dest)


def _deploy_and_verify_nginx(
    cert_pem: str, key_pem: str, verify_host: str, verify_port: int, nginx_container: str
) -> None:
    deploy_cert_path = os.getenv("DEPLOY_CERT_PATH", "./local.crt")
    deploy_key_path = os.getenv("DEPLOY_KEY_PATH", "./local.key")

    atomic_deploy_file(deploy_cert_path, cert_pem, make_backup=True)
    atomic_deploy_file(deploy_key_path, key_pem, make_backup=True)

    reload_cmd = ["docker", "exec", nginx_container, "nginx", "-s", "reload"]
    res = subprocess.run(reload_cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(
            f"Failed to reload Nginx container '{nginx_container}' (exit {res.returncode}):\n"
            f"Stdout: {res.stdout}\nStderr: {res.stderr}"
        )

    expected_expiry, expected_fp = verify.get_pem_cert_info(cert_pem)
    live_expiry, live_fp = None, None
    for _ in range(10):
        try:
            live_expiry, live_fp = verify.get_live_cert_info(verify_host, verify_port)
            if live_fp == expected_fp and live_expiry == expected_expiry:
                break
        except Exception:
            pass
        time.sleep(0.5)

    if live_fp != expected_fp or live_expiry != expected_expiry:
        raise RuntimeError(
            f"Verification FAILED: Live served certificate does not match newly issued cert!\n"
            f"Expected SHA256: {expected_fp} (Expiry: {expected_expiry})\n"
            f"Live SHA256:     {live_fp} (Expiry: {live_expiry})"
        )


def get_active_connectors() -> list[Any]:
    """
    Returns active connectors from DB 'connectors' table authoritative first
    when any connector has explicit DB configuration.
    Falls back to environment variables when DB connector configs are empty defaults.
    """
    connectors = []
    try:
        db_rows = db.list_connectors(active_only=True)
        configured_rows = []
        for row in db_rows:
            cfg = db.decrypt_config(row.get("config", "{}"))
            if cfg:
                configured_rows.append((row, cfg))

        if configured_rows:
            for row, cfg in configured_rows:
                cname = row["name"]
                cat = (row.get("category") or "").lower()
                thresh = row.get("renewal_threshold_days")
                try:
                    if cat in ("secret_store", "hashicorp", "vault") or "hashicorp" in cname.lower() or "vault" in cname.lower():
                        vault_addr = cfg.get("url") or cfg.get("vault_addr") or cfg.get("VAULT_ADDR") or "http://localhost:8200"
                        vault_token = cfg.get("token") or cfg.get("vault_token") or cfg.get("VAULT_TOKEN") or ""
                        c = vault_client.HashiCorpVaultClient(vault_addr=vault_addr, vault_token=vault_token, renewal_threshold_days=thresh)
                        c.name = cname
                        connectors.append(c)
                    elif cat == "azure" or "azure" in cname.lower():
                        c = azurekeyvault.AzureKeyVaultClient.from_env(renewal_threshold_days=thresh)
                        c.name = cname
                        connectors.append(c)
                    elif cat in ("host", "ssh_host", "ssh") or "ssh" in cname.lower():
                        host = cfg.get("hostname") or cfg.get("host", "localhost")
                        port = int(cfg.get("port", 22))
                        username = cfg.get("username", "root")
                        password = cfg.get("password")
                        key_filename = cfg.get("key_filename")
                        c = host_connector.SSHHostConnector(
                            hostname=host,
                            port=port,
                            username=username,
                            password=password,
                            key_filename=key_filename,
                            renewal_threshold_days=thresh,
                        )
                        c.name = cname
                        connectors.append(c)
                    elif cat in ("winrm_host", "winrm") or "winrm" in cname.lower():
                        c = host_connector.WinRMHostConnector.from_env(renewal_threshold_days=thresh)
                        c.name = cname
                        connectors.append(c)
                except Exception as exc:
                    logger.error("Failed to instantiate DB connector '%s': %s", cname, exc)
            if connectors:
                return connectors
    except Exception as exc:
        logger.warning("Could not query DB connectors table (%s), falling back to env vars.", exc)

    # Check numbered registry fallback (CONNECTOR_1_TYPE, CONNECTOR_2_TYPE, ...)
    for i in range(1, 20):
        ctype = os.getenv(f"CONNECTOR_{i}_TYPE")
        if not ctype:
            continue
        thresh_str = os.getenv(f"CONNECTOR_{i}_THRESHOLD_DAYS")
        thresh = float(thresh_str) if thresh_str else None
        ctype_lower = ctype.lower().strip()
        if ctype_lower in ("hashicorp", "vault", "secret_store"):
            connectors.append(vault_client.HashiCorpVaultClient.from_env(renewal_threshold_days=thresh))
        elif ctype_lower == "azure":
            connectors.append(azurekeyvault.AzureKeyVaultClient.from_env(renewal_threshold_days=thresh))
        elif ctype_lower in ("ssh_host", "ssh"):
            connectors.append(host_connector.SSHHostConnector.from_env(renewal_threshold_days=thresh))
        elif ctype_lower in ("winrm_host", "winrm"):
            connectors.append(host_connector.WinRMHostConnector.from_env(renewal_threshold_days=thresh))

    if connectors:
        return connectors

    # Fallback auto-detection for backwards compatibility
    if os.getenv("VAULT_ADDR") and os.getenv("VAULT_TOKEN"):
        try:
            connectors.append(vault_client.HashiCorpVaultClient.from_env())
        except Exception as exc:
            logger.error("Failed to instantiate HashiCorpVaultClient: %s", exc)

    if os.getenv("AZURE_KEYVAULT_URL"):
        try:
            connectors.append(azurekeyvault.AzureKeyVaultClient.from_env())
        except Exception as exc:
            logger.error("Failed to instantiate AzureKeyVaultClient: %s", exc)

    if os.getenv("ENABLE_SSH_HOST", "").lower() in ("true", "1", "yes"):
        try:
            connectors.append(host_connector.SSHHostConnector.from_env())
        except Exception as exc:
            logger.error("Failed to instantiate SSHHostConnector: %s", exc)

    if os.getenv("ENABLE_WINRM_HOST", "").lower() in ("true", "1", "yes"):
        try:
            connectors.append(host_connector.WinRMHostConnector.from_env())
        except Exception as exc:
            logger.error("Failed to instantiate WinRMHostConnector: %s", exc)

    return connectors


def confirm_and_reload_host(
    connector_name: str,
    cert_id: str,
    verify_host: str | None = None,
    verify_port: int | None = None,
) -> bool:
    """
    Explicit confirmation step to trigger service reload on a host connector
    and verify the live served certificate TLS fingerprint.
    """
    load_dotenv()
    if verify_host is None:
        verify_host = os.getenv("VERIFY_HOST", "localhost")
    if verify_port is None:
        verify_port = int(os.getenv("VERIFY_PORT", "443"))

    connector: host_connector.HostConnector
    if connector_name == "ssh_host":
        connector = host_connector.SSHHostConnector.from_env()
    elif connector_name == "winrm_host":
        connector = host_connector.WinRMHostConnector.from_env()
    else:
        raise RuntimeError(f"Unknown host connector type: '{connector_name}'")

    db_rec = db.get_certificate(connector_name, cert_id)
    if not db_rec:
        raise RuntimeError(f"Certificate '{cert_id}' for connector '{connector_name}' not found in DB.")

    gid = db_rec.get("group_id")
    if not db.is_group_in_maintenance_window(gid):
        print(f"[MAINTENANCE WINDOW HOLD] Certificate '{cert_id}' (group ID={gid}) is outside active maintenance window. Reload held.")
        db.update_pipeline_stage(connector_name, cert_id, "Hold: outside maintenance window")
        return False

    stage = db_rec.get("pipeline_stage")
    if stage not in ("Deployed, pending reload", "Deployed pending reload"):
        logger.warning(
            "Certificate '%s' is in pipeline_stage='%s' (expected 'Deployed pending reload'). Proceeding with explicit reload.",
            cert_id,
            stage,
        )

    print(f"[RELOAD CONFIRMATION] Triggering service reload for '{cert_id}' via connector '{connector_name}'...")
    reload_res = connector.trigger_reload(cert_id=cert_id)
    if not reload_res.success:
        raise RuntimeError(f"Service reload FAILED for '{cert_id}':\n{reload_res.output}")

    print(f"Service reload output:\n{reload_res.output}")

    # Read deployed cert to know expected fingerprint
    cert_data = connector.read_certificate(cert_id)
    expected_expiry, expected_fp = verify.get_pem_cert_info(cert_data.cert_pem)

    live_expiry, live_fp = None, None
    for _ in range(10):
        try:
            live_expiry, live_fp = verify.get_live_cert_info(verify_host, verify_port)
            if live_fp == expected_fp and live_expiry == expected_expiry:
                break
        except Exception:
            pass
        time.sleep(0.5)

    if live_fp != expected_fp or live_expiry != expected_expiry:
        raise RuntimeError(
            f"Verification FAILED: Live served certificate does not match newly deployed host cert!\n"
            f"Expected SHA256: {expected_fp} (Expiry: {expected_expiry})\n"
            f"Live SHA256:     {live_fp} (Expiry: {live_expiry})"
        )

    db.update_pipeline_stage(connector_name, cert_id, "Reload confirmed")
    print(f"[RELOAD CONFIRMED] Verification PASSED. Pipeline stage updated to 'Reload confirmed'.")
    return True


def run_notification_check(db_path: str | None = None) -> int:
    """
    Independent check pass that evaluates certificates against notification policies
    assigned to their group. Completely decoupled from auto-renewal.
    Deduplicates via notification_log table.
    """
    now_utc = datetime.now(timezone.utc)
    certs = db.list_all_certificates(db_path=db_path)
    sent_count = 0

    for c in certs:
        gid = c.get("group_id")
        if gid is None:
            continue
        policies = db.list_notification_policies(group_id=gid, db_path=db_path)
        if not policies:
            continue

        expiry_dt = c["expiry_utc"]
        remaining_days = (expiry_dt - now_utc).total_seconds() / 86400.0

        for p in policies:
            if remaining_days <= p["threshold_days"]:
                if not db.has_notification_been_sent(c["name"], p["id"], db_path=db_path):
                    notifier.dispatch_notification(
                        cert_name=c["name"],
                        vault_source=c["vault_source"],
                        remaining_days=remaining_days,
                        threshold_days=p["threshold_days"],
                    )
                    print(
                        f"[NOTIFICATION DELIVERED] Certificate '{c['name']}' lifetime ({remaining_days:.2f}d) "
                        f"<= Policy threshold ({p['threshold_days']}d). Logging notification."
                    )
                    db.record_notification_sent(c["vault_source"], c["name"], p["id"], db_path=db_path)
                    sent_count += 1
                else:
                    print(
                        f"[NOTIFICATION DEDUPLICATED] Notification for certificate '{c['name']}' "
                        f"under policy ID={p['id']} already sent."
                    )
    return sent_count



def run_renewal_loop() -> RenewalSummary:
    """
    Runs the multi-vault and multi-host certificate renewal loop.
    Returns a RenewalSummary containing statistics per connector.
    """
    load_dotenv()

    threshold_days = float(os.getenv("RENEWAL_THRESHOLD_DAYS", "2"))
    password_file = os.getenv("STEP_CA_PASSWORD_FILE", "./pass.txt")
    ca_url = os.getenv("STEP_CA_URL", "https://localhost:8443")
    fingerprint = os.getenv("STEP_CA_FINGERPRINT")

    verify_host = os.getenv("VERIFY_HOST", "localhost")
    verify_port = int(os.getenv("VERIFY_PORT", "443"))
    nginx_container = os.getenv("NGINX_CONTAINER_NAME", "certops-nginx-1")
    nginx_cert_name = os.getenv("VAULT_CERT_PATH", "secret/local-certs").split("/")[-1]

    summary = RenewalSummary()
    active_connectors = get_active_connectors()

    for connector in active_connectors:
        c_name = connector.name
        summary[c_name] = {"succeeded": 0, "skipped": 0, "failed": 0}

        if isinstance(connector, host_connector.HostConnector):
            try:
                print(f"\n[HOST CONNECTOR: {c_name}] Discovering certificates...")
                meta_list = connector.discover_certificates()
                print(f"[HOST CONNECTOR: {c_name}] Found {len(meta_list)} certificate(s).")
            except Exception as exc:
                logger.error("Host discovery failed for connector '%s': %s", c_name, exc)
                summary[c_name]["failed"] += 1
                continue

            for meta_item in meta_list:
                try:
                    db.upsert_certificate(
                        vault_source=c_name,
                        name=meta_item.cert_id,
                        expiry_utc=meta_item.expiry_utc,
                        common_name=meta_item.common_name,
                        connector_category="host",
                        pipeline_stage=None,
                        renewal_threshold_days=getattr(connector, "renewal_threshold_days", None),
                    )
                except Exception as exc:
                    logger.error("Failed to upsert host cert '%s' into DB: %s", meta_item.cert_id, exc)
                    summary[c_name]["failed"] += 1

            try:
                due_certs = db.get_due_certificates(vault_source=c_name, threshold_days=threshold_days)
            except Exception as exc:
                logger.error("Failed to query due host certificates for '%s': %s", c_name, exc)
                summary[c_name]["failed"] += 1
                continue

            due_map = {c["name"]: c.get("renewal_threshold_days", threshold_days) for c in due_certs}
            for meta_item in meta_list:
                cid = meta_item.cert_id
                now_utc = datetime.now(timezone.utc)
                rem_days = (meta_item.expiry_utc - now_utc).total_seconds() / 86400.0
                print(f"  - [{c_name}] Host cert '{cid}' expires at {meta_item.expiry_utc} ({rem_days:.4f} days remaining)")

                if cid not in due_map:
                    rec = db.get_certificate(c_name, cid)
                    evaluated_thresh = (rec.get("renewal_threshold_days") if rec else None) or threshold_days
                    print(f"    -> Host cert '{cid}' is not due (lifetime {rem_days:.4f} days > threshold {evaluated_thresh} days). Skipped.")
                    summary[c_name]["skipped"] += 1
                    continue

                evaluated_thresh = due_map[cid]
                print(f"    -> Host cert '{cid}' is due (lifetime <= {evaluated_thresh} days). Renewing...")
                try:
                    # Stage 1: Renewed
                    existing_data = connector.read_certificate(cid)
                    subject = existing_data.common_name or cid.split("/")[-1]
                    with db.renewal_context(c_name, "host", cid, existing_data.expiry_utc):
                        new_cert_pem, new_key_pem = ca_client.issue_certificate(
                            subject=subject,
                            password_file=password_file,
                            ca_url=ca_url,
                            fingerprint=fingerprint,
                        )
                    db.update_pipeline_stage(c_name, cid, "Renewed")

                    rec = db.get_certificate(c_name, cid)
                    gid = rec.get("group_id") if rec else None
                    if not db.is_group_in_maintenance_window(gid):
                        db.update_pipeline_stage(c_name, cid, "Hold: outside maintenance window")
                        print(f"    -> [MAINTENANCE WINDOW HOLD] Certificate '{cid}' renewed, but group ID={gid} is outside active maintenance window. Holding before deploy.")
                        summary[c_name]["succeeded"] += 1
                        db.log_activity(
                            event_type="certificate_renewed",
                            target=cid,
                            details={"connector_name": c_name, "category": "host", "old_expiry": existing_data.expiry_utc.isoformat(), "status": "held_pending_maintenance_window"},
                        )
                        continue

                    # Stage 2: Deployed, pending reload
                    new_expiry, _ = verify.get_pem_cert_info(new_cert_pem)
                    deploy_data = host_connector.CertData(
                        cert_id=cid,
                        cert_pem=new_cert_pem,
                        expiry_utc=new_expiry,
                        common_name=subject,
                        private_key_pem=new_key_pem,
                        key_path=meta_item.key_path,
                    )
                    connector.deploy_certificate(cid, deploy_data)
                    db.upsert_certificate(
                        vault_source=c_name,
                        name=cid,
                        expiry_utc=new_expiry,
                        common_name=subject,
                        connector_category="host",
                        pipeline_stage="Deployed, pending reload",
                        renewal_threshold_days=getattr(connector, "renewal_threshold_days", None),
                    )
                    summary[c_name]["succeeded"] += 1
                    db.log_activity(
                        event_type="certificate_renewed",
                        target=cid,
                        details={"connector_name": c_name, "category": "host", "old_expiry": existing_data.expiry_utc.isoformat(), "new_expiry": new_expiry.isoformat()},
                    )
                    print(
                        f"    -> Successfully deployed renewed cert '{cid}' to host '{c_name}'.\n"
                        f"       Pipeline status: 'Deployed, pending reload'. Requires explicit confirmation to reload."
                    )
                except Exception as exc:
                    logger.error("Failed renewing/deploying host cert '%s' on '%s': %s", cid, c_name, exc)
                    summary[c_name]["failed"] += 1
                    db.log_activity(
                        event_type="certificate_renewal_failed",
                        target=cid,
                        details={"connector_name": c_name, "category": "host", "error": str(exc)},
                    )

        else:
            # SecretStoreConnector (HashiCorp / Azure)
            try:
                print(f"\n[VAULT: {c_name}] Discovering certificates...")
                certs = connector.list_certificates()
                print(f"[VAULT: {c_name}] Found {len(certs)} certificate(s).")
            except Exception as exc:
                logger.error("Vault loop failed during list_certificates for '%s': %s", c_name, exc)
                summary[c_name]["failed"] += 1
                continue

            for cert_item in certs:
                try:
                    db.upsert_certificate(
                        vault_source=c_name,
                        name=cert_item["name"],
                        expiry_utc=cert_item["expiry_utc"],
                        version=cert_item.get("version"),
                        connector_category="secret_store",
                        renewal_threshold_days=getattr(connector, "renewal_threshold_days", None),
                    )
                except Exception as exc:
                    logger.error("Failed to upsert certificate name='%s' into DB: %s", cert_item["name"], exc)
                    summary[c_name]["failed"] += 1

            try:
                due_certs = db.get_due_certificates(vault_source=c_name, threshold_days=threshold_days)
            except Exception as exc:
                logger.error("Failed to query due certificates for '%s': %s", c_name, exc)
                summary[c_name]["failed"] += 1
                continue

            due_map = {c["name"]: c.get("renewal_threshold_days", threshold_days) for c in due_certs}
            for cert_item in certs:
                cname = cert_item["name"]
                now_utc = datetime.now(timezone.utc)
                dt = db._parse_utc_datetime(cert_item["expiry_utc"])
                rem_days = (dt - now_utc).total_seconds() / 86400.0
                print(f"  - [{c_name}] Cert '{cname}' expires at {dt} ({rem_days:.4f} days remaining)")

                if cname not in due_map:
                    rec = db.get_certificate(c_name, cname)
                    evaluated_thresh = (rec.get("renewal_threshold_days") if rec else None) or threshold_days
                    print(f"    -> Cert '{cname}' is not due (lifetime {rem_days:.4f} days > threshold {evaluated_thresh} days). Skipped.")
                    summary[c_name]["skipped"] += 1
                    continue

                evaluated_thresh = due_map[cname]
                print(f"    -> Cert '{cname}' is due (lifetime <= {evaluated_thresh} days). Renewing...")
                try:
                    cert_info = connector.get_certificate(cname)
                    subject = cert_info.get("common_name") or cname
                    with db.renewal_context(c_name, "secret_store", cname, dt):
                        new_cert_pem, new_key_pem = ca_client.issue_certificate(
                            subject=subject,
                            password_file=password_file,
                            ca_url=ca_url,
                            fingerprint=fingerprint,
                        )

                    write_res = connector.write_certificate(cname, new_cert_pem, new_key_pem)
                    db.upsert_certificate(
                        vault_source=c_name,
                        name=cname,
                        expiry_utc=write_res["expiry_utc"],
                        version=write_res.get("version"),
                        connector_category="secret_store",
                        renewal_threshold_days=getattr(connector, "renewal_threshold_days", None),
                    )

                    # Deploy to Nginx if this is the active reverse-proxy certificate in Phase 1 mode
                    if cname == nginx_cert_name and c_name == "hashicorp":
                        _deploy_and_verify_nginx(
                            new_cert_pem, new_key_pem, verify_host, verify_port, nginx_container
                        )

                    summary[c_name]["succeeded"] += 1
                    db.log_activity(
                        event_type="certificate_renewed",
                        target=cname,
                        details={"connector_name": c_name, "category": "secret_store", "old_expiry": dt.isoformat(), "new_expiry": write_res["expiry_utc"].isoformat()},
                    )
                    print(f"    -> Successfully renewed '{cname}' in vault '{c_name}'.")
                except Exception as exc:
                    logger.error("Certificate processing failed for name='%s' in '%s': %s", cname, c_name, exc)
                    summary[c_name]["failed"] += 1
                    db.log_activity(
                        event_type="certificate_renewal_failed",
                        target=cname,
                        details={"connector_name": c_name, "category": "secret_store", "error": str(exc)},
                    )

    print("\n" + "=" * 70)
    print("RENEWAL LOOP SUMMARY")
    print("=" * 70)
    for c_source, stats in summary.items():
        print(
            f"Connector: {c_source:<12} | Succeeded: {stats['succeeded']} | "
            f"Skipped: {stats['skipped']} | Failed: {stats['failed']}"
        )
    print("=" * 70)

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CertOps Renewal Loop and Host Reload Confirmation")
    parser.add_argument("--confirm-reload", nargs=2, metavar=("CONNECTOR", "CERT_ID"), help="Explicitly trigger reload and verify live cert")
    args = parser.parse_args()

    if args.confirm_reload:
        connector_name, cert_id = args.confirm_reload
        success = confirm_and_reload_host(connector_name, cert_id)
        sys.exit(0 if success else 1)

    run_renewal_loop()
    sys.exit(0)
