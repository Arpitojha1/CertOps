"""
Real deployment and verification execution logic for Celery tasks.
Handles live connector dispatch, database stage transitions, and activity logging.

Connector category branching:
  "host"         -> SSHHostConnector / WinRMHostConnector
                    deploy:  connector.deploy_certificate(cert_id, CertData)
                    verify:  connector.trigger_reload(cert_id) + live TLS fingerprint
  "secret_store" -> HashiCorpVaultClient / AzureKeyVaultClient
                    deploy:  connector.write_certificate(cert_id, cert_pem, key_pem)
                    verify:  connector.get_certificate(cert_id) read-back fingerprint compare
  any other      -> raise ValueError early (fast-fail on unknown category)

The connector object is resolved via get_active_connectors_by_name() which reads from
the DB connectors table (DB-authoritative source, no env var fallback).
"""

import json
import logging
import os
import time
from typing import Any

from src import db, verify
from src.host_connector import CertData

logger = logging.getLogger("certops.deployer")


def _parse_config(raw_config: Any) -> dict[str, Any]:
    if isinstance(raw_config, dict):
        return raw_config
    if isinstance(raw_config, str):
        try:
            return json.loads(raw_config)
        except Exception:
            return {}
    return {}


def get_active_connectors_by_name(connector_name: str, db_path: str | None = None) -> Any:
    """
    Resolves the live connector object for connector_name from the DB-authoritative
    connectors table.  Returns None if not found or not active.

    Imports get_active_connectors from main to reuse the existing object-construction
    logic (env/config merging, credential decryption) without duplicating it.
    """
    # Import here to avoid circular imports at module load time
    from src.main import get_active_connectors
    connectors = get_active_connectors(db_path=db_path)
    for connector in connectors:
        if getattr(connector, "name", None) == connector_name:
            return connector
    return None


def run_deploy_pipeline(
    cert_id: str, connector_name: str, db_path: str | None = None
) -> dict[str, Any]:
    """
    Executes real deployment pipeline for a certificate via connector_name.

    For host connectors: calls connector.deploy_certificate(cert_id, CertData) using the
    pending_cert_pem / pending_cert_key staged in the DB by task_renew_certificate.

    For secret_store connectors: calls connector.write_certificate(cert_id, cert_pem, key_pem)
    to write the renewed cert back into the vault.

    Updates certificates.pipeline_stage to 'deployed' or 'deploy_failed'.
    Appends structured outcome to activity_log.
    """
    # 1. Load connector DB record (for category branching — resolved before object construction
    #    so a bad category fails fast with a clear error rather than an AttributeError later)
    conn_rec = db.get_connector_by_name(connector_name, db_path=db_path)
    if not conn_rec:
        err_msg = f"Connector '{connector_name}' not found"
        db.update_pipeline_stage(connector_name, cert_id, "deploy_failed", db_path=db_path)
        db.log_activity(
            event_type="certificate_deploy_failed",
            target=f"{connector_name}/{cert_id}",
            details={"cert_id": cert_id, "connector": connector_name, "error": err_msg},
            db_path=db_path,
        )
        return {"cert_id": cert_id, "connector_name": connector_name,
                "stage": "deploy_failed", "success": False, "error": err_msg}

    category = conn_rec.get("category") or "secret_store"
    if category not in ("host", "secret_store"):
        err_msg = f"Unknown connector category '{category}' for '{connector_name}' — only 'host' and 'secret_store' are deployable"
        db.update_pipeline_stage(connector_name, cert_id, "deploy_failed", db_path=db_path)
        db.log_activity(
            event_type="certificate_deploy_failed",
            target=f"{connector_name}/{cert_id}",
            details={"cert_id": cert_id, "connector": connector_name, "error": err_msg},
            db_path=db_path,
        )
        return {"cert_id": cert_id, "connector_name": connector_name,
                "stage": "deploy_failed", "success": False, "error": err_msg}

    # 2. Load staged pending cert from DB (written by task_renew_certificate)
    cert_rec = db.get_certificate(connector_name, cert_id, db_path=db_path)
    if not cert_rec:
        err_msg = f"Certificate record not found for '{connector_name}/{cert_id}'"
        db.update_pipeline_stage(connector_name, cert_id, "deploy_failed", db_path=db_path)
        db.log_activity(
            event_type="certificate_deploy_failed",
            target=f"{connector_name}/{cert_id}",
            details={"cert_id": cert_id, "connector": connector_name, "error": err_msg},
            db_path=db_path,
        )
        return {"cert_id": cert_id, "connector_name": connector_name,
                "stage": "deploy_failed", "success": False, "error": err_msg}

    pending_cert_pem = cert_rec.get("pending_cert_pem")
    pending_cert_key = cert_rec.get("pending_cert_key")
    if not pending_cert_pem:
        err_msg = f"No pending_cert_pem staged for '{connector_name}/{cert_id}' — renewal may not have run"
        db.update_pipeline_stage(connector_name, cert_id, "deploy_failed", db_path=db_path)
        db.log_activity(
            event_type="certificate_deploy_failed",
            target=f"{connector_name}/{cert_id}",
            details={"cert_id": cert_id, "connector": connector_name, "error": err_msg},
            db_path=db_path,
        )
        return {"cert_id": cert_id, "connector_name": connector_name,
                "stage": "deploy_failed", "success": False, "error": err_msg}

    # 3. Resolve live connector object
    connector = get_active_connectors_by_name(connector_name, db_path=db_path)
    if connector is None:
        err_msg = f"Connector '{connector_name}' not found in active connector list"
        db.update_pipeline_stage(connector_name, cert_id, "deploy_failed", db_path=db_path)
        db.log_activity(
            event_type="certificate_deploy_failed",
            target=f"{connector_name}/{cert_id}",
            details={"cert_id": cert_id, "connector": connector_name, "error": err_msg},
            db_path=db_path,
        )
        return {"cert_id": cert_id, "connector_name": connector_name,
                "stage": "deploy_failed", "success": False, "error": err_msg}

    # 4. Dispatch to the right deploy method based on category
    try:
        if category == "host":
            # HostConnector: write-then-rename file deploy (does NOT reload service)
            cert_data = CertData(
                cert_id=cert_id,
                cert_pem=pending_cert_pem,
                expiry_utc=cert_rec["expiry_utc"],
                common_name=cert_rec.get("common_name"),
                private_key_pem=pending_cert_key,
                key_path=None,   # key_path stored on the host; connector resolves it
            )
            connector.deploy_certificate(cert_id, cert_data)
            logger.info("HostConnector.deploy_certificate() completed for %s/%s", connector_name, cert_id)
        else:
            # SecretStoreConnector: write renewed cert back into vault
            if not pending_cert_key:
                raise ValueError(f"private key is required for write_certificate but pending_cert_key is empty for '{cert_id}'")
            connector.write_certificate(cert_id, pending_cert_pem, pending_cert_key)
            logger.info("SecretStoreConnector.write_certificate() completed for %s/%s", connector_name, cert_id)

        db.update_pipeline_stage(connector_name, cert_id, "Deployed pending reload", db_path=db_path)
        db.log_activity(
            event_type="certificate_deployed",
            target=f"{connector_name}/{cert_id}",
            details={
                "cert_id": cert_id,
                "connector": connector_name,
                "category": category,
                "status": "Deployed pending reload",
            },
            db_path=db_path,
        )
        return {
            "cert_id": cert_id,
            "connector_name": connector_name,
            "stage": "Deployed pending reload",
            "success": True,
        }

    except Exception as exc:
        logger.exception("Deploy failed for %s/%s: %s", connector_name, cert_id, exc)
        db.update_pipeline_stage(connector_name, cert_id, "deploy_failed", db_path=db_path)
        db.log_activity(
            event_type="certificate_deploy_failed",
            target=f"{connector_name}/{cert_id}",
            details={"cert_id": cert_id, "connector": connector_name,
                     "category": category, "error": str(exc)},
            db_path=db_path,
        )
        return {
            "cert_id": cert_id,
            "connector_name": connector_name,
            "stage": "deploy_failed",
            "success": False,
            "error": str(exc),
        }


def run_verify_pipeline(
    cert_id: str, connector_name: str, db_path: str | None = None
) -> dict[str, Any]:
    """
    Executes real verification/reload pipeline for a certificate via connector_name.

    For host connectors:
      1. Calls connector.trigger_reload(cert_id) to restart the service.
      2. Calls verify.get_live_cert_info(host, port) to confirm the live-served
         certificate fingerprint matches the staged cert's fingerprint.

    For secret_store connectors:
      1. Calls connector.get_certificate(cert_id) to read the cert back from the vault.
      2. Compares the fingerprint of the read-back cert against the staged pending_cert_pem.
      This confirms the write actually persisted, without a live TLS handshake.

    Both paths log 'verification_method' ('live_tls' or 'readback') in the activity log
    so the guarantee made is auditable.

    Updates certificates.pipeline_stage to 'verified' or 'verify_failed'.
    Appends structured outcome to activity_log.
    """
    # 1. Load connector DB record for category branching
    conn_rec = db.get_connector_by_name(connector_name, db_path=db_path)
    if not conn_rec:
        err_msg = f"Connector '{connector_name}' not found"
        db.update_pipeline_stage(connector_name, cert_id, "verify_failed", db_path=db_path)
        db.log_activity(
            event_type="certificate_verify_failed",
            target=f"{connector_name}/{cert_id}",
            details={"cert_id": cert_id, "connector": connector_name, "error": err_msg},
            db_path=db_path,
        )
        return {"cert_id": cert_id, "connector_name": connector_name,
                "stage": "verify_failed", "success": False, "error": err_msg}

    category = conn_rec.get("category") or "secret_store"
    if category not in ("host", "secret_store"):
        err_msg = f"Unknown connector category '{category}' — cannot verify"
        db.update_pipeline_stage(connector_name, cert_id, "verify_failed", db_path=db_path)
        db.log_activity(
            event_type="certificate_verify_failed",
            target=f"{connector_name}/{cert_id}",
            details={"cert_id": cert_id, "connector": connector_name, "error": err_msg},
            db_path=db_path,
        )
        return {"cert_id": cert_id, "connector_name": connector_name,
                "stage": "verify_failed", "success": False, "error": err_msg}

    # 2. Load staged cert for fingerprint comparison baseline
    cert_rec = db.get_certificate(connector_name, cert_id, db_path=db_path)
    pending_cert_pem = cert_rec.get("pending_cert_pem") if cert_rec else None

    # 3. Resolve live connector object
    connector = get_active_connectors_by_name(connector_name, db_path=db_path)
    if connector is None:
        err_msg = f"Connector '{connector_name}' not found in active connector list"
        db.update_pipeline_stage(connector_name, cert_id, "verify_failed", db_path=db_path)
        db.log_activity(
            event_type="certificate_verify_failed",
            target=f"{connector_name}/{cert_id}",
            details={"cert_id": cert_id, "connector": connector_name, "error": err_msg},
            db_path=db_path,
        )
        return {"cert_id": cert_id, "connector_name": connector_name,
                "stage": "verify_failed", "success": False, "error": err_msg}

    # 4. Branch on category
    try:
        if category == "host":
            # HostConnector: trigger service reload, then confirm via live TLS handshake
            reload_result = connector.trigger_reload(cert_id)
            if not reload_result.success:
                raise RuntimeError(f"Service reload failed: {reload_result.output}")
            logger.info("trigger_reload() completed for %s/%s", connector_name, cert_id)

            # Compute expected fingerprint from staged PEM
            expected_fp: str | None = None
            if pending_cert_pem:
                try:
                    _, expected_fp = verify.get_pem_cert_info(pending_cert_pem)
                except Exception:
                    pass

            if expected_fp is None:
                raise RuntimeError(
                    f"Cannot verify fingerprint for '{connector_name}/{cert_id}': expected_fingerprint is missing or unresolvable from staged DB record (pending_cert_pem is empty or invalid)"
                )

            # Live TLS fingerprint comparison with brief retry for Nginx worker reload settling (~100-500ms)
            verify_host = os.getenv("VERIFY_HOST", "localhost")
            verify_port = int(os.getenv("VERIFY_PORT", "443"))
            live_fp: str | None = None
            for attempt in range(4):
                try:
                    _, live_fp = verify.get_live_cert_info(verify_host, verify_port)
                except Exception:
                    pass
                if live_fp == expected_fp or attempt == 3:
                    break
                time.sleep(0.5)

            logger.info("Live TLS cert fingerprint at %s:%s → %s", verify_host, verify_port, live_fp)

            if live_fp is None:
                raise RuntimeError(
                    f"Cannot verify fingerprint for '{connector_name}/{cert_id}': live_fingerprint could not be retrieved from {verify_host}:{verify_port}"
                )

            fp_match = (live_fp == expected_fp)
            verification_method = "live_tls"
            extra = {
                "reload_output": reload_result.output,
                "live_fingerprint": live_fp,
                "expected_fingerprint": expected_fp,
                "fingerprint_match": fp_match,
            }
            if not fp_match:
                raise RuntimeError(
                    f"Live TLS fingerprint mismatch: live={live_fp} expected={expected_fp}"
                )

        else:
            # SecretStoreConnector: read-back verification
            read_back = connector.get_certificate(cert_id)
            read_back_pem = read_back.get("cert_pem", "") if isinstance(read_back, dict) else ""
            logger.info("SecretStoreConnector.get_certificate() read-back completed for %s/%s",
                        connector_name, cert_id)

            # Compare fingerprints
            read_back_fp: str | None = None
            expected_fp: str | None = None
            if read_back_pem:
                try:
                    _, read_back_fp = verify.get_pem_cert_info(read_back_pem)
                except Exception:
                    pass
            if pending_cert_pem:
                try:
                    _, expected_fp = verify.get_pem_cert_info(pending_cert_pem)
                except Exception:
                    pass

            if expected_fp is None:
                raise RuntimeError(
                    f"Cannot verify fingerprint for '{connector_name}/{cert_id}': expected_fingerprint is missing or unresolvable from staged DB record (pending_cert_pem is empty or invalid)"
                )
            if read_back_fp is None:
                raise RuntimeError(
                    f"Cannot verify fingerprint for '{connector_name}/{cert_id}': readback_fingerprint could not be retrieved or parsed from secret store read-back PEM"
                )

            fp_match = (read_back_fp == expected_fp)
            verification_method = "readback"
            extra = {
                "readback_fingerprint": read_back_fp,
                "expected_fingerprint": expected_fp,
                "fingerprint_match": fp_match,
            }
            if not fp_match:
                raise RuntimeError(
                    f"Read-back fingerprint mismatch: read_back={read_back_fp} expected={expected_fp}"
                )

        db.update_pipeline_stage(connector_name, cert_id, "Reload confirmed", db_path=db_path)
        db.clear_pending_cert(connector_name, cert_id, db_path=db_path)
        db.log_activity(
            event_type="certificate_verified",
            target=f"{connector_name}/{cert_id}",
            details={
                "cert_id": cert_id,
                "connector": connector_name,
                "category": category,
                "status": "Reload confirmed",
                "verification_method": verification_method,
                **extra,
            },
            db_path=db_path,
        )
        return {
            "cert_id": cert_id,
            "connector_name": connector_name,
            "stage": "Reload confirmed",
            "success": True,
            "verification_method": verification_method,
        }

    except Exception as exc:
        logger.exception("Verify failed for %s/%s: %s", connector_name, cert_id, exc)
        db.update_pipeline_stage(connector_name, cert_id, "verify_failed", db_path=db_path)
        db.log_activity(
            event_type="certificate_verify_failed",
            target=f"{connector_name}/{cert_id}",
            details={"cert_id": cert_id, "connector": connector_name,
                     "category": category, "error": str(exc)},
            db_path=db_path,
        )
        return {
            "cert_id": cert_id,
            "connector_name": connector_name,
            "stage": "verify_failed",
            "success": False,
            "error": str(exc),
        }
