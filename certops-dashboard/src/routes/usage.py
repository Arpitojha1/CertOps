"""Usage metering API endpoints."""
import sys
from pathlib import Path

from fastapi import APIRouter, Depends

_agent_root = Path(__file__).resolve().parent.parent.parent / "certops-agent"
if _agent_root.exists() and str(_agent_root) not in sys.path:
    sys.path.append(str(_agent_root))
_agent_src = _agent_root / "src"
if _agent_src.exists() and str(_agent_src) not in sys.path:
    sys.path.append(str(_agent_src))

if __package__ is None or __package__ == "":
    import db
else:
    from .. import db

router = APIRouter(tags=["Usage"])


@router.get("/api/agents/{agent_id}/usage")
def get_agent_usage(
    agent_id: str,
    limit: int = 100,
    token_data: dict = Depends(__import__("auth").require_admin_user),
):
    records = db.get_agent_usage(db_path=None, agent_id=agent_id, limit=limit)
    return {"agent_id": agent_id, "records": records}


@router.get("/api/usage/summary")
def get_usage_summary(
    token_data: dict = Depends(__import__("auth").require_admin_user),
):
    tenant_id = token_data.get("tenant_id", "default")
    return db.get_tenant_usage_summary(db_path=None, tenant_id=tenant_id)
