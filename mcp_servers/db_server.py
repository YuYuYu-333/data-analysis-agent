"""
Database MCP Server：只读执行
SQL，并在服务层做四道硬拦截。
不知道用户问什么，也不生成
SQL；只负责安全地查数据。
"""

import logging
import re
import sqlite3
import sys
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "retail.db"
SQL_TIMEOUT_SECONDS = 5
ROW_LIMIT = 1000

# stdio 传输时 stdout 是协议通道，日志必须走 stderr
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("db_server")

mcp = FastMCP("db-server")

_DANGEROUS_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|PRAGMA|VACUUM|REINDEX|REPLACE|TRUNCATE)\b",
    re.IGNORECASE, )
_LOAD_EXTENSION = re.compile(r"\bload_extension\b", re.IGNORECASE)


def _strip_literals_and_comments(sql: str) -> str:
    """去掉字符串字面量、标识符引号和注释，只留可检查的 SQL 结构"""
    out = []
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if ch in ("'", '"', "`"):
            quote = ch
            out.append(" ")
            i += 1
            while i < n:
                if sql[i] == quote:
                    if i + 1 < n and sql[i + 1] == quote:
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            out.append(" ")
        elif ch == "[":
            out.append(" ")
            i += 1
            while i < n and sql[i] != "]":
                i += 1
            if i < n:
                i += 1
            out.append(" ")
        elif ch == "-" and nxt == "-":
            i += 2
            while i < n and sql[i] not in "\r\n":
                i += 1
            out.append(" ")
        elif ch == "/" and nxt == "*":
            i += 2
            while i < n and not (sql[i] == "*" and i + 1 < n and sql[i + 1] == "/"):
                i += 1
            if i < n:
                out.append(" ")
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def validate_sql(sql: str) -> str | None:
    """返回错误信息；None 表示允许执行。"""
    cleaned = _strip_literals_and_comments(sql).strip()
    if not cleaned:
        return "SQL 为空"

    first = re.match(r"[A-Za-z]+", cleaned)
    if first is None or first.group(0).upper() not in {"SELECT", "WITH"}:
        return "只允许 SELECT / WITH 开头的只读查询"

    if _DANGEROUS_KEYWORDS.search(cleaned):
        return "包含不允许的写操作关键字"
    if _LOAD_EXTENSION.search(cleaned):
        return "不允许加载扩展"

    body = cleaned
    if body.endswith(";"):
        body = body[:-1].rstrip()
    if ";" in body:
        return "不允许多条语句"

    return None


def _connect() -> sqlite3.Connection:
    # mode=ro 是文件层只读；就算前面三道被绕过，写操作也会在这里失败
    uri = f"file:{DB_PATH.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def execute_readonly_sql(sql: str) -> dict:
    """执行只读 SQL，返回列、行、行数；超时或超行数会明确标记。"""
    error = validate_sql(sql)
    if error is not None:
        logger.warning("SQL 被拒绝: %s", error)
        return {"error": error}

    if not DB_PATH.exists():
        return {"error": "数据库文件不存在，请先运行 scripts / generate_data.py"}

    conn = _connect()
    try:
        deadline = time.monotonic() + SQL_TIMEOUT_SECONDS
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 1000, )
        try:
            cursor = conn.execute(sql)
        except sqlite3.OperationalError as exc:
            if "interrupted" in str(exc).lower():
                return {"error": f"SQL 执行超时（超过{SQL_TIMEOUT_SECONDS}秒）"}
            return {"error": str(exc)}

        columns = [item[0] for item in cursor.description] if cursor.description else []
        fetched = cursor.fetchmany(ROW_LIMIT + 1)
        truncated = len(fetched) > ROW_LIMIT
        rows = [list(row) for row in fetched[:ROW_LIMIT]]
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
        }
    finally:
        conn.close()


def describe_tables() -> dict:
    """返回表名与行数，给模型做初步判断。"""
    if not DB_PATH.exists():
        return {"error": "数据库文件不存在，请先运行 scripts / generate_data.py"}

    conn = _connect()
    try:
        names = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        ]
        tables = []
        for name in names:
            quoted = '"' + name.replace('"', '""') + '"'
            count = conn.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
            tables.append({"name": name, "rows": count})
        return {"tables": tables}
    finally:
        conn.close()


@mcp.tool(name="execute_readonly_sql")
def _execute_readonly_sql_tool(sql: str) -> dict:
    """执行一条只读 SELECT / WITH 查询，最多返回 1000 行，5 秒超时"""
    return execute_readonly_sql(sql)


@mcp.tool(name="describe_tables")
def _describe_tables_tool() -> dict:
    """返回所有表的名字和行数。"""
    return describe_tables()


if __name__ == '__main__':
    mcp.run(transport="stdio")
