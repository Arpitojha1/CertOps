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

if __package__ is None or __package__ == "":
    import auth
    import db
    import main as main_module
    from auth import get_current_user, require_admin
else:
    from . import auth, db, main as main_module
    from .auth import get_current_user, require_admin

load_dotenv()

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

# Auth routes (login/me/logout/signup) — mounted at root level so /auth/* works
app.include_router(auth.router)


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


# ─── certificates ─────────────────────────────────────────────────────────────

@app.get("/api/certificates")
def list_certificates(_: dict = Depends(get_current_user)) -> list[dict[str, Any]]:
    now_utc = datetime.now(timezone.utc)
    group_names = {g["id"]: g["name"] for g in db.list_groups()}
    return [_serialize_cert(c, group_names, now_utc) for c in db.list_all_certificates()]


@app.get("/api/certificates/due")
def list_due_certificates(
    threshold_days: float | None = Query(default=None),
    vault_source: str | None = Query(default=None),
    group_id: int | None = Query(default=None),
    _: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    now_utc = datetime.now(timezone.utc)
    group_names = {g["id"]: g["name"] for g in db.list_groups()}
    due = db.get_due_certificates(vault_source=vault_source, threshold_days=threshold_days, group_id=group_id)
    return [_serialize_cert(c, group_names, now_utc) for c in due]


@app.get("/api/certificates/{vault_source}/{name}")
def get_certificate(vault_source: str, name: str, _: dict = Depends(get_current_user)) -> dict[str, Any]:
    cert = db.get_certificate(vault_source, name)
    if cert is None:
        raise HTTPException(status_code=404, detail="Certificate not found")
    now_utc = datetime.now(timezone.utc)
    group_names = {g["id"]: g["name"] for g in db.list_groups()}
    return _serialize_cert(cert, group_names, now_utc)


# ─── renewal log ──────────────────────────────────────────────────────────────

@app.get("/api/renewal-log")
def get_renewal_log(
    cert_id: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    success: bool | None = Query(default=None),
    _: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    logs = db.get_renewal_logs(cert_id=cert_id)
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
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    is_admin = current_user.get("role") == "admin"
    return db.get_activity_logs(
        limit=limit,
        offset=offset,
        event_type=event_type,
        admin_only=is_admin,
    )


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
    _: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    rows = db.list_connectors(active_only=active_only)
    return [_serialize_connector(r) for r in rows]


@app.post("/api/connectors")
def create_connector(body: CreateConnectorRequest, current_user: dict = Depends(require_admin)) -> dict[str, Any]:
    existing = db.get_connector_by_name(body.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Connector '{body.name}' already exists")
    config_str = json.dumps(body.config)
    cid = db.create_connector(
        name=body.name,
        category=body.category,
        renewal_threshold_days=body.renewal_threshold_days,
        config=config_str,
        is_active=body.is_active,
    )
    connector = db.get_connector(cid)
    actor_id, actor_email = _actor_from_user(current_user)
    db.log_activity(
        event_type="connector_created",
        actor_user_id=actor_id,
        actor_email=actor_email,
        target=body.name,
        details={"name": body.name, "category": body.category, "config": db.redact_config(body.config)},
    )
    return _serialize_connector(connector)


@app.put("/api/connectors/{connector_id}")
@app.patch("/api/connectors/{connector_id}")
def update_connector(
    connector_id: int,
    body: UpdateConnectorRequest,
    current_user: dict = Depends(require_admin),
) -> dict[str, Any]:
    existing = db.get_connector(connector_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Connector not found")

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
    )
    return _serialize_connector(updated)


@app.delete("/api/connectors/{connector_id}")
def delete_connector(connector_id: int, current_user: dict = Depends(require_admin)) -> dict[str, Any]:
    existing = db.get_connector(connector_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Connector not found")
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
    )
    return {"status": "ok", "deleted": connector_id}


@app.post("/api/connectors/{connector_id}/test")
def test_connector(connector_id: int, current_user: dict = Depends(require_admin)) -> dict[str, Any]:
    existing = db.get_connector(connector_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Connector not found")
    actor_id, actor_email = _actor_from_user(current_user)
    db.log_activity(
        event_type="connector_tested",
        actor_user_id=actor_id,
        actor_email=actor_email,
        target=existing["name"],
        details={"connector_id": connector_id, "name": existing["name"]},
    )
    return {
        "success": True,
        "is_stub": True,
        "message": f"[STUB] Simulated connectivity test for connector '{existing['name']}' ({existing['category']}). External live probe stubbed pending integration.",
    }


# ─── groups ───────────────────────────────────────────────────────────────────

@app.get("/api/groups")
def list_groups(_: dict = Depends(get_current_user)) -> list[dict[str, Any]]:
    return db.list_groups()


class CreateGroupRequest(BaseModel):
    name: str
    description: str = ""


@app.post("/api/groups")
def create_group(body: CreateGroupRequest, current_user: dict = Depends(require_admin)) -> dict[str, Any]:
    group_id = db.create_group(body.name, body.description)
    actor_id, actor_email = _actor_from_user(current_user)
    db.log_activity(
        event_type="group_created",
        actor_user_id=actor_id,
        actor_email=actor_email,
        target=body.name,
        details={"group_id": group_id, "name": body.name, "description": body.description},
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
    _: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    windows = db.list_maintenance_windows(group_id=group_id)
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
    window_id = db.create_maintenance_window(body.group_id, body.start_time, body.end_time, body.recurrence)
    windows = db.list_maintenance_windows(group_id=body.group_id)
    match = next(w for w in windows if w["id"] == window_id)
    actor_id, actor_email = _actor_from_user(current_user)
    db.log_activity(
        event_type="maintenance_window_created",
        actor_user_id=actor_id,
        actor_email=actor_email,
        target=f"group:{body.group_id}",
        details={"window_id": window_id, "group_id": body.group_id, "start_time": body.start_time, "end_time": body.end_time, "recurrence": body.recurrence},
    )
    return {**match, "start_time": match["start_time"].isoformat(), "end_time": match["end_time"].isoformat()}


# ─── notification policies ────────────────────────────────────────────────────

@app.get("/api/notification-policies")
def list_notification_policies(
    group_id: int | None = Query(default=None),
    _: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    return db.list_notification_policies(group_id=group_id)


class CreateNotificationPolicyRequest(BaseModel):
    group_id: int
    threshold_days: float


@app.post("/api/notification-policies")
def create_notification_policy(
    body: CreateNotificationPolicyRequest,
    current_user: dict = Depends(require_admin),
) -> dict[str, Any]:
    policy_id = db.create_notification_policy(body.group_id, body.threshold_days)
    policies = db.list_notification_policies(group_id=body.group_id)
    actor_id, actor_email = _actor_from_user(current_user)
    db.log_activity(
        event_type="notification_policy_created",
        actor_user_id=actor_id,
        actor_email=actor_email,
        target=f"group:{body.group_id}",
        details={"policy_id": policy_id, "group_id": body.group_id, "threshold_days": body.threshold_days},
    )
    return next(p for p in policies if p["id"] == policy_id)


@app.delete("/api/notification-policies/{policy_id}")
def delete_notification_policy(policy_id: int, current_user: dict = Depends(require_admin)) -> dict[str, str]:
    conn = db.get_db_connection()
    try:
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
    )
    return {"status": "deleted"}


# ─── notification log ─────────────────────────────────────────────────────────

@app.get("/api/notification-log")
def get_notification_log(
    cert_id: str | None = Query(default=None),
    _: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    return db.get_notification_logs(cert_id=cert_id)


# ─── scheduler status ─────────────────────────────────────────────────────────

@app.get("/api/scheduler/status")
def scheduler_status(_: dict = Depends(get_current_user)) -> dict[str, Any]:
    """
    Derives scheduler state from certificates.next_renewal_at and recent renewal_log rows.
    No live scheduler process handle exists in this HTTP process.
    """
    now_utc = datetime.now(timezone.utc)
    certs = db.list_all_certificates()
    upcoming = sorted(
        (c for c in certs if c.get("next_renewal_at") is not None),
        key=lambda c: c["next_renewal_at"],
    )
    next_job = upcoming[0] if upcoming else None
    recent_events = db.get_renewal_logs()[-20:]
    return {
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
