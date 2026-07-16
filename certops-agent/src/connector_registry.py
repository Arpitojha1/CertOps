"""
Dict-based connector registry: maps category keys to (connector_class, match_fn) tuples.
Replaces the hardcoded if/elif dispatch chain in main.py.
"""

import json
import logging
import os
from typing import Any

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
    from src import azurekeyvault, vault_client, host_connector

    cfg_raw = row.get("config", "{}")
    cfg = json.loads(cfg_raw) if isinstance(cfg_raw, str) else (cfg_raw or {})
    cname = row["name"]
    cat = (row.get("category") or "").lower()
    thresh = row.get("renewal_threshold_days")

    if _match_azure(cat, cname, cfg, thresh):
        c = azurekeyvault.AzureKeyVaultClient.from_config(cfg, renewal_threshold_days=thresh)
        c.name = cname
        return c
    if _match_hashicorp(cat, cname, cfg, thresh):
        vault_addr = cfg.get("url") or cfg.get("vault_addr") or cfg.get("VAULT_ADDR") or os.getenv("VAULT_ADDR")
        vault_token = cfg.get("token") or cfg.get("vault_token") or cfg.get("VAULT_TOKEN") or os.getenv("VAULT_TOKEN")
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
