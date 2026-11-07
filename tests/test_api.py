"""
API 层：健康检查、鉴权、参数校验。
"""

import pytest
from fastapi.testclient import TestClient

import app.api as api


@pytest.fixture
def client():
    # 不写 with：不触发 lifespan，就不拉 MCP 子进程、不碰真模型
    return TestClient(api.app)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_analyze_without_configured_key_returns_503(client, monkeypatch):
    monkeypatch.setattr(api, "API_KEY", None)
    response = client.post("/analyze", json={"question": "销售额"})
    assert response.status_code == 503


def test_analyze_with_wrong_key_returns_401(client, monkeypatch):
    monkeypatch.setattr(api, "API_KEY", "secret")
    response = client.post(
        "/analyze", json={"question": "销售额"},
        headers={"X-API-Key": "nope"})
    assert response.status_code == 401


def test_analyze_with_right_key_returns_answer(client, monkeypatch):
    monkeypatch.setattr(api, "API_KEY", "secret")

    async def fake_agent(question, session_id, schema_mode):
        return {
            "answer": "华东 24884.15",
            "columns": ["sales_amount"],
            "rows": [[24884.15]],
            "citations": [{"value": 24884.15, "row": 0, "column": "sales_amount"}],
            "attempts": 1,
            "degraded": False,
        }

    monkeypatch.setattr(api, "run_agent", fake_agent)
    response = client.post(
        "/analyze", json={"question": "销售额"},
        headers={"X-API-Key": "secret"})
    assert response.status_code == 200
    body = response.json()
    assert body["row_count"] == 1
    assert body["answer"] == "华东 24884.15"
    assert body["degraded"] is False


def test_empty_question_is_rejected(client):
    response = client.post("/demo/analyze", json={"question": ""})
    assert response.status_code == 422


def test_demo_rate_limit_returns_429(client, monkeypatch):
    monkeypatch.setattr(api, "demo_limiter", api.RateLimiter(2))

    async def fake_agent(question, session_id, schema_mode):
        return {
            "answer": "ok",
            "columns": [],
            "rows": [],
            "citations": [],
            "attempts": 1,
            "degraded": False
        }

    monkeypatch.setattr(api, "run_agent", fake_agent)
    codes = [client.post("/demo/analyze", json={"question": "x"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_different_ips_have_separate_quota(client, monkeypatch):
    monkeypatch.setattr(api, "TRUST_PROXY", True, raising=False)
    monkeypatch.setattr(api, "demo_limiter", api.RateLimiter(1))

    async def fake_agent(question, session_id, schema_mode):
        return {
            "answer": "ok",
            "columns": [],
            "rows": [],
            "citations": [],
            "attempts": 1,
            "degraded": False
        }

    monkeypatch.setattr(api, "run_agent", fake_agent)
    first = client.post("/demo/analyze", json={"question": "x"}, headers={"X-Forwarded-For": "1.1.1.1"})
    second = client.post("/demo/analyze", json={"question": "x"}, headers={"X-Forwarded-For": "2.2.2.2"})
    third = client.post("/demo/analyze", json={"question": "x"}, headers={"X-Forwarded-For": "1.1.1.1"})
    assert [first.status_code, second.status_code,
            third.status_code] == [200, 200, 429]


def test_response_has_request_id_header(client):
    response = client.get("/health")
    assert response.headers["x-request-id"]


def test_metrics_endpoint(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "analyze_requests_total" in response.text


def test_index_serves_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_stream_returns_sse(client, monkeypatch):
    monkeypatch.setattr(api, "demo_limiter", api.RateLimiter(10))

    async def fake_stream(question, session_id, schema_mode="rag"):
        yield {"type": "step",
               "node": "generate_sql"}
        yield {"type": "final",
               "state": {
                   "answer": "ok",
                   "columns": [],
                   "rows": [],
                   "citations": [],
                   "attempts": 1,
                   "degraded": False,
               }
               }

    monkeypatch.setattr(api, "analyze_stream", fake_stream)
    response = client.post("/demo/analyze/stream", json={"question": "x"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"type": "step"' in response.text
    assert '"label": "生成 SQL"' in response.text
    assert '"type": "final"' in response.text


def test_unknown_path_does_not_create_new_label(client):
    """指标标签用路由模板；随便一个 URL 不能新增一条时间序列"""
    client.get("/nope")
    text = client.get("/metrics").text
    assert 'endpoint="/nope"' not in text
    assert 'endpoint="unmatched"' in text


def test_startup_survives_mcp_failure(monkeypatch):
    """MCP 连不上时进程仍要起来，依赖状态交给 /ready 报告"""

    async def broken():
        raise RuntimeError("mcp down")

    monkeypatch.setattr(api, "connect", broken)
    with TestClient(api.app) as client:
        assert client.get("/health").status_code == 200


def _ok_agent(monkeypatch):
    async def fake(question, session_id, schema_mode):
        return {"answer": "ok", "columns": [], "rows": [], "citations": [], "attempts": 1, "degraded": False}

    monkeypatch.setattr(api, "run_agent", fake)


def test_forwarded_header_is_ignored_by_default(client, monkeypatch):
    """没开 TRUST_PROXY 时，客户端自己写的头不算数"""
    monkeypatch.setattr(api, "TRUST_PROXY", False, raising=False)
    monkeypatch.setattr(api, "demo_limiter", api.RateLimiter(1))
    _ok_agent(monkeypatch)
    codes = [
        client.post(
            "/demo/analyze",
            json={"question": "x"},
            headers={"X-Forwarded-For": ip}
        ).status_code for ip in ("1.1.1.1", "2.2.2.2")
    ]
    assert codes == [200, 429]


def test_forwarded_header_uses_last_hop(client, monkeypatch):
    """信任代理时取最后一跳，前面那截是客户端能伪造的"""
    monkeypatch.setattr(api, "TRUST_PROXY", True, raising=False)
    monkeypatch.setattr(api, "demo_limiter", api.RateLimiter(1))
    _ok_agent(monkeypatch)
    codes = [
        client.post(
            "/demo/analyze",
            json={"question": "x"},
            headers={"X-Forwarded-For": f"{ip}, 9.9.9.9"}
        ).status_code
        for ip in ("1.1.1.1", "2.2.2.2")
    ]
    assert codes == [200, 429]
