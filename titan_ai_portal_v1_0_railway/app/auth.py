from __future__ import annotations
import hmac
import os
from fastapi import Request

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
SESSION_SECRET = os.environ.get("SESSION_SECRET", "development-only-secret")

def verify_password(value: str) -> bool:
    return bool(ADMIN_PASSWORD) and hmac.compare_digest(value, ADMIN_PASSWORD)

def is_logged_in(request: Request) -> bool:
    return request.session.get("admin") is True
