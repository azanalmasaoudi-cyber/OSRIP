"""Small in-process sliding-window limiter for unauthenticated e-mail endpoints.

Per API process only (a deployment with several workers multiplies the limit by
the number of workers). Keys are keyed digests of client addresses, never raw IPs.
Per-account limits on issued tokens are enforced separately in the database.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from app.core.errors import ApiError

_lock = threading.Lock()
_hits: dict[str, deque[float]] = defaultdict(deque)


def check(key: str, limit: int, window_seconds: int) -> None:
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and q[0] <= now - window_seconds:
            q.popleft()
        if len(q) >= limit:
            raise ApiError(
                429, "too_many_requests", "Too many requests. Wait a while and try again."
            )
        q.append(now)


def reset() -> None:
    with _lock:
        _hits.clear()
