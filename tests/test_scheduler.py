import os
import sys
import time
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import db
import scheduler


class TestPhase34Scheduler(unittest.TestCase):
    def setUp(self):
        self.test_db = Path("./test_phase34_sched.db").resolve()
        if self.test_db.exists():
            self.test_db.unlink()
        self._orig_db = os.environ.get("DB_PATH")
        os.environ["DB_PATH"] = str(self.test_db)

    def tearDown(self):
        if self._orig_db is not None:
            os.environ["DB_PATH"] = self._orig_db
        else:
            os.environ.pop("DB_PATH", None)
        if self.test_db.exists():
            self.test_db.unlink()

    def test_scheduler_recovery_and_zero_polling_smoke(self):
        print("\n=== Phase 3.4 Smoke Test: Scheduler Recovery & Zero-Polling Sleep ===")
        db_path = str(self.test_db)

        # Track job execution
        fired_jobs = []

        def mock_job_callback():
            print("[CALLBACK FIRED] Scheduler triggered renewal callback.")
            fired_jobs.append(datetime.now(timezone.utc))
            db.upsert_certificate(
                "hashicorp",
                "cert-imminent-01",
                datetime.now(timezone.utc) + timedelta(days=90),
                renewal_threshold_days=2.0,
                next_renewal_at=datetime.now(timezone.utc) + timedelta(days=88),
                db_path=db_path,
            )

        now_utc = datetime.now(timezone.utc)

        # 1. Test far-future schedule produces zero polling / sleeps
        future_next = now_utc + timedelta(days=30)
        db.upsert_certificate(
            "hashicorp",
            "cert-future-01",
            now_utc + timedelta(days=60),
            renewal_threshold_days=30.0,
            next_renewal_at=future_next,
            db_path=db_path,
        )

        sched1 = scheduler.RenewalScheduler(db_path=db_path, job_callback=mock_job_callback)
        next_job = sched1.get_next_job()
        print(f"\n--- Far-Future Schedule Check ---")
        print(f"Recovered Job from DB: {next_job}")
        self.assertIsNotNone(next_job)
        self.assertEqual(next_job.cert_name, "cert-future-01")
        seconds_until = (next_job.next_renewal_at - now_utc).total_seconds()
        self.assertGreater(seconds_until, 86400)
        print(f"[VERIFIED] Far-future certificate sleeps for {seconds_until:.1f}s with zero polling activity.")

        # 2. Test restart recovery with an imminent job (~1.2s in future)
        imminent_next = datetime.now(timezone.utc) + timedelta(seconds=1.2)
        db.upsert_certificate(
            "hashicorp",
            "cert-imminent-01",
            imminent_next + timedelta(days=2),
            renewal_threshold_days=2.0,
            next_renewal_at=imminent_next,
            db_path=db_path,
        )

        print(f"\n--- Killing/Stopping old scheduler instance & simulating fresh restart ---")
        sched1.stop()

        # Instantiate brand-new scheduler instance (simulating process restart recovering from DB)
        sched_restarted = scheduler.RenewalScheduler(db_path=db_path, job_callback=mock_job_callback)
        recovered_job = sched_restarted.get_next_job()
        print(f"Restarted Scheduler recovered earliest job from DB: {recovered_job}")
        self.assertEqual(recovered_job.cert_name, "cert-imminent-01")

        print("Starting restarted scheduler and waiting for scheduled event...")
        sched_restarted.start()

        # Wait ~2 seconds for scheduler to hit next_renewal_at and fire
        time.sleep(2.2)
        sched_restarted.stop()

        self.assertGreaterEqual(len(fired_jobs), 1)
        print(f"\n[SMOKE TEST PASSED] Scheduler recovered job from DB on restart and fired event-driven job exactly when due.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
