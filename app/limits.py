"""
进程内限流：滑动窗口数请求次数。
内存版，重启归零；多实例各算各的——写进已知局限。
"""

import time
from collections import defaultdict, deque

WINDOW_SECONDS = 60
DEMO_PER_MINUTE = 5
API_PER_MINUTE = 30


class RateLimiter:
    def __init__(self, limit: int, window: int =
    WINDOW_SECONDS):
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True
