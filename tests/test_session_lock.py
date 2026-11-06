"""
会话级串行锁：同 key 串行，不同 key 并行，用完回收。
"""

import asyncio

from app.session_lock import SessionLocks


def test_same_key_is_serialized():
    locks = SessionLocks()
    running = 0
    peak = 0

    async def work():
        nonlocal running, peak
        async with locks.hold("abc"):
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.01)
            running -= 1

    async def main():
        await asyncio.gather(*(work() for _ in range(5)))

    asyncio.run(main())
    assert peak == 1


def test_different_keys_run_concurrently():
    locks = SessionLocks()
    running = 0
    peak = 0

    async def work(key):
        nonlocal running, peak
        async with locks.hold(key):
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.01)
            running -= 1

    async def main():
        await asyncio.gather(*(work(str(i)) for i in range(5)))

    asyncio.run(main())
    assert peak == 5


def test_locks_are_released_after_use():
    locks = SessionLocks()

    async def main():
        async with locks.hold("abc"):
            assert locks.size == 1
        assert locks.size == 0

    asyncio.run(main())


def test_waiter_keeps_lock_alive():
    """有人在排队时不能删锁，否则排队者和新请求会各拿一把。"""
    locks = SessionLocks()
    seen = []

    async def holder():
        async with locks.hold("abc"):
            await asyncio.sleep(0.02)

    async def waiter():
        await asyncio.sleep(0.005)
        async with locks.hold("abc"):
            seen.append(locks.size)

    async def main():
        await asyncio.gather(holder(), waiter())

    asyncio.run(main())
    assert seen == [1]
    assert locks.size == 0
