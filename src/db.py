"""
Database layer for CertOps certificate tracking and due-date calculation.
# ponytail: Using sqlite3 standard library for persistence. Keyed on (vault_source, name)
# to disambiguate identical certificate names across multiple vaults.
"""

import base64
import functools
import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

if __package__ is None or __package__ == "":
    import verify
else:
    from . import verify


def _parse_utc_datetime(dt_val: Any) -> datetime:
    if isinstance(dt_val, datetime):
        if dt_val.tzinfo is None:
            return dt_val.replace(tzinfo=timezone.utc)
        return dt_val.astimezone(timezone.utc)
    # Parse ISO string
    dt = datetime.fromisoformat(str(dt_val))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_db_connection(db_path: str | None = None) -> sqlite3.Connection:
    if db_path is None:
        db_path = os.getenv("CERTOPS_DB_PATH", os.getenv("DB_PATH", "./certops.db"))
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS certificates (
            vault_source TEXT NOT NULL,
            name TEXT NOT NULL,
            expiry_utc TEXT NOT NULL,
            version TEXT,
            common_name TEXT,
            updated_at TEXT,
            connector_category TEXT DEFAULT 'secret_store',
            pipeline_stage TEXT,
            PRIMARY KEY (vault_source, name)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS maintenance_windows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER REFERENCES groups(id),
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            recurrence TEXT DEFAULT 'once'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_policies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER REFERENCES groups(id),
            threshold_days REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vault_source TEXT,
            cert_id TEXT NOT NULL,
            policy_id INTEGER REFERENCES notification_policies(id),
            sent_at TEXT NOT NULL
        )
        """
    )
    # Idempotent column migrations for existing databases
    cursor = conn.execute("PRAGMA table_info(certificates)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    if "connector_category" not in existing_cols:
        conn.execute("ALTER TABLE certificates ADD COLUMN connector_category TEXT DEFAULT 'secret_store'")
    if "pipeline_stage" not in existing_cols:
        conn.execute("ALTER TABLE certificates ADD COLUMN pipeline_stage TEXT")
    if "renewal_threshold_days" not in existing_cols:
        conn.execute("ALTER TABLE certificates ADD COLUMN renewal_threshold_days REAL")
    if "group_id" not in existing_cols:
        conn.execute("ALTER TABLE certificates ADD COLUMN group_id INTEGER REFERENCES groups(id)")
    if "next_renewal_at" not in existing_cols:
        conn.execute("ALTER TABLE certificates ADD COLUMN next_renewal_at TEXT")
    if "next_notification_check_at" not in existing_cols:
        conn.execute("ALTER TABLE certificates ADD COLUMN next_notification_check_at TEXT")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS renewal_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vault_source TEXT,
            cert_id TEXT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            connector_category TEXT,
            connector_type TEXT,
            old_expiry TEXT,
            new_expiry TEXT,
            old_fingerprint TEXT,
            new_fingerprint TEXT,
            success BOOLEAN NOT NULL,
            detail TEXT
        )
        """
    )
    cursor = conn.execute("PRAGMA table_info(renewal_log)")
    log_cols = {row[1] for row in cursor.fetchall()}
    if "vault_source" not in log_cols:
        conn.execute("ALTER TABLE renewal_log ADD COLUMN vault_source TEXT")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_invites (
            token TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            expires_utc TEXT NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS connectors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL,
            renewal_threshold_days REAL NULL,
            config TEXT NOT NULL DEFAULT '{}',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            actor_user_id INTEGER,
            actor_email TEXT,
            target TEXT,
            details TEXT,
            timestamp TEXT NOT NULL
        )
        """
    )

    cur = conn.execute("SELECT COUNT(*) FROM connectors")
    if cur.fetchone()[0] == 0:
        now_iso = datetime.now(timezone.utc).isoformat()
        defaults = [
            ("hashicorp", "secret_store", None, "{}", 1, now_iso),
            ("azure", "secret_store", None, "{}", 1, now_iso),
            ("ssh_host", "host", None, "{}", 1, now_iso),
            ("step_ca", "ca", None, "{}", 1, now_iso),
        ]
        conn.executemany(
            "INSERT INTO connectors (name, category, renewal_threshold_days, config, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            defaults,
        )
    conn.commit()
    return conn


def create_user(
    email: str,
    password_hash: str,
    role: str = "viewer",
    db_path: str | None = None,
) -> int:
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (email, password_hash, role, now_iso),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_user_by_email(email: str, db_path: str | None = None) -> dict[str, Any] | None:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT id, email, password_hash, role, created_at FROM users WHERE email = ?",
            (email,),
        )
        row = cursor.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {"id": row[0], "email": row[1], "password_hash": row[2], "role": row[3], "created_at": row[4]}


def get_user_by_id(user_id: int, db_path: str | None = None) -> dict[str, Any] | None:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT id, email, password_hash, role, created_at FROM users WHERE id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {"id": row[0], "email": row[1], "password_hash": row[2], "role": row[3], "created_at": row[4]}


def create_invite(
    token: str,
    email: str,
    role: str,
    expires_utc: datetime,
    db_path: str | None = None,
) -> dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    expires_iso = expires_utc.isoformat()
    conn = get_db_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO user_invites (token, email, role, expires_utc, used, created_at)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (token, email, role, expires_iso, now_iso),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "token": token,
        "email": email,
        "role": role,
        "expires_utc": expires_iso,
        "used": False,
        "created_at": now_iso,
    }


def get_invite(token: str, db_path: str | None = None) -> dict[str, Any] | None:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT token, email, role, expires_utc, used, created_at FROM user_invites WHERE token = ?",
            (token,),
        )
        row = cursor.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {
        "token": row[0],
        "email": row[1],
        "role": row[2],
        "expires_utc": row[3],
        "used": bool(row[4]),
        "created_at": row[5],
    }


def mark_invite_used(token: str, db_path: str | None = None) -> bool:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            "UPDATE user_invites SET used = 1 WHERE token = ? AND used = 0",
            (token,),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


# ─── Connector Credential Encryption & Redaction ─────────────────────────────

def _get_fernet() -> Fernet:
    raw_key = os.getenv("CERTOPS_CONFIG_ENCRYPTION_KEY")
    if raw_key:
        try:
            return Fernet(raw_key.encode("utf-8"))
        except Exception as e:
            logger.warning("CERTOPS_CONFIG_ENCRYPTION_KEY is set but invalid (%s). Falling back to JWT_SECRET-derived key (DEPRECATED).", e)
    else:
        logger.warning(
            "CRITICAL SECURITY WARNING: CERTOPS_CONFIG_ENCRYPTION_KEY is not set. "
            "Falling back to deriving encryption key from JWT_SECRET (DEPRECATED and insecure for production)."
        )
    secret = os.getenv("JWT_SECRET", "certops-dev-encryption-key-do-not-use-in-prod").encode("utf-8")
    derived = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(derived)


_SENSITIVE_KEY_SUBSTRINGS = ("token", "password", "secret", "key", "pass")


def _is_sensitive_key(key: str) -> bool:
    k = key.lower()
    return any(sub in k for sub in _SENSITIVE_KEY_SUBSTRINGS)


def encrypt_config(config_dict: dict[str, Any]) -> str:
    f = _get_fernet()
    out = {}
    for k, v in config_dict.items():
        if _is_sensitive_key(k) and isinstance(v, str) and not v.startswith("ENC:v1:"):
            enc = f.encrypt(v.encode("utf-8")).decode("utf-8")
            out[k] = f"ENC:v1:{enc}"
        else:
            out[k] = v
    return json.dumps(out)


def decrypt_config(config_str: str) -> dict[str, Any]:
    f = _get_fernet()
    try:
        data = json.loads(config_str) if isinstance(config_str, str) else (config_str or {})
    except Exception:
        return {}
    out = {}
    for k, v in data.items():
        if isinstance(v, str) and v.startswith("ENC:v1:"):
            ciphertext = v[len("ENC:v1:"):]
            try:
                out[k] = f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
            except Exception:
                out[k] = v
        else:
            out[k] = v
    return out


def redact_config(config_obj: dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(config_obj, str):
        try:
            config_obj = json.loads(config_obj)
        except Exception:
            config_obj = {}
    out = {}
    for k, v in (config_obj or {}).items():
        if _is_sensitive_key(k) and v:
            out[k] = "********"
        else:
            out[k] = v
    return out


def list_connectors(active_only: bool = False, db_path: str | None = None) -> list[dict[str, Any]]:
    conn = get_db_connection(db_path)
    try:
        query = "SELECT id, name, category, renewal_threshold_days, config, is_active, created_at FROM connectors"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY name ASC"
        rows = conn.execute(query).fetchall()
    finally:
        conn.close()
    default_thresh = float(os.getenv("RENEWAL_THRESHOLD_DAYS", "2"))
    return [
        {
            "id": r[0],
            "name": r[1],
            "category": r[2],
            "renewal_threshold_days": float(r[3]) if r[3] is not None else default_thresh,
            "config": r[4],
            "is_active": bool(r[5]),
            "created_at": r[6],
        }
        for r in rows
    ]


def get_connector(connector_id: int, db_path: str | None = None) -> dict[str, Any] | None:
    conn = get_db_connection(db_path)
    try:
        r = conn.execute(
            "SELECT id, name, category, renewal_threshold_days, config, is_active, created_at FROM connectors WHERE id = ?",
            (connector_id,),
        ).fetchone()
    finally:
        conn.close()
    if not r:
        return None
    default_thresh = float(os.getenv("RENEWAL_THRESHOLD_DAYS", "2"))
    return {
        "id": r[0],
        "name": r[1],
        "category": r[2],
        "renewal_threshold_days": float(r[3]) if r[3] is not None else default_thresh,
        "config": r[4],
        "is_active": bool(r[5]),
        "created_at": r[6],
    }


def get_connector_by_name(name: str, db_path: str | None = None) -> dict[str, Any] | None:
    conn = get_db_connection(db_path)
    try:
        r = conn.execute(
            "SELECT id, name, category, renewal_threshold_days, config, is_active, created_at FROM connectors WHERE name = ?",
            (name,),
        ).fetchone()
    finally:
        conn.close()
    if not r:
        return None
    default_thresh = float(os.getenv("RENEWAL_THRESHOLD_DAYS", "2"))
    return {
        "id": r[0],
        "name": r[1],
        "category": r[2],
        "renewal_threshold_days": float(r[3]) if r[3] is not None else default_thresh,
        "config": r[4],
        "is_active": bool(r[5]),
        "created_at": r[6],
    }


def _maybe_encrypt_config_str(cfg_str: str) -> str:
    try:
        obj = json.loads(cfg_str)
        if isinstance(obj, dict):
            return encrypt_config(obj)
    except Exception:
        pass
    return cfg_str


def create_connector(
    name: str,
    category: str,
    renewal_threshold_days: float,
    config: str = "{}",
    is_active: bool = True,
    db_path: str | None = None,
) -> int:
    now_iso = datetime.now(timezone.utc).isoformat()
    encrypted_cfg = _maybe_encrypt_config_str(config)
    conn = get_db_connection(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO connectors (name, category, renewal_threshold_days, config, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (name, category, float(renewal_threshold_days), encrypted_cfg, 1 if is_active else 0, now_iso),
        )
        conn.commit()
        cid = cur.lastrowid
    finally:
        conn.close()
    return cid


def update_connector(
    connector_id: int,
    name: str | None = None,
    category: str | None = None,
    renewal_threshold_days: float | None = None,
    config: str | None = None,
    is_active: bool | None = None,
    db_path: str | None = None,
) -> bool:
    conn = get_db_connection(db_path)
    try:
        fields = []
        params: list[Any] = []
        if name is not None:
            fields.append("name = ?")
            params.append(name)
        if category is not None:
            fields.append("category = ?")
            params.append(category)
        if renewal_threshold_days is not None:
            fields.append("renewal_threshold_days = ?")
            params.append(float(renewal_threshold_days))
        if config is not None:
            fields.append("config = ?")
            params.append(_maybe_encrypt_config_str(config))
        if is_active is not None:
            fields.append("is_active = ?")
            params.append(1 if is_active else 0)
        if not fields:
            return False
        params.append(connector_id)
        cur = conn.execute(f"UPDATE connectors SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_connector(connector_id: int, db_path: str | None = None) -> bool:
    conn = get_db_connection(db_path)
    try:
        c_row = conn.execute("SELECT name FROM connectors WHERE id = ?", (connector_id,)).fetchone()
        if not c_row:
            return False
        cname = c_row[0]
        cert_count = conn.execute("SELECT COUNT(*) FROM certificates WHERE vault_source = ?", (cname,)).fetchone()[0]
        if cert_count > 0:
            raise ValueError(f"Cannot delete connector '{cname}': {cert_count} certificate(s) are currently tracked under this connector.")
        cur = conn.execute("DELETE FROM connectors WHERE id = ?", (connector_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def upsert_certificate(
    vault_source: str,
    name: str,
    expiry_utc: Any,
    version: str | None = None,
    common_name: str | None = None,
    connector_category: str = "secret_store",
    pipeline_stage: str | None = None,
    renewal_threshold_days: float | None = None,
    group_id: int | None = None,
    next_renewal_at: Any | None = None,
    next_notification_check_at: Any | None = None,
    db_path: str | None = None,
) -> None:
    """
    Upserts a certificate record keyed on (vault_source, name).
    Computes next_renewal_at automatically if not explicitly provided.
    """
    dt = _parse_utc_datetime(expiry_utc)
    expiry_iso = dt.isoformat()
    now_iso = datetime.now(timezone.utc).isoformat()

    thresh = float(renewal_threshold_days) if renewal_threshold_days is not None else float(os.getenv("RENEWAL_THRESHOLD_DAYS", "2"))
    if next_renewal_at is not None:
        next_ren_iso = _parse_utc_datetime(next_renewal_at).isoformat()
    else:
        next_ren_iso = (dt - timedelta(days=thresh)).isoformat()

    next_notif_iso = _parse_utc_datetime(next_notification_check_at).isoformat() if next_notification_check_at is not None else None

    conn = get_db_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO certificates (
                vault_source, name, expiry_utc, version, common_name,
                connector_category, pipeline_stage, renewal_threshold_days, group_id,
                next_renewal_at, next_notification_check_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(vault_source, name) DO UPDATE SET
                expiry_utc=excluded.expiry_utc,
                version=excluded.version,
                common_name=COALESCE(excluded.common_name, certificates.common_name),
                connector_category=excluded.connector_category,
                pipeline_stage=COALESCE(excluded.pipeline_stage, certificates.pipeline_stage),
                renewal_threshold_days=excluded.renewal_threshold_days,
                group_id=COALESCE(excluded.group_id, certificates.group_id),
                next_renewal_at=excluded.next_renewal_at,
                next_notification_check_at=COALESCE(excluded.next_notification_check_at, certificates.next_notification_check_at),
                updated_at=excluded.updated_at
            """,
            (
                vault_source,
                name,
                expiry_iso,
                str(version) if version is not None else None,
                common_name,
                connector_category,
                pipeline_stage,
                renewal_threshold_days,
                group_id,
                next_ren_iso,
                next_notif_iso,
                now_iso,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def update_pipeline_stage(
    vault_source: str,
    name: str,
    pipeline_stage: str,
    db_path: str | None = None,
) -> None:
    """
    Updates the pipeline_stage for a specific certificate.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = get_db_connection(db_path)
    try:
        conn.execute(
            """
            UPDATE certificates
            SET pipeline_stage = ?, updated_at = ?
            WHERE vault_source = ? AND name = ?
            """,
            (pipeline_stage, now_iso, vault_source, name),
        )
        conn.commit()
    finally:
        conn.close()


def get_due_certificates(
    vault_source: str | None = None,
    threshold_days: float | None = None,
    connector_category: str | None = None,
    group_id: int | None = None,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    """
    Returns all certificates matching criteria whose remaining lifetime is <= threshold_days.
    """
    if threshold_days is None:
        threshold_days = float(os.getenv("RENEWAL_THRESHOLD_DAYS", "2"))

    conn = get_db_connection(db_path)
    try:
        query = """
            SELECT vault_source, name, expiry_utc, version, common_name,
                   connector_category, pipeline_stage, renewal_threshold_days, group_id
            FROM certificates
            WHERE 1=1
        """
        params: list[Any] = []
        if vault_source is not None:
            query += " AND vault_source = ?"
            params.append(vault_source)
        if connector_category is not None:
            query += " AND connector_category = ?"
            params.append(connector_category)
        if group_id is not None:
            query += " AND group_id = ?"
            params.append(group_id)

        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
    finally:
        conn.close()

    conn = get_db_connection(db_path)
    try:
        cur = conn.execute("SELECT name, renewal_threshold_days FROM connectors WHERE renewal_threshold_days IS NOT NULL")
        conn_map = {r[0]: float(r[1]) for r in cur.fetchall()}
    finally:
        conn.close()

    now_utc = datetime.now(timezone.utc)
    due_certs = []
    for row in rows:
        expiry_dt = _parse_utc_datetime(row[2])
        remaining_days = (expiry_dt - now_utc).total_seconds() / 86400.0
        cert_threshold = float(row[7]) if row[7] is not None else conn_map.get(row[0], threshold_days)
        if remaining_days <= cert_threshold:
            due_certs.append({
                "vault_source": row[0],
                "name": row[1],
                "expiry_utc": expiry_dt,
                "version": row[3],
                "common_name": row[4],
                "connector_category": row[5] or "secret_store",
                "pipeline_stage": row[6],
                "renewal_threshold_days": cert_threshold,
                "group_id": row[8],
                "remaining_days": remaining_days,
            })
    return due_certs


def get_certificate(
    vault_source: str, name: str, db_path: str | None = None
) -> dict[str, Any] | None:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            """
            SELECT vault_source, name, expiry_utc, version, common_name,
                   connector_category, pipeline_stage, renewal_threshold_days, group_id,
                   next_renewal_at, next_notification_check_at
            FROM certificates
            WHERE vault_source = ? AND name = ?
            """,
            (vault_source, name),
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    if not row:
        return None
    return {
        "vault_source": row[0],
        "name": row[1],
        "expiry_utc": _parse_utc_datetime(row[2]),
        "version": row[3],
        "common_name": row[4],
        "connector_category": row[5] or "secret_store",
        "pipeline_stage": row[6],
        "renewal_threshold_days": row[7],
        "group_id": row[8],
        "next_renewal_at": _parse_utc_datetime(row[9]) if row[9] else None,
        "next_notification_check_at": _parse_utc_datetime(row[10]) if row[10] else None,
    }


def create_group(name: str, description: str = "", db_path: str | None = None) -> int:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            "INSERT INTO groups (name, description) VALUES (?, ?)",
            (name, description),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_group(group_id: int, db_path: str | None = None) -> dict[str, Any] | None:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT id, name, description FROM groups WHERE id = ?",
            (group_id,),
        )
        row = cursor.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {"id": row[0], "name": row[1], "description": row[2]}


def list_groups(db_path: str | None = None) -> list[dict[str, Any]]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute("SELECT id, name, description FROM groups ORDER BY id")
        rows = cursor.fetchall()
    finally:
        conn.close()
    return [{"id": r[0], "name": r[1], "description": r[2]} for r in rows]


def assign_certificate_group(
    vault_source: str,
    name: str,
    group_id: int | None,
    db_path: str | None = None,
) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = get_db_connection(db_path)
    try:
        conn.execute(
            "UPDATE certificates SET group_id = ?, updated_at = ? WHERE vault_source = ? AND name = ?",
            (group_id, now_iso, vault_source, name),
        )
        conn.commit()
    finally:
        conn.close()


def create_maintenance_window(
    group_id: int,
    start_time: Any,
    end_time: Any,
    recurrence: str = "once",
    db_path: str | None = None,
) -> int:
    start_iso = _parse_utc_datetime(start_time).isoformat()
    end_iso = _parse_utc_datetime(end_time).isoformat()
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            "INSERT INTO maintenance_windows (group_id, start_time, end_time, recurrence) VALUES (?, ?, ?, ?)",
            (group_id, start_iso, end_iso, recurrence),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def list_maintenance_windows(group_id: int | None = None, db_path: str | None = None) -> list[dict[str, Any]]:
    conn = get_db_connection(db_path)
    try:
        if group_id is not None:
            cursor = conn.execute(
                "SELECT id, group_id, start_time, end_time, recurrence FROM maintenance_windows WHERE group_id = ? ORDER BY id",
                (group_id,),
            )
        else:
            cursor = conn.execute(
                "SELECT id, group_id, start_time, end_time, recurrence FROM maintenance_windows ORDER BY id"
            )
        rows = cursor.fetchall()
    finally:
        conn.close()
    return [
        {
            "id": r[0],
            "group_id": r[1],
            "start_time": _parse_utc_datetime(r[2]),
            "end_time": _parse_utc_datetime(r[3]),
            "recurrence": r[4],
        }
        for r in rows
    ]


def is_group_in_maintenance_window(
    group_id: int | None,
    check_time: Any | None = None,
    db_path: str | None = None,
) -> bool:
    """
    Returns True if the group has no maintenance windows defined, OR if check_time falls
    within an active maintenance window.
    Returns False if the group has maintenance windows defined but check_time is outside all of them.
    Ungrouped (group_id is None) returns True.
    """
    if group_id is None:
        return True

    now_dt = _parse_utc_datetime(check_time) if check_time is not None else datetime.now(timezone.utc)
    windows = list_maintenance_windows(group_id, db_path=db_path)
    if not windows:
        return True

    for w in windows:
        if w["start_time"] <= now_dt <= w["end_time"]:
            return True
    return False


def list_all_certificates(db_path: str | None = None) -> list[dict[str, Any]]:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT vault_source, name, expiry_utc, version, common_name, connector_category, pipeline_stage, renewal_threshold_days, group_id, next_renewal_at, next_notification_check_at FROM certificates"
        )
        rows = cursor.fetchall()
    finally:
        conn.close()
    return [
        {
            "vault_source": r[0],
            "name": r[1],
            "expiry_utc": _parse_utc_datetime(r[2]),
            "version": r[3],
            "common_name": r[4],
            "connector_category": r[5] or "secret_store",
            "pipeline_stage": r[6],
            "renewal_threshold_days": r[7],
            "group_id": r[8],
            "next_renewal_at": _parse_utc_datetime(r[9]) if r[9] else None,
            "next_notification_check_at": _parse_utc_datetime(r[10]) if r[10] else None,
        }
        for r in rows
    ]


def create_notification_policy(
    group_id: int,
    threshold_days: float,
    db_path: str | None = None,
) -> int:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            "INSERT INTO notification_policies (group_id, threshold_days) VALUES (?, ?)",
            (group_id, float(threshold_days)),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def list_notification_policies(group_id: int | None = None, db_path: str | None = None) -> list[dict[str, Any]]:
    conn = get_db_connection(db_path)
    try:
        if group_id is not None:
            cursor = conn.execute(
                "SELECT id, group_id, threshold_days FROM notification_policies WHERE group_id = ? ORDER BY threshold_days DESC",
                (group_id,),
            )
        else:
            cursor = conn.execute(
                "SELECT id, group_id, threshold_days FROM notification_policies ORDER BY threshold_days DESC"
            )
        rows = cursor.fetchall()
    finally:
        conn.close()
    return [{"id": r[0], "group_id": r[1], "threshold_days": float(r[2])} for r in rows]


def has_notification_been_sent(
    cert_id: str,
    policy_id: int,
    db_path: str | None = None,
) -> bool:
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT id FROM notification_log WHERE cert_id = ? AND policy_id = ?",
            (cert_id, policy_id),
        )
        row = cursor.fetchone()
    finally:
        conn.close()
    return row is not None


def record_notification_sent(
    vault_source: str,
    cert_id: str,
    policy_id: int,
    db_path: str | None = None,
) -> int:
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            "INSERT INTO notification_log (vault_source, cert_id, policy_id, sent_at) VALUES (?, ?, ?, ?)",
            (vault_source, cert_id, policy_id, now_iso),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_notification_logs(cert_id: str | None = None, db_path: str | None = None) -> list[dict[str, Any]]:
    conn = get_db_connection(db_path)
    try:
        if cert_id is not None:
            cursor = conn.execute(
                "SELECT id, vault_source, cert_id, policy_id, sent_at FROM notification_log WHERE cert_id = ? ORDER BY id",
                (cert_id,),
            )
        else:
            cursor = conn.execute(
                "SELECT id, vault_source, cert_id, policy_id, sent_at FROM notification_log ORDER BY id"
            )
        rows = cursor.fetchall()
    finally:
        conn.close()
    return [
        {
            "id": r[0],
            "vault_source": r[1],
            "cert_id": r[2],
            "policy_id": r[3],
            "sent_at": r[4],
        }
        for r in rows
    ]


def insert_renewal_log(
    cert_id: str | None,
    event_type: str,
    success: bool,
    vault_source: str | None = None,
    connector_category: str | None = None,
    connector_type: str | None = None,
    old_expiry: Any = None,
    new_expiry: Any = None,
    old_fingerprint: str | None = None,
    new_fingerprint: str | None = None,
    detail: str | None = None,
    db_path: str | None = None,
) -> int:
    """
    Append-only audit log insertion.
    Never updates or deletes records.
    Stores composite key context via (vault_source, cert_id).
    cert_id is NULL when failure happens before a specific certificate is identified.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    old_exp_str = _parse_utc_datetime(old_expiry).isoformat() if old_expiry is not None else None
    new_exp_str = _parse_utc_datetime(new_expiry).isoformat() if new_expiry is not None else None

    if cert_id == "ALL" or cert_id == "":
        cert_id = None
    if vault_source is None and connector_type is not None:
        vault_source = connector_type

    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO renewal_log (
                vault_source, cert_id, timestamp, event_type, connector_category, connector_type,
                old_expiry, new_expiry, old_fingerprint, new_fingerprint, success, detail
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                vault_source,
                cert_id,
                now_iso,
                event_type,
                connector_category,
                connector_type,
                old_exp_str,
                new_exp_str,
                old_fingerprint,
                new_fingerprint,
                1 if success else 0,
                detail,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_renewal_logs(
    cert_id: str | None = None,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    conn = get_db_connection(db_path)
    try:
        query = "SELECT * FROM renewal_log"
        params: list[Any] = []
        if cert_id is not None:
            query += " WHERE cert_id = ?"
            params.append(cert_id)
        query += " ORDER BY id"
        cursor = conn.execute(query, params)
        cols = [description[0] for description in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]
    finally:
        conn.close()


# ─── Activity Log ────────────────────────────────────────────────────────────

_ADMIN_ONLY_EVENTS = {"user_login", "invite_generated", "invite_redeemed"}


def log_activity(
    event_type: str,
    actor_user_id: int | None = None,
    actor_email: str | None = None,
    target: str | None = None,
    details: dict[str, Any] | None = None,
    db_path: str | None = None,
) -> int:
    # ponytail: No retention/pruning policy yet. Table will grow unbounded.
    # Future: add TTL-based pruning or archival when operational needs arise.
    """Append-only activity log entry. Returns the new row id."""
    now_iso = datetime.now(timezone.utc).isoformat()
    details_json = json.dumps(details) if details is not None else None
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            "INSERT INTO activity_log (event_type, actor_user_id, actor_email, target, details, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (event_type, actor_user_id, actor_email, target, details_json, now_iso),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_activity_logs(
    limit: int = 50,
    offset: int = 0,
    event_type: str | None = None,
    admin_only: bool = False,
    db_path: str | None = None,
) -> dict[str, Any]:
    """
    Paginated activity log query.
    When admin_only=False (viewer), excludes _ADMIN_ONLY_EVENTS.
    Returns {"items": [...], "total": int}.
    """
    conn = get_db_connection(db_path)
    try:
        where_clauses: list[str] = []
        params: list[Any] = []

        if not admin_only and _ADMIN_ONLY_EVENTS:
            placeholders = ", ".join("?" for _ in _ADMIN_ONLY_EVENTS)
            where_clauses.append(f"event_type NOT IN ({placeholders})")
            params.extend(_ADMIN_ONLY_EVENTS)

        if event_type is not None:
            where_clauses.append("event_type = ?")
            params.append(event_type)

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        count_row = conn.execute(f"SELECT COUNT(*) FROM activity_log{where_sql}", params).fetchone()
        total = count_row[0]

        query = f"SELECT id, event_type, actor_user_id, actor_email, target, details, timestamp FROM activity_log{where_sql} ORDER BY id DESC LIMIT ? OFFSET ?"
        cursor = conn.execute(query, [*params, limit, offset])
        cols = [d[0] for d in cursor.description]
        items = [dict(zip(cols, row)) for row in cursor.fetchall()]

        return {"items": items, "total": total}
    finally:
        conn.close()


def log_connector_event(event_type: str):
    """
    Decorator wrapping connector state-transition methods to record append-only audit log entries.
    Guarantees a log entry is recorded even if the wrapped function raises.
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(self, *args, **kwargs):
            c_type = getattr(self, "name", "unknown")
            c_cat = "host" if "host" in c_type else "secret_store"

            cert_id = kwargs.get("name") or kwargs.get("cert_id")
            if not cert_id and args:
                if isinstance(args[0], str):
                    cert_id = args[0]

            new_exp = None
            new_fp = None

            cert_pem = kwargs.get("cert_pem")
            if not cert_pem and len(args) >= 2 and isinstance(args[1], str) and "BEGIN CERTIFICATE" in args[1]:
                cert_pem = args[1]
            elif not cert_pem and len(args) >= 2 and hasattr(args[1], "cert_pem"):
                cert_pem = getattr(args[1], "cert_pem", None)
                if hasattr(args[1], "expiry_utc"):
                    new_exp = getattr(args[1], "expiry_utc", None)

            if cert_pem:
                try:
                    exp, fp = verify.get_pem_cert_info(cert_pem)
                    if new_exp is None:
                        new_exp = exp
                    new_fp = fp
                except Exception:
                    pass

            try:
                result = fn(self, *args, **kwargs)
                db_path = kwargs.get("db_path")
                if event_type == "discovered":
                    if isinstance(result, list):
                        for item in result:
                            cid = getattr(item, "cert_id", None) or (item.get("name") if isinstance(item, dict) else str(item))
                            exp = getattr(item, "expiry_utc", None) or (item.get("expiry_utc") if isinstance(item, dict) else None)
                            insert_renewal_log(
                                cert_id=cid,
                                event_type="discovered",
                                success=True,
                                vault_source=c_type,
                                connector_category=c_cat,
                                connector_type=c_type,
                                new_expiry=exp,
                                db_path=db_path,
                            )
                elif event_type == "reload_confirmed":
                    success = getattr(result, "success", True)
                    actual_event = "reload_confirmed" if success else "reload_failed"
                    detail = getattr(result, "output", None)
                    insert_renewal_log(
                        cert_id=cert_id,
                        event_type=actual_event,
                        success=success,
                        vault_source=c_type,
                        connector_category=c_cat,
                        connector_type=c_type,
                        detail=detail,
                        db_path=db_path,
                    )
                else:
                    insert_renewal_log(
                        cert_id=cert_id,
                        event_type=event_type,
                        success=True,
                        vault_source=c_type,
                        connector_category=c_cat,
                        connector_type=c_type,
                        new_expiry=new_exp,
                        new_fingerprint=new_fp,
                        db_path=db_path,
                    )
                return result
            except Exception as exc:
                db_path = kwargs.get("db_path")
                insert_renewal_log(
                    cert_id=cert_id,
                    event_type="error",
                    success=False,
                    vault_source=c_type,
                    connector_category=c_cat,
                    connector_type=c_type,
                    detail=str(exc),
                    db_path=db_path,
                )
                raise
        return wrapper
    return decorator


class renewal_context:
    """
    Context manager for logging renewal_started and handling errors during renewal.
    """
    def __init__(
        self,
        connector_type: str,
        connector_category: str,
        cert_id: str | None,
        old_expiry: Any = None,
        old_fingerprint: str | None = None,
        vault_source: str | None = None,
        db_path: str | None = None,
    ):
        self.connector_type = connector_type
        self.connector_category = connector_category
        self.cert_id = cert_id
        self.old_expiry = old_expiry
        self.old_fingerprint = old_fingerprint
        self.vault_source = vault_source or connector_type
        self.db_path = db_path

    def __enter__(self):
        insert_renewal_log(
            cert_id=self.cert_id,
            event_type="renewal_started",
            success=True,
            vault_source=self.vault_source,
            connector_category=self.connector_category,
            connector_type=self.connector_type,
            old_expiry=self.old_expiry,
            old_fingerprint=self.old_fingerprint,
            db_path=self.db_path,
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            insert_renewal_log(
                cert_id=self.cert_id,
                event_type="error",
                success=False,
                vault_source=self.vault_source,
                connector_category=self.connector_category,
                connector_type=self.connector_type,
                old_expiry=self.old_expiry,
                old_fingerprint=self.old_fingerprint,
                detail=str(exc_val),
                db_path=self.db_path,
            )
        return False


if __name__ == "__main__":
    test_db = "./test_certops.db"
    if Path(test_db).exists():
        Path(test_db).unlink()

    upsert_certificate("hashicorp", "cert-a", datetime.now(timezone.utc), version="v1", connector_category="secret_store", db_path=test_db)
    upsert_certificate("ssh_host", "/etc/nginx/certs/local.crt", datetime.now(timezone.utc), version="v1", connector_category="host", pipeline_stage="Renewed", db_path=test_db)

    hc_due = get_due_certificates("hashicorp", threshold_days=30, db_path=test_db)
    host_due = get_due_certificates("ssh_host", threshold_days=30, db_path=test_db)
    all_due = get_due_certificates(threshold_days=30, db_path=test_db)

    assert len(hc_due) == 1 and hc_due[0]["connector_category"] == "secret_store"
    assert len(host_due) == 1 and host_due[0]["connector_category"] == "host" and host_due[0]["pipeline_stage"] == "Renewed"
    assert len(all_due) == 2

    update_pipeline_stage("ssh_host", "/etc/nginx/certs/local.crt", "Deployed, pending reload", db_path=test_db)
    cert = get_certificate("ssh_host", "/etc/nginx/certs/local.crt", db_path=test_db)
    assert cert is not None and cert["pipeline_stage"] == "Deployed, pending reload"

    insert_renewal_log("cert-a", "discovered", success=True, connector_category="secret_store", connector_type="hashicorp", db_path=test_db)
    insert_renewal_log("cert-a", "error", success=False, connector_category="secret_store", connector_type="hashicorp", detail="simulated error", db_path=test_db)
    logs = get_renewal_logs("cert-a", db_path=test_db)
    assert len(logs) == 2
    assert logs[0]["event_type"] == "discovered" and bool(logs[0]["success"]) is True
    assert logs[1]["event_type"] == "error" and bool(logs[1]["success"]) is False

    print("db.py self-test passed: connector_category, pipeline_stage, and renewal_log verified.")
    if Path(test_db).exists():
        Path(test_db).unlink()

