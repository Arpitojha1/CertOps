"""
Azure Key Vault client for reading, listing, and writing certificate secrets.
"""

import logging
import os
import ssl
from typing import Any

from azure.identity import ClientSecretCredential
from azure.keyvault.certificates import (
    CertificateClient,
    CertificateContentType,
    CertificatePolicy,
)
from cryptography import x509

if __package__ is None or __package__ == "":
    import db
else:
    from . import db

logger = logging.getLogger(__name__)


class AzureKeyVaultClient:
    name = "azure"

    def __init__(self, vault_url: str | None = None, credential: Any | None = None, renewal_threshold_days: float | None = None) -> None:
        if vault_url is None:
            vault_url = os.getenv("AZURE_KEYVAULT_URL")
            if not vault_url:
                raise RuntimeError("AZURE_KEYVAULT_URL not set")

        if credential is None:
            tenant_id = os.getenv("AZURE_TENANT_ID")
            if not tenant_id:
                raise RuntimeError("AZURE_TENANT_ID not set")
            client_id = os.getenv("AZURE_CLIENT_ID")
            if not client_id:
                raise RuntimeError("AZURE_CLIENT_ID not set")
            client_secret = os.getenv("AZURE_CLIENT_SECRET")
            if not client_secret:
                raise RuntimeError("AZURE_CLIENT_SECRET not set")

            credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret,
            )

        self.vault_url = vault_url.rstrip("/")
        self.credential = credential
        self.client = CertificateClient(
            vault_url=self.vault_url, credential=self.credential
        )
        self.renewal_threshold_days = renewal_threshold_days

    @classmethod
    def from_env(cls, renewal_threshold_days: float | None = None) -> "AzureKeyVaultClient":
        if renewal_threshold_days is None:
            thresh_str = os.getenv("AZURE_RENEWAL_THRESHOLD_DAYS")
            renewal_threshold_days = float(thresh_str) if thresh_str else None
        return cls(renewal_threshold_days=renewal_threshold_days)

    @classmethod
    def from_config(cls, config: dict[str, Any], renewal_threshold_days: float | None = None) -> "AzureKeyVaultClient":
        """
        Constructs AzureKeyVaultClient from a DB config dict.
        DB values are authoritative; env vars are fallback per-field only when
        the DB config key is absent (not when it's None or empty).
        """
        def _get_field(keys: list[str], env_var: str) -> Any:
            for k in keys:
                if k in config and config[k] is not None:
                    return config[k]
            return os.getenv(env_var)

        vault_url = _get_field(["keyvault_url", "url"], "AZURE_KEYVAULT_URL")
        if not vault_url:
            raise RuntimeError("Azure Key Vault URL not found in DB config or AZURE_KEYVAULT_URL env var")

        tenant_id = _get_field(["tenant_id"], "AZURE_TENANT_ID")
        client_id = _get_field(["client_id"], "AZURE_CLIENT_ID")
        client_secret = _get_field(["client_secret"], "AZURE_CLIENT_SECRET")

        if not all([tenant_id, client_id, client_secret]):
            missing = [k for k, v in {"tenant_id": tenant_id, "client_id": client_id, "client_secret": client_secret}.items() if not v]
            raise RuntimeError(f"Azure credentials incomplete: missing {', '.join(missing)} (checked DB config and env vars)")

        credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )

        if renewal_threshold_days is None:
            thresh_str = _get_field(["renewal_threshold_days"], "AZURE_RENEWAL_THRESHOLD_DAYS")
            renewal_threshold_days = float(thresh_str) if thresh_str else None

        return cls(vault_url=vault_url, credential=credential, renewal_threshold_days=renewal_threshold_days)

    @staticmethod
    def _get_common_name(cert: Any) -> str:
        if getattr(cert, "cer", None):
            try:
                x509_cert = x509.load_der_x509_certificate(cert.cer)
                cns = x509_cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
                if cns:
                    return str(cns[0].value)
            except Exception:
                pass

        if getattr(cert, "policy", None) and getattr(cert.policy, "subject", None):
            for part in cert.policy.subject.split(","):
                part = part.strip()
                if part.upper().startswith("CN="):
                    return part[3:].strip()
            return cert.policy.subject

        return ""

    @db.log_connector_event("discovered")
    def list_certificates(self) -> list[dict]:
        results = []
        try:
            pages = self.client.list_properties_of_certificates()
        except Exception as exc:
            raise RuntimeError(
                f"Failed to list certificates from Azure Key Vault: {exc}"
            ) from exc

        for prop in pages:
            try:
                if not prop.expires_on:
                    logger.warning(
                        "Certificate '%s' has no expiry metadata; skipping.",
                        prop.name,
                    )
                    continue

                results.append({
                    "name": prop.name,
                    "vault_path": getattr(prop, "id", prop.name) or prop.name,
                    "expiry_utc": prop.expires_on,
                })
            except Exception as exc:
                logger.warning(
                    "Malformed certificate entry encountered during listing: %s", exc
                )
                continue

        return results

    def get_certificate(self, name: str) -> dict:
        cert = self.client.get_certificate(name)
        if not getattr(cert, "cer", None):
            raise RuntimeError(
                f"Certificate '{name}' returned no certificate bytes (cer is missing/empty)."
            )

        cert_pem = ssl.DER_cert_to_PEM_cert(cert.cer)
        common_name = self._get_common_name(cert)

        return {
            "name": cert.name or name,
            "version": cert.properties.version,
            "cert_pem": cert_pem,
            "expiry_utc": cert.properties.expires_on,
            "common_name": common_name,
        }

    @db.log_connector_event("renewed")
    def write_certificate(
        self, name: str, cert_pem: str, private_key_pem: str
    ) -> dict:
        try:
            from cryptography.hazmat.primitives import serialization
            key_obj = serialization.load_pem_private_key(
                private_key_pem.encode("utf-8"), password=None
            )
            normalized_key_pem = key_obj.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ).decode("utf-8")
        except Exception:
            normalized_key_pem = private_key_pem

        combined_pem = f"{normalized_key_pem.strip()}\n{cert_pem.strip()}\n".encode(
            "utf-8"
        )
        policy = CertificatePolicy(content_type=CertificateContentType.pem)

        try:
            imported = self.client.import_certificate(
                certificate_name=name,
                certificate_bytes=combined_pem,
                policy=policy,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to write certificate '{name}' to Key Vault: {exc}"
            ) from exc

        return {
            "name": imported.name or name,
            "version": imported.properties.version,
            "expiry_utc": imported.properties.expires_on,
        }


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    client = AzureKeyVaultClient()

    print("Testing list_certificates()...")
    certs = client.list_certificates()
    print(f"Found {len(certs)} certificate(s):")
    for c in certs:
        print(f"  - {c['name']} (expires: {c['expiry_utc']})")

    if certs:
        test_name = certs[0]["name"]
        print(f"\nTesting get_certificate('{test_name}')...")
        info = client.get_certificate(test_name)
        assert "-----BEGIN CERTIFICATE-----" in info["cert_pem"]
        print(
            f"get_certificate OK: CN={info['common_name']}, Expiry={info['expiry_utc']}"
        )
