"""
Agent-Side Push Client (`src/agent_telemetry.py`) for Track C.
Implements strict allow-list filtering and error sanitization according to TELEMETRY_CONTRACT.md.
"""

from datetime import datetime, timezone
from typing import Any
import requests


class AgentTelemetryClient:
    """
    Reads current cert/connector state or accepts state items,
    builds payload matching Track A allow-list exactly,
    sends using agent token (never dashboard auth path).
    """
    def __init__(self, agent_id: str, agent_version: str, agent_token: str, ingest_url: str | None = None) -> None:
        self.agent_id = agent_id
        self.agent_version = agent_version
        self.agent_token = agent_token
        self.ingest_url = ingest_url

    def build_payload(self, connectors: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Builds structured telemetry payload from connector/cert state dicts.
        Enforces strict allow-list filtering — any extra or sensitive field
        present in input dicts is stripped out.
        """
        items = []
        for c in connectors:
            items.append({
                "connector_type": str(c.get("connector_type", "secret_store")),
                "connector_opaque_id": str(c.get("connector_opaque_id", "unknown")),
                "connector_health": str(c.get("connector_health", "ok")),
                "connector_status": str(c.get("connector_status", "ok")),
                "error_code": c.get("error_code") if c.get("error_code") is not None else None,
                "cert_cn": str(c.get("cert_cn", "")),
                "cert_san": list(c.get("cert_san", [])),
                "expiry_utc": str(c.get("expiry_utc", "")),
                "renewal_stage": str(c.get("renewal_stage", "healthy"))
            })

        return {
            "agent_id": str(self.agent_id),
            "agent_version": str(self.agent_version),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "items": items
        }

    def push(self, connectors: list[dict[str, Any]], timeout: int = 10) -> tuple[int, dict[str, Any]]:
        """
        Send payload to telemetry ingestion endpoint using agent token in Authorization header.
        """
        if not self.ingest_url:
            raise ValueError("ingest_url must be provided to push telemetry")
        payload = self.build_payload(connectors)
        headers = {
            "Authorization": f"Bearer {self.agent_token}",
            "Content-Type": "application/json"
        }
        resp = requests.post(self.ingest_url, headers=headers, json=payload, timeout=timeout)
        try:
            data = resp.json()
        except Exception:
            data = {"detail": resp.text}
        return resp.status_code, data


def sanitize_connector_error(
    connector_type: str,
    connector_opaque_id: str,
    raw_error_message: str,
    cert_cn: str,
    expiry_utc: str,
    renewal_stage: str
) -> dict[str, Any]:
    """
    Sanitize raw error strings (which might contain stack traces, passwords, IPs, or hostnames)
    into clean, contract-compliant items.
    """
    raw_lower = raw_error_message.lower() if raw_error_message else ""
    if "timeout" in raw_lower:
        error_code = "ERR_CONNECTION_TIMEOUT"
        status_msg = "Connection timed out during host check"
    elif any(k in raw_lower for k in ["refused", "unreachable", "10061", "10060", "connect error"]):
        error_code = "ERR_CONNECTOR_UNREACHABLE"
        status_msg = "Connection error on connector"
    elif any(k in raw_lower for k in ["auth", "password", "permission", "unauthorized", "401", "403", "forbidden"]):
        error_code = "ERR_AUTH_FAILED"
        status_msg = "Authentication failed on connector"
    else:
        error_code = "ERR_CONNECTOR_OPERATION_FAILED"
        status_msg = "Operation failed on connector"

    return {
        "connector_type": connector_type,
        "connector_opaque_id": connector_opaque_id,
        "connector_health": "error",
        "connector_status": status_msg,
        "error_code": error_code,
        "cert_cn": cert_cn,
        "cert_san": [],
        "expiry_utc": expiry_utc,
        "renewal_stage": renewal_stage
    }
