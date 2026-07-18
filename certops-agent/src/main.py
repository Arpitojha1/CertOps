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

_src_dir = Path(__file__).resolve().parent
_project_dir = _src_dir.parent
if str(_project_dir) not in sys.path:
    sys.path.insert(0, str(_project_dir))
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

import requests
from dotenv import load_dotenv
if __package__ is None or __package__ == "":
    import azurekeyvault
    import ca_client
    import connector_registry
    import db
    import host_connector
    import notifier
    import vault_client
    import verify
    from agent_telemetry import AgentTelemetryClient
else:
    from . import azurekeyvault, ca_client, connector_registry, db, host_connector, notifier, vault_client, verify
    from .agent_telemetry import AgentTelemetryClient

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


def get_active_connectors(db_path: str | None = None) -> list[Any]:
    """
    Returns active connectors strictly from the DB 'connectors' table authoritative source.
    Uses connector_registry.resolve_connector() for type dispatch.
    """
    connectors = []
    try:
        db_rows = db.list_connectors(active_only=True, db_path=db_path)
        for row in db_rows:
            try:
                c = connector_registry.resolve_connector(row)
                connectors.append(c)
            except Exception as exc:
                logger.error("Failed to instantiate DB connector '%s': %s", row["name"], exc)
    except Exception as exc:
        logger.error("Could not query DB connectors table (%s)", exc)

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

    db_row = db.get_connector_by_name(connector_name)
    if not db_row:
        raise RuntimeError(f"Connector '{connector_name}' not found in DB.")
    connector = connector_registry.resolve_host_connector(db_row)
    connector.name = connector_name

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


def _setup_register(
    dashboard_url: str,
    admin_email: str,
    admin_password: str,
    agent_name: str | None,
    db_path: str | None = None,
) -> None:
    """Step 1: Register agent with dashboard, store token in agent.db."""
    from agent_db import init_agent_db, set_identity, set_status

    init_agent_db(db_path)

    auth_resp = requests.post(
        f"{dashboard_url.rstrip('/')}/auth/login",
        json={"email": admin_email, "password": admin_password},
        timeout=10,
    )
    if auth_resp.status_code != 200:
        print(f"ERROR: Dashboard login failed ({auth_resp.status_code})")
        raise SystemExit(1)

    admin_token = auth_resp.json().get("access_token") or auth_resp.json().get("token")
    if not admin_token:
        print("ERROR: No token in login response")
        raise SystemExit(1)

    reg_resp = requests.post(
        f"{dashboard_url.rstrip('/')}/api/agents/register",
        json={"name": agent_name},
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10,
    )
    if reg_resp.status_code != 200:
        detail = reg_resp.json().get("detail", "Unknown error")
        print(f"ERROR: Agent registration failed ({reg_resp.status_code}): {detail}")
        raise SystemExit(1)

    data = reg_resp.json()
    set_identity("agent_id", data["agent_id"], db_path)
    set_identity("tenant_id", data["tenant_id"], db_path)
    set_identity("token", data["token"], db_path)
    set_identity("dashboard_url", dashboard_url, db_path)
    set_status("registered", db_path)

    print(f"  Agent ID: {data['agent_id']}")
    print(f"  Token stored in agent.db")


def _setup_configure(
    backend: str | None,
    credentials: dict[str, str],
    db_path: str | None = None,
) -> None:
    """Step 2: Configure secret store credentials in agent.db."""
    from agent_db import set_config, set_status

    if backend == "vault":
        set_config("vault_addr", credentials["vault_addr"], db_path)
        set_config("vault_token", credentials["vault_token"], db_path)
    elif backend == "azure":
        set_config("azure_keyvault_url", credentials["azure_keyvault_url"], db_path)
        set_config("azure_tenant_id", credentials.get("azure_tenant_id", ""), db_path)
        set_config("azure_client_id", credentials.get("azure_client_id", ""), db_path)
        set_config("azure_client_secret", credentials.get("azure_client_secret", ""), db_path)

    if backend:
        set_config("secret_store_backend", backend, db_path)
    set_status("configured", db_path)


def _setup_validate(db_path: str | None = None) -> None:
    """Step 3: Run first discovery cycle, mark agent as active."""
    from agent_db import set_status

    summary = run_renewal_loop(db_path=None)
    total = summary.get("total", 0) if hasattr(summary, "get") else sum(
        v.get("succeeded", 0) + v.get("skipped", 0) + v.get("failed", 0)
        for v in summary.values() if isinstance(v, dict)
    )
    succeeded = summary.get("succeeded", 0) if hasattr(summary, "get") else sum(
        v.get("succeeded", 0) for v in summary.values() if isinstance(v, dict)
    )
    print(f"  Found {total} certificates, {succeeded} succeeded")
    set_status("active", db_path)


def cmd_setup(args):
    """Full setup wizard entry point."""
    from agent_db import init_agent_db, get_status, get_identity

    init_agent_db(args.agent_db)
    current_status = get_status(args.agent_db)

    if current_status == "active":
        agent_id = get_identity("agent_id", args.agent_db) or "unknown"
        print(f"Agent is already set up (ID: {agent_id}).")
        print("Run `certops agent status` for details.")
        return

    print("\nCertOps Agent Setup")
    print("=" * 40)

    # Step 1: Dashboard Registration
    if current_status == "pending":
        print("\nStep 1/3: Dashboard Registration")
        print("-" * 30)
        dashboard_url = args.dashboard_url or input("Dashboard URL: ").strip()
        admin_email = args.admin_email or input("Admin email: ").strip()
        admin_password = args.admin_password or input("Admin password: ").strip()
        agent_name = args.agent_name or input("Agent name (optional): ").strip() or None

        print("\n  Connecting to dashboard...")
        _setup_register(dashboard_url, admin_email, admin_password, agent_name, args.agent_db)
        print("  Registration complete!")
        current_status = "registered"
    else:
        print("\n  Skipping registration (already registered)")

    # Step 2: Secret Store Configuration
    if current_status == "registered":
        print("\nStep 2/3: Secret Store Configuration")
        print("-" * 30)
        print("  How do you connect to your secret store?")
        print("    1. Vault (HashiCorp)")
        print("    2. Azure Key Vault")
        print("    3. Skip (configure later)")
        choice = args.backend_choice or input("  Select [1/2/3]: ").strip()

        backend = None
        credentials = {}
        if choice == "1":
            backend = "vault"
            credentials["vault_addr"] = args.vault_addr or input("  Vault address: ").strip()
            credentials["vault_token"] = args.vault_token or input("  Vault token: ").strip()
        elif choice == "2":
            backend = "azure"
            credentials["azure_keyvault_url"] = args.azure_url or input("  Azure Key Vault URL: ").strip()
            credentials["azure_tenant_id"] = args.azure_tenant_id or input("  Azure Tenant ID: ").strip()
            credentials["azure_client_id"] = args.azure_client_id or input("  Azure Client ID: ").strip()
            credentials["azure_client_secret"] = args.azure_client_secret or input("  Azure Client Secret: ").strip()

        print("\n  Configuring secret store...")
        _setup_configure(backend, credentials, args.agent_db)
        print("  Configuration complete!")
        current_status = "configured"
    else:
        print("\n  Skipping configuration (already configured)")

    # Step 3: Validation
    if current_status == "configured":
        print("\nStep 3/3: Validation")
        print("-" * 30)
        print("  Running first discovery cycle...")
        _setup_validate(args.agent_db)

    agent_id = get_identity("agent_id", args.agent_db) or "unknown"
    print(f"\nSetup complete. Agent ID: {agent_id}")


def _try_push_telemetry(summary: dict, db_path: str | None = None) -> None:
    """Push telemetry to dashboard if agent.db or environment variables are configured."""
    from agent_db import get_identity, get_usage_snapshot, update_usage_snapshot

    agent_id = get_identity("agent_id", db_path) or os.getenv("AGENT_ID", "Local-Windows-Dev-Agent")
    token = get_identity("token", db_path) or os.getenv("AGENT_TOKEN")
    dashboard_url = get_identity("dashboard_url", db_path) or os.getenv("DASHBOARD_URL")
    ingest_url = os.getenv("INGEST_URL") or (f"{dashboard_url.rstrip('/')}/api/telemetry/ingest" if dashboard_url else None)

    if not token or not ingest_url:
        return

    total_ok = sum(v.get("succeeded", 0) for v in summary.values() if isinstance(v, dict))
    total_fail = sum(v.get("failed", 0) for v in summary.values() if isinstance(v, dict))

    snap = get_usage_snapshot(db_path)
    new_ok = snap["renewals_succeeded"] + total_ok
    new_fail = snap["renewals_failed"] + total_fail

    cert_count = sum(
        v.get("succeeded", 0) + v.get("skipped", 0)
        for v in summary.values() if isinstance(v, dict)
    )

    connectors = {}
    for k in summary.keys():
        ctype = k.split("_")[0] if "_" in k else k
        connectors[ctype] = connectors.get(ctype, 0) + 1

    update_usage_snapshot(
        db_path,
        cert_count=cert_count,
        renewals_ok=new_ok,
        renewals_fail=new_fail,
        connectors=connectors,
    )

    usage = get_usage_snapshot(db_path)

    try:
        client = AgentTelemetryClient(
            agent_id=agent_id,
            agent_version=os.getenv("CERTOPS_VERSION", "2.5c"),
            agent_token=token,
            ingest_url=ingest_url,
        )
        status_code, _ = client.push(connectors=[], usage_snapshot=usage)
    except Exception:
        pass


def run_renewal_loop(db_path: str | None = None) -> RenewalSummary:
    """
    Runs the multi-vault and multi-host certificate renewal loop.
    Returns a RenewalSummary containing statistics per connector.
    """
    load_dotenv()

    db.run_migrations(db_path=db_path)
    connector_registry.seed_connectors_from_env(db_path=db_path)

    threshold_days = float(os.getenv("RENEWAL_THRESHOLD_DAYS", "2"))
    password_file = os.getenv("STEP_CA_PASSWORD_FILE", "./pass.txt")
    ca_url = os.getenv("STEP_CA_URL", "https://localhost:8443")
    fingerprint = os.getenv("STEP_CA_FINGERPRINT")

    verify_host = os.getenv("VERIFY_HOST", "localhost")
    verify_port = int(os.getenv("VERIFY_PORT", "443"))
    nginx_container = os.getenv("NGINX_CONTAINER_NAME", "certops-nginx-1")
    nginx_cert_name = os.getenv("VAULT_CERT_PATH", "secret/local-certs").split("/")[-1]

    summary = RenewalSummary()
    active_connectors = get_active_connectors(db_path=db_path)

    if not active_connectors:
        print("\n" + "=" * 70)
        print("RENEWAL LOOP SUMMARY: 0 checked, 0 renewed (no active connectors in DB)")
        print("=" * 70)
        return summary

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
                        db_path=db_path,
                    )
                except Exception as exc:
                    logger.error("Failed to upsert host cert '%s' into DB: %s", meta_item.cert_id, exc)
                    summary[c_name]["failed"] += 1

            try:
                due_certs = db.get_due_certificates(vault_source=c_name, threshold_days=threshold_days, db_path=db_path)
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
                    rec = db.get_certificate(c_name, cid, db_path=db_path)
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
                    with db.renewal_context(c_name, "host", cid, existing_data.expiry_utc, db_path=db_path):
                        new_cert_pem, new_key_pem = ca_client.issue_certificate(
                            subject=subject,
                            password_file=password_file,
                            ca_url=ca_url,
                            fingerprint=fingerprint,
                        )
                    db.update_pipeline_stage(c_name, cid, "Renewed", db_path=db_path)

                    rec = db.get_certificate(c_name, cid, db_path=db_path)
                    gid = rec.get("group_id") if rec else None
                    if not db.is_group_in_maintenance_window(gid, db_path=db_path):
                        db.update_pipeline_stage(c_name, cid, "Hold: outside maintenance window", db_path=db_path)
                        print(f"    -> [MAINTENANCE WINDOW HOLD] Certificate '{cid}' renewed, but group ID={gid} is outside active maintenance window. Holding before deploy.")
                        summary[c_name]["succeeded"] += 1
                        db.log_activity(
                            event_type="certificate_renewed",
                            target=cid,
                            details={"connector_name": c_name, "category": "host", "old_expiry": existing_data.expiry_utc.isoformat(), "status": "held_pending_maintenance_window"},
                            db_path=db_path,
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
                        db_path=db_path,
                    )
                    summary[c_name]["succeeded"] += 1
                    db.log_activity(
                        event_type="certificate_renewed",
                        target=cid,
                        details={"connector_name": c_name, "category": "host", "old_expiry": existing_data.expiry_utc.isoformat(), "new_expiry": new_expiry.isoformat()},
                        db_path=db_path,
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
                        db_path=db_path,
                    )

        elif getattr(connector, "category", "") == "ca" or "ca" in c_name.lower():
            # Certificate Authorities are used during issuance, not secret discovery
            continue
        elif hasattr(connector, "list_certificates"):
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
                        db_path=db_path,
                    )
                except Exception as exc:
                    logger.error("Failed to upsert certificate name='%s' into DB: %s", cert_item["name"], exc)
                    summary[c_name]["failed"] += 1

            try:
                due_certs = db.get_due_certificates(vault_source=c_name, threshold_days=threshold_days, db_path=db_path)
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
                    rec = db.get_certificate(c_name, cname, db_path=db_path)
                    evaluated_thresh = (rec.get("renewal_threshold_days") if rec else None) or threshold_days
                    print(f"    -> Cert '{cname}' is not due (lifetime {rem_days:.4f} days > threshold {evaluated_thresh} days). Skipped.")
                    summary[c_name]["skipped"] += 1
                    continue

                evaluated_thresh = due_map[cname]
                print(f"    -> Cert '{cname}' is due (lifetime <= {evaluated_thresh} days). Renewing...")
                try:
                    cert_info = connector.get_certificate(cname)
                    subject = cert_info.get("common_name") or cname
                    with db.renewal_context(c_name, "secret_store", cname, dt, db_path=db_path):
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
                        db_path=db_path,
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
                        db_path=db_path,
                    )
                    print(f"    -> Successfully renewed '{cname}' in vault '{c_name}'.")
                except Exception as exc:
                    logger.error("Certificate processing failed for name='%s' in '%s': %s", cname, c_name, exc)
                    summary[c_name]["failed"] += 1
                    db.log_activity(
                        event_type="certificate_renewal_failed",
                        target=cname,
                        details={"connector_name": c_name, "category": "secret_store", "error": str(exc)},
                        db_path=db_path,
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

    _try_push_telemetry(summary, db_path)

    return summary


parser = argparse.ArgumentParser(description="CertOps Agent")
subparsers = parser.add_subparsers(dest="command")

# Legacy confirm-reload
reload_parser = subparsers.add_parser("confirm-reload")
reload_parser.add_argument("connector_name")
reload_parser.add_argument("cert_id")

# Setup wizard
setup_parser = subparsers.add_parser("setup", help="Run agent setup wizard")
setup_parser.add_argument("--agent-db", default="./agent.db", help="Path to agent.db")
setup_parser.add_argument("--dashboard-url", default=None)
setup_parser.add_argument("--admin-email", default=None)
setup_parser.add_argument("--admin-password", default=None)
setup_parser.add_argument("--agent-name", default=None)
setup_parser.add_argument("--backend-choice", default=None, choices=["1", "2", "3"])
setup_parser.add_argument("--vault-addr", default=None)
setup_parser.add_argument("--vault-token", default=None)
setup_parser.add_argument("--azure-url", default=None)
setup_parser.add_argument("--azure-tenant-id", default=None)
setup_parser.add_argument("--azure-client-id", default=None)
setup_parser.add_argument("--azure-client-secret", default=None)


if __name__ == "__main__":
    args = parser.parse_args()

    if args.command == "confirm-reload":
        success = confirm_and_reload_host(args.connector_name, args.cert_id)
        sys.exit(0 if success else 1)
    elif args.command == "setup":
        cmd_setup(args)
    else:
        run_renewal_loop()
    sys.exit(0)
