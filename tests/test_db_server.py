"""
Database MCP
Server：四道拦截与只读执行。
"""

import pytest

from mcp_servers import db_server
from mcp_servers.db_server import describe_tables, execute_readonly_sql, validate_sql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM store",
        "WITH x AS (SELECT 1) SELECT * FROM x",
        "SELECT 1;",
        "SELECT '; DROP TABLE store'",
        "SELECT 1 -- ; DROP TABLE store",
        "SELECT 1 /* ; DROP TABLE store */",
    ],
)
def test_allows_readonly_sql(sql):
    assert validate_sql(sql) is None


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE store",
        "DELETE FROM sales_item",
        "UPDATE store SET region = 'x'",
        "INSERT INTO store VALUES ('S99', 'x', 'y', 'z', '2026-01-01')",
        "ATTACH DATABASE 'x' AS y",
        "PRAGMA table_info(store)",
        "CREATE TABLE x (id INTEGER)",
        "ALTER TABLE store ADD COLUMN x TEXT",
        "VACUUM",
        "WITH x AS (DELETE FROM store RETURNING *) SELECT * FROM x",
        "SELECT 1; DROP TABLE store",
        "SELECT 1; SELECT 2",
        "SELECT load_extension('x')",
    ],
)
def test_rejects_dangerous_sql(sql):
    assert validate_sql(sql) is not None


@pytest.mark.skipif(not
                    db_server.DB_PATH.exists(), reason="retail.db未生成")


def test_execute_select_returns_rows():
    result = execute_readonly_sql("SELECT COUNT(*) AS n FROM store")
    assert result["columns"] == ["n"]
    assert result["rows"] == [[12]]
    assert result["row_count"] == 1
    assert result["truncated"] is False


@pytest.mark.skipif(not
                    db_server.DB_PATH.exists(), reason="retail.db未生成")
def test_execute_rejects_dangerous_sql():
    result = execute_readonly_sql("DROP TABLE store")
    assert "error" in result


@pytest.mark.skipif(not
                    db_server.DB_PATH.exists(), reason="retail.db未生成")
def test_execute_returns_sqlite_error():
    result = execute_readonly_sql("SELECT * FROM no_such_table")
    assert "error" in result
    assert "no such table" in result["error"]


@pytest.mark.skipif(not
                    db_server.DB_PATH.exists(), reason="retail.db 未生成")
def test_row_limit_marks_truncated():
    result = execute_readonly_sql("SELECT * FROM sales_item")
    assert result["row_count"] == 1000
    assert result["truncated"] is True


@pytest.mark.skipif(not
                    db_server.DB_PATH.exists(), reason="retail.db未生成")
def test_describe_tables():
    result = describe_tables()
    tables = {item["name"]: item["rows"] for
              item in result["tables"]}
    assert tables["store"] == 12
    assert tables["product"] == 60
    assert tables["sales_order"] == 5000
    assert tables["sales_item"] == 13572
