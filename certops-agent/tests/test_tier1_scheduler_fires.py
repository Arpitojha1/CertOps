from datetime import datetime, timedelta, timezone
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import db, scheduler, tasks


class TestTier1SchedulerFires(unittest.TestCase):
    def test_scheduler_fires_due_jobs_and_respects_idempotency(self):
        """
        Proves check_and_trigger_renewals triggers pipeline for due certificates
        AND skips certificates that are already in an in-flight pipeline stage.
        """
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            test_db = f.name

        try:
            now_utc = datetime.now(timezone.utc)
            past_utc = now_utc - timedelta(hours=1)
            future_utc = now_utc + timedelta(days=10)

            # 1. Cert due and idle -> should fire
            db.upsert_certificate(
                vault_source="hashicorp",
                name="cert-idle-due",
                expiry_utc=future_utc,
                next_renewal_at=past_utc,
                pipeline_stage="Reload confirmed",
                db_path=test_db,
            )

            # 2. Cert due but already in-flight -> should NOT fire (idempotency guard)
            db.upsert_certificate(
                vault_source="hashicorp",
                name="cert-in-flight",
                expiry_utc=future_utc,
                next_renewal_at=past_utc,
                pipeline_stage="Issued pending deploy",
                db_path=test_db,
            )

            with patch("src.tasks.start_pipeline") as mock_start:
                triggered = tasks.check_and_trigger_renewals(db_path=test_db)

                self.assertEqual(len(triggered), 1)
                self.assertEqual(triggered[0]["cert_id"], "cert-idle-due")
                mock_start.assert_called_once_with("hashicorp", "cert-idle-due", db_path=test_db)

        finally:
            if Path(test_db).exists():
                Path(test_db).unlink()


if __name__ == "__main__":
    unittest.main(verbosity=2)
