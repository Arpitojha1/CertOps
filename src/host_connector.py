"""
Host connectors for discovering, reading, and deploying certificates directly on VMs/hosts.
Includes abstract base class HostConnector, SSHHostConnector (Linux/nginx), and scaffolded WinRMHostConnector (Windows/IIS).
"""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import base64
import json
import uuid

import paramiko
import winrm
from cryptography.hazmat.primitives.serialization import NoEncryption, load_pem_private_key, pkcs12
from cryptography.x509 import load_pem_x509_certificate

if __package__ is None or __package__ == "":
    import db
    import verify
else:
    from . import db, verify


logger = logging.getLogger(__name__)


@dataclass
class CertMetadata:
    cert_id: str
    name: str
    path: str
    expiry_utc: datetime
    common_name: str | None = None
    key_path: str | None = None


@dataclass
class CertData:
    cert_id: str
    cert_pem: str
    expiry_utc: datetime
    common_name: str | None = None
    private_key_pem: str | None = None
    key_path: str | None = None


@dataclass
class ReloadResult:
    success: bool
    output: str


class HostConnector(ABC):
    name: str

    @abstractmethod
    def discover_certificates(self) -> list[CertMetadata]:
        """Scan known config/cert paths on the host. Returns metadata only, no private key material."""

    @abstractmethod
    def read_certificate(self, cert_id: str) -> CertData:
        """Fetch the current cert (and only the cert — never private keys) for inspection/expiry check."""

    @abstractmethod
    def deploy_certificate(self, cert_id: str, cert_data: CertData) -> None:
        """Write the renewed cert to the host. Must use write-then-rename. Does NOT reload the service."""

    @abstractmethod
    def trigger_reload(self, cert_id: str | None = None) -> ReloadResult:
        """Explicit, separate step. Only called after user confirmation. Returns success/failure + service output."""


class SSHHostConnector(HostConnector):
    name = "ssh_host"

    def __init__(
        self,
        hostname: str = "localhost",
        port: int = 22,
        username: str = "root",
        password: str | None = None,
        key_filename: str | None = None,
        nginx_conf_dir: str = "/etc/nginx/conf.d",
        renewal_threshold_days: float | None = None,
    ) -> None:
        self.hostname = hostname
        self.port = port
        self.username = username
        self.password = password
        self.key_filename = key_filename
        self.nginx_conf_dir = nginx_conf_dir
        self.renewal_threshold_days = renewal_threshold_days

    @classmethod
    def from_env(cls, renewal_threshold_days: float | None = None) -> "SSHHostConnector":
        if renewal_threshold_days is None:
            thresh_str = os.getenv("SSH_RENEWAL_THRESHOLD_DAYS")
            renewal_threshold_days = float(thresh_str) if thresh_str else None
        return cls(
            hostname=os.getenv("SSH_HOST", "localhost"),
            port=int(os.getenv("SSH_PORT", "2222")),
            username=os.getenv("SSH_USERNAME", "root"),
            password=os.getenv("SSH_PASSWORD", "certops"),
            key_filename=os.getenv("SSH_KEY_FILE") or None,
            nginx_conf_dir=os.getenv("SSH_NGINX_CONF_DIR", "/etc/nginx/conf.d"),
            renewal_threshold_days=renewal_threshold_days,
        )

    @classmethod
    def from_config(cls, config: dict[str, Any], renewal_threshold_days: float | None = None) -> "SSHHostConnector":
        return cls(
            hostname=config.get("hostname", "localhost"),
            port=int(config.get("port", 2222)),
            username=config.get("username", "root"),
            password=config.get("password") or None,
            key_filename=config.get("key_filename") or None,
            nginx_conf_dir=config.get("nginx_conf_dir", "/etc/nginx/conf.d"),
            renewal_threshold_days=renewal_threshold_days,
        )

    def _get_ssh_client(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.hostname,
            port=self.port,
            username=self.username,
            password=self.password,
            key_filename=self.key_filename,
            timeout=10,
        )
        return client

    def _exec_command(self, client: paramiko.SSHClient, cmd: str) -> tuple[int, str, str]:
        stdin, stdout, stderr = client.exec_command(cmd)
        exit_status = stdout.channel.recv_exit_status()
        out_str = stdout.read().decode("utf-8", errors="replace")
        err_str = stderr.read().decode("utf-8", errors="replace")
        return exit_status, out_str, err_str

    @db.log_connector_event("discovered")
    def discover_certificates(self) -> list[CertMetadata]:
        """
        Scans Nginx configuration directories for ssl_certificate directives,
        reads the public certificates over SFTP/SSH, and returns metadata.
        Never touches private keys.
        """
        client = self._get_ssh_client()
        try:
            # Check both nginx_conf_dir and /etc/nginx/sites-enabled if they exist
            cmd = (
                f"find {self.nginx_conf_dir} /etc/nginx/sites-enabled /etc/nginx/conf.d -maxdepth 3 -name '*.conf' -exec grep -HnE '^[[:space:]]*ssl_certificate[[:space:]]+[^;]+;' {{}} + 2>/dev/null || "
                f"grep -E '^[[:space:]]*ssl_certificate[[:space:]]+[^;]+;' {self.nginx_conf_dir}/*.conf 2>/dev/null"
            )
            exit_code, out, _ = self._exec_command(client, cmd)
            cert_paths: set[str] = set()
            key_map: dict[str, str] = {}

            if out:
                for line in out.splitlines():
                    parts = line.strip().split()
                    for idx, token in enumerate(parts):
                        if token == "ssl_certificate" and idx + 1 < len(parts):
                            c_path = parts[idx + 1].rstrip(";")
                            cert_paths.add(c_path)

            # Also discover matching ssl_certificate_key directives if present
            cmd_key = (
                f"grep -rE '^[[:space:]]*ssl_certificate_key[[:space:]]+[^;]+;' "
                f"{self.nginx_conf_dir} /etc/nginx/sites-enabled 2>/dev/null || "
                f"grep -rE '^[[:space:]]*ssl_certificate_key[[:space:]]+[^;]+;' {self.nginx_conf_dir} 2>/dev/null"
            )
            _, out_key, _ = self._exec_command(client, cmd_key)
            key_paths: list[str] = []
            if out_key:
                for line in out_key.splitlines():
                    parts = line.strip().split()
                    for idx, token in enumerate(parts):
                        if token == "ssl_certificate_key" and idx + 1 < len(parts):
                            k_path = parts[idx + 1].rstrip(";")
                            key_paths.append(k_path)

            results: list[CertMetadata] = []
            sftp = client.open_sftp()
            try:
                for idx, c_path in enumerate(sorted(cert_paths)):
                    try:
                        with sftp.open(c_path, "r") as f:
                            cert_pem = f.read().decode("utf-8")
                        expiry_utc, _ = verify.get_pem_cert_info(cert_pem)
                        k_path = key_paths[idx] if idx < len(key_paths) else None
                        results.append(
                            CertMetadata(
                                cert_id=c_path,
                                name=os.path.basename(c_path),
                                path=c_path,
                                expiry_utc=expiry_utc,
                                common_name=os.path.basename(c_path),
                                key_path=k_path,
                            )
                        )
                    except Exception as exc:
                        logger.warning("Failed to inspect certificate '%s' on host '%s': %s", c_path, self.hostname, exc)
            finally:
                sftp.close()
            return results
        finally:
            client.close()

    def read_certificate(self, cert_id: str) -> CertData:
        """
        Reads the public certificate PEM from the host at cert_id.
        Never touches private keys.
        """
        client = self._get_ssh_client()
        try:
            sftp = client.open_sftp()
            try:
                with sftp.open(cert_id, "r") as f:
                    cert_pem = f.read().decode("utf-8")
            finally:
                sftp.close()

            expiry_utc, _ = verify.get_pem_cert_info(cert_pem)
            return CertData(
                cert_id=cert_id,
                cert_pem=cert_pem,
                expiry_utc=expiry_utc,
                common_name=os.path.basename(cert_id),
                private_key_pem=None,
            )
        finally:
            client.close()

    @db.log_connector_event("deployed_pending_reload")
    def deploy_certificate(self, cert_id: str, cert_data: CertData) -> None:
        """
        Writes renewed certificate (and optional private key) to the remote host using write-then-rename.
        Does NOT reload Nginx.
        """
        client = self._get_ssh_client()
        try:
            sftp = client.open_sftp()
            try:
                tmp_cert = f"{cert_id}.tmp"
                with sftp.open(tmp_cert, "w") as f:
                    f.write(cert_data.cert_pem)

                # Atomic rename
                exit_code, out, err = self._exec_command(client, f"mv -f {tmp_cert} {cert_id}")
                if exit_code != 0:
                    raise RuntimeError(f"Failed to atomically deploy cert to '{cert_id}': {err or out}")

                if cert_data.private_key_pem and cert_data.key_path:
                    tmp_key = f"{cert_data.key_path}.tmp"
                    with sftp.open(tmp_key, "w") as f:
                        f.write(cert_data.private_key_pem)
                    exit_code, out, err = self._exec_command(client, f"mv -f {tmp_key} {cert_data.key_path}")
                    if exit_code != 0:
                        raise RuntimeError(f"Failed to atomically deploy private key to '{cert_data.key_path}': {err or out}")
            finally:
                sftp.close()
        finally:
            client.close()

    @db.log_connector_event("reload_confirmed")
    def trigger_reload(self, cert_id: str | None = None) -> ReloadResult:
        """
        Explicit step to reload Nginx after config validation.
        Fails loudly if 'nginx -t' fails.
        """
        client = self._get_ssh_client()
        try:
            exit_code, out, err = self._exec_command(client, "nginx -t")
            if exit_code != 0:
                logger.error("nginx -t failed before reload: %s %s", out, err)
                return ReloadResult(
                    success=False,
                    output=f"nginx -t FAILED (exit {exit_code}):\n{out}\n{err}",
                )

            r_code, r_out, r_err = self._exec_command(client, "nginx -s reload")
            success = (r_code == 0)
            combined = f"{out}\n{err}\n--- reload ---\n{r_out}\n{r_err}".strip()
            return ReloadResult(success=success, output=combined)
        finally:
            client.close()


class WinRMHostConnector(HostConnector):
    """
    WinRM connector for Windows/IIS certificate discovery, PFX deployment, and targeted app pool recycle.
    Supports NTLM (dev/test) and Kerberos (prod) via auth_type.
    """
    name = "winrm_host"

    def __init__(
        self,
        hostname: str = "localhost",
        port: int = 5985,
        username: str = "Administrator",
        password: str = "",
        auth_type: str = "ntlm",
        iis_site_name: str = "Default Web Site",
        renewal_threshold_days: float | None = None,
    ) -> None:
        self.hostname = hostname
        self.port = port
        self.username = username
        self.password = password
        self.auth_type = auth_type
        self.iis_site_name = iis_site_name
        self.renewal_threshold_days = renewal_threshold_days

    @classmethod
    def from_env(cls, renewal_threshold_days: float | None = None) -> "WinRMHostConnector":
        if renewal_threshold_days is None:
            thresh_str = os.getenv("WINRM_RENEWAL_THRESHOLD_DAYS")
            renewal_threshold_days = float(thresh_str) if thresh_str else None
        return cls(
            hostname=os.getenv("WINRM_HOST", "localhost"),
            port=int(os.getenv("WINRM_PORT", "5985")),
            username=os.getenv("WINRM_USERNAME", "Administrator"),
            password=os.getenv("WINRM_PASSWORD", ""),
            auth_type=os.getenv("WINRM_AUTH_TYPE") or os.getenv("WINRM_AUTH", "ntlm"),
            iis_site_name=os.getenv("WINRM_IIS_SITE_NAME", "Default Web Site"),
            renewal_threshold_days=renewal_threshold_days,
        )

    def _run_ps(self, script: str) -> tuple[int, str, str]:
        endpoint = f"http://{self.hostname}:{self.port}/wsman"
        session = winrm.Session(
            endpoint,
            auth=(self.username, self.password),
            transport=self.auth_type,
            server_cert_validation="ignore",
            message_encryption="auto",
        )
        resp = session.run_ps(script)
        out_str = resp.std_out.decode("utf-8", errors="replace") if resp.std_out else ""
        err_str = resp.std_err.decode("utf-8", errors="replace") if resp.std_err else ""
        return resp.status_code, out_str, err_str

    @db.log_connector_event("discovered")
    def discover_certificates(self) -> list[CertMetadata]:
        ps_script = """
$ErrorActionPreference = 'Stop'
Import-Module WebAdministration -ErrorAction SilentlyContinue
$results = @()
$bindings = Get-ChildItem -Path "IIS:\\SslBindings" -ErrorAction SilentlyContinue
if (-not $bindings) {
    $bindings = Get-WebBinding -Protocol https -ErrorAction SilentlyContinue
}
foreach ($b in $bindings) {
    $thumb = $b.Thumbprint
    if ($thumb) {
        $cItem = Get-Item "Cert:\\LocalMachine\\My\\$thumb" -ErrorAction SilentlyContinue
        if ($cItem) {
            $results += [PSCustomObject]@{
                Thumbprint = $cItem.Thumbprint
                Subject = $cItem.Subject
                NotAfterUtc = $cItem.NotAfter.ToUniversalTime().ToString("o")
            }
        }
    }
}
$results | ConvertTo-Json -Compress
"""
        code, out, err = self._run_ps(ps_script)
        if code != 0:
            logger.warning("Failed to discover certificates on WinRM host '%s': %s", self.hostname, err or out)
            return []

        cleaned = out.strip()
        if not cleaned:
            return []

        try:
            parsed = json.loads(cleaned)
        except Exception as exc:
            logger.warning("Failed to parse JSON from WinRM discovery output: %s", exc)
            return []

        items = parsed if isinstance(parsed, list) else [parsed]
        results: list[CertMetadata] = []
        for item in items:
            if not isinstance(item, dict) or "Thumbprint" not in item:
                continue
            cid = item["Thumbprint"]
            dt_str = item.get("NotAfterUtc", "")
            try:
                expiry_utc = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            except Exception:
                continue
            results.append(
                CertMetadata(
                    cert_id=cid,
                    name=cid,
                    path=f"Cert:\\LocalMachine\\My\\{cid}",
                    expiry_utc=expiry_utc,
                    common_name=item.get("Subject", cid),
                    key_path=None,
                )
            )
        return results

    def read_certificate(self, cert_id: str) -> CertData:
        """
        Reads public certificate DER from Cert:\\LocalMachine\\My and returns public PEM.
        Never touches private keys.
        """
        ps_script = f"""
$ErrorActionPreference = 'Stop'
$cert = Get-Item "Cert:\\LocalMachine\\My\\{cert_id}" -ErrorAction Stop
[System.Convert]::ToBase64String($cert.RawData, [System.Base64FormattingOptions]::InsertLineBreaks)
"""
        code, out, err = self._run_ps(ps_script)
        if code != 0:
            raise RuntimeError(f"Failed to read certificate '{cert_id}' over WinRM: {err or out}")
        b64_str = out.strip()
        cert_pem = f"-----BEGIN CERTIFICATE-----\n{b64_str}\n-----END CERTIFICATE-----\n"
        expiry_utc, _ = verify.get_pem_cert_info(cert_pem)
        return CertData(
            cert_id=cert_id,
            cert_pem=cert_pem,
            expiry_utc=expiry_utc,
            common_name=cert_id,
            private_key_pem=None,
        )

    @db.log_connector_event("deployed_pending_reload")
    def deploy_certificate(self, cert_id: str, cert_data: CertData) -> None:
        """
        Safely imports renewed PFX into Cert:\\LocalMachine\\My, guarantees temp PFX cleanup,
        and flips IIS HTTPS binding without deleting the old certificate.
        """
        if not cert_data.private_key_pem:
            raise ValueError("deploy_certificate on Windows/IIS requires private_key_pem to import PFX.")

        cert_obj = load_pem_x509_certificate(cert_data.cert_pem.encode("utf-8"))
        key_obj = load_pem_private_key(cert_data.private_key_pem.encode("utf-8"), password=None)
        pfx_bytes = pkcs12.serialize_key_and_certificates(
            name=b"certops",
            key=key_obj,
            cert=cert_obj,
            cas=None,
            encryption_algorithm=NoEncryption(),
        )
        pfx_b64 = base64.b64encode(pfx_bytes).decode("ascii")
        temp_filename = f"certops_deploy_{uuid.uuid4().hex}.pfx"

        ps_script = f"""
$ErrorActionPreference = 'Stop'
$pfxB64 = '{pfx_b64}'
$tempPath = "$env:TEMP\\{temp_filename}"
try {{
    $bytes = [System.Convert]::FromBase64String($pfxB64)
    [System.IO.File]::WriteAllBytes($tempPath, $bytes)
    $imported = Import-PfxCertificate -FilePath $tempPath -CertStoreLocation "Cert:\\LocalMachine\\My" -Exportable -ErrorAction Stop
    $newThumb = $imported.Thumbprint
    if (-not $newThumb) {{
        throw "Import-PfxCertificate failed to return a Thumbprint."
    }}
    Import-Module WebAdministration -ErrorAction SilentlyContinue
    $binding = Get-WebBinding -Name '{self.iis_site_name}' -Protocol https -ErrorAction SilentlyContinue
    if ($binding) {{
        $binding.RemoveSslCertificate()
        $binding.AddSslCertificate($newThumb, "my")
    }}
    Write-Output "IMPORTED_THUMBPRINT=$newThumb"
}} finally {{
    if (Test-Path $tempPath) {{
        Remove-Item -Path $tempPath -Force -ErrorAction SilentlyContinue
    }}
}}
"""
        code, out, err = self._run_ps(ps_script)
        if code != 0:
            raise RuntimeError(f"Failed to deploy certificate '{cert_id}' over WinRM: {err or out}")

    @db.log_connector_event("reload_confirmed")
    def trigger_reload(self, cert_id: str | None = None) -> ReloadResult:
        """
        Executes targeted application pool recycle for the configured IIS site.
        Avoids server-wide iisreset to minimize blast radius.
        """
        ps_script = f"""
$ErrorActionPreference = 'Stop'
Import-Module WebAdministration -ErrorAction Stop
$site = Get-Website -Name '{self.iis_site_name}' -ErrorAction Stop
$appPool = $site.applicationPool
Restart-WebAppPool -Name $appPool
Write-Output "Recycled AppPool: $appPool for site: {self.iis_site_name}"
"""
        code, out, err = self._run_ps(ps_script)
        success = (code == 0)
        output = out if success else f"AppPool recycle FAILED (exit {code}):\n{out}\n{err}"
        return ReloadResult(success=success, output=output.strip())


if __name__ == "__main__":
    # Self-test interface conformance
    assert issubclass(SSHHostConnector, HostConnector)
    assert issubclass(WinRMHostConnector, HostConnector)
    print("host_connector.py interface conformance verified.")
