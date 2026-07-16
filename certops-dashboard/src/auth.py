"""
Auth layer: bcrypt passwords, HS256 JWT in httpOnly cookie.
Role enforcement: viewer=read-only, admin=full access.
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt as pyjwt
from dotenv import load_dotenv
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel

load_dotenv()

import sys
from pathlib import Path
_agent_root = Path(__file__).resolve().parent.parent.parent / "certops-agent"
if _agent_root.exists() and str(_agent_root) not in sys.path:
    sys.path.append(str(_agent_root))
_agent_src = _agent_root / "src"
if _agent_src.exists() and str(_agent_src) not in sys.path:
    sys.path.append(str(_agent_src))

if __package__ is None or __package__ == "":
    import db
else:
    from . import db

JWT_SECRET = os.getenv("JWT_SECRET", "change-me-before-any-external-access")
if JWT_SECRET == "change-me-before-any-external-access":
    raise RuntimeError(
        "JWT_SECRET is set to the insecure default placeholder. "
        "Set a real secret in .env or environment. See .env.example for instructions."
    )
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
COOKIE_NAME = "certops_token"

import logging

logger = logging.getLogger("certops.auth")

router = APIRouter(tags=["auth"])


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def _make_token(user_id: int, email: str, role: str, tenant_id: str = "default") -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {"sub": str(user_id), "email": email, "role": role, "tenant_id": tenant_id, "exp": expire}
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> dict:
    try:
        data = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if "tenant_id" not in data:
            data["tenant_id"] = "default"
        return data
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def _cookie_kwargs() -> dict:
    secure = os.getenv("ENV", "").lower() == "production" or os.getenv("COOKIE_SECURE", "false").lower() in ("true", "1", "yes")
    return {"httponly": True, "samesite": "strict", "secure": secure, "max_age": JWT_EXPIRE_HOURS * 3600, "path": "/"}


def get_current_user(token: Optional[str] = Cookie(default=None, alias=COOKIE_NAME)) -> dict:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return _decode_token(token)


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


class LoginRequest(BaseModel):
    email: str
    password: str


class SignupRequest(BaseModel):
    email: str
    password: str
    role: str = "viewer"


@router.post("/auth/login")
def login(body: LoginRequest, response: Response):
    user = db.get_user_by_email(body.email)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    tid = user.get("tenant_id") or "default"
    token = _make_token(user["id"], user["email"], user["role"], tenant_id=tid)
    response.set_cookie(COOKIE_NAME, token, **_cookie_kwargs())
    db.log_activity(event_type="user_login", actor_user_id=user["id"], actor_email=user["email"])
    return {"id": user["id"], "email": user["email"], "role": user["role"], "tenant_id": tid}


@router.get("/auth/me")
def me(current_user: dict = Depends(get_current_user)):
    user = db.get_user_by_id(int(current_user["sub"]))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return {"id": user["id"], "email": user["email"], "role": user["role"]}


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/", samesite="lax")
    return {"status": "logged out"}


@router.post("/auth/signup")
def signup(body: SignupRequest, current_user: dict = Depends(require_admin)):
    if db.get_user_by_email(body.email):
        raise HTTPException(status_code=409, detail="User already exists")
    if body.role not in ("admin", "viewer"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'viewer'")
    inviter_tenant = current_user.get("tenant_id", "default")
    uid = db.create_user(body.email, hash_password(body.password), body.role, tenant_id=inviter_tenant)
    user = db.get_user_by_id(uid)
    return {"id": user["id"], "email": user["email"], "role": user["role"], "tenant_id": inviter_tenant}


class InviteRequest(BaseModel):
    email: str
    role: str = "viewer"
    expires_in_hours: int = 48


class RegisterWithInviteRequest(BaseModel):
    token: str
    password: str


@router.post("/auth/invites")
def create_invite(body: InviteRequest, current_user: dict = Depends(require_admin)):
    if body.role not in ("admin", "viewer"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'viewer'")
    if db.get_user_by_email(body.email):
        raise HTTPException(status_code=409, detail="User already exists")
    token = secrets.token_urlsafe(32)
    expires_utc = datetime.now(timezone.utc) + timedelta(hours=body.expires_in_hours)
    inviter_tenant = current_user.get("tenant_id", "default")
    invite = db.create_invite(token, body.email, body.role, expires_utc, inviter_tenant_id=inviter_tenant)
    # Log only redacted reference (last 6 chars) — never log full token string
    logger.info("Admin created invite for email='%s', role='%s', token_ref='***%s'", body.email, body.role, token[-6:])
    db.log_activity(
        event_type="invite_generated",
        actor_user_id=int(current_user["sub"]),
        actor_email=current_user.get("email"),
        target=body.email,
        details={"email": body.email, "role": body.role},
    )
    return {
        "invite_token": invite["token"],
        "invite_url": f"/signup?token={invite['token']}",
        "email": invite["email"],
        "role": invite["role"],
        "expires_utc": invite["expires_utc"],
    }


@router.post("/auth/register-with-invite")
def register_with_invite(body: RegisterWithInviteRequest, response: Response):
    invite = db.get_invite(body.token)
    if not invite:
        raise HTTPException(status_code=404, detail="Invite token not found")
    if invite["used"]:
        raise HTTPException(status_code=400, detail="Invite token already used")
    expires_dt = datetime.fromisoformat(invite["expires_utc"])
    if expires_dt <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invite token expired")
    if db.get_user_by_email(invite["email"]):
        raise HTTPException(status_code=409, detail="User already exists")

    inviter_tenant = invite.get("inviter_tenant_id", "default")
    uid = db.create_user(invite["email"], hash_password(body.password), invite["role"], tenant_id=inviter_tenant)
    db.mark_invite_used(body.token)
    user = db.get_user_by_id(uid)

    token = _make_token(user["id"], user["email"], user["role"], tenant_id=inviter_tenant)
    response.set_cookie(COOKIE_NAME, token, **_cookie_kwargs())
    db.log_activity(
        event_type="invite_redeemed",
        actor_user_id=user["id"],
        actor_email=user["email"],
        target=user["email"],
        details={"email": user["email"], "role": user["role"]},
    )
    return {"id": user["id"], "email": user["email"], "role": user["role"]}

