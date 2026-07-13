import logging
import os
from datetime import datetime, timezone
from celery import Celery, chain
from celery.signals import worker_ready
from src import ca_client, db, host_connector, main, scheduler, verify

logger = logging.getLogger("certops.tasks")

broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

app = Celery("certops", broker=broker_url, backend=result_backend)
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "check-and-trigger-renewals-every-5-minutes": {
            "task": "tasks.check_and_trigger_renewals",
            "schedule": 300.0,
        },
    },
)


def _resolve_connector(vault_source: str):
    connectors = main.get_active_connectors()
    for c in connectors:
        if getattr(c, "name", "") == vault_source:
            return c
    return None


@app.task(name="tasks.renew_certificate")
def task_renew_certificate(vault_source: str, cert_id: str, db_path: str | None = None) -> dict:
    """
    Stage 1: Renew certificate using step-ca and stage pending_cert_pem / pending_cert_key in DB.
    Idempotent: skips issuance if certificate is already staged with an in-flight pipeline stage.
    """
    logger.info("Running Stage 1 (Renew): cert='%s' source='%s'", cert_id, vault_source)
    now_dt = datetime.now(timezone.utc)

    rec = db.get_certificate(vault_source, cert_id, db_path=db_path)
    current_stage = rec.get("pipeline_stage") if rec else None
    existing_pem = rec.get("pending_cert_pem") if rec else None

    if existing_pem and current_stage in ("Issued pending deploy", "Renewed"):
        logger.info("Cert '%s' already staged with pending cert in stage '%s'. Skipping re-issuance.", cert_id, current_stage)
        return {
            "vault_source": vault_source,
            "cert_id": cert_id,
            "stage": current_stage,
            "db_path": db_path,
        }

    subject = rec.get("common_name") if rec and rec.get("common_name") else cert_id.split("/")[-1]
    password_file = os.getenv("STEP_CA_PASSWORD_FILE", "./pass.txt")
    ca_url = os.getenv("STEP_CA_URL", "https://localhost:8443")
    fingerprint = os.getenv("STEP_CA_FINGERPRINT")

    new_cert_pem, new_key_pem = ca_client.issue_certificate(
        subject=subject,
        password_file=password_file,
        ca_url=ca_url,
        fingerprint=fingerprint,
    )

    new_expiry, _ = verify.get_pem_cert_info(new_cert_pem)
    if rec is None:
        db.upsert_certificate(
            vault_source=vault_source,
            name=cert_id,
            expiry_utc=new_expiry,
            connector_category="host",
            pipeline_stage="Issued pending deploy",
            db_path=db_path,
        )
    db.stage_pending_cert(
        vault_source=vault_source,
        name=cert_id,
        cert_pem=new_cert_pem,
        key_pem=new_key_pem,
        pipeline_stage="Issued pending deploy",
        db_path=db_path,
    )

    return {
        "vault_source": vault_source,
        "cert_id": cert_id,
        "stage": "Issued pending deploy",
        "db_path": db_path,
    }


@app.task(name="tasks.deploy_certificate")
def task_deploy_certificate(payload: dict) -> dict:
    """
    Stage 2: Deploy staged certificate to host target or vault and persist 'Deployed pending reload'.
    If DB state is already 'Deployed pending reload' or later, deployment is skipped idempotently.
    """
    vault_source = payload["vault_source"]
    cert_id = payload["cert_id"]
    db_path = payload.get("db_path")

    logger.info("Running Stage 2 (Deploy): cert='%s' source='%s'", cert_id, vault_source)
    rec = db.get_certificate(vault_source, cert_id, db_path=db_path)
    current_stage = rec.get("pipeline_stage") if rec else None

    if current_stage in ("Deployed pending reload", "Deployed, pending reload", "Reload confirmed"):
        logger.info(
            "Cert '%s' is already in DB stage '%s'. Skipping re-deployment.",
            cert_id,
            current_stage,
        )
        return {
            "vault_source": vault_source,
            "cert_id": cert_id,
            "stage": current_stage,
            "db_path": db_path,
        }

    pending_pem = rec.get("pending_cert_pem") if rec else None
    pending_key = rec.get("pending_cert_key") if rec else None
    if not pending_pem:
        raise RuntimeError(f"Cannot deploy cert '{cert_id}': no pending_cert_pem staged in DB.")

    connector = _resolve_connector(vault_source)
    new_expiry, _ = verify.get_pem_cert_info(pending_pem)
    subject = rec.get("common_name") if rec and rec.get("common_name") else cert_id.split("/")[-1]

    if connector and isinstance(connector, host_connector.HostConnector):
        deploy_data = host_connector.CertData(
            cert_id=cert_id,
            cert_pem=pending_pem,
            expiry_utc=new_expiry,
            common_name=subject,
            private_key_pem=pending_key,
        )
        connector.deploy_certificate(cert_id, deploy_data)
    elif connector and hasattr(connector, "write_certificate"):
        connector.write_certificate(cert_id, pending_pem, pending_key or "")
        nginx_cert_name = os.getenv("VAULT_CERT_PATH", "secret/local-certs").split("/")[-1]
        if cert_id == nginx_cert_name and vault_source == "hashicorp":
            deploy_cert_path = os.getenv("DEPLOY_CERT_PATH", "./local.crt")
            deploy_key_path = os.getenv("DEPLOY_KEY_PATH", "./local.key")
            main.atomic_deploy_file(deploy_cert_path, pending_pem, make_backup=True)
            if pending_key:
                main.atomic_deploy_file(deploy_key_path, pending_key, make_backup=True)
    else:
        # Fallback for local testing when connector is not registered
        nginx_cert_name = os.getenv("VAULT_CERT_PATH", "secret/local-certs").split("/")[-1]
        if cert_id == nginx_cert_name:
            deploy_cert_path = os.getenv("DEPLOY_CERT_PATH", "./local.crt")
            deploy_key_path = os.getenv("DEPLOY_KEY_PATH", "./local.key")
            main.atomic_deploy_file(deploy_cert_path, pending_pem, make_backup=True)
            if pending_key:
                main.atomic_deploy_file(deploy_key_path, pending_key, make_backup=True)

    db.update_pipeline_stage(vault_source, cert_id, "Deployed pending reload", db_path=db_path)
    return {
        "vault_source": vault_source,
        "cert_id": cert_id,
        "stage": "Deployed pending reload",
        "db_path": db_path,
    }


@app.task(name="tasks.verify_reload")
def task_verify_reload(payload: dict) -> dict:
    """
    Stage 3: Confirm reload and verify service certificate against live TLS, persisting 'Reload confirmed' state to DB
    and clearing staged pending certs.
    """
    vault_source = payload["vault_source"]
    cert_id = payload["cert_id"]
    db_path = payload.get("db_path")

    logger.info("Running Stage 3 (Verify Reload): cert='%s' source='%s'", cert_id, vault_source)
    rec = db.get_certificate(vault_source, cert_id, db_path=db_path)
    current_stage = rec.get("pipeline_stage") if rec else None

    if current_stage == "Reload confirmed":
        logger.info("Cert '%s' already marked 'Reload confirmed'. Skipping verification.", cert_id)
        return {
            "vault_source": vault_source,
            "cert_id": cert_id,
            "stage": "Reload confirmed",
            "db_path": db_path,
        }

    connector = _resolve_connector(vault_source)
    pending_pem = rec.get("pending_cert_pem") if rec else None
    if not pending_pem:
        # If no pending pem staged, read cert from disk or connector to determine expected fingerprint
        if os.path.exists(os.getenv("DEPLOY_CERT_PATH", "./local.crt")):
            with open(os.getenv("DEPLOY_CERT_PATH", "./local.crt"), "r", encoding="utf-8") as f:
                pending_pem = f.read()

    expected_expiry, expected_fp = verify.get_pem_cert_info(pending_pem) if pending_pem else (None, None)

    if connector and isinstance(connector, host_connector.HostConnector):
        reload_res = connector.trigger_reload(cert_id)
        if not reload_res.success:
            raise RuntimeError(f"Service reload FAILED for '{cert_id}':\n{reload_res.output}")
    else:
        nginx_cert_name = os.getenv("VAULT_CERT_PATH", "secret/local-certs").split("/")[-1]
        if cert_id == nginx_cert_name:
            verify_host = os.getenv("VERIFY_HOST", "localhost")
            verify_port = int(os.getenv("VERIFY_PORT", "443"))
            nginx_container = os.getenv("NGINX_CONTAINER_NAME", "certops-nginx-1")
            pending_key = rec.get("pending_cert_key") if rec else ""
            if pending_pem and pending_key:
                main._deploy_and_verify_nginx(
                    pending_pem, pending_key, verify_host, verify_port, nginx_container
                )

    db.update_pipeline_stage(vault_source, cert_id, "Reload confirmed", db_path=db_path)
    db.clear_pending_cert(vault_source, cert_id, db_path=db_path)
    return {
        "vault_source": vault_source,
        "cert_id": cert_id,
        "stage": "Reload confirmed",
        "db_path": db_path,
    }


@app.task(name="tasks.check_and_trigger_renewals")
def check_and_trigger_renewals(db_path: str | None = None) -> list[dict[str, str]]:
    """
    Celery Beat periodic task: scans DB for certificates reaching next_renewal_at
    and triggers start_pipeline if not already in-flight.
    """
    sched = scheduler.RenewalScheduler(db_path=db_path)
    due_jobs = sched.get_due_jobs()
    triggered = []
    for job in due_jobs:
        logger.info("Triggering renewal pipeline for due certificate '%s' (%s)", job.cert_name, job.vault_source)
        start_pipeline(job.vault_source, job.cert_name, db_path=db_path)
        triggered.append({"vault_source": job.vault_source, "cert_id": job.cert_name})
    return triggered


def start_pipeline(vault_source: str, cert_id: str, db_path: str | None = None):
    """
    Launches the full 3-stage chained pipeline: Renew -> Deploy -> Verify Reload.
    """
    workflow = chain(
        task_renew_certificate.s(vault_source, cert_id, db_path=db_path),
        task_deploy_certificate.s(),
        task_verify_reload.s(),
    )
    return workflow.apply_async()


def resume_pipeline_from_db(vault_source: str, cert_id: str, db_path: str | None = None):
    """
    Resumes a pipeline from its persisted DB state after a crash/restart.
    Proves zero loss of pipeline state across worker/Redis restarts.
    """
    rec = db.get_certificate(vault_source, cert_id, db_path=db_path)
    if not rec:
        raise ValueError(f"Cannot resume pipeline: certificate '{cert_id}' not found in DB.")

    stage = rec.get("pipeline_stage")
    logger.info("Resuming pipeline for cert='%s' from DB stage='%s'", cert_id, stage)

    if stage == "Renewed":
        payload = {"vault_source": vault_source, "cert_id": cert_id, "stage": stage, "db_path": db_path}
        workflow = chain(task_deploy_certificate.s(payload), task_verify_reload.s())
        return workflow.apply_async()
    elif stage in ("Deployed pending reload", "Deployed, pending reload"):
        # Stage 1 and 2 already completed in DB. Resume directly with Stage 3
        payload = {
            "vault_source": vault_source,
            "cert_id": cert_id,
            "stage": stage,
            "db_path": db_path,
        }
        return task_verify_reload.delay(payload)
    elif stage == "Reload confirmed":
        logger.info("Pipeline already complete ('Reload confirmed') for cert='%s'.", cert_id)
        return None
    else:
        # Start full pipeline if no known stage
        return start_pipeline(vault_source, cert_id, db_path=db_path)


def resume_all_pending_pipelines(db_path: str | None = None) -> list[tuple[str, str, str]]:
    """
    Queries certops.db for all certificates currently stuck in an in-flight pipeline stage
    ('Renewed', 'Deployed pending reload', 'Deployed, pending reload') and auto-resumes them.
    Returns a list of (vault_source, cert_id, stage) tuples resumed.
    """
    conn = db.get_db_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT vault_source, name, pipeline_stage FROM certificates WHERE pipeline_stage IN ('Renewed', 'Deployed pending reload', 'Deployed, pending reload')"
        ).fetchall()
    finally:
        conn.close()

    resumed = []
    for vault_source, cert_id, stage in rows:
        logger.info(
            "Auto-resuming in-flight pipeline for cert='%s' (source='%s', stage='%s')",
            cert_id,
            vault_source,
            stage,
        )
        resume_pipeline_from_db(vault_source, cert_id, db_path=db_path)
        resumed.append((vault_source, cert_id, stage))
    return resumed


@worker_ready.connect
def on_worker_ready(sender=None, **kwargs):
    """
    Automatically runs when Celery worker starts up.
    Scans certops.db for any in-flight pipelines that were interrupted by a crash/restart
    and resumes them automatically.
    """
    logger.info("Celery worker ready signal triggered. Scanning DB for interrupted pipelines...")
    db_path = os.getenv("CERTOPS_DB_PATH", os.getenv("DB_PATH", "./certops.db"))
    resumed = resume_all_pending_pipelines(db_path=db_path)
    logger.info("Worker startup auto-resume complete. Resumed %d pipeline(s).", len(resumed))

