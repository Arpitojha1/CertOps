"""
Tier 2 Integration Test: SQLite WAL Concurrency & Lock Safety
Proves that PRAGMA journal_mode=WAL and PRAGMA busy_timeout=5000 prevent lock failures
and lost updates under concurrent writer load.
"""
import concurrent.futures
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from src import db


class TestTier2SQLiteConcurrency(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_concurrency.db")
        with db.get_db_connection(self.db_path):
            pass

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_wal_mode_and_busy_timeout_pragmas(self):
        with db.get_db_connection(self.db_path) as conn:
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]

        self.assertEqual(journal_mode.lower(), "wal", "Database must be in WAL journal mode")
        self.assertEqual(int(busy_timeout), 5000, "busy_timeout must be configured to 5000ms")

    def test_concurrent_writers_no_locks_or_lost_updates(self):
        worker_count = 10
        writes_per_worker = 15

        def worker_task(worker_id: int):
            errors = []
            for i in range(writes_per_worker):
                try:
                    cert_name = f"cert-worker-{worker_id}-item-{i}"
                    exp = datetime.now(timezone.utc) + timedelta(days=30 + i)
                    db.upsert_certificate(
                        vault_source="hashicorp",
                        name=cert_name,
                        expiry_utc=exp,
                        db_path=self.db_path,
                    )
                    db.update_pipeline_stage("hashicorp", cert_name, "Renewed", db_path=self.db_path)
                    db.log_activity(
                        actor_email=f"worker{worker_id}@certops.internal",
                        event_type="certificate_renewed",
                        target=cert_name,
                        details={"worker": worker_id, "iteration": i},
                        db_path=self.db_path,
                    )
                except Exception as exc:
                    errors.append(str(exc))
            return errors

        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(worker_task, w_id) for w_id in range(worker_count)]
            all_errors = []
            for f in concurrent.futures.as_completed(futures):
                all_errors.extend(f.result())

        self.assertEqual(all_errors, [], f"Concurrent workers encountered errors/lock failures: {all_errors[:5]}")

        # Verify all records persisted accurately
        certs = db.list_all_certificates(db_path=self.db_path)
        self.assertEqual(len(certs), worker_count * writes_per_worker, "All concurrent certificate writes must be persisted")

        # Verify all activity logs persisted
        with db.get_db_connection(self.db_path) as conn:
            log_count = conn.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]
        self.assertEqual(log_count, worker_count * writes_per_worker, "All concurrent activity log entries must be persisted")


if __name__ == "__main__":
    unittest.main()
