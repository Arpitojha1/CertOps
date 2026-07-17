"""
End-to-End Multi-Certificate Verification Test against Live HashiCorp Vault and Azure Key Vault.

Tests:
1. Setup of 6 self-signed test certificates (3 per vault: clearly due, edge case due, clearly not due).
2. Direct vault baseline recording (raw unrounded timestamps & versions).
3. Execution of real main.run_renewal_loop().
4. Direct vault verification showing due certs renewed (new version & later expiry) and
   not-due certs remain byte-for-byte unchanged.
5. Error isolation / failure injection test proving one vault failure does not stop the other.
"""

import datetime
import os
import sys
import unittest
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from dotenv import load_dotenv

# Ensure package root and src are in sys.path
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))
_sibling = _root.parent / "certops-dashboard"
if _sibling.exists() and str(_sibling) not in sys.path:
    sys.path.insert(0, str(_sibling))

import azurekeyvault
import main
import vault_client


def _build_self_signed_cert(
    common_name: str, expiry_utc: datetime.datetime
) -> tuple[str, str]:
    """
    Generates a self-signed X.509 certificate with a specified expiry timestamp.
    Returns (cert_pem, private_key_pem_pkcs8).
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
        )
        .not_valid_after(expiry_utc)
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    return cert_pem, key_pem


LIVE = os.getenv("CERTOPS_RUN_LIVE") == "1"


@unittest.skipUnless(LIVE, "Live integration test; set CERTOPS_RUN_LIVE=1 to run in a sandbox")
class TestMultiCertLoopLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_env = os.environ.copy()
        load_dotenv()
        os.environ["RENEWAL_THRESHOLD_DAYS"] = "0.8"
        os.environ["VAULT_RENEWAL_THRESHOLD_DAYS"] = "0.8"
        os.environ["AZURE_RENEWAL_THRESHOLD_DAYS"] = "0.8"
        cls.threshold_days = 0.8
        cls.hc_client = vault_client.HashiCorpVaultClient.from_env()
        cls.az_client = azurekeyvault.AzureKeyVaultClient.from_env()

    @classmethod
    def tearDownClass(cls):
        os.environ.clear()
        os.environ.update(cls._orig_env)

    def test_multi_cert_loop_and_error_isolation(self):
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        print("\n" + "=" * 70)
        print("PHASE 1: SEEDING 6 TEST CERTIFICATES ACROSS HASHICORP & AZURE VAULTS")
        print(f"Configured RENEWAL_THRESHOLD_DAYS: {self.threshold_days}")
        print("=" * 70)

        # 1. Clearly due (well inside threshold): remaining = 0.2 days (4.8 hours)
        expiry_due = now_utc + datetime.timedelta(days=0.2)
        # 2. Edge case (at threshold boundary <= threshold_days): remaining = 0.8 days (19.2 hours)
        expiry_edge = now_utc + datetime.timedelta(days=0.8)
        # 3. Clearly not due (well outside threshold): remaining = 30 days
        expiry_not_due = now_utc + datetime.timedelta(days=30.0)

        cert_specs = [
            ("hc-due-01", self.hc_client, expiry_due, "CLEARLY DUE"),
            ("hc-edge-01", self.hc_client, expiry_edge, "EDGE CASE DUE (<= threshold)"),
            ("hc-notdue-01", self.hc_client, expiry_not_due, "CLEARLY NOT DUE"),
            ("az-due-01", self.az_client, expiry_due, "CLEARLY DUE"),
            ("az-edge-01", self.az_client, expiry_edge, "EDGE CASE DUE (<= threshold)"),
            ("az-notdue-01", self.az_client, expiry_not_due, "CLEARLY NOT DUE"),
        ]

        # Seed all 6 certs
        for cname, client, expiry, label in cert_specs:
            cert_pem, key_pem = _build_self_signed_cert(cname, expiry)
            client.write_certificate(cname, cert_pem, key_pem)

        # Record baseline directly from vaults
        print("\n" + "=" * 70)
        print("PHASE 2: DIRECT VAULT BASELINE RECORDING (RAW FULL-PRECISION)")
        print("=" * 70)
        baseline = {"hashicorp": {}, "azure": {}}
        for cname, client, _, label in cert_specs:
            info = client.get_certificate(cname)
            v_name = client.name
            baseline[v_name][cname] = {
                "version": info["version"],
                "expiry_utc": info["expiry_utc"],
            }
            print(
                f"[{v_name:<10}] {cname:<14} | Label: {label:<28} | "
                f"Version: {info['version']} | Raw Expiry: {info['expiry_utc'].isoformat()}"
            )

        # Run multi-cert loop
        print("\n" + "=" * 70)
        print("PHASE 3: EXECUTING main.run_renewal_loop()")
        print("=" * 70)
        summary = main.run_renewal_loop()
        self.assertIsInstance(summary, main.RenewalSummary)

        # Verify post-run directly from vaults
        print("\n" + "=" * 70)
        print("PHASE 4: DIRECT VAULT POST-RUN VERIFICATION & ASSERTIONS")
        print("=" * 70)
        for cname, client, _, label in cert_specs:
            v_name = client.name
            pre = baseline[v_name][cname]
            post = client.get_certificate(cname)

            if "NOT DUE" in label:
                # Must be unchanged
                self.assertEqual(
                    post["version"],
                    pre["version"],
                    f"Not-due cert '{cname}' version changed unexpectedly!",
                )
                self.assertEqual(
                    post["expiry_utc"],
                    pre["expiry_utc"],
                    f"Not-due cert '{cname}' expiry changed unexpectedly!",
                )
                print(
                    f"PASS: [{v_name:<10}] {cname:<14} UNCHANGED | "
                    f"Version: {post['version']} | Raw Expiry: {post['expiry_utc'].isoformat()}"
                )
            else:
                # Must be renewed
                self.assertNotEqual(
                    post["version"],
                    pre["version"],
                    f"Due cert '{cname}' version did not change!",
                )
                self.assertGreater(
                    post["expiry_utc"],
                    pre["expiry_utc"],
                    f"Due cert '{cname}' expiry is not strictly later than baseline!",
                )
                print(
                    f"PASS: [{v_name:<10}] {cname:<14} RENEWED   | "
                    f"New Version: {post['version']} | New Raw Expiry: {post['expiry_utc'].isoformat()}"
                )

        # Failure injection test (Bidirectional error isolation)
        print("\n" + "=" * 70)
        print("PHASE 5: BIDIRECTIONAL ERROR ISOLATION & FAILURE INJECTION TEST")
        print("=" * 70)

        # Direction 1: HashiCorp Vault unreachable -> Azure Key Vault processes correctly
        print("\n--- Phase 5A: Direction 1 (HashiCorp Down / Azure Up) ---")
        expiry_fi = now_utc + datetime.timedelta(days=0.2)
        cert_pem, key_pem = _build_self_signed_cert("az-fi-due-01", expiry_fi)
        self.az_client.write_certificate("az-fi-due-01", cert_pem, key_pem)
        pre_az_fi = self.az_client.get_certificate("az-fi-due-01")

        original_hc_addr = os.environ.get("VAULT_ADDR", "")
        try:
            os.environ["VAULT_ADDR"] = "http://localhost:19999"  # Unreachable address
            print("Injected bad VAULT_ADDR='http://localhost:19999'. Running loop...")
            fi_summary_1 = main.run_renewal_loop()
            self.assertGreaterEqual(
                fi_summary_1["hashicorp"]["failed"],
                1,
                "Expected HashiCorp Vault failure count >= 1",
            )
            self.assertEqual(
                fi_summary_1["azure"]["failed"],
                0,
                "Azure Key Vault should have 0 failures despite HashiCorp failure",
            )
            self.assertGreaterEqual(
                fi_summary_1["azure"]["succeeded"],
                1,
                "Azure Key Vault should have successfully renewed due cert while HashiCorp was unreachable",
            )
            post_az_fi = self.az_client.get_certificate("az-fi-due-01")
            self.assertNotEqual(
                post_az_fi["version"],
                pre_az_fi["version"],
                "Expected az-fi-due-01 to be renewed during Direction 1 test",
            )
            print("PASS: Direction 1 verified. Unreachable HashiCorp Vault did not break Azure Key Vault loop.")
        finally:
            if original_hc_addr:
                os.environ["VAULT_ADDR"] = original_hc_addr
            else:
                os.environ.pop("VAULT_ADDR", None)

        # Direction 2: Azure Key Vault unreachable -> HashiCorp Vault processes correctly
        print("\n--- Phase 5B: Direction 2 (Azure Down / HashiCorp Up) ---")
        cert_pem, key_pem = _build_self_signed_cert("hc-fi-due-01", expiry_fi)
        self.hc_client.write_certificate("hc-fi-due-01", cert_pem, key_pem)
        pre_hc_fi = self.hc_client.get_certificate("hc-fi-due-01")

        original_az_url = os.environ.get("AZURE_KEYVAULT_URL", "")
        try:
            os.environ["AZURE_KEYVAULT_URL"] = "https://localhost:19999"  # Unreachable address
            print("Injected bad AZURE_KEYVAULT_URL='https://localhost:19999'. Running loop...")
            fi_summary_2 = main.run_renewal_loop()
            self.assertGreaterEqual(
                fi_summary_2["azure"]["failed"],
                1,
                "Expected Azure Key Vault failure count >= 1",
            )
            self.assertEqual(
                fi_summary_2["hashicorp"]["failed"],
                0,
                "HashiCorp Vault should have 0 failures despite Azure failure",
            )
            self.assertGreaterEqual(
                fi_summary_2["hashicorp"]["succeeded"],
                1,
                "HashiCorp Vault should have successfully renewed due cert while Azure was unreachable",
            )
            post_hc_fi = self.hc_client.get_certificate("hc-fi-due-01")
            self.assertNotEqual(
                post_hc_fi["version"],
                pre_hc_fi["version"],
                "Expected hc-fi-due-01 to be renewed during Direction 2 test",
            )
            print("PASS: Direction 2 verified. Unreachable Azure Key Vault did not break HashiCorp Vault loop.")
        finally:
            if original_az_url:
                os.environ["AZURE_KEYVAULT_URL"] = original_az_url
            else:
                os.environ.pop("AZURE_KEYVAULT_URL", None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
