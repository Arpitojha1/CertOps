"""
HTTP API bridge between the Python backend (db.py / main.py / scheduler.py) and the
React frontend. Thin wrapper — no reimplemented backend logic lives here.

Auth: JWT in httpOnly cookie via auth.py.
  GET routes: any authenticated user (viewer or admin).
  Mutating routes (POST/PATCH): admin only.
  /auth/* routes: public (login) or admin-only (signup).
"""

import json
import os
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import logging

import sys
from pathlib import Path
_agent_root = Path(__file__).resolve().parent.parent.parent / "certops-agent"
if _agent_root.exists() and str(_agent_root) not in sys.path:
    sys.path.append(str(_agent_root))
_agent_src = _agent_root / "src"
if _agent_src.exists() and str(_agent_src) not in sys.path:
    sys.path.append(str(_agent_src))

if __package__ is None or __package__ == "":
    import agent_auth
    import auth
    import db
    import main as main_module
    from auth import get_current_user, require_admin
    from scheduler import RenewalScheduler
    from routes import telemetry_ingest
else:
    from . import agent_auth, auth, db, main as main_module
    from .auth import get_current_user, require_admin
    from .scheduler import RenewalScheduler
    from .routes import telemetry_ingest

load_dotenv()

logger = logging.getLogger(__name__)

app = FastAPI(title="CertOps API")

# CORS: read allowed origins from env; never use "*" with credentials.
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


def _event_driven_scheduler_callback() -> None:
    logger.info("RenewalScheduler due job detected; Celery Beat owns actual triggering.")


@app.on_event("startup")
def startup_bootstrap() -> None:
    db.run_migrations()
    db.bootstrap_default_connectors()
    sched = RenewalScheduler(job_callback=_event_driven_scheduler_callback)
    sched.start()
    app.state.scheduler = sched


@app.on_event("shutdown")
def shutdown_cleanup() -> None:
    sched = getattr(app.state, "scheduler", None)
    if sched is not None:
        sched.stop()


# Auth routes (login/me/logout/signup) — mounted at root level so /auth/* works
app.include_router(auth.router)
app.include_router(agent_auth.router)
app.include_router(telemetry_ingest.router)


# ─── helpers ────────────────────────────────────────────────────────────────

def _actor_from_user(user: dict) -> tuple[int | None, str | None]:
    return (int(user["sub"]), user.get("email"))


def _status_for(cert: dict[str, Any], now_utc: datetime | None = None) -> str:
    stage = cert.get("pipeline_stage")
    if stage == "Deployed, pending reload":
        return "deployed_pending_reload"
    if stage == "Reload confirmed":
        return "reload_confirmed"
    if stage == "Renewed":
        return "renewed"

    now_utc = now_utc or datetime.now(timezone.utc)
    remaining_days = (cert["expiry_utc"] - now_utc).total_seconds() / 86400.0
    threshold = cert.get("renewal_threshold_days") or float(os.getenv("RENEWAL_THRESHOLD_DAYS", "2"))
    if remaining_days <= 0:
        return "overdue"
    if remaining_days <= threshold:
        return "due_soon"
    return "healthy"


def _serialize_cert(cert: dict[str, Any], group_names: dict[int, str], now_utc: datetime) -> dict[str, Any]:
    remaining_days = (cert["expiry_utc"] - now_utc).total_seconds() / 86400.0
    return {
        "id": f"{cert['vault_source']}:{cert['name']}",
        "vaultSource": cert["vault_source"],
        "name": cert["name"],
        "domain": cert.get("common_name") or cert["name"],
        "source": {
            "connectorId": cert["vault_source"],
            "connectorName": cert["vault_source"],
            "connectorType": "vault" if cert.get("connector_category", "secret_store") == "secret_store" else "host",
        },
        "expiryDate": cert["expiry_utc"].isoformat(),
        "daysRemaining": round(remaining_days, 4),
        "status": _status_for(cert, now_utc),
        "pipelineStage": cert.get("pipeline_stage"),
        "group": group_names.get(cert.get("group_id")) if cert.get("group_id") is not None else None,
        "groupId": cert.get("group_id"),
        "renewalThresholdDays": cert.get("renewal_threshold_days"),
        "nextRenewalAt": cert["next_renewal_at"].isoformat() if cert.get("next_renewal_at") else None,
        "nextNotificationCheckAt": cert["next_notification_check_at"].isoformat()
        if cert.get("next_notification_check_at")
        else None,
    }


# ─── health (public) ─────────────────────────────────────────────────────────

@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _get_tenant_scope(current_user: dict) -> str | None:
    if current_user.get("role") == "admin":
        return None
    return current_user.get("tenant_id", "default")


# ─── certificates ─────────────────────────────────────────────────────────────

@app.get("/api/certificates")
def list_certificates(current_user: dict = Depends(get_current_user)) -> list[dict[str, Any]]:
    now_utc = datetime.now(timezone.utc)
    group_names = {g["id"]: g["name"] for g in db.list_groups()}
    scope = _get_tenant_scope(current_user)
    return [_serialize_cert(c, group_names, now_utc) for c in db.list_all_certificates(tenant_id=scope)]


@app.get("/api/certificates/due")
def list_due_certificates(
    threshold_days: float | None = Query(default=None),
    vault_source: str | None = Query(default=None),
    group_id: int | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    now_utc = datetime.now(timezone.utc)
    group_names = {g["id"]: g["name"] for g in db.list_groups()}
    scope = _get_tenant_scope(current_user)
    due = db.get_due_certificates(vault_source=vault_source, threshold_days=threshold_days, group_id=group_id, tenant_id=scope)
    return [_serialize_cert(c, group_names, now_utc) for c in due]


@app.get("/api/certificates/{vault_source}/{name:path}")
def get_certificate(vault_source: str, name: str, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    scope = _get_tenant_scope(current_user)
    cert = db.get_certificate(vault_source, name, tenant_id=scope)
    if cert is None:
        raise HTTPException(status_code=404, detail="Certificate not found")
    now_utc = datetime.now(timezone.utc)
    group_names = {g["id"]: g["name"] for g in db.list_groups()}
    return _serialize_cert(cert, group_names, now_utc)


class TriggerRenewalRequest(BaseModel):
    vault_source: str
    cert_name: str


@app.post("/api/trigger_renewal")
@app.post("/api/certificates/{vault_source}/{name:path}/renew")
def trigger_certificate_renewal(
    vault_source: str | None = None,
    name: str | None = None,
    body: TriggerRenewalRequest | None = None,
    current_user: dict = Depends(require_admin),
) -> dict[str, Any]:
    from src import tasks
    vs = vault_source or (body.vault_source if body else None)
    nm = name or (body.cert_name if body else None)
    if not vs or not nm:
        raise HTTPException(status_code=400, detail="vault_source and cert_name required")
    scope = _get_tenant_scope(current_user)
    cert = db.get_certificate(vs, nm, tenant_id=scope)
    if not cert:
        raise HTTPException(status_code=404, detail=f"Certificate '{nm}' not found for source '{vs}'")
    db_p = os.getenv("CERTOPS_DB_PATH", os.getenv("DB_PATH", "./certops.db"))
    res = tasks.start_pipeline(vs, nm, db_path=db_p)
    return {
        "status": "triggered",
        "task_id": getattr(res, "id", str(res)),
        "cert_id": f"{vs}:{nm}",
        "pipelineStage": cert.get("pipeline_stage"),
    }



# ─── renewal log ──────────────────────────────────────────────────────────────

@app.get("/api/renewal-log")
def get_renewal_log(
    cert_id: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    success: bool | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    scope = _get_tenant_scope(current_user)
    logs = db.get_renewal_logs(cert_id=cert_id, tenant_id=scope)
    if event_type is not None:
        logs = [l for l in logs if l.get("event_type") == event_type]
    if success is not None:
        logs = [l for l in logs if bool(l.get("success")) == success]
    return logs


# ─── activity log ────────────────────────────────────────────────────────────

@app.get("/api/activity-log")
def get_activity_log(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    event_type: str | None = Query(default=None),
    include_renewal_log: bool = Query(default=True),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    is_admin = current_user.get("role") == "admin"
    scope = _get_tenant_scope(current_user)
    res = db.get_activity_logs(
        limit=max(limit + offset, 500) if include_renewal_log else limit,
        offset=0 if include_renewal_log else offset,
        event_type=event_type,
        admin_only=is_admin,
        tenant_id=scope,
    )
    items = list(res["items"])
    total = res["total"]

    if include_renewal_log:
        ren_logs = db.get_renewal_logs(tenant_id=scope)
        for row in ren_logs:
            et = row.get("event_type") or "certificate_renewed"
            if event_type is not None and et != event_type:
                continue
            ren_item = {
                "id": -(int(row.get("id", 0)) + 100000),
                "event_type": et,
                "actor_user_id": None,
                "actor_email": "system (renewal pipeline)",
                "target": row.get("cert_id") or row.get("vault_source") or "Certificate",
                "details": json.dumps({
                    "source": "renewal_log",
                    "connector": row.get("vault_source"),
                    "category": row.get("connector_category"),
                    "old_expiry": row.get("old_expiry"),
                    "new_expiry": row.get("new_expiry"),
                    "success": row.get("success"),
                    "detail": row.get("detail"),
                }),
                "timestamp": str(row.get("timestamp") or ""),
            }
            items.append(ren_item)

        items.sort(key=lambda x: str(x.get("timestamp") or ""), reverse=True)
        total = len(items)
        items = items[offset : offset + limit]

    return {"items": items, "total": total}


# ─── connectors ───────────────────────────────────────────────────────────────

def _serialize_connector(c: dict[str, Any]) -> dict[str, Any]:
    decrypted_config = db.decrypt_config(c["config"]) if isinstance(c.get("config"), str) else (c.get("config") or {})
    redacted_config = db.redact_config(decrypted_config)
    return {
        "id": c["id"],
        "name": c["name"],
        "category": c["category"],
        "renewal_threshold_days": c["renewal_threshold_days"],
        "renewalThresholdDays": c["renewal_threshold_days"],
        "config": redacted_config,
        "is_active": c["is_active"],
        "isActive": c["is_active"],
        "created_at": c["created_at"],
    }


class CreateConnectorRequest(BaseModel):
    name: str
    category: str
    renewal_threshold_days: float
    config: dict[str, Any] = {}
    is_active: bool = True


class UpdateConnectorRequest(BaseModel):
    name: str | None = None
    category: str | None = None
    renewal_threshold_days: float | None = None
    config: dict[str, Any] | None = None
    is_active: bool | None = None


@app.get("/api/connectors")
def list_connectors(
    active_only: bool = Query(default=False),
    current_user: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    scope = _get_tenant_scope(current_user)
    rows = db.list_connectors(active_only=active_only, tenant_id=scope)
    return [_serialize_connector(r) for r in rows]


@app.post("/api/connectors")
def create_connector(body: CreateConnectorRequest, current_user: dict = Depends(require_admin)) -> dict[str, Any]:
    caller_tenant = current_user.get("tenant_id", "default")
    existing = db.get_connector_by_name(body.name, tenant_id=caller_tenant)
    if existing:
        raise HTTPException(status_code=409, detail=f"Connector '{body.name}' already exists")
    config_str = json.dumps(body.config)
    cid = db.create_connector(
        name=body.name,
        category=body.category,
        renewal_threshold_days=body.renewal_threshold_days,
        config=config_str,
        is_active=body.is_active,
        tenant_id=caller_tenant,
    )
    connector = db.get_connector(cid)
    actor_id, actor_email = _actor_from_user(current_user)
    db.log_activity(
        event_type="connector_created",
        actor_user_id=actor_id,
        actor_email=actor_email,
        target=body.name,
        details={"name": body.name, "category": body.category, "config": db.redact_config(body.config)},
        tenant_id=caller_tenant,
    )
    return _serialize_connector(connector)


@app.put("/api/connectors/{connector_id}")
@app.patch("/api/connectors/{connector_id}")
def update_connector(
    connector_id: int,
    body: UpdateConnectorRequest,
    current_user: dict = Depends(require_admin),
) -> dict[str, Any]:
    caller_tenant = current_user.get("tenant_id", "default")
    existing = db.get_connector(connector_id, tenant_id=caller_tenant)
    if not existing:
        raise HTTPException(status_code=404, detail="Connector not found")
    if existing.get("tenant_id", "default") != caller_tenant:
        raise HTTPException(status_code=403, detail="Access denied: connector belongs to a different tenant")

    config_str = json.dumps(body.config) if body.config is not None else None
    db.update_connector(
        connector_id=connector_id,
        name=body.name,
        category=body.category,
        renewal_threshold_days=body.renewal_threshold_days,
        config=config_str,
        is_active=body.is_active,
    )
    updated = db.get_connector(connector_id)
    actor_id, actor_email = _actor_from_user(current_user)
    details: dict[str, Any] = {"connector_id": connector_id, "name": existing["name"]}
    if body.config is not None:
        details["config"] = db.redact_config(body.config)
    if body.renewal_threshold_days is not None:
        details["renewal_threshold_days"] = body.renewal_threshold_days
    if body.is_active is not None:
        details["is_active"] = body.is_active
    db.log_activity(
        event_type="connector_updated",
        actor_user_id=actor_id,
        actor_email=actor_email,
        target=existing["name"],
        details=details,
        tenant_id=caller_tenant,
    )
    return _serialize_connector(updated)


@app.delete("/api/connectors/{connector_id}")
def delete_connector(connector_id: int, current_user: dict = Depends(require_admin)) -> dict[str, Any]:
    caller_tenant = current_user.get("tenant_id", "default")
    existing = db.get_connector(connector_id, tenant_id=caller_tenant)
    if not existing:
        raise HTTPException(status_code=404, detail="Connector not found")
    if existing.get("tenant_id", "default") != caller_tenant:
        raise HTTPException(status_code=403, detail="Access denied: connector belongs to a different tenant")
    try:
        db.delete_connector(connector_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    actor_id, actor_email = _actor_from_user(current_user)
    db.log_activity(
        event_type="connector_deleted",
        actor_user_id=actor_id,
        actor_email=actor_email,
        target=existing["name"],
        details={"connector_id": connector_id, "name": existing["name"], "category": existing["category"]},
        tenant_id=caller_tenant,
    )
    return {"status": "ok", "deleted": connector_id}


@app.post("/api/connectors/{connector_id}/test")
def test_connector(connector_id: int, current_user: dict = Depends(require_admin)) -> dict[str, Any]:
    caller_tenant = current_user.get("tenant_id", "default")
    existing = db.get_connector(connector_id, tenant_id=caller_tenant)
    if not existing:
        raise HTTPException(status_code=404, detail="Connector not found")
    if existing.get("tenant_id", "default") != caller_tenant:
        raise HTTPException(status_code=403, detail="Access denied: connector belongs to a different tenant")
    actor_id, actor_email = _actor_from_user(current_user)
    db.log_activity(
        event_type="connector_tested",
        actor_user_id=actor_id,
        actor_email=actor_email,
        target=existing["name"],
        details={"connector_id": connector_id, "name": existing["name"]},
        tenant_id=caller_tenant,
    )
    return {
        "success": True,
        "is_stub": True,
        "message": f"[STUB] Simulated connectivity test for connector '{existing['name']}' ({existing['category']}). External live probe stubbed pending integration.",
    }


# ─── groups ───────────────────────────────────────────────────────────────────

@app.get("/api/groups")
def list_groups(current_user: dict = Depends(get_current_user)) -> list[dict[str, Any]]:
    scope = _get_tenant_scope(current_user)
    return db.list_groups(tenant_id=scope)


class CreateGroupRequest(BaseModel):
    name: str
    description: str = ""


@app.post("/api/groups")
def create_group(body: CreateGroupRequest, current_user: dict = Depends(require_admin)) -> dict[str, Any]:
    caller_tenant = current_user.get("tenant_id", "default")
    group_id = db.create_group(body.name, body.description, tenant_id=caller_tenant)
    actor_id, actor_email = _actor_from_user(current_user)
    db.log_activity(
        event_type="group_created",
        actor_user_id=actor_id,
        actor_email=actor_email,
        target=body.name,
        details={"group_id": group_id, "name": body.name, "description": body.description},
        tenant_id=caller_tenant,
    )
    return db.get_group(group_id)


class AssignGroupRequest(BaseModel):
    vault_source: str
    name: str
    group_id: int | None


@app.post("/api/certificates/assign-group")
def assign_certificate_group(body: AssignGroupRequest, current_user: dict = Depends(require_admin)) -> dict[str, str]:
    db.assign_certificate_group(body.vault_source, body.name, body.group_id)
    actor_id, actor_email = _actor_from_user(current_user)
    db.log_activity(
        event_type="group_assigned",
        actor_user_id=actor_id,
        actor_email=actor_email,
        target=f"{body.vault_source}:{body.name}",
        details={"vault_source": body.vault_source, "cert_name": body.name, "group_id": body.group_id},
    )
    return {"status": "ok"}


# ─── maintenance windows ──────────────────────────────────────────────────────

@app.get("/api/maintenance-windows")
def list_maintenance_windows(
    group_id: int | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    scope = _get_tenant_scope(current_user)
    windows = db.list_maintenance_windows(group_id=group_id, tenant_id=scope)
    return [
        {**w, "start_time": w["start_time"].isoformat(), "end_time": w["end_time"].isoformat()}
        for w in windows
    ]


class CreateMaintenanceWindowRequest(BaseModel):
    group_id: int
    start_time: str
    end_time: str
    recurrence: str = "once"


@app.post("/api/maintenance-windows")
def create_maintenance_window(
    body: CreateMaintenanceWindowRequest,
    current_user: dict = Depends(require_admin),
) -> dict[str, Any]:
    caller_tenant = current_user.get("tenant_id", "default")
    window_id = db.create_maintenance_window(
        body.group_id, body.start_time, body.end_time, body.recurrence,
        tenant_id=caller_tenant,
    )
    windows = db.list_maintenance_windows(group_id=body.group_id)
    match = next(w for w in windows if w["id"] == window_id)
    actor_id, actor_email = _actor_from_user(current_user)
    db.log_activity(
        event_type="maintenance_window_created",
        actor_user_id=actor_id,
        actor_email=actor_email,
        target=f"group:{body.group_id}",
        details={"window_id": window_id, "group_id": body.group_id, "start_time": body.start_time, "end_time": body.end_time, "recurrence": body.recurrence},
        tenant_id=caller_tenant,
    )
    return {**match, "start_time": match["start_time"].isoformat(), "end_time": match["end_time"].isoformat()}


# ─── notification policies ────────────────────────────────────────────────────

@app.get("/api/notification-policies")
def list_notification_policies(
    group_id: int | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    scope = _get_tenant_scope(current_user)
    return db.list_notification_policies(group_id=group_id, tenant_id=scope)


class CreateNotificationPolicyRequest(BaseModel):
    group_id: int
    threshold_days: float


@app.post("/api/notification-policies")
def create_notification_policy(
    body: CreateNotificationPolicyRequest,
    current_user: dict = Depends(require_admin),
) -> dict[str, Any]:
    caller_tenant = current_user.get("tenant_id", "default")
    policy_id = db.create_notification_policy(body.group_id, body.threshold_days, tenant_id=caller_tenant)
    policies = db.list_notification_policies(group_id=body.group_id)
    actor_id, actor_email = _actor_from_user(current_user)
    db.log_activity(
        event_type="notification_policy_created",
        actor_user_id=actor_id,
        actor_email=actor_email,
        target=f"group:{body.group_id}",
        details={"policy_id": policy_id, "group_id": body.group_id, "threshold_days": body.threshold_days},
        tenant_id=caller_tenant,
    )
    return next(p for p in policies if p["id"] == policy_id)


@app.delete("/api/notification-policies/{policy_id}")
def delete_notification_policy(policy_id: int, current_user: dict = Depends(require_admin)) -> dict[str, str]:
    caller_tenant = current_user.get("tenant_id", "default")
    conn = db.get_db_connection()
    try:
        row = conn.execute(
            "SELECT tenant_id FROM notification_policies WHERE id = ?", (policy_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Notification policy not found")
        if (row[0] or "default") != caller_tenant:
            raise HTTPException(status_code=403, detail="Access denied: policy belongs to a different tenant")
        conn.execute("DELETE FROM notification_policies WHERE id = ?", (policy_id,))
        conn.commit()
    finally:
        conn.close()
    actor_id, actor_email = _actor_from_user(current_user)
    db.log_activity(
        event_type="notification_policy_deleted",
        actor_user_id=actor_id,
        actor_email=actor_email,
        target=f"policy:{policy_id}",
        details={"policy_id": policy_id},
        tenant_id=caller_tenant,
    )
    return {"status": "deleted"}


# ─── notification log ─────────────────────────────────────────────────────────

@app.get("/api/notification-log")
def get_notification_log(
    cert_id: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    scope = _get_tenant_scope(current_user)
    return db.get_notification_logs(cert_id=cert_id, tenant_id=scope)


# ─── scheduler status ─────────────────────────────────────────────────────────

@app.get("/api/scheduler/status")
def scheduler_status(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """
    Derives scheduler state from certificates.next_renewal_at and recent renewal_log rows.
    Also exposes whether the in-process event-driven RenewalScheduler thread is running.
    """
    now_utc = datetime.now(timezone.utc)
    scope = _get_tenant_scope(current_user)
    certs = db.list_all_certificates(tenant_id=scope)
    upcoming = sorted(
        (c for c in certs if c.get("next_renewal_at") is not None),
        key=lambda c: c["next_renewal_at"],
    )
    next_job = upcoming[0] if upcoming else None
    recent_events = db.get_renewal_logs(tenant_id=scope)[-20:]
    sched = getattr(app.state, "scheduler", None)
    is_running = bool(
        sched is not None
        and getattr(sched, "_worker_thread", None) is not None
        and sched._worker_thread.is_alive()
    )
    return {
        "isRunning": is_running,
        "nextJob": {
            "vaultSource": next_job["vault_source"],
            "name": next_job["name"],
            "nextRenewalAt": next_job["next_renewal_at"].isoformat(),
            "secondsUntilDue": (next_job["next_renewal_at"] - now_utc).total_seconds(),
        }
        if next_job
        else None,
        "upcoming": [
            {
                "vaultSource": c["vault_source"],
                "name": c["name"],
                "nextRenewalAt": c["next_renewal_at"].isoformat(),
                "secondsUntilDue": (c["next_renewal_at"] - now_utc).total_seconds(),
            }
            for c in upcoming[:20]
        ],
        "recentEvents": recent_events,
    }


# ─── host reload (admin) ──────────────────────────────────────────────────────

class ConfirmReloadRequest(BaseModel):
    connector_name: str
    cert_id: str


@app.post("/api/host/confirm-reload")
def confirm_reload(body: ConfirmReloadRequest, _: dict = Depends(require_admin)) -> dict[str, Any]:
    try:
        success = main_module.confirm_and_reload_host(body.connector_name, body.cert_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"success": success}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("API_PORT", "8000")))
