"""
FastAPI 服务层：只管 HTTP——收请求、鉴权、限流、返回。
SQL 怎么生成、表怎么查，全在 app.graph 里，这里不碰。
"""

import secrets
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from app.checkpointer import close_checkpointer, get_checkpointer
from app.config import API_KEY, DEBUG, ROOT
from app.graph import analyze as run_agent
from app.limits import API_PER_MINUTE, DEMO_PER_MINUTE, RateLimiter
from app.logging import setup_logging
from app.mcp_client import close_client, connect, describe_tables
from app.models import AnalyzeRequest, AnalyzeResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await connect()
    yield
    await close_client()
    await close_checkpointer()


app = FastAPI(title="data-analysis-agent", lifespan=lifespan)
WEB_INDEX = ROOT / "web" / "index.html"
demo_limiter = RateLimiter(DEMO_PER_MINUTE)
api_limiter = RateLimiter(API_PER_MINUTE)


def client_ip(request: Request) -> str:
    """Render 会在 X-Forwarded-For 里塞真实 IP；直连时用它自己的"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
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
        _: None = Depends(require_api_key),
) -> AnalyzeResponse:
    session_id = req.session_id or uuid4().hex
    state = await run_agent(req.question, session_id=session_id, schema_mode="rag")
    return _to_response(session_id, state)


@app.post("/demo/analyze",
          response_model=AnalyzeResponse)
async def demo_analyze(req: AnalyzeRequest, request: Request) -> AnalyzeResponse:
    if not demo_limiter.allow(client_ip(request)):
        raise HTTPException(status_code=429, detail="请求太繁忙,请稍后再试")
    session_id = req.session_id or uuid4().hex
    state = await run_agent(req.question, session_id=session_id, schema_mode="rag")
    return _to_response(session_id, state)
