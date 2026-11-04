"""
HTTP 请求 / 响应模型。Pydantic 负责校验和序列化。
"""

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    session_id: str | None = None


class AnalyzeResponse(BaseModel):
    session_id: str
    answer: str
    columns: list[str]
    rows: list[list]
    row_count: int
    truncated: bool
    citations: list[dict]
    attempts: int
    degraded: bool
    trace: list[str] | None = None
