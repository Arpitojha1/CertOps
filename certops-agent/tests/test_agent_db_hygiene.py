# certops-agent/tests/test_agent_db_hygiene.py
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))

from src import agent_db


class TestAgentDBHygiene(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        agent_db.init_agent_db(self.db_path)

    def tearDown(self):
        import gc
        gc.collect()
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except PermissionError:
                pass

    def test_connection_closes_on_execute_error(self):
        # Simulate an OperationalError during set_identity
        real_conn = sqlite3.connect(self.db_path)
        mock_conn = MagicMock()
        mock_conn.close = MagicMock(wraps=real_conn.close)
        mock_conn.execute = MagicMock(side_effect=sqlite3.OperationalError("database is locked"))

        try:
            with patch("sqlite3.connect", return_value=mock_conn):
                with self.assertRaises(sqlite3.OperationalError):
                    agent_db.set_identity("key", "val", db_path=self.db_path)

            mock_conn.close.assert_called_once()
        finally:
            real_conn.close()


if __name__ == "__main__":
    unittest.main()
