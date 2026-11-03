"""
MCP 客户端：content block 解析。
"""

from app.mcp_client import _parse_result


def test_parse_content_block():
    raw = [{"type": "text", "text": '{"a": 1}'}]
    assert _parse_result(raw) == {"a": 1}


def test_parse_plain_json_string():
    assert _parse_result('{"a": 1}') == {"a": 1}


def test_parse_non_json_text():
    raw = [{"type": "text", "text": "hello"}]
    assert _parse_result(raw) == "hello"
