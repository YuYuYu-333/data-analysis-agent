"""
FastAPI 服务层：只管 HTTP——收请求、鉴权、限流、返回。
SQL 怎么生成、表怎么查，全在 app.graph 里，这里不碰。
"""

import json
import logging
import time
import secrets
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from app.checkpointer import close_checkpointer, get_checkpointer
from app.config import API_KEY, DEBUG, ROOT, TRUST_PROXY
from app.graph import analyze as run_agent, analyze_stream
from app.limits import API_PER_MINUTE, DEMO_PER_MINUTE, RateLimiter
from app.logging import request_id_var, setup_logging
from app.mcp_client import close_client, connect, describe_tables
from app.models import AnalyzeRequest, AnalyzeResponse
from app.session_lock import SessionLocks

logger = logging.getLogger("app.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    try:
        await connect()
    except Exception as exc:
        # 依赖挂了也要能回话：/health 继续活着， / ready 会报出哪项不行
        logger.warning("MCP 启动连接失败: %s", exc)
    yield
    await close_client()
    await close_checkpointer()


app = FastAPI(title="data-analysis-agent", lifespan=lifespan)
demo_limiter = RateLimiter(DEMO_PER_MINUTE)
api_limiter = RateLimiter(API_PER_MINUTE)
session_locks = SessionLocks()

WEB_INDEX = ROOT / "web" / "index.html"
REQUESTS = Counter("analyze_requests_total", "请求数", ["endpoint", "status"])
DURATION = Histogram("analyze_duration_seconds", "请求耗时", ["endpoint"])
TOKENS = Counter("analyze_tokens_total", "LLM token 数")
ATTEMPTS = Counter("analyze_attempts_total", "SQL 尝试次数")
DEGRADED = Counter("analyze_degraded_total", "答案降级次数")

STEP_LABELS = {
    "retrieve_schema": "检索 schema",
    "generate_sql": "生成 SQL",
    "execute_sql": "执行查询",
    "build_answer": "撰写结论",
    "verify_citations": "校验溯源",
    "give_up": "放弃",
}


def _endpoint_label(request: Request) -> str:
    """指标标签用路由模板；同一个接口的不同 URL 必须算同一条时间序列"""
    route = request.scope.get("route")
    return getattr(route, "path", "unmatched")


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid4().hex[:12]
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        REQUESTS.labels(endpoint=_endpoint_label(request), status="500").inc()
        logger.exception("request failed")
        raise
    else:
        endpoint = _endpoint_label(request)
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        REQUESTS.labels(endpoint=endpoint, status=str(response.status_code)).inc()
        DURATION.labels(endpoint=endpoint).observe(latency_ms / 1000)
        response.headers["X-Request-Id"] = request_id
        logger.info("request", extra={"latency_ms": latency_ms, "status": response.status_code})
        return response
    finally:
        request_id_var.reset(token)


def client_ip(request: Request) -> str:
    """只有开了 TRUST_PROXY 才读 X-Forwarded-For。
    代理会把自己看到的对端追加在末尾，所以取最后一跳；
    前面那截客户端自己就能写，取第一跳等于允许伪造。"""
    if TRUST_PROXY:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """像函数一样的依赖：FastAPI 会在进路由前先调用它，抛异常就直接返回错误"""
    if not API_KEY:
        raise HTTPException(status_code=503, detail="服务未配置 API_KEY")
    if not x_api_key or not secrets.compare_digest(x_api_key, API_KEY):
        raise HTTPException(status_code=401, detail="API key 无效")


def _to_response(session_id: str, state: dict) -> AnalyzeResponse:
    rows = state.get("rows") or []
    return AnalyzeResponse(
        session_id=session_id,
        answer=state.get("answer") or "",
        columns=state.get("columns") or [],
        rows=rows,
        row_count=len(rows),
        truncated=bool(state.get("truncated")),
        citations=state.get("citations") or [],
        attempts=state.get("attempts", 0),
        degraded=bool(state.get("degraded")),
        trace=state.get("trace") if DEBUG else None,
    )


def _record_usage(state: dict, session_id: str) -> None:
    tokens = state.get("tokens", 0) or 0
    attempts = state.get("attempts", 0) or 0
    degraded = bool(state.get("degraded"))
    TOKENS.inc(tokens)
    ATTEMPTS.inc(attempts)
    if degraded:
        DEGRADED.inc()
    logger.info("analyze done",
                extra={"session_id": session_id,
                       "attempts": attempts,
                       "tokens": tokens,
                       "citations_ok": not degraded
                       },
                )


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def stream_events(question: str, session_id: str):
    async with session_locks.hold(session_id):
        try:
            async for event in analyze_stream(question, session_id):
                if event["type"] == "final":
                    state = event["state"]
                    _record_usage(state, session_id)
                    body = _to_response(session_id, state).model_dump()
                    yield _sse({"type": "final", **body})
                else:
                    node = event["node"]
                    yield _sse({
                        "type": "step",
                        "step": node,
                        "label": STEP_LABELS.get(node, node),
                    })
        except Exception as exc:
            logger.exception("stream failed")
            yield _sse({"type": "error", "detail": str(exc)})


def _stream_response(question: str, session_id: str) -> StreamingResponse:
    return StreamingResponse(
        stream_events(question, session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/")
async def index():
    return FileResponse(WEB_INDEX)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    checks = {}
    try:
        await get_checkpointer()
        checks["checkpointer"] = True
    except Exception as exc:
        checks["checkpointer"] = str(exc)
    try:
        await describe_tables()
        checks["mcp"] = True
    except Exception as exc:
        checks["mcp"] = str(exc)

    ok = all(value is True for value in checks.values())
    return JSONResponse(status_code=200 if ok else 503, content={"ready": ok, "checks": checks})


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_endpoint(
        req: AnalyzeRequest,
        request: Request,
        _: None = Depends(require_api_key),
) -> AnalyzeResponse:
    if not api_limiter.allow("api"):
        raise HTTPException(status_code=429, detail="请求太频繁, 请稍后再试")
    session_id = req.session_id or uuid4().hex
    state = await run_session(req.question, session_id=session_id)
    _record_usage(state, session_id)
    return _to_response(session_id, state)


@app.post("/demo/analyze",
          response_model=AnalyzeResponse)
async def demo_analyze(req: AnalyzeRequest, request: Request) -> AnalyzeResponse:
    if not demo_limiter.allow(client_ip(request)):
        raise HTTPException(status_code=429, detail="请求太繁忙,请稍后再试")
    session_id = req.session_id or uuid4().hex
    state = await run_session(req.question, session_id=session_id)
    _record_usage(state, session_id)
    return _to_response(session_id, state)


async def run_session(question: str, session_id: str) -> dict:
    """同一个 session_id 串行执行，不同会话互不阻塞。"""
    async with session_locks.hold(session_id):
        return await run_agent(question, session_id=session_id, schema_mode="rag")


@app.post("/analyze/stream")
async def analyze_stream_endpoint(
        req: AnalyzeRequest,
        _: None = Depends(require_api_key),
):
    if not api_limiter.allow("api"):
        raise HTTPException(status_code=429, detail="请求太频繁, 请稍后再试")
    session_id = req.session_id or uuid4().hex
    return _stream_response(req.question, session_id)


@app.post("/demo/analyze/stream")
async def demo_stream_endpoint(req: AnalyzeRequest, request: Request):
    if not demo_limiter.allow(client_ip(request)):
        raise HTTPException(status_code=429, detail="请求太繁忙,请稍后再试")
    session_id = req.session_id or uuid4().hex
    return _stream_response(req.question, session_id)


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
