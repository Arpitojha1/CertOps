"""
Dict-based connector registry: maps category keys to (connector_class, match_fn) tuples.
Replaces the hardcoded if/elif dispatch chain in main.py.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

_src_dir = Path(__file__).resolve().parent
_project_dir = _src_dir.parent
if str(_project_dir) not in sys.path:
    sys.path.insert(0, str(_project_dir))
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

logger = logging.getLogger(__name__)


class _GenericConnector:
    """Fallback for unknown connector types. No-op methods, preserves metadata."""
    pass


def _match_azure(cat: str, cname: str, cfg: dict, thresh: float | None) -> bool:
    return (
        cat == "azure"
        or "azure" in cname.lower()
        or cfg.get("provider", "").lower() == "azure"
        or cfg.get("type", "").lower() == "azure"
    )


def _match_hashicorp(cat: str, cname: str, cfg: dict, thresh: float | None) -> bool:
    return (
        cat in ("secret_store", "hashicorp", "vault")
        or "hashicorp" in cname.lower()
        or "vault" in cname.lower()
    )


def _match_ssh(cat: str, cname: str, cfg: dict, thresh: float | None) -> bool:
    return (
        cat in ("host", "ssh_host", "ssh")
        or "ssh" in cname.lower()
    )


def _match_winrm(cat: str, cname: str, cfg: dict, thresh: float | None) -> bool:
    return (
        cat in ("winrm_host", "winrm")
        or "winrm" in cname.lower()
    )


CONNECTOR_REGISTRY: dict[str, tuple[type, callable]] = {
    "azure": (None, _match_azure),
    "hashicorp": (None, _match_hashicorp),
    "ssh_host": (None, _match_ssh),
    "winrm_host": (None, _match_winrm),
}


def resolve_connector(row: dict[str, Any]) -> Any:
    """
    Takes a DB row dict (name, category, config, renewal_threshold_days),
    returns an instantiated connector object.
    Falls back to _GenericConnector for unknown types.
    """
    from src import azurekeyvault, vault_client, host_connector, db

    cfg_raw = row.get("config", "{}")
    cfg = db.decrypt_config(cfg_raw) if isinstance(cfg_raw, str) else (cfg_raw or {})
    cname = row["name"]
    cat = (row.get("category") or "").lower()
    thresh = row.get("renewal_threshold_days")

    if _match_azure(cat, cname, cfg, thresh):
        c = azurekeyvault.AzureKeyVaultClient.from_config(cfg, renewal_threshold_days=thresh)
        c.name = cname
        return c
    if _match_hashicorp(cat, cname, cfg, thresh):
        def _get_field(keys: list[str], env_var: str) -> Any:
            for k in keys:
                if k in cfg and cfg[k] is not None:
                    return cfg[k]
            return os.getenv(env_var)

        vault_addr = _get_field(["url", "vault_addr", "VAULT_ADDR"], "VAULT_ADDR")
        vault_token = _get_field(["token", "vault_token", "VAULT_TOKEN"], "VAULT_TOKEN")
        c = vault_client.HashiCorpVaultClient(vault_addr=vault_addr, vault_token=vault_token, renewal_threshold_days=thresh)
        c.name = cname
        return c
    if _match_ssh(cat, cname, cfg, thresh):
        c = host_connector.SSHHostConnector.from_config(cfg, renewal_threshold_days=thresh)
        c.name = cname
        return c
    if _match_winrm(cat, cname, cfg, thresh):
        c = host_connector.WinRMHostConnector.from_config(cfg, renewal_threshold_days=thresh)
        c.name = cname
        return c

    c = _GenericConnector()
    c.name = cname
    c.category = cat
    c.renewal_threshold_days = thresh
    return c


def resolve_host_connector(row: dict[str, Any]) -> Any:
    """
    Resolves a host connector (SSH/WinRM) from a DB row.
    Raises RuntimeError for non-host connector types.
    """
    cat = (row.get("category") or "").lower()
    cname = row["name"]
    cfg_raw = row.get("config", "{}")
    from src import db
    cfg = db.decrypt_config(cfg_raw) if isinstance(cfg_raw, str) else (cfg_raw or {})

    if _match_ssh(cat, cname, cfg, None):
        from src import host_connector
        c = host_connector.SSHHostConnector.from_config(cfg)
        c.name = cname
        return c
    if _match_winrm(cat, cname, cfg, None):
        from src import host_connector
        c = host_connector.WinRMHostConnector.from_config(cfg)
        c.name = cname
        return c

    raise RuntimeError(f"Unknown host connector type: '{cname}' (category='{cat}')")


def probe_env_vars() -> list[dict]:
    """
    Checks environment variables and returns a list of connector configs to seed.
    One entry per detected backend. Incomplete configs are still returned
    (the connector class will raise at instantiation time if required fields are missing).
    """
    configs = []

    vault_addr = os.getenv("VAULT_ADDR")
    if vault_addr:
        configs.append({
            "name": "hashicorp",
            "category": "hashicorp",
            "config": {
                "url": vault_addr,
                "token": os.getenv("VAULT_TOKEN"),
            },
        })

    azure_url = os.getenv("AZURE_KEYVAULT_URL")
    if azure_url:
        configs.append({
            "name": "azure",
            "category": "azure",
            "config": {
                "keyvault_url": azure_url,
                "tenant_id": os.getenv("AZURE_TENANT_ID"),
                "client_id": os.getenv("AZURE_CLIENT_ID"),
                "client_secret": os.getenv("AZURE_CLIENT_SECRET"),
            },
        })

    return configs


def seed_connectors_from_env(db_path: str | None = None) -> list[str]:
    """
    Probes env vars and creates DB connector rows for detected backends.
    Skips backends that already have a connector with the same name (idempotent).
    Returns list of newly seeded connector names.
    """
    from src import db

    configs = probe_env_vars()
    seeded = []
    for cfg in configs:
        existing = db.get_connector_by_name(cfg["name"], db_path=db_path)
        if existing:
            logger.info("Connector '%s' already exists in DB, skipping seed", cfg["name"])
            continue
        db.create_connector(
            name=cfg["name"],
            category=cfg["category"],
            renewal_threshold_days=float(os.getenv("RENEWAL_THRESHOLD_DAYS", "2")),
            config=json.dumps(cfg["config"]),
            is_active=True,
            db_path=db_path,
        )
        logger.info("Seeded connector '%s' from environment variables", cfg["name"])
        seeded.append(cfg["name"])
    return seeded
