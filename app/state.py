"""
LangGraph 的状态定义。
"""

import operator
from typing import Annotated, TypedDict


class AnalysisState(TypedDict, total=False):
    question: str
    session_id: str
    schema_mode: str
    history: list[dict]
    schema_context: str
    sql: str
    error: str | None
    attempts: int
    columns: list[str] | None
    rows: list[list] | None
    truncated: bool
    answer: str | None
    raw_answer: str | None
    citations: list[dict]
    degraded: bool
    trace: Annotated[list[str], operator.add]
    tokens: Annotated[int, operator.add]
