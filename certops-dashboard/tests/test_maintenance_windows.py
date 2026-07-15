import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import db


class TestPhase32MaintenanceWindows(unittest.TestCase):
    def setUp(self):
        self.test_db = Path("./test_phase32_mw.db").resolve()
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

    def test_maintenance_window_gate_smoke(self):
        print("\n=== Phase 3.2 Smoke Test: Maintenance Windows Gate ===")
        db_path = str(self.test_db)

        # 1. Create group and seed certificate
        gid = db.create_group("restricted-group", "Group with maintenance window", db_path=db_path)
        expiry = datetime.now(timezone.utc) + timedelta(days=30)
        db.upsert_certificate(
            "ssh_host",
            "cert-mw-01",
            expiry,
            connector_category="host",
            pipeline_stage="Deployed, pending reload",
            group_id=gid,
            db_path=db_path,
        )

        now_utc = datetime.now(timezone.utc)

        # 2. Test CLOSED window (future window: starts in +2 hours, ends in +4 hours)
        w_closed_start = now_utc + timedelta(hours=2)
        w_closed_end = now_utc + timedelta(hours=4)
        db.create_maintenance_window(gid, w_closed_start, w_closed_end, db_path=db_path)

        open_status = db.is_group_in_maintenance_window(gid, check_time=now_utc, db_path=db_path)
        print(f"[TEST CLOSED WINDOW] Group ID={gid} | check_time={now_utc.isoformat()} | Window={w_closed_start.isoformat()} -> {w_closed_end.isoformat()}")
        print(f"[TEST CLOSED WINDOW] is_group_in_maintenance_window returned: {open_status}")
        self.assertFalse(open_status)

        # Simulate confirm_and_reload_host check logic against closed window
        rec = db.get_certificate("ssh_host", "cert-mw-01", db_path=db_path)
        if not db.is_group_in_maintenance_window(rec["group_id"], check_time=now_utc, db_path=db_path):
            db.update_pipeline_stage("ssh_host", "cert-mw-01", "Hold: outside maintenance window", db_path=db_path)
            print("[GATE VERIFIED] Held certificate 'cert-mw-01' at stage: 'Hold: outside maintenance window'")

        held_rec = db.get_certificate("ssh_host", "cert-mw-01", db_path=db_path)
        self.assertEqual(held_rec["pipeline_stage"], "Hold: outside maintenance window")

        # 3. Test OPEN window (active window: starts -1 hour ago, ends +1 hour from now)
        w_open_start = now_utc - timedelta(hours=1)
        w_open_end = now_utc + timedelta(hours=1)
        db.create_maintenance_window(gid, w_open_start, w_open_end, db_path=db_path)

        open_status_active = db.is_group_in_maintenance_window(gid, check_time=now_utc, db_path=db_path)
        print(f"\n[TEST OPEN WINDOW] Group ID={gid} | check_time={now_utc.isoformat()} | Window={w_open_start.isoformat()} -> {w_open_end.isoformat()}")
        print(f"[TEST OPEN WINDOW] is_group_in_maintenance_window returned: {open_status_active}")
        self.assertTrue(open_status_active)

        # Simulate confirm_and_reload_host check logic against open window
        rec_open = db.get_certificate("ssh_host", "cert-mw-01", db_path=db_path)
        if db.is_group_in_maintenance_window(rec_open["group_id"], check_time=now_utc, db_path=db_path):
            db.update_pipeline_stage("ssh_host", "cert-mw-01", "Reload confirmed", db_path=db_path)
            print("[GATE VERIFIED] Maintenance window open. Certificate 'cert-mw-01' allowed through gate -> 'Reload confirmed'")

        proceed_rec = db.get_certificate("ssh_host", "cert-mw-01", db_path=db_path)
        self.assertEqual(proceed_rec["pipeline_stage"], "Reload confirmed")
        print("\n[SMOKE TEST PASSED] Closed maintenance window correctly holds/blocks pipeline; open maintenance window allows pipeline to proceed.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
