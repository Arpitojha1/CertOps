"""
pytest conftest for certops-agent tests.

Uses a session-scoped autouse fixture that:
1. Snapshots all watched env vars at session start.
2. Clears them immediately so external pollution cannot affect any test.
3. Restores the original snapshot at session end.

Individual tests that need specific vars set them in setUp/setUpClass and
clean up in tearDown/tearDownClass, which is the existing pattern.
"""

import os
import pytest


# All env vars that any agent test file mutates (discovered by grep).
_WATCHED_VARS = [
    "DB_PATH",
    "CERTOPS_DB_PATH",
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
