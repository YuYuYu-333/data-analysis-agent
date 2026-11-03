"""
多轮检查点：本地 SQLite（WAL）；云端 Postgres 在 后面接。
"""

from pathlib import Path

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.config import CHECKPOINT_DB, DATABASE_URL

_checkpointer: AsyncSqliteSaver | None = None
_conn: aiosqlite.Connection | None = None


async def build_sqlite_checkpointer(path: Path) -> tuple[AsyncSqliteSaver, aiosqlite.Connection]:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(str(path))
    saver = AsyncSqliteSaver(conn)
    await saver.setup()
    return saver, conn


async def get_checkpointer() -> AsyncSqliteSaver:
    global _checkpointer, _conn
    if _checkpointer is None:
        if DATABASE_URL:
            raise RuntimeError("Postgres checkpointer 在 M6 接入；本地请清空 DATABASE_URL")
        _checkpointer, _conn = await build_sqlite_checkpointer(CHECKPOINT_DB)
    return _checkpointer


async def close_checkpointer() -> None:
    global _checkpointer, _conn
    if _conn is not None:
        await _conn.close()
    _checkpointer = None
    _conn = None
