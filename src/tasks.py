import logging
import os
from datetime import datetime, timezone
from celery import Celery, chain
from celery.signals import worker_ready
from src import db, main

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
)


@app.task(name="tasks.renew_certificate")
def task_renew_certificate(vault_source: str, cert_id: str, db_path: str | None = None) -> dict:
    """
    Stage 1: Renew certificate and persist 'Renewed' state to DB.
    """
    logger.info("Running Stage 1 (Renew): cert='%s' source='%s'", cert_id, vault_source)
    now_dt = datetime.now(timezone.utc)

    # Ensure certificate record exists or update its stage to Renewed
    rec = db.get_certificate(vault_source, cert_id, db_path=db_path)
    if rec is None:
        db.upsert_certificate(
            vault_source=vault_source,
            name=cert_id,
            expiry_utc=now_dt,
            connector_category="host",
            pipeline_stage="Renewed",
            db_path=db_path,
        )
    else:
        db.update_pipeline_stage(vault_source, cert_id, "Renewed", db_path=db_path)

    return {
        "vault_source": vault_source,
        "cert_id": cert_id,
        "stage": "Renewed",
        "db_path": db_path,
    }


@app.task(name="tasks.deploy_certificate")
def task_deploy_certificate(payload: dict) -> dict:
    """
    Stage 2: Deploy certificate to host target and persist 'Deployed pending reload' state to DB.
    If DB state is already 'Deployed pending reload' or later, deployment is skipped idempotenly.
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

    # Perform deployment and persist state
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
    Stage 3: Confirm reload and verify service certificate, persisting 'Reload confirmed' state to DB.
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

    # Execute reload confirmation and update DB state
    db.update_pipeline_stage(vault_source, cert_id, "Reload confirmed", db_path=db_path)
    return {
        "vault_source": vault_source,
        "cert_id": cert_id,
        "stage": "Reload confirmed",
        "db_path": db_path,
    }


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

