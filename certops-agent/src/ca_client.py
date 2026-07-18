"""
Certificate Authority client for issuing certificates via Smallstep (step-ca).
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def _find_step_binary() -> str:
    binary = shutil.which("step")
    if binary:
        return binary

    # Check known WinGet default path on Windows
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if local_appdata:
        winget_path = Path(local_appdata) / "Microsoft" / "WinGet" / "Packages"
        if winget_path.exists():
            for exe in winget_path.glob("Smallstep.step_*/step_*/bin/step.exe"):
                return str(exe)

    raise RuntimeError(
        "Could not find 'step' executable in PATH or standard WinGet packages directory."
    )


def issue_certificate(
    subject: str,
    password_file: str,
    ca_url: str | None = None,
    fingerprint: str | None = None,
) -> tuple[str, str]:
    """
    Issues a new certificate and private key from step-ca for the given subject.
    Returns (certificate_pem, private_key_pem).
    Raises RuntimeError if issuance fails.
    """
    step_bin = _find_step_binary()
    abs_password_file = str(Path(password_file).resolve())

    if not Path(abs_password_file).exists():
        raise RuntimeError(f"CA password file not found at '{abs_password_file}'")

    with tempfile.TemporaryDirectory() as tmpdir:
        cert_path = os.path.join(tmpdir, "issued.crt")
        key_path = os.path.join(tmpdir, "issued.key")

        cmd = [
            step_bin,
            "ca",
            "certificate",
            subject,
            cert_path,
            key_path,
            "--provisioner-password-file",
            abs_password_file,
            "--force",
        ]
        if ca_url:
            cmd.extend(["--ca-url", ca_url])

        root_file = os.getenv("STEP_CA_ROOT_FILE")
        if root_file and os.path.exists(root_file):
            cmd.extend(["--root", root_file])

        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise RuntimeError(
                f"step-ca certificate issuance failed (exit {res.returncode}):\n"
                f"Stdout: {res.stdout}\nStderr: {res.stderr}"
            )

        if not os.path.exists(cert_path) or not os.path.exists(key_path):
            raise RuntimeError(
                "step ca certificate command succeeded but did not write expected output files."
            )

        with open(cert_path, "r", encoding="utf-8") as f:
            cert_pem = f.read()
        with open(key_path, "r", encoding="utf-8") as f:
            key_pem = f.read()

        return cert_pem, key_pem


if __name__ == "__main__":
    # Small runnable check against live step-ca
    print("Testing issue_certificate for localhost...")
    c, k = issue_certificate(
        subject="localhost",
        password_file="./pass.txt",
        ca_url="https://localhost:8443",
    )
    assert "-----BEGIN CERTIFICATE-----" in c
    assert "-----BEGIN EC PRIVATE KEY-----" in k or "-----BEGIN PRIVATE KEY-----" in k
    print("issue_certificate OK. Lengths:", len(c), len(k))
