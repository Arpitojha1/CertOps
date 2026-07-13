"""
Verification utilities for inspecting live served TLS certificates and PEM certificates.
"""

import hashlib
import socket
import ssl
from datetime import datetime

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding


def get_live_cert_info(host: str, port: int = 443) -> tuple[datetime, str]:
    """
    Connects to host:port via TLS without verifying against system root CA store
    and returns (expiry_utc: datetime, sha256_fingerprint_hex: str) of the served certificate.
    Raises RuntimeError or socket/ssl errors on failure.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        with socket.create_connection((host, port), timeout=5) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                der_cert = ssock.getpeercert(binary_form=True)
                if not der_cert:
                    raise RuntimeError(f"Server at {host}:{port} did not present a TLS certificate.")
    except Exception as exc:
        raise RuntimeError(
            f"Failed to fetch live TLS certificate from {host}:{port}: {exc}"
        ) from exc

    cert = x509.load_der_x509_certificate(der_cert)
    fingerprint = hashlib.sha256(der_cert).hexdigest()
    return cert.not_valid_after_utc, fingerprint


def get_pem_cert_info(cert_pem: str) -> tuple[datetime, str]:
    """
    Parses a PEM certificate string and returns (expiry_utc: datetime, sha256_fingerprint_hex: str).
    """
    cert = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
    der_bytes = cert.public_bytes(Encoding.DER)
    fingerprint = hashlib.sha256(der_bytes).hexdigest()
    return cert.not_valid_after_utc, fingerprint


if __name__ == "__main__":
    # Small runnable check against live https://localhost
    print("Testing get_live_cert_info against localhost:443...")
    exp, fp = get_live_cert_info("localhost", 443)
    assert isinstance(exp, datetime)
    assert len(fp) == 64
    print("get_live_cert_info OK -> Expiry:", exp, "SHA256:", fp)

    with open("./local.crt", "r", encoding="utf-8") as f:
        pem_text = f.read()
    pem_exp, pem_fp = get_pem_cert_info(pem_text)
    print("get_pem_cert_info OK -> Expiry:", pem_exp, "SHA256:", pem_fp)
    assert exp == pem_exp and fp == pem_fp, "Live served cert must match local.crt on disk"
    print("Live cert matches local.crt!")
