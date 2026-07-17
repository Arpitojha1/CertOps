import os
import sqlite3
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))
_sibling = _root.parent / "certops-agent"
if _sibling.exists() and str(_sibling) not in sys.path:
    sys.path.insert(0, str(_sibling))

import db
import main


class TestPhase33Notifications(unittest.TestCase):
    def setUp(self):
        self.test_db = Path("./test_phase33_notif.db").resolve()
        if self.test_db.exists():
            self.test_db.unlink()
        self._orig_db = os.environ.get("DB_PATH")
        os.environ["DB_PATH"] = str(self.test_db)
        db.run_migrations(str(self.test_db))

    def tearDown(self):
        if self._orig_db is not None:
            os.environ["DB_PATH"] = self._orig_db
        else:
            os.environ.pop("DB_PATH", None)
        db.close_db_connection(str(self.test_db))
        for p in (self.test_db, Path(f"{self.test_db}-wal"), Path(f"{self.test_db}-shm")):
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass

    def test_notification_deduplication_smoke(self):
        print("\n=== Phase 3.3 Smoke Test: Notification Policy & Deduplication ===")
        db_path = str(self.test_db)

        # 1. Create a group and a notification policy (45 days threshold)
        gid = db.create_group("notif-group", "Group with notification policy", db_path=db_path)
        pid = db.create_notification_policy(gid, threshold_days=45.0, db_path=db_path)
        print(f"Created Group ID={gid}, Policy ID={pid} with threshold=45.0 days")

        # Create a certificate expiring in 20 days (triggers notification policy, but NOT due for auto-renewal at 2 days)
        expiry = datetime.now(timezone.utc) + timedelta(days=20)
        db.upsert_certificate(
            "hashicorp",
            "cert-notif-01",
            expiry,
            connector_category="secret_store",
            pipeline_stage=None,
            renewal_threshold_days=2.0,
            group_id=gid,
            db_path=db_path,
        )

        # 2. First pass of run_notification_check()
        print("\n--- First pass: run_notification_check() ---")
        sent_first = main.run_notification_check(db_path=db_path)
        self.assertEqual(sent_first, 1)

        # 3. Second pass of run_notification_check()
        print("\n--- Second pass: run_notification_check() ---")
        sent_second = main.run_notification_check(db_path=db_path)
        self.assertEqual(sent_second, 0)

        # 4. Raw SELECT * FROM notification_log verification
        print("\n--- Raw SELECT * FROM notification_log ---")
        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT * FROM notification_log ORDER BY id").fetchall()
        conn.close()
        for r in rows:
            print(f"  id={r[0]} | vault_source={r[1]} | cert_id={r[2]} | policy_id={r[3]} | sent_at={r[4]}")
        self.assertEqual(len(rows), 1)

        # 5. Confirm certificate auto-renewal state is unaffected
        cert_rec = db.get_certificate("hashicorp", "cert-notif-01", db_path=db_path)
        self.assertEqual(cert_rec["renewal_threshold_days"], 2.0)
        self.assertIsNone(cert_rec["pipeline_stage"])
        print("\n[SMOKE TEST PASSED] Notification policy fired, deduplicated correctly on second pass, and left auto-renewal state decoupled.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
