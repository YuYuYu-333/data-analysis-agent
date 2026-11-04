"""
MCP 客户端：拉起两个 stdio Server，加载工具，并把
content block 解析成 dict。
图只调用这里的三个函数，不关心 MCP 协议。
"""

import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

ROOT = Path(__file__).resolve().parents[1]

_client: MultiServerMCPClient | None = None
_tools: dict[str, BaseTool] | None = None
_stack: AsyncExitStack | None = None


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
    """第一次调用时启动两个 Server 并保持会话；之后复用工具对象"""
    global _client, _tools, _stack
    if _tools is not None:
        return _tools

    _client = _build_client()
    _stack = AsyncExitStack()
    tools: dict[str, BaseTool] = {}
    for server_name in ("schema", "database"):
        session = await _stack.enter_async_context(_client.session(server_name))
        for tool in await load_mcp_tools(session):
            tools[tool.name] = tool
    _tools = tools
    return _tools


async def close_client() -> None:
    """关闭会话和子进程；进程退出前必须调用，否则 Windows 会卡在 process.wait()"""
    global _client, _tools, _stack
    if _stack is not None:
        await _stack.aclose()
    _client = None
    _tools = None
    _stack = None


async def connect() -> dict[str, BaseTool]:
    """在调用方自己的任务里把会话连上。
    anyio 要求 cancel scope在同一个任务里进入和退出。
    LangGraph 节点跑在它自己创建的子任务里，所以第一次 get_tools()如果发生在节点里，
    收尾时就会报 "exit cancel scope in a different task"。
    在 run() 开头显式连一次，开和关就都在主任务里了。
    """
    return await get_tools()


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


async def _call(name: str, payload: dict) -> dict:
    tools = await get_tools()
    try:
        return _parse_result(await tools[name].ainvoke(payload))
    except Exception:
        return _parse_result(await tools[name].ainvoke(payload))


async def search_schema(query: str, top_k: int = 3) -> dict:
    return await _call("search_schema", {"query": query, "top_k": top_k})


async def execute_sql(sql: str) -> dict:
    return await _call("execute_readonly_sql", {"sql": sql})


async def describe_tables() -> dict:
    return await _call("describe_tables", {})
