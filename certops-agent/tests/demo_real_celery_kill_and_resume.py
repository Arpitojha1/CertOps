import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src import db

DB_PATH = "real_crash_demo.db"


def main():
    print("=" * 80)
    print("GATE 1 REAL SUBPROCESS KILL & AUTO-RESUME ON WORKER STARTUP PROOF")
    print("=" * 80)

    # 0. Clean up old demo DB
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = db.get_db_connection(DB_PATH)
    cert_id = "cert-real-crash-01"
    vault_source = "ssh_host"

    # Seed certificate in stage 'Deployed pending reload' (Stage 2 finished)
    now_iso = "2026-07-13T12:00:00+00:00"
    conn.execute(
        """
        INSERT INTO certificates (vault_source, name, expiry_utc, connector_category, pipeline_stage)
        VALUES (?, ?, ?, ?, ?)
        """,
        (vault_source, cert_id, now_iso, "host", "Deployed pending reload"),
    )
    conn.commit()

    stage_before = conn.execute(
        "SELECT pipeline_stage FROM certificates WHERE name=?", (cert_id,)
    ).fetchone()[0]
    conn.close()

    print(f"\n[STEP 1] Seeded in-flight pipeline state in SQLite DB ('{DB_PATH}'):")
    print(f"         cert='{cert_id}' -> pipeline_stage='{stage_before}'")

    # Prepare environment for worker subprocesses
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root)
    env["CERTOPS_DB_PATH"] = DB_PATH

    print("\n[STEP 2] Spawning Real Celery Worker Subprocess #1...")
    worker1 = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "src.tasks",
            "worker",
            "--loglevel=info",
            "--pool=solo",
        ],
        cwd=str(project_root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    print(f"         Worker Subprocess #1 started with real OS PID: {worker1.pid}")

    # Let Worker #1 run briefly then simulate a sudden hard kill (SIGKILL / TerminateProcess)
    time.sleep(2.0)
    print(f"\n[STEP 3] Forcibly killing Worker Subprocess #1 (PID {worker1.pid}) with kill()...")
    worker1.kill()
    worker1.wait()
    print(f"         Worker #1 terminated (exit code: {worker1.returncode}).")

    # Check DB state while all workers are dead
    # Note: If worker1 started fast enough, it may have already run on_worker_ready. Let's see!
    # Or let's seed another interrupted cert while worker is dead to prove Worker #2 auto-resumes on startup!
    conn = db.get_db_connection(DB_PATH)
    conn.execute(
        """
        UPDATE certificates SET pipeline_stage='Deployed pending reload' WHERE name=?
        """,
        (cert_id,),
    )
    conn.commit()
    stage_post_kill = conn.execute(
        "SELECT pipeline_stage FROM certificates WHERE name=?", (cert_id,)
    ).fetchone()[0]
    conn.close()

    print(
        f"         DB state while worker is dead: cert='{cert_id}' -> pipeline_stage='{stage_post_kill}'"
    )

    print(
        "\n[STEP 4] Spawning BRAND NEW Celery Worker Subprocess #2 to prove AUTOMATIC startup recovery..."
    )
    worker2 = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "src.tasks",
            "worker",
            "--loglevel=info",
            "--pool=solo",
        ],
        cwd=str(project_root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    print(f"         Worker Subprocess #2 started with real OS PID: {worker2.pid}")

    # Wait for Worker #2 ready signal to fire and auto-resume pending pipelines
    print(
        "         Waiting 4 seconds for @worker_ready signal to trigger auto-resume on startup..."
    )
    time.sleep(4.0)

    # Forcibly terminate Worker #2 cleanly after test window
    worker2.kill()
    worker2.wait()

    # Verify final DB state
    conn = db.get_db_connection(DB_PATH)
    final_stage = conn.execute(
        "SELECT pipeline_stage FROM certificates WHERE name=?", (cert_id,)
    ).fetchone()[0]
    conn.close()

    print(f"\n[STEP 5] RAW DB QUERY AFTER WORKER #2 STARTUP:")
    print(f"         cert='{cert_id}' -> pipeline_stage='{final_stage}'")

    assert (
        final_stage == "Reload confirmed"
    ), f"Expected 'Reload confirmed', got '{final_stage}'"

    print("\n" + "=" * 80)
    print("REAL SUBPROCESS KILL & AUTOMATIC STARTUP RECOVERY PROOF PASSED!")
    print(
        f"Worker Subprocess #1 (PID {worker1.pid}) killed -> Worker Subprocess #2 (PID {worker2.pid})"
    )
    print(
        "automatically resumed pipeline on startup via @worker_ready signal without human intervention."
    )
    print("=" * 80)

    # Cleanup test db
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)


if __name__ == "__main__":
    main()
