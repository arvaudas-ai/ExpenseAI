from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, status


class AIRequestLimiter:
    def __init__(self, max_requests: int = 20, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[int, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, user_id: int, now: float | None = None) -> None:
        current_time = time.monotonic() if now is None else now
        cutoff = current_time - self.window_seconds
        with self._lock:
            timestamps = self._requests[user_id]
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= self.max_requests:
                retry_after = max(1, int(self.window_seconds - (current_time - timestamps[0])))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="AI request limit reached. Please wait before trying again.",
                    headers={"Retry-After": str(retry_after)},
                )
            timestamps.append(current_time)
            if len(self._requests) > 2048:
                stale_users = [
                    stored_user_id
                    for stored_user_id, stored_times in self._requests.items()
                    if not stored_times or stored_times[-1] <= cutoff
                ]
                for stale_user_id in stale_users:
                    self._requests.pop(stale_user_id, None)


ai_request_limiter = AIRequestLimiter()
