"""
In-memory sliding-window rate limiting for auth endpoints.

State lives in the process, so limits are per worker and reset on restart.
That's fine for a single-instance deployment; with several workers or
instances, move this to a shared store such as Redis.
"""
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.core.config import settings


class SlidingWindowLimiter:
    def __init__(self, max_events: int, window_seconds: int):
        self.max_events = max_events
        self.window = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        events = self._events[key]
        while events and events[0] <= now - self.window:
            events.popleft()
        if not events:
            del self._events[key]  # keep memory bounded to active keys
            return deque()
        return events

    def retry_after(self, key: str) -> int:
        """Seconds until `key` may try again (0 = allowed now)."""
        with self._lock:
            now = time.monotonic()
            events = self._prune(key, now)
            if len(events) < self.max_events:
                return 0
            return max(1, int(events[0] + self.window - now))

    def hit(self, key: str) -> None:
        with self._lock:
            self._events[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)


# Failed logins: tight per account, looser per IP (shared networks / NAT)
login_failures_by_email = SlidingWindowLimiter(settings.LOGIN_MAX_ATTEMPTS, settings.LOGIN_WINDOW_SECONDS)
login_failures_by_ip = SlidingWindowLimiter(settings.LOGIN_MAX_ATTEMPTS * 4, settings.LOGIN_WINDOW_SECONDS)
# Account creation per IP
registrations_by_ip = SlidingWindowLimiter(10, 60 * 60)


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
