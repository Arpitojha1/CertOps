"""
Stub Ingestion Endpoint (`src/routes/telemetry_ingest.py`) for Track C.
Validates agent token (`scope: "telemetry_push"`), enforces allow-list schema,
and logs/stores received payload in an inspectable memory/DB sink.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict

router = APIRouter(tags=["Telemetry Ingestion"])

# In-memory inspectable sink and token registry (scaffold for Track B / test isolation)
_RECEIVED_PAYLOADS: list[dict[str, Any]] = []
_VALID_TOKENS: dict[str, str] = {}
_REVOKED_TOKENS: set[str] = set()


def clear_received_payloads() -> None:
    _RECEIVED_PAYLOADS.clear()


def get_received_payloads() -> list[dict[str, Any]]:
    return list(_RECEIVED_PAYLOADS)


def register_agent_token(token: str, scope: str = "telemetry_push", revoked: bool = False) -> None:
    if revoked:
        _REVOKED_TOKENS.add(token)
        _VALID_TOKENS.pop(token, None)
    else:
        _VALID_TOKENS[token] = scope
        _REVOKED_TOKENS.discard(token)


def require_agent_token_or_db(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_agent_token: Optional[str] = Header(None, alias="X-Agent-Token")
) -> dict:
    """
    Validates agent token against in-memory registry or DB via agent_auth.
    Returns dict with keys: raw_token, tenant_id, record (DB record or None for in-memory).
    Must be completely separate from dashboard user auth (jwt/cookie).
    """
    raw_token = None
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization[7:].strip()
    elif x_agent_token:
        raw_token = x_agent_token.strip()

    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing agent token")

    if raw_token in _REVOKED_TOKENS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Agent token has been revoked")
    if raw_token in _VALID_TOKENS:
        if _VALID_TOKENS[raw_token] != "telemetry_push":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent token lacks telemetry_push scope")
        return {"raw_token": raw_token, "tenant_id": "default", "record": None}

    # Fallback to DB-backed check via agent_auth if not in memory registry
    try:
        import sys
        from pathlib import Path
        _agent_root = Path(__file__).resolve().parent.parent.parent.parent / "certops-agent"
        if _agent_root.exists() and str(_agent_root) not in sys.path:
            sys.path.append(str(_agent_root))
        _agent_src = _agent_root / "src"
        if _agent_src.exists() and str(_agent_src) not in sys.path:
            sys.path.append(str(_agent_src))

        if __package__ is None or __package__ == "" or not __package__.startswith("src"):
            import agent_auth
        else:
            from .. import agent_auth
        token_data = agent_auth.validate_agent_token(authorization=authorization, x_agent_token=x_agent_token)
        record = token_data.get("record", {})
        return {
            "raw_token": raw_token,
            "tenant_id": record.get("tenant_id", "default"),
            "record": record,
        }
    except Exception as exc:
        if isinstance(exc, (HTTPException, RuntimeError)):
            raise exc
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent token") from exc


class TelemetryItemModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_type: str
    connector_opaque_id: str
    connector_health: str
    connector_status: str
    error_code: Optional[str] = None
    cert_cn: str
    cert_san: list[str] = []
    expiry_utc: str
    renewal_stage: str


class TelemetryPayloadModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    agent_version: str
    timestamp: str
    tenant_id: str = "default"
    items: list[TelemetryItemModel] = []


@router.post("/api/telemetry/ingest", status_code=status.HTTP_202_ACCEPTED)
@router.post("/telemetry/ingest", status_code=status.HTTP_202_ACCEPTED)
@router.post("/api/telemetry/push", status_code=status.HTTP_202_ACCEPTED)
def ingest_telemetry(
    payload: TelemetryPayloadModel,
    token_data: dict = Depends(require_agent_token_or_db)
) -> dict[str, str]:
    """
    Ingests telemetry batch from agent push client.
    Stores payload along with server arrival timestamp in inspectable sink.
    Enforces that the agent token's tenant_id matches the payload's tenant_id.
    """
    token_tenant = token_data.get("tenant_id", "default")
    payload_tenant = payload.tenant_id
    if token_tenant != payload_tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tenant mismatch: token belongs to tenant '{token_tenant}', payload targets tenant '{payload_tenant}'"
        )

    entry = {
        "payload": payload.model_dump(),
        "server_received_at": datetime.now(timezone.utc).isoformat(),
        "agent_token": token_data["raw_token"],
        "tenant_id": token_tenant,
    }
    _RECEIVED_PAYLOADS.append(entry)
    return {"status": "accepted"}
