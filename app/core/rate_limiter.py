import threading
from collections import deque
from datetime import UTC, datetime, timedelta


class InMemoryRateLimiter:
    """Sliding-window rate limiter keyed by arbitrary strings (e.g. IP address)."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window = timedelta(seconds=window_seconds)
        self._buckets: dict[str, deque[datetime]] = {}
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        now = datetime.now(UTC)
        with self._lock:
            bucket = self._buckets.setdefault(key, deque())
            while bucket and bucket[0] <= now - self.window:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                return False
            bucket.append(now)
            return True

    def seconds_until_reset(self, key: str) -> int:
        now = datetime.now(UTC)
        with self._lock:
            bucket = self._buckets.get(key, deque())
            if not bucket:
                return 0
            oldest = bucket[0]
            return max(0, int((oldest + self.window - now).total_seconds()))


# Sensitive authentication paths are deliberately throttled in addition to the
# password-reset limit. In-memory state is suitable for one process; production
# deployments with several workers should replace this with a shared store.
forgot_password_limiter = InMemoryRateLimiter(max_requests=3, window_seconds=900)
login_limiter = InMemoryRateLimiter(max_requests=5, window_seconds=900)
registration_limiter = InMemoryRateLimiter(max_requests=5, window_seconds=3600)
