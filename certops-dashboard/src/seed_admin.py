"""
One-time admin seed script.
Reads ADMIN_EMAIL and ADMIN_PASSWORD from environment (never hardcoded).
Safe to re-run — exits cleanly if admin already exists.

Usage:
  python src/seed_admin.py

Required env vars (via .env or shell):
  ADMIN_EMAIL      e.g. admin@example.com
  ADMIN_PASSWORD   strong password
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Locate db and auth relative to this file's directory
from pathlib import Path
sys.path.insert(0, os.path.dirname(__file__))
_agent_src = Path(__file__).resolve().parent.parent.parent / "certops-agent" / "src"
if _agent_src.exists() and str(_agent_src) not in sys.path:
    sys.path.insert(0, str(_agent_src))
import auth
import db

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

if not ADMIN_EMAIL or not ADMIN_PASSWORD:
    print("ERROR: ADMIN_EMAIL and ADMIN_PASSWORD must be set in environment.", file=sys.stderr)
    sys.exit(1)

existing = db.get_user_by_email(ADMIN_EMAIL)
if existing:
    print(f"Admin '{ADMIN_EMAIL}' already exists (role={existing['role']}). Nothing to do.")
    sys.exit(0)

uid = db.create_user(ADMIN_EMAIL, auth.hash_password(ADMIN_PASSWORD), role="admin")
print(f"Admin user created: id={uid} email={ADMIN_EMAIL}")
