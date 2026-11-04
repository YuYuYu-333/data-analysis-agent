"""
限流器：次数上限、key 隔离、窗口过期。
"""

import time

from app.limits import RateLimiter


def test_allows_up_to_limit():
    limiter = RateLimiter(2)
    assert limiter.allow("a")
    assert limiter.allow("a")
    assert not limiter.allow("a")


def test_keys_are_isolated():
    limiter = RateLimiter(1)
    assert limiter.allow("a")
    assert limiter.allow("b")
    assert not limiter.allow("a")


def test_window_expires():
    limiter = RateLimiter(1, window=0.01)
    assert limiter.allow("a")
    time.sleep(0.02)
    assert limiter.allow("a")
