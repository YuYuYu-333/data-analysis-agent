"""
会话级串行锁：同一个 session_id 的请求排队执行。
为什么不写完就删锁：删除的那一刻可能还有请求在排队，
新请求会新建一把，两边同时写同一个 thread 的检查点。
所以按引用计数回收——持有者和排队者都算引用。
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class SessionLocks:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._refs: dict[str, int] = {}

    @asynccontextmanager
    async def hold(self, key: str) -> AsyncIterator[None]:
        lock = self._locks.setdefault(key, asyncio.Lock())
        self._refs[key] = self._refs.get(key, 0) + 1
        try:
            async with lock:
                yield
        finally:
            self._refs[key] -= 1
            if self._refs[key] == 0:
                del self._refs[key]
                del self._locks[key]

    @property
    def size(self) -> int:
        return len(self._locks)
