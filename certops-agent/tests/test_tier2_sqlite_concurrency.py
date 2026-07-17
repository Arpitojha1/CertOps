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
import sys
from pathlib import Path
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))
_sibling = _root.parent / "certops-dashboard"
if _sibling.exists() and str(_sibling) not in sys.path:
    sys.path.insert(0, str(_sibling))

from src import db


class TestTier2SQLiteConcurrency(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_concurrency.db")
        db.run_migrations(self.db_path)

    def tearDown(self):
        db.close_db_connection(self.db_path)
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

    def test_get_db_connection_singleton_and_no_hotpath_migrations(self):
        # Verify Option A: singleton connection cached in db._db_connections by absolute path
        abs_path = os.path.normcase(os.path.abspath(self.db_path))
        self.assertTrue(hasattr(db, "_db_connections"), "db module must have _db_connections dictionary for Option A")
        
        conn1 = db.get_db_connection(self.db_path)
        conn2 = db.get_db_connection(self.db_path)
        self.assertIn(abs_path, db._db_connections)
        self.assertIs(db._db_connections[abs_path], conn1._raw_conn, "get_db_connection must return wrapper over singleton connection")
        self.assertIs(conn1._raw_conn, conn2._raw_conn, "Multiple calls must share the same underlying connection")
        
        # Verify .close() on proxy releases without closing underlying connection
        conn1.close()
        self.assertIsNotNone(conn2.execute("SELECT 1").fetchone(), "Underlying connection must remain open after proxy .close()")

        # Verify no hotpath DDL / user_version checks: fresh DB file without calling run_migrations should have no tables
        fresh_db = os.path.join(self.temp_dir, "fresh_no_hotpath.db")
        conn_fresh = db.get_db_connection(fresh_db)
        try:
            cur = conn_fresh.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='certificates'")
            self.assertEqual(cur.fetchone()[0], 0, "get_db_connection must NOT run migrations automatically on hot path")
        finally:
            conn_fresh.close()
            if hasattr(db, "close_db_connection"):
                db.close_db_connection(fresh_db)

    def test_concurrent_fastapi_and_celery_simulation_with_lock(self):
        # Simulate concurrent FastAPI requests and Celery background tasks writing/reading simultaneously
        fastapi_workers = 5
        celery_workers = 5
        iterations = 10

        def fastapi_request_task(idx: int):
            errors = []
            for i in range(iterations):
                try:
                    cert_name = f"sim-fastapi-{idx}-{i}"
                    exp = datetime.now(timezone.utc) + timedelta(days=60 + i)
                    db.upsert_certificate(
                        vault_source="hashicorp",
                        name=cert_name,
                        expiry_utc=exp,
                        db_path=self.db_path,
                    )
                    db.log_activity(
                        actor_email=f"api_{idx}@certops.internal",
                        event_type="certificate_created",
                        target=cert_name,
                        details={"source": "fastapi_sim", "idx": idx, "i": i},
                        db_path=self.db_path,
                    )
                except Exception as exc:
                    errors.append(f"FastAPI worker {idx} iter {i} error: {exc}")
            return errors

        def celery_background_task(idx: int):
            errors = []
            for i in range(iterations):
                try:
                    cert_name = f"sim-celery-{idx}-{i}"
                    exp = datetime.now(timezone.utc) + timedelta(days=90 + i)
                    db.upsert_certificate(
                        vault_source="step_ca",
                        name=cert_name,
                        expiry_utc=exp,
                        db_path=self.db_path,
                    )
                    db.update_pipeline_stage("step_ca", cert_name, "Verified and Reloaded", db_path=self.db_path)
                    db.log_activity(
                        actor_email="celery_worker@certops.internal",
                        event_type="pipeline_resumed",
                        target=cert_name,
                        details={"source": "celery_sim", "idx": idx, "i": i},
                        db_path=self.db_path,
                    )
                except Exception as exc:
                    errors.append(f"Celery worker {idx} iter {i} error: {exc}")
            return errors

        with concurrent.futures.ThreadPoolExecutor(max_workers=fastapi_workers + celery_workers) as executor:
            futures = []
            for w in range(fastapi_workers):
                futures.append(executor.submit(fastapi_request_task, w))
            for w in range(celery_workers):
                futures.append(executor.submit(celery_background_task, w))

            all_errors = []
            for f in concurrent.futures.as_completed(futures):
                all_errors.extend(f.result())

        self.assertEqual(all_errors, [], f"Simulated concurrent FastAPI & Celery workers produced errors: {all_errors[:5]}")

        # Verify all records persisted accurately under Option A locking
        certs = db.list_all_certificates(db_path=self.db_path)
        # We expect worker_count * writes_per_worker (from test 2 if running in same db? Wait, this runs on self.db_path which is reset per test in setUp or let's check)
        # Let's count only the sim certificates created in this test method:
        sim_certs = [c for c in certs if c["name"].startswith("sim-fastapi-") or c["name"].startswith("sim-celery-")]
        self.assertEqual(len(sim_certs), (fastapi_workers + celery_workers) * iterations, "All simulated FastAPI and Celery certificates must be persisted")


if __name__ == "__main__":
    unittest.main()
