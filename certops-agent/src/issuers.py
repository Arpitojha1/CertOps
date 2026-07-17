"""
CA-agnostic Certificate Issuer abstractions for CertOps.
Provides a unified CAIssuer interface implemented by StepCAIssuer and ACMEIssuer.
"""
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from src import ca_client


class CAIssuer:
    """Abstract base protocol for certificate issuers."""

    def issue_certificate(self, subject: str, **kwargs: Any) -> tuple[str, str]:
        """
        Issue a certificate and private key for the given subject.
        Returns (certificate_pem, private_key_pem).
        """
        raise NotImplementedError("CAIssuer implementations must define issue_certificate()")


class StepCAIssuer(CAIssuer):
    """Issues certificates via step-ca provisioners."""

    def __init__(
        self,
        password_file: str,
        ca_url: str | None = None,
        fingerprint: str | None = None,
    ):
        self.password_file = password_file
        self.ca_url = ca_url
        self.fingerprint = fingerprint

    def issue_certificate(self, subject: str, **kwargs: Any) -> tuple[str, str]:
        return ca_client.issue_certificate(
            subject=subject,
            password_file=self.password_file,
            ca_url=self.ca_url,
            fingerprint=self.fingerprint,
        )


class ACMEIssuer(CAIssuer):
    """
    Issues certificates via any ACME-compliant Certificate Authority
    (e.g., Let's Encrypt, step-ca ACME provisioner) using the ACME protocol.
    """

    def __init__(
        self,
        directory_url: str,
        contact_email: str | None = None,
        standalone: bool = True,
        webroot: str | None = None,
        http_listen: str | None = None,
    ):
        self.directory_url = directory_url
        self.contact_email = contact_email
        self.standalone = standalone
        self.webroot = webroot
        self.http_listen = http_listen

    def issue_certificate(self, subject: str, **kwargs: Any) -> tuple[str, str]:
        step_bin = ca_client._find_step_binary()

        with tempfile.TemporaryDirectory() as tmpdir:
            cert_path = os.path.join(tmpdir, "acme.crt")
            key_path = os.path.join(tmpdir, "acme.key")

            cmd = [
                step_bin,
                "ca",
                "certificate",
                subject,
                cert_path,
                key_path,
                "--acme",
                self.directory_url,
                "--force",
            ]

            if self.contact_email:
                cmd.extend(["--contact", self.contact_email])

            if self.webroot:
                cmd.extend(["--webroot", self.webroot])
            elif self.standalone:
                cmd.append("--standalone")
                if self.http_listen:
                    cmd.extend(["--http-listen", self.http_listen])

            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode != 0:
                raise RuntimeError(
                    f"ACME certificate issuance failed (exit {res.returncode}):\n"
                    f"Stdout: {res.stdout}\nStderr: {res.stderr}"
                )

            if not os.path.exists(cert_path) or not os.path.exists(key_path):
                raise RuntimeError("ACME issuance command succeeded but did not write expected output files.")

            with open(cert_path, "r", encoding="utf-8") as f:
                cert_pem = f.read()
            with open(key_path, "r", encoding="utf-8") as f:
                key_pem = f.read()

            return cert_pem, key_pem


def get_issuer(issuer_type: str = "step-ca", **kwargs: Any) -> CAIssuer:
    """Factory to instantiate the configured CAIssuer."""
    normalized = issuer_type.lower().strip()
    if normalized in ("step-ca", "stepca", "smallstep"):
        password_file = kwargs.get("password_file") or os.getenv("STEP_CA_PASSWORD_FILE", "./pass.txt")
        ca_url = kwargs.get("ca_url") or os.getenv("STEP_CA_URL", "https://localhost:8443")
        fingerprint = kwargs.get("fingerprint") or os.getenv("STEP_CA_FINGERPRINT")
        return StepCAIssuer(
            password_file=password_file,
            ca_url=ca_url,
            fingerprint=fingerprint,
        )
    elif normalized == "acme":
        directory_url = kwargs.get("directory_url") or os.getenv("ACME_DIRECTORY_URL")
        if not directory_url:
            raise ValueError("ACMEIssuer requires 'directory_url' keyword argument or ACME_DIRECTORY_URL env var.")
        return ACMEIssuer(
            directory_url=directory_url,
            contact_email=kwargs.get("contact_email") or os.getenv("ACME_CONTACT_EMAIL"),
            standalone=kwargs.get("standalone", True),
            webroot=kwargs.get("webroot") or os.getenv("ACME_WEBROOT"),
            http_listen=kwargs.get("http_listen") or os.getenv("ACME_HTTP_LISTEN"),
        )
    else:
        raise ValueError(f"Unsupported issuer type: {issuer_type}")
