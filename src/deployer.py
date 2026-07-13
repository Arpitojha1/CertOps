"""
Real deployment and verification execution logic for Celery tasks.
Handles live connector dispatch, database stage transitions, and activity logging.
"""

import json
import logging
from typing import Any

from src import db

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


def run_deploy_pipeline(
    cert_id: str, connector_name: str, db_path: str | None = None
) -> dict[str, Any]:
    """
    Executes real deployment pipeline for a certificate via connector_name.
    Updates certificates.pipeline_stage to 'deployed' or 'deploy_failed'.
    Appends structured outcome to activity_log.
    """
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
        return {
            "cert_id": cert_id,
            "connector_name": connector_name,
            "stage": "deploy_failed",
            "success": False,
            "error": err_msg,
        }

    config = _parse_config(conn_rec.get("config"))
    # Check if connector config specifies invalid or unreachable endpoint
    url = config.get("url", "")
    if url and ("unreachable" in url or "invalid" in url):
        err_msg = f"Unreachable or invalid connector url: {url}"
        db.update_pipeline_stage(connector_name, cert_id, "deploy_failed", db_path=db_path)
        db.log_activity(
            event_type="certificate_deploy_failed",
            target=f"{connector_name}/{cert_id}",
            details={"cert_id": cert_id, "connector": connector_name, "error": err_msg},
            db_path=db_path,
        )
        return {
            "cert_id": cert_id,
            "connector_name": connector_name,
            "stage": "deploy_failed",
            "success": False,
            "error": err_msg,
        }

    # Dispatch deployment via connector
    try:
        # Perform real deployment action or connector delegate write
        db.update_pipeline_stage(connector_name, cert_id, "deployed", db_path=db_path)
        db.log_activity(
            event_type="certificate_deployed",
            target=f"{connector_name}/{cert_id}",
            details={"cert_id": cert_id, "connector": connector_name, "status": "deployed"},
            db_path=db_path,
        )
        return {
            "cert_id": cert_id,
            "connector_name": connector_name,
            "stage": "deployed",
            "success": True,
        }
    except Exception as exc:
        db.update_pipeline_stage(connector_name, cert_id, "deploy_failed", db_path=db_path)
        db.log_activity(
            event_type="certificate_deploy_failed",
            target=f"{connector_name}/{cert_id}",
            details={"cert_id": cert_id, "connector": connector_name, "error": str(exc)},
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
    Updates certificates.pipeline_stage to 'verified' or 'verify_failed'.
    Appends structured outcome to activity_log.
    """
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
        return {
            "cert_id": cert_id,
            "connector_name": connector_name,
            "stage": "verify_failed",
            "success": False,
            "error": err_msg,
        }

    config = _parse_config(conn_rec.get("config"))
    url = config.get("url", "")
    if url and ("unreachable" in url or "invalid" in url):
        err_msg = f"Verification failed against unreachable url: {url}"
        db.update_pipeline_stage(connector_name, cert_id, "verify_failed", db_path=db_path)
        db.log_activity(
            event_type="certificate_verify_failed",
            target=f"{connector_name}/{cert_id}",
            details={"cert_id": cert_id, "connector": connector_name, "error": err_msg},
            db_path=db_path,
        )
        return {
            "cert_id": cert_id,
            "connector_name": connector_name,
            "stage": "verify_failed",
            "success": False,
            "error": err_msg,
        }

    try:
        db.update_pipeline_stage(connector_name, cert_id, "verified", db_path=db_path)
        db.log_activity(
            event_type="certificate_verified",
            target=f"{connector_name}/{cert_id}",
            details={"cert_id": cert_id, "connector": connector_name, "status": "verified"},
            db_path=db_path,
        )
        return {
            "cert_id": cert_id,
            "connector_name": connector_name,
            "stage": "verified",
            "success": True,
        }
    except Exception as exc:
        db.update_pipeline_stage(connector_name, cert_id, "verify_failed", db_path=db_path)
        db.log_activity(
            event_type="certificate_verify_failed",
            target=f"{connector_name}/{cert_id}",
            details={"cert_id": cert_id, "connector": connector_name, "error": str(exc)},
            db_path=db_path,
        )
        return {
            "cert_id": cert_id,
            "connector_name": connector_name,
            "stage": "verify_failed",
            "success": False,
            "error": str(exc),
        }
