"""
Tier 2 Integration Test: Real Webhook Notification Delivery & Deduplication
Proves that run_notification_check() sends a live HTTP POST payload to a configured webhook
and deduplicates subsequent runs via notification_log.
"""
import http.server
import json
import os
import shutil
import tempfile
import threading
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

from src import db, main, notifier


class _WebhookHandler(http.server.BaseHTTPRequestHandler):
    received_requests: list[dict] = []

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8")
        payload = json.loads(body)
        _WebhookHandler.received_requests.append({
            "path": self.path,
            "payload": payload,
        })
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, format, *args):
        pass


class TestTier2WebhookNotification(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_tier2_webhook.db")
        db.run_migrations(self.db_path)

        _WebhookHandler.received_requests = []
        self.server = http.server.HTTPServer(("127.0.0.1", 0), _WebhookHandler)
        self.port = self.server.server_port
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

        os.environ["WEBHOOK_URL"] = f"http://127.0.0.1:{self.port}/webhook"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        db.close_db_connection(self.db_path)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        os.environ.pop("WEBHOOK_URL", None)

    def test_webhook_delivery_and_deduplication(self):
        # 1. Create a group and certificate due for expiry warning
        group_id = db.create_group("OpsTeam", db_path=self.db_path)
        policy_id = db.create_notification_policy(group_id, threshold_days=7.0, db_path=self.db_path)

        soon_dt = datetime.now(timezone.utc) + timedelta(days=2.0)
        db.upsert_certificate(
            vault_source="hashicorp",
            name="prod-web-cert",
            expiry_utc=soon_dt,
            group_id=group_id,
            db_path=self.db_path,
        )

        # 2. Run notification check — should fire live HTTP webhook POST
        sent_count = main.run_notification_check(db_path=self.db_path)
        self.assertEqual(sent_count, 1, "Expected exactly 1 notification delivered")
        self.assertEqual(len(_WebhookHandler.received_requests), 1, "HTTP listener should receive 1 webhook POST")

        req = _WebhookHandler.received_requests[0]
        self.assertEqual(req["path"], "/webhook")
        payload = req["payload"]
        self.assertEqual(payload["event"], "certificate_expiry_warning")
        self.assertEqual(payload["cert_name"], "prod-web-cert")
        self.assertEqual(payload["vault_source"], "hashicorp")
        self.assertEqual(payload["threshold_days"], 7.0)

        sent_count_second = main.run_notification_check(db_path=self.db_path)
        self.assertEqual(sent_count_second, 0, "Second run should deduplicate via notification_log")
        self.assertEqual(len(_WebhookHandler.received_requests), 1, "HTTP listener should receive no duplicate webhook POST")

    def test_smtp_transport_delivery(self):
        from unittest.mock import MagicMock, patch

        os.environ["SMTP_HOST"] = "smtp.test.internal"
        os.environ["SMTP_PORT"] = "587"
        os.environ["SMTP_SENDER"] = "alert@certops.internal"
        os.environ["SMTP_RECIPIENT"] = "sre@certops.internal"
        os.environ["SMTP_USE_TLS"] = "false"

        try:
            with patch("smtplib.SMTP") as mock_smtp_cls:
                mock_server = MagicMock()
                mock_smtp_cls.return_value = mock_server
                results = notifier.dispatch_notification(
                    cert_name="api.example.com",
                    vault_source="hashicorp",
                    remaining_days=1.5,
                    threshold_days=3.0,
                )
                self.assertTrue(results["smtp"], "SMTP delivery should succeed")
                mock_server.send_message.assert_called_once()
                msg = mock_server.send_message.call_args[0][0]
                self.assertEqual(msg["Subject"], "[CertOps Warning] Certificate 'api.example.com' expiring in 1.50 days")
                self.assertEqual(msg["To"], "sre@certops.internal")
        finally:
            for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_SENDER", "SMTP_RECIPIENT", "SMTP_USE_TLS"):
                os.environ.pop(k, None)


if __name__ == "__main__":
    unittest.main()
