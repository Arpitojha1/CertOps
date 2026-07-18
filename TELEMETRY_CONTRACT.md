# CertOps Telemetry Contract (`TELEMETRY_CONTRACT.md`)
**Source of Truth for Agent ⇄ Dashboard Communication across the Architecture Boundary.**

---

## 1. Scope & Architectural Boundary

CertOps operates as two decoupled systems:
- **The Agent (`certops-agent`)**: Deployed on customer infrastructure. Has local network access to Vault, Azure Key Vault, SSH/WinRM targets, and `step-ca`. Holds private keys, passwords, and sensitive configuration.
- **The Dashboard (`certops-dashboard`)**: Hosted central observability control plane. Receives telemetry pulses from agents to display fleet status, renewal timelines, and connector health.

To guarantee zero-knowledge observability where secrets and internal topologies never leak to the dashboard, all outgoing agent transmissions MUST strictly adhere to this Telemetry Contract.

---

## 2. Edge Case Interrogation & Rules

1. **HostConnector (SSH/WinRM) Identity (`connector_opaque_id` vs. `raw hostname`)**:
   - Remote host connectors target internal hostnames/IPs (`web-prod-01.internal.corp`, `10.240.12.8`). Transmitting literal hostnames/IPs exposes internal network topologies and server roles to central logs.
   - **Rule**: Hostnames and IPs are classified as sensitive-by-default (`raw hostname`). Every connector instance MUST report a stable, connector-scoped opaque ID (`connector_opaque_id: conn_[uuid/hash]`). Only `connector_opaque_id` and `connector_type` (`vault`, `azure_kv`, `ssh`, `winrm`) cross the wire.
2. **Multiple Certificates Behind a Single Connector**:
   - An SSH host or Vault store often serves/holds dozens of vhosts or certificates. Aggregated connector heartbeats (`"cert_count": 12`) cannot track individual certificate lifecycle progression or isolated deployment failures.
   - **Rule**: Telemetry operates strictly at **certificate granularity**. When an agent checks or renews multiple certificates on a connector, it emits distinct item records inside the batch `items` array, each carrying its own `cert_cn`, `cert_san`, `expiry_utc`, and `renewal_stage`.
3. **Error Payloads & Strict Sanitization**:
   - Unhandled exceptions (`FileNotFoundError`, `AuthenticationException`, `HTTPError`) leak internal filesystem paths, configuration locations, private key filenames, and target URLs.
   - **Rule**: Strict deny-list rule prohibits raw Python exception strings, tracebacks (`traceback.format_exc()`), or OS error descriptions from crossing the wire. All errors are mapped at the agent boundary to a fixed enumerated type (`error_code: TelemetryErrorCode`).
4. **Renewal Stage Vocabulary**:
   - Exact preservation and reuse of existing vocabulary (`healthy`, `due_soon`, `overdue`, `Renewed`, `Deployed pending reload`, `Reload confirmed`). Do NOT invent new unmapped terms.

---

## 3. Batched Envelope & Item Allow-List vs. Deny-List

### Batched Envelope Structure (`TelemetryPayloadModel`)
Every HTTP POST request to `/api/telemetry/push` (or `/api/telemetry/ingest`) MUST use this JSON top-level envelope:
- `agent_id` (string): Unique identifier for the agent installation (`UUIDv4` or `agent-[string]`).
- `agent_version` (string): Semantic version of the running agent (`1.0.0`).
- `timestamp` / `timestamp_utc` (string): ISO 8601 UTC timestamp (`YYYY-MM-DDTHH:MM:SS.sssZ`).
- `items` (array of `TelemetryItemModel`): Array of individual connector/certificate telemetry records.

### Crosses the Wire: Item Allow-List (`TelemetryItemModel`)
Only the exact fields below are permitted in each item record:
- `connector_type` (string): `"vault"`, `"azure_kv"`, `"ssh"`, `"winrm"`, or `"secret_store"`.
- `connector_opaque_id` (string): Stable opaque string (`UUIDv4` or `conn-[hash]`).
- `connector_health` (string): `"ok"`, `"degraded"`, or `"error"`.
- `connector_status` (string): Sanitized human-readable summary (`"Healthy secret store connection"`, `"Connection timed out during host check"`).
- `error_code` (string | null): Fixed enum value from `TelemetryErrorCode` (or `null` if healthy).
- `cert_cn` (string): Domain string (`CN` / primary SAN).
- `cert_san` (list of strings): Array of domain strings (Subject Alternative Names).
- `expiry_utc` (string): ISO 8601 UTC timestamp of certificate expiration.
- `renewal_stage` (string): Pipeline stage (`"healthy"`, `"due_soon"`, `"overdue"`, `"Renewed"`, `"Deployed pending reload"`, `"Reload confirmed"`).

### Never Crosses the Wire (Deny-List)
- **Private Keys**: RSA/ECDSA keys (`.key`, `.pem`, PKCS#8/1, DER, JWK), PKCS#12 (`.pfx`/`.p12`) archives or passphrases, and in-memory key representations.
- **Plaintext Credentials**: Vault tokens (`VAULT_TOKEN`), AppRole secret IDs, Azure Key Vault client secrets/identities, SSH private keys/passphrases, WinRM passwords, and DB connection strings.
- **Full Connector Config & Sensitive Fields**: Raw `config` JSON blobs from DB, Vault engine paths (`secret/data/...`), Azure Key Vault URIs (`https://...vault.azure.net/`), remote target hostnames/FQDNs/IPs, target usernames/ports (`root:22`), and remote certificate installation paths (`/etc/nginx/ssl/...`).
- **Raw Hostnames or IP Addresses**: Any literal server name, internal domain, or IP (`10.x.x.x`, `192.168.x.x`), unless explicitly captured inside `cert_cn` or `cert_san` of the managed certificate.
- **Free-Text Error Messages & Tracebacks**: Python tracebacks (`Traceback (most recent call last): ...`), raw exception strings (`FileNotFoundError`, `AuthenticationException`), and OS/network error strings.

---

## 4. Fixed Error-Code Enumeration (`TelemetryErrorCode`)

| Error Code | Classification | Description |
| :--- | :--- | :--- |
| `ERR_CONNECTOR_UNREACHABLE` | Network / Reachability | Network timeout or connection failure connecting to Vault, Azure KV, SSH host, or WinRM host. |
| `ERR_CONNECTION_TIMEOUT` | Network / Timeout | Connection timed out during remote host check or socket handshake. |
| `ERR_AUTH_FAILED` | Authentication / Authorization | Credentials rejected by secret store or remote host connector. |
| `ERR_CERT_NOT_FOUND` | Discovery / Missing Target | Certificate ID or secret path does not exist on target store/filesystem. |
| `ERR_RENEWAL_REJECTED` | CA Client / Issuance Failure | CA rejected CSR or domain validation failed (`Stage 1`). |
| `ERR_DEPLOY_FAILED` | Target Deployment Failure | Writing renewed cert/key to target path failed (`Stage 2`). |
| `ERR_RELOAD_FAILED` | Service Reload Failure | Service reload command (`systemctl reload nginx` / IIS recycle) failed (`Stage 3`). |
| `ERR_VERIFY_FAILED` | Endpoint Verification Failure | Post-reload TLS handshake verification failed against target endpoint (`Stage 3`). |
| `ERR_MAINTENANCE_WINDOW_ACTIVE` | Policy Gate / Held | Operation held because target group is currently outside its maintenance window. |
| `ERR_CONNECTOR_OPERATION_FAILED` | General Connector Failure | Generic/unclassified operation failure on connector (sanitized). |
| `ERR_INTERNAL_AGENT_ERROR` | Unhandled Agent Exception | Internal logic failure (traceback stripped; only enum code crosses wire). |

---

## 5. Literal Example Payloads

### Example 1: Batched Telemetry Push Envelope (`/api/telemetry/push`)
```json
{
  "agent_id": "agent-prod-us-east-1",
  "agent_version": "1.0.0",
  "timestamp": "2026-07-15T03:31:00.000Z",
  "items": [
    {
      "connector_type": "vault",
      "connector_opaque_id": "conn-vault-sha256-a1b2",
      "connector_health": "ok",
      "connector_status": "Healthy secret store connection",
      "error_code": null,
      "cert_cn": "vault-cert.local",
      "cert_san": [
        "www.vault-cert.local",
        "api.vault-cert.local"
      ],
      "expiry_utc": "2028-07-13T00:00:00Z",
      "renewal_stage": "healthy"
    },
    {
      "connector_type": "ssh",
      "connector_opaque_id": "conn-ssh-sha256-e5f6",
      "connector_health": "ok",
      "connector_status": "SSH deploy check passed",
      "error_code": null,
      "cert_cn": "ssh-host.local",
      "cert_san": [
        "host1.local"
      ],
      "expiry_utc": "2026-07-24T00:00:00Z",
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
      "expiry_utc": "2026-07-15T00:00:00Z",
      "renewal_stage": "overdue"
    }
  ]
}
```

---

## 6. Sign-Off

- [x] Maintainer 1 review
- [x] Maintainer 2 review
- [x] Agent implementation verified against contract
- [x] Dashboard ingestion verified against contract
