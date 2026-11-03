"""
MCP 客户端：拉起两个 stdio Server，加载工具，并把
content block 解析成 dict。
图只调用这里的三个函数，不关心 MCP 协议。
"""

import json
import os
import sys
from pathlib import Path

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

ROOT = Path(__file__).resolve().parents[1]

_client: MultiServerMCPClient | None = None
_tools: dict[str, BaseTool] | None = None


def _build_client() -> MultiServerMCPClient:
    return MultiServerMCPClient(
        {
            "schema": {
                "transport": "stdio",
                "command": sys.executable,
                "args": ["-m", "mcp_servers.schema_server"],
                "cwd": str(ROOT),
                "env": os.environ.copy(),
            },
            "database": {
                "transport": "stdio",
                "command": sys.executable,
                "args": ["-m", "mcp_servers.db_server"],
                "cwd": str(ROOT),
                "env": os.environ.copy(),
            }
        }
    )


async def get_tools() -> dict[str, BaseTool]:
    """第一次调用启动 Server 并加载工具; 之后复用工具对象"""
    global _client, _tools
    if _tools is None:
        _client = _build_client()
        loaded = await _client.get_tools()
        _tools = {tool.name: tool for tool in loaded}
    return _tools


def _parse_result(result):
    """适配器返回 content block 列表; 把 text 里的 JSON解出来."""
    if isinstance(result, dict):
        return result

    content = getattr(result, "content", None)
    if content is not None:
        return _parse_result(content)

    if isinstance(result, str):
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return result

    if isinstance(result, list) and result:
        first = result[0]
        if isinstance(first, dict) and first.get("type") == "text":
            text = first.get("text", "")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text

    return result


async def search_schema(query: str, top_k: int = 3) -> dict:
    tools = await get_tools()
    raw = await tools["search_schema"].ainvoke({"query": query, "top_k": top_k})
    return _parse_result(raw)


async def execute_sql(sql: str) -> dict:
    tools = await get_tools()
    raw = await tools["execute_readonly_sql"].ainvoke({"sql": sql})
    return _parse_result(raw)


async def describe_tables() -> dict:
    tools = await get_tools()
    raw = await tools["describe_tables"].ainvoke({})
    return _parse_result(raw)
