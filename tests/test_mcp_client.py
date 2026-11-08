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


class _FakeSession:
    def __init__(self, name, closed):
        self.name = name
        self.closed = closed

    async def __aenter__(self):
        if self.name == "database":
            raise RuntimeError("server 起不来")
        return self

    async def __aexit__(self, *exc):
        self.closed.append(self.name)


class _FakeClient:
    def __init__(self, closed):
        self.closed = closed

    def session(self, name):
        return _FakeSession(name, self.closed)


def test_get_tools_closes_started_sessions_on_failure(monkeypatch):
    """第二个 server 起不来时，第一个已经起来的会话必须关掉"""
    closed = []

    async def fake_load(session):
        return []

    monkeypatch.setattr(mcp_client, "_build_client", lambda: _FakeClient(closed))
    monkeypatch.setattr(mcp_client, "load_mcp_tools", fake_load)
    monkeypatch.setattr(mcp_client, "_client", None)
    monkeypatch.setattr(mcp_client, "_tools", None)
    monkeypatch.setattr(mcp_client, "_stack", None)

    with pytest.raises(RuntimeError):
        asyncio.run(mcp_client.get_tools())

    assert closed == ["schema"]
    assert mcp_client._stack is None
    assert mcp_client._tools is None
