"""
pytest conftest for certops-dashboard tests.

Uses a session-scoped autouse fixture that:
1. Snapshots all watched env vars at session start.
2. Clears them immediately so external pollution (e.g. SKIP_DEFAULT_CONNECTORS=1
   set in the shell) cannot affect any test.
3. Restores the original snapshot at session end.

Individual tests that need specific vars set them in setUp/setUpClass and
clean up in tearDown/tearDownClass, which is the existing pattern.
"""

import gc
import logging
import os
import sqlite3
import time

import pytest

logger = logging.getLogger(__name__)


# All env vars that any dashboard test file mutates (discovered by grep).
_WATCHED_VARS = [
    "DB_PATH",
    "CERTOPS_DB_PATH",
    "AGENT_DB_PATH",
    "CERTOPS_CONFIG_ENCRYPTION_KEY",
    "SKIP_DEFAULT_CONNECTORS",
    "RENEWAL_THRESHOLD_DAYS",
    "VAULT_RENEWAL_THRESHOLD_DAYS",
    "AZURE_RENEWAL_THRESHOLD_DAYS",
    "SSH_RENEWAL_THRESHOLD_DAYS",
    "ENV",
    "COOKIE_SECURE",
    "JWT_SECRET",
    "AGENT_TOKEN_SIGNING_KEY",
    "CONNECTOR_1_TYPE",
    "CONNECTOR_1_THRESHOLD_DAYS",
    "VAULT_ADDR",
    "VAULT_TOKEN",
    "HASHICORP_TOKEN",
    "STEP_CA_PASSWORD_FILE",
    "STEP_CA_URL",
    "STEP_CA_FINGERPRINT",
    "VERIFY_HOST",
    "VERIFY_PORT",
    "NGINX_CONTAINER_NAME",
    "VAULT_CERT_PATH",
    "CERTOPS_RUN_LIVE",
    "WEBHOOK_URL",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_SENDER",
    "SMTP_RECIPIENT",
    "SMTP_USE_TLS",
    "SSH_HOST",
    "SSH_PORT",
    "SSH_USERNAME",
    "SSH_PASSWORD",
    "ENABLE_SSH_HOST",
    "AZURE_KEYVAULT_URL",
    "AZURE_VAULT_URL",
    "AZURE_TENANT_ID",
    "AZURE_CLIENT_ID",
    "AZURE_CLIENT_SECRET",
    "WINRM_HOST",
    "WINRM_PORT",
    "WINRM_USERNAME",
    "WINRM_PASSWORD",
    "WINRM_AUTH_TYPE",
    "WINRM_IIS_SITE_NAME",
]


@pytest.fixture(autouse=True, scope="session")
def _isolate_env_vars_session():
    """Snapshot, clear, and later restore all watched env vars."""
    snapshot = {var: os.environ.get(var) for var in _WATCHED_VARS}

    # Clear all watched vars so external shell state cannot leak in.
    for var in _WATCHED_VARS:
        os.environ.pop(var, None)

    yield

    # Restore the original session-level snapshot.
    for var, orig in snapshot.items():
        if orig is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = orig


@pytest.fixture(autouse=True, scope="function")
def _isolate_env_vars_function():
    """Snapshot and restore watched env vars around each test function to prevent intra-session pollution."""
    snapshot = {var: os.environ.get(var) for var in _WATCHED_VARS}
    yield
    for var, orig in snapshot.items():
        if orig is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = orig


def _safe_remove_db(db_path: str, retries: int = 3, delay: float = 0.1) -> None:
    """Close all connections, GC, and delete a SQLite DB file with retry backoff.

    On Windows, SQLite file handles may not be released immediately after
    close_db_connection() due to lingering references in TestClient app state
    or WAL/SHM auxiliary files. This function retries with exponential backoff.
    If file deletion ultimately fails, it falls back to a SQL-level table wipe
    so that subsequent run_migrations() starts with clean tables.
    """
    from src import db as _db

    _db.reset_db_connections()
    gc.collect()
    deleted = False
    for attempt in range(retries):
        try:
            if os.path.exists(db_path):
                os.remove(db_path)
            for suffix in ("-wal", "-shm"):
                sidecar = db_path + suffix
                if os.path.exists(sidecar):
                    try:
                        os.remove(sidecar)
                    except OSError:
                        pass
            deleted = True
            break
        except OSError as exc:
            if attempt < retries - 1:
                gc.collect()
                time.sleep(delay * (2 ** attempt))
            else:
                logger.warning("Could not delete %s after %d retries: %s — using SQL wipe fallback", db_path, retries, exc)

    if not deleted and os.path.exists(db_path):
        _TABLE_NAMES = [
            "certificates", "groups", "maintenance_windows",
            "notification_policies", "notification_log", "renewal_log",
            "users", "user_invites", "connectors", "activity_log",
            "agent_tokens", "settings", "agents", "usage_metrics",
        ]
        try:
            conn = sqlite3.connect(db_path, timeout=5.0)
            for table in _TABLE_NAMES:
                conn.execute(f"DROP TABLE IF EXISTS {table}")
            conn.execute("PRAGMA user_version = 0")
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("SQL wipe fallback failed for %s: %s", db_path, exc)

