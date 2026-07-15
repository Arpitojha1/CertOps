"""
Hermetic verification tests for Track C:
- Stub Ingestion Endpoint (src/routes/telemetry_ingest.py)
- Agent-Side Push Client (src/agent_telemetry.py)
- Programmatic Allow-list / Deny-list Check against Track A contract (TELEMETRY_CONTRACT.md)
"""

import json
import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

# Add repo root and src/ to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from src.api import app
from src import agent_telemetry
from src.routes import telemetry_ingest


# Programmatic Allow-list and Deny-list rules corresponding to TELEMETRY_CONTRACT.md & Track C requirements
ALLOW_LIST_KEYS = {
    "agent_id",
    "agent_version",
    "timestamp",
    "items",
    "connectors",
    "certificates",
    "connector_type",
    "connector_opaque_id",
    "connector_health",
    "connector_status",
    "error_code",
    "error_codes",
    "cert_cn",
    "CN",
    "cert_san",
    "SAN",
    "expiry_utc",
    "expiry",
    "renewal_stage"
}

DENY_LIST_PATTERNS = [
    "BEGIN RSA PRIVATE KEY",
    "BEGIN PRIVATE KEY",
    "BEGIN CERTIFICATE",
    "secret/data/",
    "password",
    "passwd",
    "Traceback (most recent call last)",
    "Exception:",
    "ConnectionRefusedError",
    "WinError",
    "192.168.",
    "10.0.0.",
    "vault-server.internal",
    "sre-password"
]


def check_payload_allow_list(data: Any) -> list[str]:
    """Recursively verify all keys in dictionary or list of dictionaries are in ALLOW_LIST_KEYS."""
    violations = []
    if isinstance(data, dict):
        for k, v in data.items():
            if k not in ALLOW_LIST_KEYS:
                violations.append(f"Disallowed key present: '{k}'")
            violations.extend(check_payload_allow_list(v))
    elif isinstance(data, list):
        for item in data:
            violations.extend(check_payload_allow_list(item))
    return violations


def check_payload_deny_list(data: Any) -> list[str]:
    """Recursively verify no strings anywhere in data match DENY_LIST_PATTERNS."""
    violations = []
    if isinstance(data, str):
        for pattern in DENY_LIST_PATTERNS:
            if pattern.lower() in data.lower():
                violations.append(f"Deny-listed pattern '{pattern}' found in value: '{data}'")
    elif isinstance(data, dict):
        for k, v in data.items():
            for pattern in DENY_LIST_PATTERNS:
                if pattern.lower() in str(k).lower():
                    violations.append(f"Deny-listed pattern '{pattern}' found in key: '{k}'")
            violations.extend(check_payload_deny_list(v))
    elif isinstance(data, list):
        for item in data:
            violations.extend(check_payload_deny_list(item))
    return violations


class TestTelemetryPush(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        # Clear in-memory sink before each test
        telemetry_ingest.clear_received_payloads()
        # Ensure test tokens are registered
        telemetry_ingest.register_agent_token("valid-agent-token-123", scope="telemetry_push", revoked=False)
        telemetry_ingest.register_agent_token("revoked-token-456", scope="telemetry_push", revoked=True)

    def test_01_fixtures_and_programmatic_allow_list_check(self):
        """
        C.1 & C.3: Build a real payload with multiple connectors (vault, azure_kv, ssh, winrm),
        728-day future expiry, error state connector, and diff against allow-list/deny-list.
        """
        now_utc = datetime.now(timezone.utc)
        future_728_days = (now_utc + timedelta(days=728)).isoformat()

        batch_state = [
            {
                "connector_type": "vault",
                "connector_opaque_id": "conn-vault-sha256-a1b2",
                "connector_health": "ok",
                "connector_status": "Healthy secret store connection",
                "error_code": None,
                "cert_cn": "vault-cert.local",
                "cert_san": ["www.vault-cert.local", "api.vault-cert.local"],
                "expiry_utc": future_728_days,
                "renewal_stage": "healthy"
            },
            {
                "connector_type": "azure_kv",
                "connector_opaque_id": "conn-azure-sha256-c3d4",
                "connector_health": "ok",
                "connector_status": "Healthy Azure KV connection",
                "error_code": None,
                "cert_cn": "azure-cert.local",
                "cert_san": [],
                "expiry_utc": (now_utc + timedelta(days=30)).isoformat(),
                "renewal_stage": "healthy"
            },
            {
                "connector_type": "ssh",
                "connector_opaque_id": "conn-ssh-sha256-e5f6",
                "connector_health": "ok",
                "connector_status": "SSH deploy check passed",
                "error_code": None,
                "cert_cn": "ssh-host.local",
                "cert_san": ["host1.local"],
                "expiry_utc": (now_utc + timedelta(days=10)).isoformat(),
                "renewal_stage": "due_soon"
            },
            {
                "connector_type": "winrm",
                "connector_opaque_id": "conn-winrm-sha256-7890",
                "connector_health": "error",
                "connector_status": "Connection timed out during host check",
                "error_code": "ERR_CONNECTION_TIMEOUT",
                "cert_cn": "winrm-host.local",
                "cert_san": [],
                "expiry_utc": (now_utc + timedelta(days=1)).isoformat(),
                "renewal_stage": "overdue"
            }
        ]

        push_client = agent_telemetry.AgentTelemetryClient(
            agent_id="agent-prod-us-east-1",
            agent_version="1.0.0",
            agent_token="valid-agent-token-123"
        )

        # Capture real payload produced by push client
        payload = push_client.build_payload(batch_state)
        self.assertIsInstance(payload, dict)
        self.assertIn("items", payload)
        self.assertEqual(len(payload["items"]), 4)

        # Diff field-by-field against Track A allow-list programmatically
        allow_violations = check_payload_allow_list(payload)
        self.assertEqual(allow_violations, [], f"Allow-list violations found: {allow_violations}")

        # Diff against deny-list programmatically
        deny_violations = check_payload_deny_list(payload)
        self.assertEqual(deny_violations, [], f"Deny-list violations found: {deny_violations}")

    def test_02_stub_ingestion_endpoint_valid_push(self):
        """
        C.2: Stub ingestion endpoint accepts valid agent token and payload, stores/logs it in sink.
        """
        push_client = agent_telemetry.AgentTelemetryClient(
            agent_id="agent-001",
            agent_version="1.0.0",
            agent_token="valid-agent-token-123"
        )
        payload = push_client.build_payload([
            {
                "connector_type": "vault",
                "connector_opaque_id": "conn-001",
                "connector_health": "ok",
                "connector_status": "ok",
                "error_code": None,
                "cert_cn": "test.local",
                "cert_san": [],
                "expiry_utc": "2027-01-01T00:00:00Z",
                "renewal_stage": "healthy"
            }
        ])

        response = self.client.post(
            "/api/telemetry/ingest",
            headers={"Authorization": "Bearer valid-agent-token-123"},
            json=payload
        )
        self.assertEqual(response.status_code, 202, f"Expected 202, got {response.status_code}: {response.text}")
        self.assertEqual(response.json().get("status"), "accepted")

        # Verify sink stored the received payload
        received = telemetry_ingest.get_received_payloads()
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["payload"]["agent_id"], "agent-001")
        self.assertIn("server_received_at", received[0])

    def test_03_revoked_or_invalid_token_push_attempt(self):
        """
        C.1 & C.2: Push attempt with revoked token should fail cleanly with 401/403 (never hang or 500).
        """
        payload = {
            "agent_id": "agent-001",
            "agent_version": "1.0.0",
            "timestamp": "2026-07-15T03:30:00Z",
            "items": []
        }

        # Attempt push with revoked token
        response_revoked = self.client.post(
            "/api/telemetry/ingest",
            headers={"Authorization": "Bearer revoked-token-456"},
            json=payload
        )
        self.assertIn(response_revoked.status_code, [401, 403], f"Expected 401/403, got {response_revoked.status_code}")
        self.assertIn("revoked", response_revoked.json().get("detail", "").lower())

        # Attempt push with unknown invalid token
        response_invalid = self.client.post(
            "/api/telemetry/ingest",
            headers={"Authorization": "Bearer unknown-token-999"},
            json=payload
        )
        self.assertIn(response_invalid.status_code, [401, 403], f"Expected 401/403, got {response_invalid.status_code}")

        # Ensure nothing was stored in the sink from rejected attempts
        self.assertEqual(len(telemetry_ingest.get_received_payloads()), 0)

    def test_04_clock_skew_handling(self):
        """
        C.1 & C.2: Clock skew between agent timestamp and dashboard timestamp.
        Assert contract/endpoint timestamp handling doesn't assume synchronized clocks.
        """
        now_utc = datetime.now(timezone.utc)
        # Agent clock is skewed 2 hours behind server time
        skewed_timestamp = (now_utc - timedelta(hours=2)).isoformat()

        payload = {
            "agent_id": "agent-skewed",
            "agent_version": "1.0.0",
            "timestamp": skewed_timestamp,
            "items": [
                {
                    "connector_type": "ssh",
                    "connector_opaque_id": "conn-ssh-1",
                    "connector_health": "ok",
                    "connector_status": "ok",
                    "error_code": None,
                    "cert_cn": "skewed.local",
                    "cert_san": [],
                    "expiry_utc": (now_utc + timedelta(days=100)).isoformat(),
                    "renewal_stage": "healthy"
                }
            ]
        }

        response = self.client.post(
            "/api/telemetry/ingest",
            headers={"Authorization": "Bearer valid-agent-token-123"},
            json=payload
        )
        self.assertEqual(response.status_code, 202, f"Expected 202 for skewed timestamp, got {response.status_code}")

        received = telemetry_ingest.get_received_payloads()
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["payload"]["timestamp"], skewed_timestamp)
        # Verify server recorded its own arrival timestamp independently
        self.assertIsNotNone(received[0].get("server_received_at"))

    def test_05_error_state_sanitization(self):
        """
        C.1 & C.3: When an exception occurs on agent side, AgentTelemetryClient sanitizes status
        and error codes so zero exceptions, stack traces, hostnames, or credentials cross the wire.
        """
        raw_exception_str = "ConnectionRefusedError: [WinError 10061] Failed connecting to 192.168.1.50:5985 with password 'sre-password-123'"
        sanitized_item = agent_telemetry.sanitize_connector_error(
            connector_type="winrm",
            connector_opaque_id="conn-winrm-sha256-9999",
            raw_error_message=raw_exception_str,
            cert_cn="winrm-host.local",
            expiry_utc="2026-08-01T00:00:00Z",
            renewal_stage="overdue"
        )

        self.assertEqual(sanitized_item["connector_health"], "error")
        self.assertEqual(sanitized_item["error_code"], "ERR_CONNECTOR_UNREACHABLE")
        # Ensure no deny-listed string is in the sanitized item
        deny_violations = check_payload_deny_list(sanitized_item)
        self.assertEqual(deny_violations, [], f"Sanitized error item contained deny-listed data: {deny_violations}")
        self.assertNotIn("sre-password", sanitized_item["connector_status"])
        self.assertNotIn("192.168.1.50", sanitized_item["connector_status"])
        self.assertNotIn("WinError", sanitized_item["connector_status"])
        self.assertIn("Connection error on connector", sanitized_item["connector_status"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
