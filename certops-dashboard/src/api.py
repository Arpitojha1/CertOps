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
from typing import Any, Callable

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
    from auth import get_current_user, require_admin, require_plan
    from scheduler import RenewalScheduler
    from routes import telemetry_ingest, agents, usage
else:
    from . import agent_auth, auth, db
    import main as main_module
    from .auth import get_current_user, require_admin, require_plan
    from .scheduler import RenewalScheduler
    from .routes import telemetry_ingest, agents, usage

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
    allow_headers=["Content-Type", "Authorization", "X-Tenant-Id"],
    expose_headers=["Content-Type", "X-Tenant-Id"],
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
app.include_router(agents.router)
app.include_router(usage.router)


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


def _normalise_cert_status(raw_status: str) -> str:
    """Map internal pipeline/expiry status strings to the UI CertStatus union."""
    mapping = {
        "healthy": "Active",
        "due_soon": "Expiring Soon",
        "overdue": "Expired",
        "renewed": "Active",
        "deployed_pending_reload": "Pending",
        "reload_confirmed": "Active",
    }
    return mapping.get(raw_status, "Active")


def _serialize_cert(cert: dict[str, Any], group_names: dict[int, str], now_utc: datetime) -> dict[str, Any]:
    remaining_days = (cert["expiry_utc"] - now_utc).total_seconds() / 86400.0
    internal_status = _status_for(cert, now_utc)
    # connector string: prefer the human-readable vault_source name
    connector_str = cert.get("vault_source") or ""
    return {
        "id": f"{cert['vault_source']}:{cert['name']}",
        "vaultSource": cert["vault_source"],
        "name": cert["name"],
        "domain": cert.get("common_name") or cert["name"],
        # camelCase fields for frontendNew
        "connector": connector_str,
        "ca": cert.get("ca") or "Unknown",
        "expiryDate": cert["expiry_utc"].isoformat(),
        "daysRemaining": round(remaining_days, 4),
        "status": _normalise_cert_status(internal_status),
        "group": group_names.get(cert.get("group_id"), "") if cert.get("group_id") is not None else "",
        # extended fields (populated when available)
        "type": cert.get("cert_type") or "Server",
        "owner": cert.get("owner") or "",
        # legacy / internal fields retained for backward compat
        "source": {
            "connectorId": cert["vault_source"],
            "connectorName": cert["vault_source"],
            "connectorType": "vault" if cert.get("connector_category", "secret_store") == "secret_store" else "host",
        },
        "pipelineStage": cert.get("pipeline_stage"),
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
    if current_user.get("role") == "admin" and current_user.get("tenant_id", "default") == "default":
        return None
    return current_user.get("tenant_id", "default")


def require_owned_entity(
    fetch_fn: Callable[..., Any],
    *args: Any,
    tenant_id: str | None,
    entity_label: str = "resource",
) -> dict:
    """Verify an entity fetched from DB belongs to the caller's tenant."""
    entity = fetch_fn(*args)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"{entity_label} not found")
    if tenant_id is not None and entity.get("tenant_id") != tenant_id:
        raise HTTPException(status_code=403, detail=f"Access denied: {entity_label} belongs to a different tenant")
    return entity


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

def _normalise_event_type(raw: str | None) -> str:
    """Map DB event_type strings to the UI EventLog.type union."""
    if not raw:
        return "Config"
    r = raw.lower()
    if "renewal" in r or "renew" in r:
        return "Renewal"
    if "revoc" in r:
        return "Revocation"
    if "issue" in r or "enroll" in r:
        return "Issuance"
    if "login" in r or "auth" in r or "logout" in r:
        return "Login"
    if "config" in r or "connector" in r or "group" in r or "policy" in r or "setting" in r:
        return "Config"
    if "discover" in r:
        return "Discovery"
    if "fail" in r or "error" in r:
        return "Failure"
    return "Config"


def _derive_event_status(details_str: str | None, success: bool | None) -> str:
    """Derive UI status from details blob and/or a success flag."""
    if success is False:
        return "Failed"
    if success is True:
        return "Success"
    if details_str:
        d = details_str.lower()
        if any(kw in d for kw in ("error", "fail", "exception", "traceback")):
            return "Failed"
    return "Success"


def _serialize_activity_item(item: dict[str, Any]) -> dict[str, Any]:
    raw_et = item.get("event_type") or ""
    details_raw = item.get("details") or ""
    # details may be a JSON string or a dict
    if isinstance(details_raw, dict):
        details_str = json.dumps(details_raw)
        success_flag = details_raw.get("success")
    else:
        details_str = str(details_raw)
        try:
            parsed = json.loads(details_str)
            success_flag = parsed.get("success")
        except Exception:
            success_flag = None

    description = (
        item.get("description")
        or item.get("target")
        or details_str[:120]
        or raw_et
    )

    return {
        **item,
        # camelCase UI-facing overrides
        "type": _normalise_event_type(raw_et),
        "description": description,
        "status": _derive_event_status(details_str, success_flag),
        # keep snake_case originals for backward compat
        "event_type": raw_et,
        "details": details_str,
    }


@app.get("/api/activity-log")
def get_activity_log(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    event_type: str | None = Query(default=None),
    include_renewal_log: bool = Query(default=True),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
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

    # Date range filtering (client passes ISO date strings)
    if start_date or end_date:
        def _in_range(item: dict) -> bool:
            ts = str(item.get("timestamp") or "")
            if start_date and ts < start_date:
                return False
            if end_date and ts > end_date + "T23:59:59":
                return False
            return True
        items = [i for i in items if _in_range(i)]
        total = len(items)

    return {"items": [_serialize_activity_item(i) for i in items], "total": total}


# ─── connectors ───────────────────────────────────────────────────────────────

_CATEGORY_MAP: dict[str, str] = {
    "secret_store": "Secret Store",
    "azure": "Secret Store",
    "azure_keyvault": "Secret Store",
    "hashicorp": "Secret Store",
    "hashicorp_vault": "Secret Store",
    "vault": "Secret Store",
    "aws": "Secret Store",
    "host": "Host",
    "ssh": "Host",
    "ssh_host": "Host",
    "winrm": "Host",
    "winrm_host": "Host",
    "ca": "Certificate Authority",
    "certificate_authority": "Certificate Authority",
    "lets_encrypt": "Certificate Authority",
    "acme": "Certificate Authority",
    "digicert": "Certificate Authority",
}


def _normalise_category(raw: str | None) -> str:
    if not raw:
        return "Host"
    return _CATEGORY_MAP.get(raw.lower(), raw)


def _serialize_connector(c: dict[str, Any]) -> dict[str, Any]:
    decrypted_config = db.decrypt_config(c["config"]) if isinstance(c.get("config"), str) else (c.get("config") or {})
    redacted_config = db.redact_config(decrypted_config)
    raw_cat = c.get("category") or ""
    normalised_cat = _normalise_category(raw_cat)
    # Connection status: backends may store last_test_result; default to Connected if active.
    raw_status = c.get("last_test_result") or ("Connected" if c.get("is_active") else "Pending")
    status_map = {"success": "Connected", "ok": "Connected", "error": "Error", "failed": "Error"}
    ui_status = status_map.get(str(raw_status).lower(), raw_status)
    return {
        "id": c["id"],
        "name": c["name"],
        # normalised UI-facing fields
        "category": normalised_cat,
        "renewalThreshold": c["renewal_threshold_days"],
        "status": ui_status,
        # backward-compat snake_case fields
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
    is_super_admin = current_user.get("role") == "admin" and caller_tenant == "default"
    scope = None if is_super_admin else caller_tenant
    existing = require_owned_entity(db.get_connector, connector_id, tenant_id=scope, entity_label="connector")

    config_str = json.dumps(body.config) if body.config is not None else None
    db.update_connector(
        connector_id=connector_id,
        name=body.name,
        category=body.category,
        renewal_threshold_days=body.renewal_threshold_days,
        config=config_str,
        is_active=body.is_active,
        tenant_id=scope,
    )
    updated = db.get_connector(connector_id, tenant_id=scope)
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
    is_super_admin = current_user.get("role") == "admin" and caller_tenant == "default"
    scope = None if is_super_admin else caller_tenant
    existing = require_owned_entity(db.get_connector, connector_id, tenant_id=scope, entity_label="connector")
    try:
        db.delete_connector(connector_id, tenant_id=scope)
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
    groups = db.list_groups(tenant_id=scope)
    # Join maintenance windows and notification policies so frontendNew can render
    # group cards without extra round-trips.
    try:
        windows = db.list_maintenance_windows(tenant_id=scope)
        policies = db.list_notification_policies(tenant_id=scope)
    except Exception:
        windows, policies = [], []

    def _fmt_window(w: dict) -> str:
        try:
            recur = w.get("recurrence") or ""
            start = str(w.get("start_time", ""))
            end = str(w.get("end_time", ""))
            return f"{recur} {start[:16]}-{end[:16]} UTC".strip()
        except Exception:
            return "Configured"

    result = []
    for g in groups:
        gid = g.get("id")
        win = next((w for w in windows if w.get("group_id") == gid), None)
        pol = next((p for p in policies if p.get("group_id") == gid), None)
        result.append({
            **g,
            "maintenanceWindow": _fmt_window(win) if win else "Not configured",
            "notificationPolicy": f"{pol['threshold_days']} days" if pol and pol.get("threshold_days") else "Default",
        })
    return result


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
    caller_tenant = current_user.get("tenant_id", "default")
    is_super_admin = current_user.get("role") == "admin" and caller_tenant == "default"
    scope = None if is_super_admin else caller_tenant
    require_owned_entity(db.get_certificate, body.vault_source, body.name, tenant_id=scope, entity_label="certificate")
    require_owned_entity(db.get_group, body.group_id, tenant_id=scope, entity_label="group")
    db.assign_certificate_group(body.vault_source, body.name, body.group_id, tenant_id=scope)
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
    is_super_admin = current_user.get("role") == "admin" and caller_tenant == "default"
    scope = None if is_super_admin else caller_tenant
    require_owned_entity(db.get_group, body.group_id, tenant_id=scope, entity_label="group")
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
    raw_policies = db.list_notification_policies(group_id=group_id, tenant_id=scope)
    group_names = {g["id"]: g["name"] for g in db.list_groups(tenant_id=scope)}

    result = []
    for p in raw_policies:
        threshold_days = p.get("threshold_days") or 30
        is_active = p.get("is_active")
        status = "Active" if (is_active is None or bool(is_active)) else "Disabled"
        result.append({
            **p,
            # camelCase UI-facing fields
            "group": group_names.get(p.get("group_id"), str(p.get("group_id", ""))),
            "threshold": f"{int(threshold_days)} days",
            "channel": p.get("channel") or "Email",
            "status": status,
        })
    return result


class CreateNotificationPolicyRequest(BaseModel):
    group_id: int
    threshold_days: float


@app.post("/api/notification-policies")
def create_notification_policy(
    body: CreateNotificationPolicyRequest,
    current_user: dict = Depends(require_admin),
) -> dict[str, Any]:
    caller_tenant = current_user.get("tenant_id", "default")
    is_super_admin = current_user.get("role") == "admin" and caller_tenant == "default"
    scope = None if is_super_admin else caller_tenant
    require_owned_entity(db.get_group, body.group_id, tenant_id=scope, entity_label="group")
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
    is_super_admin = current_user.get("role") == "admin" and caller_tenant == "default"
    scope = None if is_super_admin else caller_tenant
    conn = db.get_db_connection()
    try:
        row = conn.execute(
            "SELECT tenant_id FROM notification_policies WHERE id = ?", (policy_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Notification policy not found")
        if scope is not None and (row[0] or "default") != scope:
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
        target=f"policy_{policy_id}",
        details={"policy_id": policy_id},
        tenant_id=caller_tenant,
    )
    return {"status": "ok"}


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
def confirm_reload(body: ConfirmReloadRequest, current_user: dict = Depends(require_admin)) -> dict[str, Any]:
    caller_tenant = current_user.get("tenant_id", "default")
    is_super_admin = current_user.get("role") == "admin" and caller_tenant == "default"
    scope = None if is_super_admin else caller_tenant
    require_owned_entity(db.get_connector_by_name, body.connector_name, tenant_id=scope, entity_label="connector")
    try:
        success = main_module.confirm_and_reload_host(body.connector_name, body.cert_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"success": success}


# ─── Tier 2: DELETE certificate ───────────────────────────────────────────────

@app.delete("/api/certificates/{vault_source}/{cert_name:path}")
def delete_certificate(
    vault_source: str,
    cert_name: str,
    current_user: dict = Depends(require_admin),
) -> dict[str, Any]:
    caller_tenant = current_user.get("tenant_id", "default")
    is_super_admin = current_user.get("role") == "admin" and caller_tenant == "default"
    scope = None if is_super_admin else caller_tenant
    cert = db.get_certificate(vault_source, cert_name, tenant_id=scope)
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    db.delete_certificate(vault_source, cert_name, tenant_id=scope)
    actor_id, actor_email = _actor_from_user(current_user)
    db.log_activity(
        event_type="certificate_deleted", actor_user_id=actor_id, actor_email=actor_email,
        target=f"{vault_source}:{cert_name}", details={"vault_source": vault_source, "name": cert_name},
        tenant_id=caller_tenant,
    )
    return {"status": "deleted", "id": f"{vault_source}:{cert_name}"}

@app.get("/api/dashboard/summary")
def get_dashboard_summary(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    now_utc = datetime.now(timezone.utc)
    scope = _get_tenant_scope(current_user)
    certs = db.list_all_certificates(tenant_id=scope)
    healthy = due_soon = overdue = pending_reload = 0
    for c in certs:
        s = _status_for(c, now_utc)
        if s in ("healthy", "renewed", "reload_confirmed"):
            healthy += 1
        elif s == "due_soon":
            due_soon += 1
        elif s == "overdue":
            overdue += 1
        if s == "deployed_pending_reload":
            pending_reload += 1
    return {"healthy": healthy, "dueSoon": due_soon, "overdue": overdue, "pendingReload": pending_reload, "total": len(certs)}

_DEFAULT_SETTINGS: dict[str, Any] = {
    "defaultRenewalThreshold": 30,
    "defaultKeySize": "RSA 2048",
    "acmeContactEmail": "",
}


@app.get("/api/settings")
def get_settings(current_user: dict = Depends(require_admin)) -> dict[str, Any]:
    stored = {k: db.get_setting(k) for k in _DEFAULT_SETTINGS if db.get_setting(k) is not None}
    return {**_DEFAULT_SETTINGS, **stored}

class SettingsUpdateRequest(BaseModel):
    defaultRenewalThreshold: int | None = None
    defaultKeySize: str | None = None
    acmeContactEmail: str | None = None


@app.put("/api/settings")
def update_settings(body: SettingsUpdateRequest, current_user: dict = Depends(require_admin)) -> dict[str, Any]:
    caller_tenant = current_user.get("tenant_id", "default")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    for k, v in updates.items():
        db.set_setting(k, v)
    actor_id, actor_email = _actor_from_user(current_user)
    db.log_activity(
        event_type="settings_updated", actor_user_id=actor_id, actor_email=actor_email,
        target="global_settings", details=updates, tenant_id=caller_tenant,
    )
    return {**_DEFAULT_SETTINGS, **updates}

class BulkRenewRequest(BaseModel):
    cert_ids: list[str]


class BulkRevokeRequest(BaseModel):
    cert_ids: list[str]
    reason: str = "unspecified"


class EnrollRequest(BaseModel):
    domain: str
    connector_id: int
    ca: str = "Let's Encrypt"
    key_size: str = "RSA 2048"


class PlanUpdateRequest(BaseModel):
    plan: str


@app.post("/api/certificates/bulk-renew")
def bulk_renew(body: BulkRenewRequest, current_user: dict = Depends(require_admin)) -> dict[str, Any]:
    from src import tasks  # noqa: PLC0415
    results = []
    for cert_id in body.cert_ids:
        parts = cert_id.split(":", 1)
        if len(parts) != 2:
            results.append({"cert_id": cert_id, "status": "error", "detail": "invalid id format"})
            continue
        vs, nm = parts
        try:
            db_p = os.getenv("CERTOPS_DB_PATH", os.getenv("DB_PATH", "./certops.db"))
            res = tasks.start_pipeline(vs, nm, db_path=db_p)
            results.append({"cert_id": cert_id, "status": "triggered", "task_id": getattr(res, "id", str(res))})
        except Exception as exc:
            results.append({"cert_id": cert_id, "status": "error", "detail": str(exc)})
    triggered_count = sum(1 for r in results if r["status"] == "triggered")
    caller_tenant = current_user.get("tenant_id", "default")
    actor_id, actor_email = _actor_from_user(current_user)
    db.log_activity(
        event_type="certificates_bulk_renewed", actor_user_id=actor_id, actor_email=actor_email,
        target=f"{len(body.cert_ids)} certificates", details={"cert_ids": body.cert_ids, "triggered": triggered_count},
        tenant_id=caller_tenant,
    )
    return {"results": results, "total": len(body.cert_ids), "triggered": triggered_count}


@app.post("/api/certificates/bulk-revoke")
def bulk_revoke(body: BulkRevokeRequest, current_user: dict = Depends(require_admin)) -> dict[str, Any]:
    caller_tenant = current_user.get("tenant_id", "default")
    actor_id, actor_email = _actor_from_user(current_user)
    results = []
    for cert_id in body.cert_ids:
        parts = cert_id.split(":", 1)
        if len(parts) != 2:
            results.append({"cert_id": cert_id, "status": "error", "detail": "invalid id format"})
            continue
        vs, nm = parts
        db.log_activity(
            event_type="certificate_revoked", actor_user_id=actor_id, actor_email=actor_email,
            target=cert_id, details={"vault_source": vs, "name": nm, "reason": body.reason}, tenant_id=caller_tenant,
        )
        results.append({"cert_id": cert_id, "status": "revoked"})
    return {"results": results, "total": len(body.cert_ids)}


@app.post("/api/certificates/enroll")
def enroll_certificate(body: EnrollRequest, current_user: dict = Depends(require_admin)) -> dict[str, Any]:
    caller_tenant = current_user.get("tenant_id", "default")
    actor_id, actor_email = _actor_from_user(current_user)
    db.log_activity(
        event_type="certificate_enrollment_requested", actor_user_id=actor_id, actor_email=actor_email,
        target=body.domain, details={"domain": body.domain, "connector_id": body.connector_id, "ca": body.ca},
        tenant_id=caller_tenant,
    )
    return {"status": "pending", "domain": body.domain, "ca": body.ca,
            "message": f"Enrollment for {body.domain} queued. CA integration (Phase 3) pending."}


@app.put("/api/users/{user_id}/plan")
def update_user_plan_endpoint(
    user_id: int,
    body: PlanUpdateRequest,
    current_user: dict = Depends(require_admin),
) -> dict[str, Any]:
    if body.plan not in ("Starter", "Professional", "Enterprise"):
        raise HTTPException(status_code=400, detail="Invalid plan tier")
    if not db.update_user_plan(user_id, body.plan):
        raise HTTPException(status_code=404, detail="User not found")
    actor_id, actor_email = _actor_from_user(current_user)
    db.log_activity(
        event_type="user_plan_updated",
        actor_user_id=actor_id,
        actor_email=actor_email,
        target=str(user_id),
        details={"user_id": user_id, "new_plan": body.plan},
        tenant_id=current_user.get("tenant_id", "default"),
    )
    return {"status": "updated", "user_id": user_id, "plan": body.plan}


@app.post("/api/certificates/{vault_source}/{cert_name:path}/reissue")
def reissue_certificate(vault_source: str, cert_name: str, current_user: dict = Depends(require_admin)) -> dict[str, Any]:
    from src import tasks  # noqa: PLC0415
    scope = _get_tenant_scope(current_user)
    cert = db.get_certificate(vault_source, cert_name, tenant_id=scope)
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    db_p = os.getenv("CERTOPS_DB_PATH", os.getenv("DB_PATH", "./certops.db"))
    res = tasks.start_pipeline(vault_source, cert_name, db_path=db_p)
    caller_tenant = current_user.get("tenant_id", "default")
    actor_id, actor_email = _actor_from_user(current_user)
    db.log_activity(
        event_type="certificate_reissue_requested", actor_user_id=actor_id, actor_email=actor_email,
        target=f"{vault_source}:{cert_name}", details={"task_id": getattr(res, "id", str(res))},
        tenant_id=caller_tenant,
    )
    return {"status": "reissue_triggered", "task_id": getattr(res, "id", str(res)), "cert_id": f"{vault_source}:{cert_name}"}


@app.get("/api/certificates/{vault_source}/{cert_name:path}/ocsp")
def check_ocsp(vault_source: str, cert_name: str, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    scope = _get_tenant_scope(current_user)
    cert = db.get_certificate(vault_source, cert_name, tenant_id=scope)
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    return {"cert_id": f"{vault_source}:{cert_name}", "ocsp_status": "good", "is_stub": True}

@app.get("/api/enterprise/discovery/rules")
def get_discovery_rules(current_user: dict = Depends(require_plan("Enterprise"))) -> dict[str, Any]:
    return {"items": [], "total": 0}


@app.get("/api/enterprise/discovery/network-inventory")
def get_network_inventory(current_user: dict = Depends(require_plan("Enterprise"))) -> dict[str, Any]:
    return {"items": [], "total": 0}


@app.get("/api/enterprise/discovery/excluded")
def get_excluded_certs(current_user: dict = Depends(require_plan("Enterprise"))) -> dict[str, Any]:
    return {"items": [], "total": 0}


@app.post("/api/enterprise/discovery/scan")
def trigger_discovery_scan(current_user: dict = Depends(require_plan("Enterprise"))) -> dict[str, Any]:
    caller_tenant = current_user.get("tenant_id", "default")
    actor_id, actor_email = _actor_from_user(current_user)
    db.log_activity(event_type="discovery_scan_triggered", actor_user_id=actor_id, actor_email=actor_email,
                    target="network", details={}, tenant_id=caller_tenant)
    return {"status": "triggered", "is_stub": True, "message": "Phase 2 network probe pending."}

@app.get("/api/enterprise/health/ca-status")
def get_ca_health_status(current_user: dict = Depends(require_plan("Enterprise"))) -> list[dict[str, Any]]:
    scope = _get_tenant_scope(current_user)
    logs = db.get_renewal_logs(tenant_id=scope)
    ca_stats: dict[str, dict] = {}
    for row in logs:
        ca = row.get("vault_source") or "Unknown"
        if ca not in ca_stats:
            ca_stats[ca] = {"total": 0, "success": 0}
        ca_stats[ca]["total"] += 1
        if row.get("success"):
            ca_stats[ca]["success"] += 1
    result = []
    for ca_name, stats in ca_stats.items():
        total, success = stats["total"], stats["success"]
        error_rate = round((1 - success / total) * 100, 1) if total > 0 else 0.0
        result.append({
            "id": ca_name, "name": ca_name, "uptime": round(100 - error_rate, 1),
            "errorRate": error_rate, "status": "Healthy" if error_rate < 5 else ("Degraded" if error_rate < 30 else "Down"),
        })
    return result


@app.get("/api/enterprise/health/metrics")
def get_health_metrics(current_user: dict = Depends(require_plan("Enterprise"))) -> dict[str, Any]:
    return {"actionFailureRate": [], "discoveryEfficiency": []}

@app.get("/api/enterprise/ca-policies")
def get_ca_policies_list(current_user: dict = Depends(require_plan("Enterprise"))) -> dict[str, Any]:
    return {"items": [], "total": 0}


@app.post("/api/enterprise/ca-policies")
def create_ca_policy(body: dict, current_user: dict = Depends(require_plan("Enterprise"))) -> dict[str, Any]:
    return {"status": "stub", "note": "CA policy storage (Phase 2) not yet implemented."}


@app.get("/api/enterprise/insights/ca-distribution")
def get_ca_distribution(current_user: dict = Depends(require_plan("Enterprise"))) -> list[dict[str, Any]]:
    scope = _get_tenant_scope(current_user)
    certs = db.list_all_certificates(tenant_id=scope)
    counts: dict[str, int] = {}
    for c in certs:
        src = c.get("vault_source") or "Unknown"
        counts[src] = counts.get(src, 0) + 1
    return [{"name": k, "value": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]


@app.get("/api/enterprise/insights/volume")
def get_volume_history(current_user: dict = Depends(require_plan("Enterprise"))) -> list[dict[str, Any]]:
    from collections import defaultdict  # noqa: PLC0415
    scope = _get_tenant_scope(current_user)
    logs = db.get_renewal_logs(tenant_id=scope)
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"issued": 0, "expired": 0})
    for row in logs:
        ts = str(row.get("timestamp") or "")[:7]
        if row.get("success"):
            buckets[ts]["issued"] += 1
        else:
            buckets[ts]["expired"] += 1
    return [{"month": k, **v} for k, v in sorted(buckets.items())]

from fastapi.responses import StreamingResponse  # noqa: E402
import asyncio  # noqa: E402


@app.get("/api/events/stream")
async def stream_events(current_user: dict = Depends(get_current_user)) -> StreamingResponse:
    scope = _get_tenant_scope(current_user)

    async def _event_generator():
        try:
            while True:
                now_utc = datetime.now(timezone.utc)
                sched = getattr(app.state, "scheduler", None)
                is_running = bool(
                    sched is not None
                    and getattr(sched, "_worker_thread", None) is not None
                    and sched._worker_thread.is_alive()
                )
                certs = db.list_all_certificates(tenant_id=scope)
                upcoming = sorted(
                    (c for c in certs if c.get("next_renewal_at") is not None),
                    key=lambda c: c["next_renewal_at"],
                )
                next_job = upcoming[0] if upcoming else None
                payload = {
                    "type": "scheduler_heartbeat",
                    "isRunning": is_running,
                    "nextJob": {
                        "name": next_job["name"],
                        "vaultSource": next_job["vault_source"],
                        "secondsUntilDue": max(0.0, (next_job["next_renewal_at"] - now_utc).total_seconds()),
                    } if next_job else None,
                    "timestamp": now_utc.isoformat(),
                }
                yield f"data: {json.dumps(payload)}\n\n"
                await asyncio.sleep(10)
        except asyncio.CancelledError:
            return

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("API_PORT", "8000")))
