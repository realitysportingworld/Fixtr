"""
Sliding-window rate limiting for the auth endpoints, stored in the database.

Because the events live in the database, limits hold across restarts and are
shared by every worker and server. Keys are SHA-256 hashes of the limiter
name plus the subject (an email or IP), so the table holds no personal data.
Each limiter uses its own short database session, so a counted attempt is
saved even when the request then fails.
"""
import hashlib
from datetime import timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy import func

from app.core.config import settings
from app.db.base import SessionLocal
from app.models.models import RateLimitEvent, utcnow

# Rows older than this are deleted as new ones arrive; longer than any window
RETENTION = timedelta(days=1)


class SlidingWindowLimiter:
    def __init__(self, name: str, max_events: int, window_seconds: int):
        self.name = name
        self.max_events = max_events
        self.window = timedelta(seconds=window_seconds)

    def _key(self, subject: str) -> str:
        return hashlib.sha256(f"{self.name}:{subject}".encode("utf-8")).hexdigest()

    def retry_after(self, subject: str) -> int:
        """Seconds until `subject` may try again (0 = allowed now)."""
        now = utcnow()
        with SessionLocal() as db:
            recent = db.query(func.count(RateLimitEvent.id), func.min(RateLimitEvent.created_at)).filter(
                RateLimitEvent.key == self._key(subject),
                RateLimitEvent.created_at > now - self.window,
            )
            count, oldest = recent.one()
        if count < self.max_events:
            return 0
        return max(1, int((oldest + self.window - now).total_seconds()) + 1)

    def hit(self, subject: str) -> None:
        now = utcnow()
        with SessionLocal() as db:
            db.query(RateLimitEvent).filter(RateLimitEvent.created_at < now - RETENTION).delete(
                synchronize_session=False
            )
            db.add(RateLimitEvent(key=self._key(subject), created_at=now))
            db.commit()

    def reset(self, subject: str) -> None:
        with SessionLocal() as db:
            db.query(RateLimitEvent).filter(RateLimitEvent.key == self._key(subject)).delete(
                synchronize_session=False
            )
            db.commit()


WINDOW = settings.LOGIN_WINDOW_SECONDS
HOUR = 60 * 60

# Failed logins: tight per account, looser per IP (shared networks / NAT)
login_failures_by_email = SlidingWindowLimiter("login-email", settings.LOGIN_MAX_ATTEMPTS, WINDOW)
login_failures_by_ip = SlidingWindowLimiter("login-ip", settings.LOGIN_MAX_ATTEMPTS * 4, WINDOW)
# Account creation per IP
registrations_by_ip = SlidingWindowLimiter("register-ip", 10, HOUR)
# Wrong current password when changing password or deleting the account, per user
password_checks_by_user = SlidingWindowLimiter("password-check-user", settings.LOGIN_MAX_ATTEMPTS, WINDOW)
# "Forgot password" emails: per address and per IP
reset_requests_by_email = SlidingWindowLimiter("reset-request-email", 3, HOUR)
reset_requests_by_ip = SlidingWindowLimiter("reset-request-ip", 10, HOUR)
# Wrong reset codes per IP (each code also dies after a few wrong tries)
reset_failures_by_ip = SlidingWindowLimiter("reset-failure-ip", 20, HOUR)
# Token refreshes per IP: generous, only there to stop hammering
refreshes_by_ip = SlidingWindowLimiter("refresh-ip", 300, WINDOW)


def client_ip(request: Request) -> str:
    # Behind a reverse proxy, run uvicorn with --proxy-headers so this is the real client
    return request.client.host if request.client else "unknown"


def raise_if_limited(*checks: tuple[SlidingWindowLimiter, str]) -> None:
    wait = max(limiter.retry_after(key) for limiter, key in checks)
    if wait:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again later.",
            headers={"Retry-After": str(wait)},
        )
