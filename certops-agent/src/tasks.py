import logging
import os
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
from celery import Celery, chain
from celery.signals import worker_ready
import sys
from pathlib import Path

_src_dir = Path(__file__).resolve().parent
_project_dir = _src_dir.parent
if str(_project_dir) not in sys.path:
    sys.path.insert(0, str(_project_dir))
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

load_dotenv()
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


def _parse_task_args(*args, **kwargs) -> tuple[str, str, str | None]:
    if len(args) == 1 and isinstance(args[0], dict):
        payload = args[0]
        cert_id = payload.get("cert_id", "")
        connector_name = payload.get("connector_name") or payload.get("vault_source") or ""
        db_path = payload.get("db_path")
        return cert_id, connector_name, db_path
    if len(args) >= 2:
        cert_id = str(args[0])
        connector_name = str(args[1])
        db_path = kwargs.get("db_path")
        return cert_id, connector_name, db_path
    cert_id = kwargs.get("cert_id", "")
    connector_name = kwargs.get("connector_name") or kwargs.get("vault_source") or ""
    db_path = kwargs.get("db_path")
    return cert_id, connector_name, db_path


@app.task(name="tasks.deploy_certificate")
def task_deploy_certificate(*args, **kwargs) -> dict:
    """
    Stage 2: Deploy staged certificate via connector and persist 'deployed' / 'deploy_failed'.
    """
    cert_id, connector_name, db_path = _parse_task_args(*args, **kwargs)
    logger.info("Running Stage 2 (Deploy): cert='%s' connector='%s'", cert_id, connector_name)
    from src import deployer
    res = deployer.run_deploy_pipeline(cert_id, connector_name, db_path=db_path)

    # Test-only delay: parks the pipeline at "Deployed pending reload" for kill/resume proof
    if os.getenv("CERTOPS_RUN_LIVE") and res.get("success"):
        delay = float(os.getenv("CERTOPS_TEST_STAGE_DELAY_SECONDS", "0"))
        if delay > 0:
            logger.info("[TEST STAGE DELAY] Parking at 'Deployed pending reload' for %.1f seconds", delay)
            time.sleep(delay)

    return {
        "vault_source": connector_name,
        "cert_id": cert_id,
        "stage": res.get("stage", "deployed"),
        "db_path": db_path,
        "success": res.get("success", True),
    }


@app.task(name="tasks.verify_reload")
def task_verify_reload(*args, **kwargs) -> dict:
    """
    Stage 3: Confirm reload and verify service certificate against live TLS, persisting 'verified' / 'verify_failed'.
    """
    cert_id, connector_name, db_path = _parse_task_args(*args, **kwargs)
    logger.info("Running Stage 3 (Verify Reload): cert='%s' connector='%s'", cert_id, connector_name)
    from src import deployer
    res = deployer.run_verify_pipeline(cert_id, connector_name, db_path=db_path)
    return {
        "vault_source": connector_name,
        "cert_id": cert_id,
        "stage": res.get("stage", "verified"),
        "db_path": db_path,
        "success": res.get("success", True),
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

    if stage in ("Renewed", "Issued pending deploy"):
        payload = {"vault_source": vault_source, "cert_id": cert_id, "stage": stage, "db_path": db_path}
        workflow = chain(task_deploy_certificate.s(payload), task_verify_reload.s())
        return workflow.apply_async()
    elif stage in ("Deployed pending reload", "Deployed, pending reload", "deployed"):
        # Stage 1 and 2 already completed in DB. Resume directly with Stage 3
        payload = {
            "vault_source": vault_source,
            "cert_id": cert_id,
            "stage": stage,
            "db_path": db_path,
        }
        return task_verify_reload.delay(payload)
    elif stage in ("Reload confirmed", "verified"):
        logger.info("Pipeline already complete ('%s') for cert='%s'.", stage, cert_id)
        return None
    else:
        # Start full pipeline if no known stage
        return start_pipeline(vault_source, cert_id, db_path=db_path)


def resume_all_pending_pipelines(db_path: str | None = None) -> list[tuple[str, str, str]]:
    """
    Queries certops.db for all certificates currently stuck in an in-flight pipeline stage
    ('Renewed', 'Issued pending deploy', 'Deployed pending reload', 'Deployed, pending reload', 'deployed') and auto-resumes them.
    Returns a list of (vault_source, cert_id, stage) tuples resumed.
    """
    conn = db.get_db_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT vault_source, name, pipeline_stage FROM certificates WHERE pipeline_stage IN ('Renewed', 'Issued pending deploy', 'Deployed pending reload', 'Deployed, pending reload', 'deployed')"
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
    from src import db
    db.run_migrations(db_path)
    resumed = resume_all_pending_pipelines(db_path=db_path)
    logger.info("Worker startup auto-resume complete. Resumed %d pipeline(s).", len(resumed))

