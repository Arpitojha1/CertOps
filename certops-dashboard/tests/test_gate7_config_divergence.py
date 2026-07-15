"""
Verification test for Phase 0 Part F: Retire env var config divergence.
Asserts that when db.list_connectors(active_only=True) returns zero rows,
run_renewal_loop exits cleanly with 0 actions even if CONNECTOR_1_TYPE=hashicorp is set in os.environ.
"""

import os
import tempfile
import unittest

from src import db, main


class TestGate7ConfigDivergence(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()
        os.environ["DB_PATH"] = self.db_path
        os.environ["SKIP_DEFAULT_CONNECTORS"] = "1"
        # Ensure fresh tables
        conn = db.get_db_connection(self.db_path)
        conn.close()

    def tearDown(self):
        os.environ.pop("SKIP_DEFAULT_CONNECTORS", None)
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def test_zero_actions_when_db_connectors_empty_with_env_vars_set(self):
        print("\n=== TEST CONFIG DIVERGENCE: DB Authoritative Source ===")
        # Set legacy env vars
        os.environ["CONNECTOR_1_TYPE"] = "hashicorp"
        os.environ["CONNECTOR_1_THRESHOLD_DAYS"] = "30"

        try:
            # Confirm DB connectors table is empty
            connectors = db.list_connectors(active_only=True, db_path=self.db_path)
            print(f"[DB STATE] len(active_connectors) == {len(connectors)}")
            self.assertEqual(len(connectors), 0)

            # Run renewal loop against DB with 0 active connectors
            summary = main.run_renewal_loop(db_path=self.db_path)

            print(f"[RENEWAL LOOP RESULT] summary == {summary}")
            self.assertEqual(len(summary), 0, "Summary must be empty when 0 active connectors exist in DB")

            # Check total actions across summary
            total_succeeded = sum(s.get("succeeded", 0) for s in summary.values())
            total_skipped = sum(s.get("skipped", 0) for s in summary.values())
            total_failed = sum(s.get("failed", 0) for s in summary.values())

            print(f"[SUMMARY ACTIONS] checked={len(summary)} succeeded={total_succeeded} skipped={total_skipped} failed={total_failed}")
            self.assertEqual(total_succeeded, 0)
            self.assertEqual(total_skipped, 0)
            self.assertEqual(total_failed, 0)
            print("[RESULT] PASSED: 0 checked, 0 renewed when DB connectors table is empty despite CONNECTOR_1_TYPE=hashicorp in os.environ")
        finally:
            os.environ.pop("CONNECTOR_1_TYPE", None)
            os.environ.pop("CONNECTOR_1_THRESHOLD_DAYS", None)


if __name__ == "__main__":
    unittest.main()
