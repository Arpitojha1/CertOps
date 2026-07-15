"""
Smoke tests for CertOps Phase 1 core loop against real running services
(Vault, step-ca, Nginx).
"""

import os
import sys
import unittest
from pathlib import Path

# Add src/ to sys.path so modules can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from src import main
from src import verify



LIVE = os.getenv("CERTOPS_RUN_LIVE") == "1"


@unittest.skipUnless(LIVE, "Live integration test; set CERTOPS_RUN_LIVE=1 to run in a sandbox")
class TestCoreLoopSmoke(unittest.TestCase):
    def setUp(self):
        self._orig_threshold = os.environ.get("RENEWAL_THRESHOLD_DAYS")

    def tearDown(self):
        if self._orig_threshold is not None:
            os.environ["RENEWAL_THRESHOLD_DAYS"] = self._orig_threshold
        else:
            os.environ.pop("RENEWAL_THRESHOLD_DAYS", None)

    def test_01_core_loop_renewal_triggered_and_verified(self):
        """
        When RENEWAL_THRESHOLD_DAYS is large enough, run_renewal_loop() must
        perform full issuance, Vault write/read, atomic disk deploy, Nginx reload,
        and live TLS certificate verification.
        """
        os.environ["RENEWAL_THRESHOLD_DAYS"] = "365"  # Ensure renewal is triggered
        renewed = main.run_renewal_loop()
        self.assertTrue(renewed, "Expected renewal loop to return True when within threshold")

        # Double-check live TLS endpoint directly
        expiry, fp = verify.get_live_cert_info("localhost", 443)
        self.assertEqual(len(fp), 64)
        self.assertIsNotNone(expiry)

    def test_02_core_loop_no_renewal_when_outside_threshold(self):
        """
        When certificate remaining lifetime is greater than RENEWAL_THRESHOLD_DAYS,
        run_renewal_loop() must exit cleanly without renewal.
        """
        os.environ["RENEWAL_THRESHOLD_DAYS"] = "0.01"  # ~14 minutes
        renewed = main.run_renewal_loop()
        self.assertFalse(
            renewed, "Expected renewal loop to return False when outside threshold"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
