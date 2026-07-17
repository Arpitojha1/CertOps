"""Agent local database (agent.db) — key-value identity + encrypted config."""
import json
import os
import sqlite3
from datetime import datetime, timezone
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


def get_usage_snapshot(db_path: Optional[str] = None) -> dict:
    """Returns current usage snapshot from agent.db."""
    path = _db_path(db_path)
    if not os.path.exists(path):
        return {"active_cert_count": 0, "renewals_succeeded": 0,
                "renewals_failed": 0, "connectors": {}, "last_heartbeat": None}
    conn = sqlite3.connect(path)

    def _read(key: str, default=None):
        row = conn.execute(
            "SELECT value FROM agent_identity WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else default

    cert_count = int(_read("usage:active_cert_count", "0"))
    ok = int(_read("usage:renewals_succeeded", "0"))
    fail = int(_read("usage:renewals_failed", "0"))
    connectors_raw = _read("usage:connectors", "{}")
    heartbeat = _read("usage:last_heartbeat", None)
    conn.close()

    try:
        connectors = json.loads(connectors_raw)
    except (json.JSONDecodeError, TypeError):
        connectors = {}

    return {
        "active_cert_count": cert_count,
        "renewals_succeeded": ok,
        "renewals_failed": fail,
        "connectors": connectors,
        "last_heartbeat": heartbeat,
    }


def update_usage_snapshot(
    db_path: Optional[str] = None,
    cert_count: int = 0,
    renewals_ok: int = 0,
    renewals_fail: int = 0,
    connectors: Optional[dict] = None,
) -> None:
    """Writes usage snapshot to agent.db."""
    path = _db_path(db_path)
    conn = sqlite3.connect(path)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("INSERT OR REPLACE INTO agent_identity (key, value) VALUES (?, ?)",
                 ("usage:active_cert_count", str(cert_count)))
    conn.execute("INSERT OR REPLACE INTO agent_identity (key, value) VALUES (?, ?)",
                 ("usage:renewals_succeeded", str(renewals_ok)))
    conn.execute("INSERT OR REPLACE INTO agent_identity (key, value) VALUES (?, ?)",
                 ("usage:renewals_failed", str(renewals_fail)))
    conn.execute("INSERT OR REPLACE INTO agent_identity (key, value) VALUES (?, ?)",
                 ("usage:connectors", json.dumps(connectors or {})))
    conn.execute("INSERT OR REPLACE INTO agent_identity (key, value) VALUES (?, ?)",
                 ("usage:last_heartbeat", now))
    conn.commit()
    conn.close()
