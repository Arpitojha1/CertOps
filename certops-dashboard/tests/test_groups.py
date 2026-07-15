import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Ensure package root, src, and agent sibling are on sys.path
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))
_sibling = _root.parent / "certops-agent"
if _sibling.exists() and str(_sibling) not in sys.path:
    sys.path.insert(0, str(_sibling))

import db


class TestPhase31Groups(unittest.TestCase):
    def setUp(self):
        self.test_db = Path("./test_phase31_groups.db").resolve()
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
        if self.test_db.exists():
            self.test_db.unlink()

    def test_groups_and_filtering_smoke(self):
        print("\n=== Phase 3.1 Smoke Test: Groups & Filtering ===")
        db_path = str(self.test_db)

        # 1. Create two groups
        gid_prod = db.create_group("prod-group", "Production certificates", db_path=db_path)
        gid_dev = db.create_group("dev-group", "Development certificates", db_path=db_path)
        print(f"Created Group 1: ID={gid_prod}, name='prod-group'")
        print(f"Created Group 2: ID={gid_dev}, name='dev-group'")

        # Seed 3 certificates (all expiring soon so they show up as due)
        due_exp = datetime.now(timezone.utc) + timedelta(days=0.5)
        db.upsert_certificate("hashicorp", "cert-prod-01", due_exp, renewal_threshold_days=2.0, group_id=gid_prod, db_path=db_path)
        db.upsert_certificate("hashicorp", "cert-dev-01", due_exp, renewal_threshold_days=2.0, group_id=gid_dev, db_path=db_path)
        db.upsert_certificate("hashicorp", "cert-ungrouped-01", due_exp, renewal_threshold_days=2.0, group_id=None, db_path=db_path)

        # 2. Query filtered by prod-group
        prod_due = db.get_due_certificates(group_id=gid_prod, db_path=db_path)
        print(f"\n--- Due Certificates for 'prod-group' (ID={gid_prod}) ---")
        for c in prod_due:
            print(f"  Cert: {c['name']} | Vault: {c['vault_source']} | GroupID: {c['group_id']}")
        self.assertEqual(len(prod_due), 1)
        self.assertEqual(prod_due[0]["name"], "cert-prod-01")

        # 3. Query filtered by dev-group
        dev_due = db.get_due_certificates(group_id=gid_dev, db_path=db_path)
        print(f"\n--- Due Certificates for 'dev-group' (ID={gid_dev}) ---")
        for c in dev_due:
            print(f"  Cert: {c['name']} | Vault: {c['vault_source']} | GroupID: {c['group_id']}")
        self.assertEqual(len(dev_due), 1)
        self.assertEqual(dev_due[0]["name"], "cert-dev-01")

        # 4. Unfiltered query surfaces all 3 certificates including ungrouped
        all_due = db.get_due_certificates(db_path=db_path)
        print(f"\n--- Unfiltered Due Certificates (all groups + ungrouped) ---")
        for c in all_due:
            print(f"  Cert: {c['name']} | Vault: {c['vault_source']} | GroupID: {c['group_id']}")
        self.assertEqual(len(all_due), 3)
        names = {c["name"] for c in all_due}
        self.assertIn("cert-prod-01", names)
        self.assertIn("cert-dev-01", names)
        self.assertIn("cert-ungrouped-01", names)
        print("\n[SMOKE TEST PASSED] Group creation, certificate assignment, group-filtered queries, and ungrouped compatibility verified.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
