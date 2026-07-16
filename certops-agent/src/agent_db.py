"""Agent local database (agent.db) — key-value identity + encrypted config."""
import os
import sqlite3
from typing import Optional

_DEFAULT_AGENT_DB = "./agent.db"

_SENSITIVE_KEY_SUBSTRINGS = ("token", "password", "secret", "key", "pass")


def _db_path(db_path: Optional[str] = None) -> str:
    if db_path is None:
        db_path = os.getenv("AGENT_DB_PATH", _DEFAULT_AGENT_DB)
    return os.path.normcase(os.path.abspath(str(db_path)))


def init_agent_db(db_path: Optional[str] = None) -> None:
    path = _db_path(db_path)
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_identity (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def get_identity(key: str, db_path: Optional[str] = None) -> Optional[str]:
    path = _db_path(db_path)
    if not os.path.exists(path):
        return None
    conn = sqlite3.connect(path)
    row = conn.execute(
        "SELECT value FROM agent_identity WHERE key = ?", (key,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def set_identity(key: str, value: str, db_path: Optional[str] = None) -> None:
    path = _db_path(db_path)
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT OR REPLACE INTO agent_identity (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()
    conn.close()


def get_config(key: str, db_path: Optional[str] = None) -> Optional[str]:
    path = _db_path(db_path)
    if not os.path.exists(path):
        return None
    conn = sqlite3.connect(path)
    row = conn.execute(
        "SELECT value FROM agent_config WHERE key = ?", (key,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    raw = row[0]
    import db as _db
    decrypted = _db.decrypt_config(raw)
    if key in decrypted:
        return decrypted[key]
    return raw


def set_config(key: str, value: str, db_path: Optional[str] = None) -> None:
    path = _db_path(db_path)
    is_sensitive = any(sub in key.lower() for sub in _SENSITIVE_KEY_SUBSTRINGS)
    if is_sensitive:
        import db as _db
        encrypted = _db.encrypt_config({key: value})
        stored = encrypted
    else:
        stored = value
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT OR REPLACE INTO agent_config (key, value) VALUES (?, ?)",
        (key, stored),
    )
    conn.commit()
    conn.close()


def get_status(db_path: Optional[str] = None) -> str:
    return get_identity("status", db_path) or "pending"


def set_status(status: str, db_path: Optional[str] = None) -> None:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    set_identity("status", status, db_path)
    if status == "registered":
        set_identity("registered_at", now, db_path)
    elif status == "configured":
        set_identity("configured_at", now, db_path)
    elif status == "active":
        set_identity("activated_at", now, db_path)
