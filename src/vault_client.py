"""
HashiCorp Vault client for reading and writing certificate secrets in KV v2 engine.
"""

import logging
import os
from typing import Any

import requests

if __package__ is None or __package__ == "":
    import db
    import verify
else:
    from . import db, verify


logger = logging.getLogger(__name__)


def _normalize_kv2_path(path: str) -> str:
    path = path.strip("/")
    parts = path.split("/")
    if len(parts) >= 2 and parts[1] == "data":
        return path
    return f"{parts[0]}/data/{'/'.join(parts[1:])}"


def read_certificate(vault_addr: str, vault_token: str, path: str) -> tuple[str, str]:
    """
    Reads certificate and private_key from Vault KV v2.
    Returns (certificate_pem, private_key_pem).
    Raises RuntimeError on failure.
    """
    api_path = _normalize_kv2_path(path)
    url = f"{vault_addr.rstrip('/')}/v1/{api_path}"
    headers = {"X-Vault-Token": vault_token}

    resp = requests.get(url, headers=headers, timeout=10)
    if not resp.ok:
        raise RuntimeError(
            f"Failed to read certificate from Vault path '{path}' "
            f"(HTTP {resp.status_code}): {resp.text}"
        )

    payload = resp.json()
    try:
        secret_data = payload["data"]["data"]
        cert = secret_data["certificate"]
        key = secret_data["private_key"]
        return cert, key
    except (KeyError, TypeError) as exc:
        raise RuntimeError(
            f"Vault secret at '{path}' missing 'certificate' or 'private_key' field: {exc}"
        ) from exc


def write_certificate(
    vault_addr: str, vault_token: str, path: str, cert_pem: str, key_pem: str
) -> None:
    """
    Writes a new version of certificate and private_key to Vault KV v2.
    Raises RuntimeError on failure.
    """
    api_path = _normalize_kv2_path(path)
    url = f"{vault_addr.rstrip('/')}/v1/{api_path}"
    headers = {"X-Vault-Token": vault_token}
    body = {"data": {"certificate": cert_pem, "private_key": key_pem}}

    resp = requests.post(url, headers=headers, json=body, timeout=10)
    if not resp.ok:
        raise RuntimeError(
            f"Failed to write certificate to Vault path '{path}' "
            f"(HTTP {resp.status_code}): {resp.text}"
        )


class HashiCorpVaultClient:
    name = "hashicorp"

    def __init__(
        self,
        vault_addr: str | None = None,
        vault_token: str | None = None,
        mount: str = "secret",
        prefix: str = "certs/",
        renewal_threshold_days: float | None = None,
    ) -> None:
        if vault_addr is None:
            vault_addr = os.getenv("VAULT_ADDR", "http://localhost:8200")
        if vault_token is None:
            vault_token = os.getenv("VAULT_TOKEN")
            if not vault_token:
                raise RuntimeError("VAULT_TOKEN not set for HashiCorpVaultClient")

        self.vault_addr = vault_addr.rstrip("/")
        self.vault_token = vault_token
        self.mount = mount.strip("/")
        self.prefix = prefix.lstrip("/")
        if self.prefix and not self.prefix.endswith("/"):
            self.prefix += "/"
        self.renewal_threshold_days = renewal_threshold_days

    @classmethod
    def from_env(cls, renewal_threshold_days: float | None = None) -> "HashiCorpVaultClient":
        prefix = os.getenv("VAULT_CERT_PREFIX", "certs/")
        if renewal_threshold_days is None:
            thresh_str = os.getenv("VAULT_RENEWAL_THRESHOLD_DAYS")
            renewal_threshold_days = float(thresh_str) if thresh_str else None
        return cls(prefix=prefix, renewal_threshold_days=renewal_threshold_days)

    def _full_api_path(self, name: str, is_metadata: bool = False) -> str:
        clean_name = name.split("/")[-1]
        kind = "metadata" if is_metadata else "data"
        return f"{self.vault_addr}/v1/{self.mount}/{kind}/{self.prefix}{clean_name}"

    @db.log_connector_event("discovered")
    def list_certificates(self) -> list[dict[str, Any]]:
        url = f"{self.vault_addr}/v1/{self.mount}/metadata/{self.prefix}?list=true"
        headers = {"X-Vault-Token": self.vault_token}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 404:
            return []
        if not resp.ok:
            raise RuntimeError(
                f"Failed to list certificates from HashiCorp Vault ({resp.status_code}): {resp.text}"
            )

        keys = resp.json().get("data", {}).get("keys", [])
        results = []
        for k in keys:
            if k.endswith("/"):
                continue
            try:
                cert_info = self.get_certificate(k)
                results.append({
                    "name": k,
                    "vault_path": f"{self.mount}/{self.prefix}{k}",
                    "expiry_utc": cert_info["expiry_utc"],
                    "version": cert_info["version"],
                })
            except Exception as exc:
                logger.warning("Skipping malformed cert entry '%s' in HashiCorp Vault: %s", k, exc)
                continue
        return results

    def get_certificate(self, name: str) -> dict[str, Any]:
        url = self._full_api_path(name, is_metadata=False)
        headers = {"X-Vault-Token": self.vault_token}
        resp = requests.get(url, headers=headers, timeout=10)
        if not resp.ok:
            raise RuntimeError(
                f"Failed to read certificate '{name}' from HashiCorp Vault ({resp.status_code}): {resp.text}"
            )

        payload = resp.json()
        data = payload.get("data", {})
        secret_data = data.get("data", {})
        metadata = data.get("metadata", {})
        version = metadata.get("version", 1)

        cert_pem = secret_data.get("certificate")
        key_pem = secret_data.get("private_key")
        if not cert_pem:
            raise RuntimeError(f"Certificate '{name}' missing 'certificate' field in Vault.")

        expiry_utc, _ = verify.get_pem_cert_info(cert_pem)
        return {
            "name": name.split("/")[-1],
            "cert_pem": cert_pem,
            "private_key_pem": key_pem,
            "expiry_utc": expiry_utc,
            "version": str(version),
            "common_name": name.split("/")[-1],
            "vault_path": f"{self.mount}/{self.prefix}{name.split('/')[-1]}",
        }

    @db.log_connector_event("renewed")
    def write_certificate(
        self, name: str, cert_pem: str, private_key_pem: str
    ) -> dict[str, Any]:
        url = self._full_api_path(name, is_metadata=False)
        headers = {"X-Vault-Token": self.vault_token}
        body = {"data": {"certificate": cert_pem, "private_key": private_key_pem}}

        resp = requests.post(url, headers=headers, json=body, timeout=10)
        if not resp.ok:
            raise RuntimeError(
                f"Failed to write certificate '{name}' to HashiCorp Vault ({resp.status_code}): {resp.text}"
            )

        payload = resp.json()
        version = payload.get("data", {}).get("version", 1)
        expiry_utc, _ = verify.get_pem_cert_info(cert_pem)
        return {
            "name": name.split("/")[-1],
            "version": str(version),
            "expiry_utc": expiry_utc,
        }


if __name__ == "__main__":
    # Small runnable check against dev Vault instance
    addr = "http://localhost:8200"
    token = "root"
    client = HashiCorpVaultClient(vault_addr=addr, vault_token=token, prefix="test-certs/")
    print("Testing HashiCorpVaultClient...")
    certs = client.list_certificates()
    print("list_certificates OK. Count:", len(certs))
