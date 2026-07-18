import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Any
import sys
from pathlib import Path

_src_dir = Path(__file__).resolve().parent
_project_dir = _src_dir.parent
if str(_project_dir) not in sys.path:
    sys.path.insert(0, str(_project_dir))
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from src import db

logger = logging.getLogger("certops.scheduler")


class RenewalJob:
    """
    Represents an event-driven scheduled task for a single certificate renewal.
    """
    def __init__(self, vault_source: str, cert_name: str, next_renewal_at: datetime):
        self.vault_source = vault_source
        self.cert_name = cert_name
        self.next_renewal_at = next_renewal_at

    def __repr__(self):
        return f"RenewalJob(cert='{self.cert_name}', next_renewal_at={self.next_renewal_at.isoformat()})"


class RenewalScheduler:
    """
    Event-driven scheduler that sleeps until the next_renewal_at timestamp across
    all monitored certificates. Recovers all scheduled jobs directly from DB on start/restart.
    Produces zero polling API/CPU activity while waiting for future renewal times.
    """
    def __init__(self, db_path: str | None = None, job_callback: Callable[[], Any] | None = None):
        self.db_path = db_path or os.getenv("CERTOPS_DB_PATH", os.getenv("DB_PATH", "./certops.db"))
        self.job_callback = job_callback
        self._stop_event = threading.Event()
        self._wakeup_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._last_evaluated_job: RenewalJob | None = None

    def start(self):
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._stop_event.clear()
        self._wakeup_event.clear()
        self._worker_thread = threading.Thread(target=self._run_loop, name="RenewalScheduler", daemon=True)
        self._worker_thread.start()
        logger.info("RenewalScheduler started (event-driven mode, DB-backed recovery).")

    def stop(self, join_timeout: float = 2.0):
        self._stop_event.set()
        self._wakeup_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=join_timeout)
        logger.info("RenewalScheduler stopped.")

    def notify_schedule_change(self):
        """
        Wakes up the scheduler loop immediately to re-query earliest scheduled renewal from DB.
        """
        self._wakeup_event.set()

    def get_next_job(self) -> RenewalJob | None:
        """
        Recovers scheduled certificate state from DB and returns the earliest upcoming RenewalJob.
        """
        certs = db.list_all_certificates(db_path=self.db_path)
        earliest_job: RenewalJob | None = None

        for c in certs:
            nr = c.get("next_renewal_at")
            if nr is None:
                continue
            job = RenewalJob(c["vault_source"], c["name"], nr)
            if earliest_job is None or job.next_renewal_at < earliest_job.next_renewal_at:
                earliest_job = job

        return earliest_job

    def get_due_jobs(self, now_utc: datetime | None = None) -> list[RenewalJob]:
        """
        Returns all scheduled certificates whose next_renewal_at <= now_utc and whose
        pipeline_stage is not already in an in-flight renewal state.
        """
        now_utc = now_utc or datetime.now(timezone.utc)
        certs = db.list_all_certificates(db_path=self.db_path)
        in_flight_stages = {
            "Renewed",
            "Issued pending deploy",
            "Deployed pending reload",
            "Deployed, pending reload",
        }
        due_jobs: list[RenewalJob] = []

        for c in certs:
            nr = c.get("next_renewal_at")
            if nr is None:
                continue
            stage = c.get("pipeline_stage")
            if stage in in_flight_stages:
                logger.info(
                    "Skipping scheduled trigger for cert '%s' (in-flight stage: '%s')",
                    c["name"],
                    stage,
                )
                continue
            if nr <= now_utc:
                due_jobs.append(RenewalJob(c["vault_source"], c["name"], nr))

        return due_jobs

    def _run_loop(self):
        while not self._stop_event.is_set():
            job = self.get_next_job()
            self._last_evaluated_job = job

            if job is None:
                # No scheduled certificates; sleep/wait until notified
                logger.debug("No upcoming renewal jobs scheduled in DB. Waiting for schedule change...")
                self._wakeup_event.wait(timeout=3600.0)
                self._wakeup_event.clear()
                continue

            now_utc = datetime.now(timezone.utc)
            seconds_until_due = (job.next_renewal_at - now_utc).total_seconds()

            if seconds_until_due <= 0:
                print(f"[SCHEDULER EVENT] Certificate '{job.cert_name}' reached next_renewal_at ({job.next_renewal_at.isoformat()}). Firing renewal job.")
                try:
                    if self.job_callback:
                        self.job_callback()
                except Exception as exc:
                    logger.error("Error executing scheduled renewal callback for '%s': %s", job.cert_name, exc)
                self._wakeup_event.clear()
                # Brief yield to avoid busy looping if callback did not advance next_renewal_at
                time.sleep(0.5)
            else:
                _MAX_SLEEP = 3600.0
                sleep_time = min(seconds_until_due, _MAX_SLEEP)
                print(f"[SCHEDULER SLEEP] Next job '{job.cert_name}' scheduled at {job.next_renewal_at.isoformat()} (in {seconds_until_due:.2f}s). Zero-polling sleep activated (capped at {sleep_time:.0f}s).")
                woke_early = self._wakeup_event.wait(timeout=sleep_time)
                self._wakeup_event.clear()
                if woke_early and not self._stop_event.is_set():
                    logger.debug("Scheduler interrupted by notify_schedule_change(). Recalculating next_renewal_at...")
