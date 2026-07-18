"""Agent registration, listing, and detail endpoints."""
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

_agent_root = Path(__file__).resolve().parent.parent.parent / "certops-agent"
if _agent_root.exists() and str(_agent_root) not in sys.path:
    sys.path.append(str(_agent_root))
_agent_src = _agent_root / "src"
if _agent_src.exists() and str(_agent_src) not in sys.path:
    sys.path.append(str(_agent_src))

if __package__ is None or __package__ == "":
    import db
    import agent_auth
    import auth
else:
    import db
    from .. import agent_auth, auth

router = APIRouter(tags=["Agents"])


class AgentRegisterRequest(BaseModel):
    name: Optional[str] = None


class AgentRegisterResponse(BaseModel):
    agent_id: str
    tenant_id: str
    token: str
    status: str


class AgentDetailResponse(BaseModel):
    id: str
    tenant_id: str
    name: Optional[str]
    status: str
    registered_at: str
    configured_at: Optional[str]
    activated_at: Optional[str]
    last_seen_at: Optional[str]
    secret_store_backend: Optional[str]


@router.post("/api/agents/register", response_model=AgentRegisterResponse)
def register_agent(
    req: AgentRegisterRequest,
    token_data: dict = Depends(auth.require_admin_user),
):
    from datetime import datetime, timezone
    import uuid

    tenant_id = token_data.get("tenant_id", "default")
    agent_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    conn = db.get_db_connection()
    try:
        conn.execute(
            "INSERT INTO agents (id, tenant_id, name, status, registered_at) VALUES (?, ?, ?, ?, ?)",
            (agent_id, tenant_id, req.name, "pending", now),
        )
        conn.commit()
    finally:
        conn.close()

    raw_token, record = agent_auth.create_agent_token(
        scope="telemetry_push",
        tenant_id=tenant_id,
    )

    conn = db.get_db_connection()
    try:
        conn.execute(
            "UPDATE agent_tokens SET agent_id = ? WHERE token_hash = ?",
            (agent_id, record["token_hash"]),
        )
        conn.commit()
    finally:
        conn.close()

    return AgentRegisterResponse(
        agent_id=agent_id,
        tenant_id=tenant_id,
        token=raw_token,
        status="pending",
    )


@router.get("/api/agents")
def list_agents(
    token_data: dict = Depends(auth.require_admin_user),
):
    tenant_id = token_data.get("tenant_id", "default")
    conn = db.get_db_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM agents WHERE tenant_id = ? ORDER BY registered_at DESC",
            (tenant_id,),
        )
        cols = [d[0] for d in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
    finally:
        conn.close()
    return rows


@router.get("/api/agents/{agent_id}")
def get_agent(
    agent_id: str,
    token_data: dict = Depends(auth.require_admin_user),
):
    tenant_id = token_data.get("tenant_id", "default")
    conn = db.get_db_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM agents WHERE id = ? AND tenant_id = ?",
            (agent_id, tenant_id),
        )
        row = cursor.fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))
