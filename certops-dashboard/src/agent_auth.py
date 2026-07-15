"""
Scoped Agent Auth Layer for CertOps (Track B).
Implements per-install agent token generation, validation, and revocation for telemetry ingestion.
"""

import hashlib
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

import jwt as pyjwt
from fastapi import APIRouter, Depends, Header, HTTPException, status

import sys
from pathlib import Path
_agent_root = Path(__file__).resolve().parent.parent.parent / "certops-agent"
if _agent_root.exists() and str(_agent_root) not in sys.path:
    sys.path.append(str(_agent_root))
_agent_src = _agent_root / "src"
if _agent_src.exists() and str(_agent_src) not in sys.path:
    sys.path.append(str(_agent_src))
_dashboard_root = Path(__file__).resolve().parent.parent.parent / "certops-dashboard"
if _dashboard_root.exists() and str(_dashboard_root) not in sys.path:
    sys.path.append(str(_dashboard_root))
_dashboard_src = _dashboard_root / "src"
if _dashboard_src.exists() and str(_dashboard_src) not in sys.path:
    sys.path.append(str(_dashboard_src))

if __package__ is None or __package__ == "":
    import db
else:
    from . import db

logger = logging.getLogger("certops.agent_auth")

router = APIRouter(tags=["agent_telemetry"])


def get_agent_token_signing_key() -> str:
    """
    Reads AGENT_TOKEN_SIGNING_KEY with strict checking.
    Fails loudly (raises RuntimeError) if not set or empty, never falling back to JWT_SECRET.
    """
    key = os.getenv("AGENT_TOKEN_SIGNING_KEY")
    if not key or not key.strip():
        raise RuntimeError("AGENT_TOKEN_SIGNING_KEY is not set or empty. Cannot sign or validate agent tokens.")
    return key


def create_agent_token(
    scope: str = "telemetry_push",
    connector_context: Optional[str] = None,
    db_path: Optional[str] = None,
) -> tuple[str, dict]:
    """
    Issues a new agent token. Token is issued once at agent registration.
    Stores the SHA-256 hash of the token in the agent_tokens database table.
    """
    signing_key = get_agent_token_signing_key()
    token_id = secrets.token_hex(16)
    now_utc = datetime.now(timezone.utc)
    now_str = now_utc.isoformat()

    payload = {
        "sub": f"agent:{token_id}",
        "token_id": token_id,
        "scope": scope,
        "iat": now_utc,
    }
    if connector_context:
        payload["connector_context"] = connector_context

    raw_token = pyjwt.encode(payload, signing_key, algorithm="HS256")
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    conn = db.get_db_connection(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO agent_tokens (token_hash, scope, created_at, revoked_at, connector_context)
            VALUES (?, ?, ?, ?, ?)
            """,
            (token_hash, scope, now_str, None, connector_context),
        )
        conn.commit()
        record_id = cur.lastrowid
    finally:
        conn.close()

    record = {
        "id": record_id,
        "token_hash": token_hash,
        "scope": scope,
        "created_at": now_str,
        "revoked_at": None,
        "connector_context": connector_context,
    }
    return raw_token, record


def revoke_agent_token(
    raw_token: Optional[str] = None,
    token_hash: Optional[str] = None,
    token_id: Optional[int] = None,
    db_path: Optional[str] = None,
) -> bool:
    """
    Revokes an agent token by setting revoked_at timestamp immediately.
    """
    if raw_token:
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    now_str = datetime.now(timezone.utc).isoformat()
    conn = db.get_db_connection(db_path)
    try:
        if token_hash:
            cur = conn.execute(
                "UPDATE agent_tokens SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
                (now_str, token_hash),
            )
        elif token_id is not None:
            cur = conn.execute(
                "UPDATE agent_tokens SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                (now_str, token_id),
            )
        else:
            return False
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def validate_agent_token(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_agent_token: Optional[str] = Header(None, alias="X-Agent-Token"),
    db_path: Optional[str] = None,
) -> dict:
    """
    FastAPI dependency that validates an incoming agent token.
    Enforces that AGENT_TOKEN_SIGNING_KEY is present, token signature matches,
    scope is 'telemetry_push', and token is present and unrevoked in the database.
    """
    signing_key = get_agent_token_signing_key()

    raw_token = None
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization[7:].strip()
    elif x_agent_token:
        raw_token = x_agent_token.strip()

    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing agent token")

    try:
        payload = pyjwt.decode(raw_token, signing_key, algorithms=["HS256"])
    except pyjwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent token signature") from exc

    if payload.get("scope") != "telemetry_push":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent token must have 'telemetry_push' scope")

    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    conn = db.get_db_connection(db_path)
    try:
        cur = conn.execute(
            "SELECT id, token_hash, scope, created_at, revoked_at, connector_context FROM agent_tokens WHERE token_hash = ?",
            (token_hash,),
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Agent token unrecognized")

    if row[4] is not None:  # revoked_at is row[4]
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Agent token has been revoked")

    record = {
        "id": row[0],
        "token_hash": row[1],
        "scope": row[2],
        "created_at": row[3],
        "revoked_at": row[4],
        "connector_context": row[5],
    }
    return {"payload": payload, "record": record}


def require_agent_token(token_data: dict = Depends(validate_agent_token)) -> dict:
    return token_data
