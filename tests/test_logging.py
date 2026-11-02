"""结构化日志：JSON 输出与 request_id。"""

import json
import logging

from app.logging import JsonFormatter, request_id_var


def _record(msg="hello"):
    return logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )


def test_formatter_outputs_json_with_request_id():
    token = request_id_var.set("req-123")
    try:
        payload = json.loads(JsonFormatter().format(_record()))
    finally:
        request_id_var.reset(token)

    assert payload["request_id"] == "req-123"
    assert payload["event"] == "hello"
    assert payload["level"] == "INFO"


def test_request_id_defaults_to_dash():
    payload = json.loads(JsonFormatter().format(_record()))
    assert payload["request_id"] == "-"
