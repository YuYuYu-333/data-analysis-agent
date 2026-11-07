"""
MCP 客户端：content block 解析。
"""
import asyncio

import pytest

import app.mcp_client as mcp_client
from app.mcp_client import _parse_result


class _BoomTool:
    def __init__(self):
        self.calls = 0

    async def ainvoke(self, payload):
        self.calls += 1
        raise RuntimeError("pipe closed")


def test_parse_content_block():
    raw = [{"type": "text", "text": '{"a": 1}'}]
    assert _parse_result(raw) == {"a": 1}


def test_parse_plain_json_string():
    assert _parse_result('{"a": 1}') == {"a": 1}


def test_parse_non_json_text():
    raw = [{"type": "text", "text": "hello"}]
    assert _parse_result(raw) == "hello"


def test_call_does_not_retry_silently(monkeypatch):
    """MCP 调用失败就抛出去，要不要再来一次由图的 route 决定"""
    tool = _BoomTool()

    async def fake_tools():
        return {"execute_readonly_sql": tool}

    monkeypatch.setattr(mcp_client, "get_tools", fake_tools)
    with pytest.raises(RuntimeError): asyncio.run(mcp_client.execute_sql("SELECT 1"))
    assert tool.calls == 1
